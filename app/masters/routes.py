from flask import (
    Blueprint,
    render_template,
    url_for,
    flash,
    redirect,
    request,
    current_app,
    abort,
    jsonify,
)
from flask_login import login_required, current_user
from app import db
from app.models.cha import (
    Customer, Department, ShipmentType, BLStatus, FreightTerm, RequestType, DocumentType, ShippingLine, Terminal, Runner, WharfProfile, Branch, ShipCategory, ShipCatDocument,Order,
    OrderItem, OrderDocument, DocumentStatus, ShipDocumentEntryMaster, ShipDocumentEntryAttachment, ChatThread, ChatMessage, ChatParticipant, ChatAttachment, ShipDocumentHistory,
    OrderShipment,ShipCatDocumentAICheck,ExportContainer,ImportContainer,ShipDocumentEntryDocument,IncomeExpense,ShipmentExpense,InvoiceDetail,InvoiceHeader,
    ExpenseSettlement, RateCard, EntryAssignmentHistory, ContainerDepositWorkflow, ContainerDepositWorkflowDocument, ContainerDocument,
    ContainerWorkflowDocument, ContainerDepositWorkflowStep, ContainerDepositWorkflowStepDocument, ContainerStepCompletion, EntryClearingAgentHistory,
    EntryClearingCompanyHistory, AgentAssignment, CompanyAssignment, AttachmentDocument, AttachmentType, CustomerAttachment,
    OsBusinessType, OsContainerSize, OsContainerType, OsJobType, OsSubType, OsCustomerCategory, OsShipmentType, ShipmentTypeBase
    )
from app.models.task_management import (
    Task, TaskComment, TaskAttachment, TimeEntry, TaskWatcher, TaskHistory, Project, ProjectMember, Issue, IssueComment, IssueHistory, IssueAttachment, IssueLink)
from app.models.task_management import Project, Task, TaskVisibility, TaskPriority, ProjectTaskStatus, ProjectMember, UserCompany
from app.models.user import User, CountryMaster, CurrencyMaster, UserActionPermission, Role
from app.masters.forms import (
    CustomerForm,
    DepartmentForm,
    ShipmentTypeForm,
    BLStatusForm,
    FreightTermForm,
    RequestTypeForm,
    DocumentTypeForm,
    ShippingLineForm,
    CountryForm,
    CurrencyForm,
    TerminalForm,
    RunnerForm,
    WharfProfileForm,
    BranchForm,
    OrderForm,
    ShipDocumentEntryForm
)
from app.models.company import CompanyInfo
from app.models.po import POHeader, PODetail, POSupplier, POMaterial, POOrderUnit, ShipmentItem, MaterialHSDocuments
from app.models.user import CountryMaster, CurrencyMaster
from app.models.hs import HSCode, HSCodeCategory, HSCodeDocument, HSCodeDocumentAttachment, HSCodeIssueBody, HSDocumentCategory
from app.models.demurrage import DemurrageRateCard, CompanyDemurrageConfig, DemurrageCalculationDetail, DemurrageReasons, ShipmentDemurrage, ShipmentDemurrageAttachment, ShipmentDemurrageBearer, DemurrageRateCardTier
from datetime import datetime, date, timedelta
import os
import secrets
from werkzeug.utils import secure_filename
from PIL import Image
import uuid
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from app.utils_cha.s3_utils import upload_file_to_s3, get_s3_url, delete_file_from_s3, serve_s3_file
from app.utils_cha.validators import validate_file
from app.utils_cha.helpers import get_enum_values
from app.utils_cha.decorators import admin_required
from app.utils_cha.exceptions import UnauthorizedAccessError
from sqlalchemy import or_
import json
import traceback
import mimetypes
from sqlalchemy.sql import and_, or_, cast
from sqlalchemy import desc
from app.email import send_email, send_async_email
from app.utils import get_sri_lanka_time
from decimal import Decimal

from app.masters import bp


def get_company_id():
    return current_user.company_id


def save_profile_picture(form_picture):
    if not form_picture:
        return "default.jpg"

    # Generate random filename with original extension
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext

    # Create S3 key
    s3_key = f"{current_app.config['S3_BASE_FOLDER']}/profile_pics/{picture_fn}"

    # Resize the image
    output_size = (400, 400)
    i = Image.open(form_picture)
    i.thumbnail(output_size)

    # Save to temporary file
    temp_path = os.path.join(current_app.root_path, "static", "temp", picture_fn)
    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
    i.save(temp_path)

    # Upload to S3
    try:
        with open(temp_path, "rb") as f:
            upload_file_to_s3(f, current_app.config["S3_BUCKET_NAME"], s3_key)
        # Clean up temp file
        os.remove(temp_path)
        return s3_key
    except Exception as e:
        print(f"Error uploading profile picture to S3: {str(e)}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return "default.jpg"


def delete_profile_picture(picture_path):
    if picture_path and picture_path != "default.jpg":
        try:
            delete_file_from_s3(current_app.config["S3_BUCKET_NAME"], picture_path)
        except Exception as e:
            print(f"Error deleting profile picture from S3: {str(e)}")


def save_document(form_document, document_type):
    if not form_document:
        return None

    # Generate random filename with original extension
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_document.filename)
    document_fn = random_hex + f_ext

    # Create S3 key
    s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/{document_type}/{document_fn}"

    # Upload to S3
    try:
        upload_file_to_s3(form_document, current_app.config["S3_BUCKET_NAME"], s3_key)
        return s3_key
    except Exception as e:
        print(f"Error uploading document to S3: {str(e)}")
        return None


def delete_document(document_path, document_type):
    if document_path:
        try:
            delete_file_from_s3(current_app.config["S3_BUCKET_NAME"], document_path)
        except Exception as e:
            print(f"Error deleting document from S3: {str(e)}")


def get_s3_client():
    """Get an S3 client"""
    return boto3.client(
        "s3",
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=current_app.config["AWS_SECRET_ACCESS_KEY"],
        region_name=current_app.config["AWS_REGION"],
        config=Config(signature_version="s3v4"),
    )


def upload_file_to_s3(file, bucket, key):
    """Upload a file to S3"""
    s3_client = get_s3_client()
    s3_client.upload_fileobj(
        file,
        bucket,
        key,
        ExtraArgs=(
            {"ContentType": file.content_type}
            if hasattr(file, "content_type")
            else None
        ),
    )


def delete_file_from_s3(bucket, key):
    """Delete a file from S3"""
    s3_client = get_s3_client()
    s3_client.delete_object(Bucket=bucket, Key=key)


def generate_presigned_url(bucket, key, expiration=300):
    """Generate a presigned URL for an S3 object"""
    s3_client = get_s3_client()
    return s3_client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expiration
    )


# CUSTOMER ROUTES
##############################




@bp.route("/customers")
@login_required
def customers():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 5, type=int)
    customer_type = request.args.get("customer_type", 1, type=int)  # 1 = Customers, 2 = CHA
    status = request.args.get("status", None)
    search = request.args.get("search", None)
    
    if customer_type == 1:  # Regular Customers
        # Base query with join to User table and CompanyInfo
        if current_user.role == 'super_admin':
            query = db.session.query(Customer, User, CompanyInfo).outerjoin(
                User, Customer.user_id == User.id
            ).join(
                CompanyInfo, Customer.company_id == CompanyInfo.id
            )
            base_query = Customer.query
        else:
            assigned_companies = db.session.query(CompanyAssignment.company_id).filter(
                CompanyAssignment.assigned_company_id == current_user.company_id,
                CompanyAssignment.is_active == True
            ).subquery()
            
            query = db.session.query(Customer, User, CompanyInfo).outerjoin(
                User, Customer.user_id == User.id
            ).join(
                CompanyInfo, Customer.company_id == CompanyInfo.id
            ).filter(Customer.company_id.in_(assigned_companies))
            base_query = Customer.query.filter(Customer.company_id.in_(assigned_companies))
        
        # Filter by customer type (1 = Company customers)
        query = query.filter(Customer.customer_type == 1)
        
        # Filter by status if provided
        if status:
            if status == 'active':
                query = query.filter(User.is_active == True)
            elif status == 'inactive':
                query = query.filter(User.is_active == False)
        
        # Filter by search if provided
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                db.or_(
                    Customer.customer_name.ilike(search_term),
                    Customer.customer_id.ilike(search_term),
                    Customer.email.ilike(search_term),
                    Customer.address.ilike(search_term),
                    Customer.telephone.ilike(search_term),
                    CompanyInfo.company_name.ilike(search_term)
                )
            )
        
        # Get the results and paginate manually
        results = query.order_by(Customer.created_at.desc()).all()
        
    else:  # CHA Users (customer_type == 2)
        # Only super_admin can view CHA tab
        if current_user.role != 'super_admin':
            flash("Unauthorized access", "danger")
            return redirect(url_for('masters.customers', customer_type=1))
        
        # Query for CHA users (role_id = 3) with their company info
        query = db.session.query(User, CompanyInfo).join(
            CompanyInfo, User.company_id == CompanyInfo.id
        ).filter(User.role_id == 3)
        
        # Filter by status if provided
        if status:
            if status == 'active':
                query = query.filter(User.is_active == True)
            elif status == 'inactive':
                query = query.filter(User.is_active == False)
        
        # Filter by search if provided
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                db.or_(
                    User.name.ilike(search_term),
                    User.username.ilike(search_term),
                    User.email.ilike(search_term),
                    User.contact_number.ilike(search_term),
                    CompanyInfo.company_name.ilike(search_term)
                )
            )
        
        # Get the results
        results = query.order_by(User.created_at.desc()).all()
        base_query = User.query.filter_by(role_id=3)
    
    # Create a custom pagination object
    from math import ceil
    total = len(results)
    start = (page - 1) * per_page
    end = start + per_page
    items = results[start:end]
    
    class CustomPagination:
        def __init__(self, items, page, per_page, total):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = total
            self.pages = ceil(total / per_page) if per_page > 0 else 0
            
        @property
        def has_prev(self):
            return self.page > 1
            
        @property
        def has_next(self):
            return self.page < self.pages
            
        @property
        def prev_num(self):
            return self.page - 1 if self.has_prev else None
            
        @property
        def next_num(self):
            return self.page + 1 if self.has_next else None
            
        def iter_pages(self, left_edge=2, right_edge=2, left_current=2, right_current=3):
            last = self.pages
            for num in range(1, last + 1):
                if num <= left_edge or \
                   (self.page - left_current - 1 < num < self.page + right_current) or \
                   num > last - right_edge:
                    yield num
    
    customers_paginated = CustomPagination(items, page, per_page, total)
    
    # Get counts for badges
    if current_user.role == 'super_admin':
        counts = {
            'company': Customer.query.filter_by(customer_type=1).count(),
            'cha': User.query.filter_by(role_id=3).count(),
        }
    else:
        assigned_companies = db.session.query(CompanyAssignment.company_id).filter(
            CompanyAssignment.assigned_company_id == current_user.company_id,
            CompanyAssignment.is_active == True
        ).subquery()
        counts = {
            'company': Customer.query.filter(Customer.company_id.in_(assigned_companies), Customer.customer_type == 1).count(),
            'cha': 0,  # Non-super admins can't see CHA count
        }
    
    return render_template(
        "masters/customers.html", 
        title="Customers", 
        customers=customers_paginated,
        counts=counts,
        current_customer_type=customer_type
    )


@bp.route("/toggle_customer_status/<int:customer_id>", methods=["POST"])
@login_required
def toggle_customer_status(customer_id):
    if current_user.role != 'super_admin':
        if request.is_json:
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        else:
            flash("Unauthorized", "danger")
            return redirect(url_for('masters.customers'))
    
    try:
        customer = Customer.query.get_or_404(customer_id)
        if not customer.user_id:
            message = "Customer has no associated user account"
            if request.is_json:
                return jsonify({"success": False, "message": message}), 400
            else:
                flash(message, "danger")
                return redirect(url_for('masters.customers'))
        
        user = User.query.get(customer.user_id)
        if not user:
            message = "Associated user not found"
            if request.is_json:
                return jsonify({"success": False, "message": message}), 404
            else:
                flash(message, "danger")
                return redirect(url_for('masters.customers'))
        
        # Store the old status to determine what action was taken
        old_status = user.is_active
        
        # Toggle the user's active status
        user.is_active = not user.is_active
        db.session.commit()
        
        # Prepare email data
        current_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        current_year = datetime.now().year
        
        # Send appropriate email based on the new status
        if user.is_active:  # Account was activated
            email_data = {
                'customer_name': customer.customer_name,
                'customer_id': customer.customer_id,
                'email': customer.email,
                'activation_date': current_date,
                'login_url': 'https://navitrax.sonaapps.com/auth/login',
                'current_year': current_year
            }
            
            send_email(
                subject=f"Account Activated - Welcome Back {customer.customer_name}",
                recipient=customer.email,
                template="email/customer_activation_notification.html",
                **email_data
            )
            print(f"Activation email sent to customer: {customer.email}")
            
        else:  # Account was deactivated
            email_data = {
                'customer_name': customer.customer_name,
                'customer_id': customer.customer_id,
                'email': customer.email,
                'deactivation_date': current_date,
                'support_email': 'support@navitrax.com',
                'support_phone': '+1-800-NAVITRAX',
                'current_year': current_year
            }
            
            send_email(
                subject=f"Account Deactivated - {customer.customer_name}",
                recipient=customer.email,
                template="email/customer_deactivation_notification.html",
                **email_data
            )
            print(f"Deactivation email sent to customer: {customer.email}")
        
        status_text = "activated" if user.is_active else "deactivated"
        message = f"Customer {status_text} successfully"
        
        if request.is_json:
            return jsonify({
                "success": True, 
                "message": message,
                "is_active": user.is_active
            })
        else:
            flash(message, "success")
            return redirect(url_for('masters.customers'))
        
    except Exception as e:
        db.session.rollback()
        print(f"Error in toggle_customer_status: {str(e)}")
        if request.is_json:
            return jsonify({"success": False, "message": str(e)}), 500
        else:
            flash(f"Error", "danger")
            return redirect(url_for('masters.customers'))


@bp.route("/toggle_cha_status/<int:user_id>", methods=["POST"])
@login_required
def toggle_cha_status(user_id):
    if current_user.role != 'super_admin':
        if request.is_json:
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        else:
            flash("Unauthorized", "danger")
            return redirect(url_for('masters.customers', customer_type=2))
    
    try:
        user = User.query.get_or_404(user_id)
        
        # Verify this is a CHA user
        if user.role_id != 3:
            message = "User is not a CHA user"
            if request.is_json:
                return jsonify({"success": False, "message": message}), 400
            else:
                flash(message, "danger")
                return redirect(url_for('masters.customers', customer_type=2))
        
        # Get company info for email
        company = CompanyInfo.query.get(user.company_id)
        if not company:
            message = "Company information not found"
            if request.is_json:
                return jsonify({"success": False, "message": message}), 404
            else:
                flash(message, "danger")
                return redirect(url_for('masters.customers', customer_type=2))
        
        # Store the old status to determine what action was taken
        old_status = user.is_active
        
        # Toggle the user's active status
        user.is_active = not user.is_active
        db.session.commit()
        
        # Prepare email data
        current_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        current_year = datetime.now().year
        
        # Send appropriate email based on the new status
        if user.is_active:  # Account was activated
            email_data = {
                'customer_name': user.name,
                'customer_id': user.username,  # Using username as ID for CHA
                'email': user.email,
                'activation_date': current_date,
                'login_url': 'https://navitrax.sonaapps.com/auth/login',
                'current_year': current_year
            }
            
            send_email(
                subject=f"CHA Account Activated - Welcome {user.name}",
                recipient=user.email,
                template="email/cha_activation_notification.html",
                **email_data
            )
            print(f"Activation email sent to CHA user: {user.email}")
            
        else:  # Account was deactivated
            email_data = {
                'customer_name': user.name,
                'customer_id': user.username,
                'email': user.email,
                'deactivation_date': current_date,
                'support_email': 'support@navitrax.com',
                'support_phone': '+1-800-NAVITRAX',
                'current_year': current_year
            }
            
            send_email(
                subject=f"CHA Account Deactivated - {user.name}",
                recipient=user.email,
                template="email/cha_deactivation_notification.html",
                **email_data
            )
            print(f"Deactivation email sent to CHA user: {user.email}")
        
        status_text = "activated" if user.is_active else "deactivated"
        message = f"CHA user {status_text} successfully"
        
        if request.is_json:
            return jsonify({
                "success": True, 
                "message": message,
                "is_active": user.is_active
            })
        else:
            flash(message, "success")
            return redirect(url_for('masters.customers', customer_type=2))
        
    except Exception as e:
        db.session.rollback()
        print(f"Error in toggle_cha_status: {str(e)}")
        if request.is_json:
            return jsonify({"success": False, "message": str(e)}), 500
        else:
            flash(f"Error", "danger")
            return redirect(url_for('masters.customers', customer_type=2))

def generate_customer_id():
    """
    Generate next customer ID in format CUS0001, CUS0002, etc.
    """
    try:
        # Get the last customer ID from the database
        last_customer = Customer.query.filter(
            Customer.customer_id.like('CUS%')
        ).order_by(Customer.customer_id.desc()).first()
        
        if last_customer and last_customer.customer_id:
            # Extract the numeric part from the last customer ID
            last_id = last_customer.customer_id
            if last_id.startswith('CUS') and len(last_id) >= 6:
                try:
                    numeric_part = int(last_id[3:])  # Get everything after 'CUS'
                    next_number = numeric_part + 1
                except ValueError:
                    # If parsing fails, start from 1
                    next_number = 1
            else:
                next_number = 1
        else:
            # No customers found, start from 1
            next_number = 1
        
        # Format with leading zeros (4 digits)
        return f"CUS{next_number:04d}"
        
    except Exception as e:
        # If any error occurs, return a default starting ID
        print(f"Error generating customer ID: {str(e)}")
        return "CUS0001"

@bp.route("/customer/new", methods=["GET", "POST"])
@login_required
def new_customer():
    form = CustomerForm()
    
    # Auto-generate customer ID for new customers
    if request.method == "GET":
        form.customer_id.data = generate_customer_id()
    
    # Get income types and currencies for rate card
    incomes = IncomeExpense.query.filter_by(
        type="income", company_id=current_user.company_id, status=True
    ).all()
    currencies = CurrencyMaster.query.all()
    
    # Default to first currency if available
    selected_currency_id = request.args.get('currency_id', None)
    if not selected_currency_id and currencies:
        selected_currency_id = currencies[0].currencyID

    # Mapping customer_type to role_id
    customer_type_to_role_id = {
        1: 4,  # Company
        2: 5,  # Clearing Agent
        3: 9   # Clearing Company
    }
    
    if form.validate_on_submit():
        # Check if customer ID already exists (extra validation)
        existing_customer = Customer.query.filter_by(customer_id=form.customer_id.data).first()
        if existing_customer:
            flash("Customer ID already exists. Please try again.", "error")
            form.customer_id.data = generate_customer_id()  # Generate new ID
            return render_template(
                "masters/customer_form.html",
                title="New Customer",
                form=form,
                legend="New Customer",
                incomes=incomes,
                currencies=currencies,
                selected_currency_id=selected_currency_id,
                rate_cards={}
            )
        
        # Map customer_type to role_id
        role_id = customer_type_to_role_id.get(form.customer_type.data)
        
        # Create the customer
        customer = Customer(
            customer_id=form.customer_id.data,
            customer_name=form.customer_name.data,
            short_name=form.short_name.data,
            customer_type=form.customer_type.data,
            role_id=role_id,
            address=form.address.data,
            email=form.email.data,
            telephone=form.telephone.data,
            credit_facility=form.credit_facility.data if form.customer_type.data == 1 else None,
            credit_period=form.credit_period.data if form.customer_type.data == 1 else None,
            dsr_format=form.dsr_format.data if form.customer_type.data == 1 else None,
            icl_report_format=form.icl_report_format.data if form.customer_type.data == 1 else None,
            new_storage_report_format=form.new_storage_report_format.data if form.customer_type.data == 1 else None,
            sales_person=form.sales_person.data if form.customer_type.data == 1 else None,
            cs_executive=form.cs_executive.data if form.customer_type.data == 1 else None,
            status=form.status.data,
            billing_party_same=form.billing_party_same.data,
            billing_party_name=form.billing_party_name.data,
            billing_party_address=form.billing_party_address.data,
            billing_party_email=form.billing_party_email.data,
            billing_party_contact_person=form.billing_party_contact_person.data,
            billing_party_telephone=form.billing_party_telephone.data,
            company_id=current_user.company_id,
        )
        db.session.add(customer)
        db.session.commit()
        
        # Save the rate card data only for companies
        if customer.customer_type == 1:
            currency_id = request.form.get('currency_id')
            income_ids = request.form.getlist('rate_card_income_ids[]')
            amounts = request.form.getlist('rate_card_amounts[]')
            
            # Create rate cards for all incomes with non-zero amounts
            for i in range(len(income_ids)):
                if amounts[i] and float(amounts[i]) > 0:
                    rate_card = RateCard(
                        customer_id=customer.id,
                        company_id=current_user.company_id,
                        income_id=income_ids[i],
                        currency_id=currency_id,
                        amount=amounts[i]
                    )
                    db.session.add(rate_card)
        
        db.session.commit()
        flash("Customer has been created successfully!", "success")
        return redirect(url_for("masters.customers"))
    
    return render_template(
        "masters/customer_form.html",
        title="New Customer",
        form=form,
        legend="New Customer",
        incomes=incomes,
        currencies=currencies,
        selected_currency_id=selected_currency_id,
        rate_cards={}  # Empty dict for new customer
    )


# Update the existing edit_customer route to include attachment data
@bp.route("/customer/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_customer(id):
    customer = Customer.query.get_or_404(id)
    
    form = CustomerForm()
    
    # Get income types and currencies for rate card
    incomes = IncomeExpense.query.filter_by(
        type="income", company_id=current_user.company_id, status=True
    ).all()
    currencies = CurrencyMaster.query.all()
    
    # Get selected currency
    selected_currency_id = request.args.get('currency_id')
    if not selected_currency_id:
        # Try to find if customer has any rate cards
        existing_rate_card = RateCard.query.filter_by(customer_id=customer.id).first()
        if existing_rate_card:
            selected_currency_id = existing_rate_card.currency_id
        elif currencies:
            selected_currency_id = currencies[0].currencyID
    
    # Get existing rate cards for the selected currency (only for companies)
    rate_cards = {}
    if selected_currency_id and customer.customer_type == 1:
        existing_rates = RateCard.query.filter_by(
            customer_id=customer.id,
            currency_id=selected_currency_id
        ).all()
        
        # Create a dict with income_id as key and amount as value
        for rate in existing_rates:
            rate_cards[rate.income_id] = rate.amount
    
    if form.validate_on_submit():
        # Store old status for comparison
        old_status = customer.status

        # Update customer fields
        customer.customer_id = form.customer_id.data
        customer.customer_name = form.customer_name.data
        customer.short_name = form.short_name.data
        customer.customer_type = form.customer_type.data  # New field
        customer.address = form.address.data
        customer.email = form.email.data
        customer.telephone = form.telephone.data
        customer.credit_facility = form.credit_facility.data if form.customer_type.data == 1 else None
        customer.credit_period = form.credit_period.data if form.customer_type.data == 1 else None
        customer.dsr_format = form.dsr_format.data if form.customer_type.data == 1 else None
        customer.icl_report_format = form.icl_report_format.data if form.customer_type.data == 1 else None
        customer.new_storage_report_format = form.new_storage_report_format.data if form.customer_type.data == 1 else None
        customer.sales_person = form.sales_person.data if form.customer_type.data == 1 else None
        customer.cs_executive = form.cs_executive.data if form.customer_type.data == 1 else None
        customer.status = form.status.data
        customer.billing_party_same = form.billing_party_same.data
        customer.billing_party_name = form.billing_party_name.data
        customer.billing_party_address = form.billing_party_address.data
        customer.billing_party_email = form.billing_party_email.data
        customer.billing_party_contact_person = form.billing_party_contact_person.data
        customer.billing_party_telephone = form.billing_party_telephone.data

        # If customer has a user and status has changed, update user status
        if customer.user_id and old_status != customer.status:
            user = User.query.get(customer.user_id)
            if user:
                user.is_active = customer.status
        
        # Update rate card data only for companies
        if customer.customer_type == 1:
            currency_id = request.form.get('currency_id')
            income_ids = request.form.getlist('rate_card_income_ids[]')
            amounts = request.form.getlist('rate_card_amounts[]')
            
            # First, delete existing rate cards for this currency
            RateCard.query.filter_by(
                customer_id=customer.id,
                currency_id=currency_id
            ).delete()
            
            # Create new rate cards for all incomes with non-zero amounts
            for i in range(len(income_ids)):
                if amounts[i] and float(amounts[i]) > 0:
                    rate_card = RateCard(
                        customer_id=customer.id,
                        company_id=current_user.company_id,
                        income_id=income_ids[i],
                        currency_id=currency_id,
                        amount=amounts[i]
                    )
                    db.session.add(rate_card)
        else:
            # If customer type changed to clearing agent, delete all rate cards
            RateCard.query.filter_by(customer_id=customer.id).delete()

        db.session.commit()
        flash("Customer has been updated successfully!", "success")
        return redirect(url_for("masters.customers"))
    elif request.method == "GET":
        form.customer_id.data = customer.customer_id
        form.customer_name.data = customer.customer_name
        form.short_name.data = customer.short_name
        form.customer_type.data = customer.customer_type  # New field
        form.address.data = customer.address
        form.email.data = customer.email
        form.telephone.data = customer.telephone
        form.credit_facility.data = customer.credit_facility
        form.credit_period.data = customer.credit_period
        form.dsr_format.data = customer.dsr_format
        form.icl_report_format.data = customer.icl_report_format
        form.new_storage_report_format.data = customer.new_storage_report_format
        form.sales_person.data = customer.sales_person
        form.cs_executive.data = customer.cs_executive
        form.status.data = customer.status
        form.billing_party_same.data = customer.billing_party_same
        form.billing_party_name.data = customer.billing_party_name
        form.billing_party_address.data = customer.billing_party_address
        form.billing_party_email.data = customer.billing_party_email
        form.billing_party_contact_person.data = customer.billing_party_contact_person
        form.billing_party_telephone.data = customer.billing_party_telephone
    
    return render_template(
        "masters/customer_form.html",
        title="Edit Customer",
        form=form,
        legend="Edit Customer",
        customer=customer,
        csrf_token=form.csrf_token.current_token,
        incomes=incomes,
        currencies=currencies,
        selected_currency_id=selected_currency_id,
        rate_cards=rate_cards
    )




@bp.route("/customer/<int:id>/view")
@login_required
def view_customer(id):
    customer = Customer.query.get_or_404(id)

    # Get income types and currencies for rate card
    incomes = IncomeExpense.query.filter_by(
        type="income", company_id=current_user.company_id, status=True
    ).all()
    currencies = CurrencyMaster.query.all()
    
    # Get currency_id from query params or use first available one
    active_currency_id = request.args.get('currency_id')
    
    # If no currency specified, find one that has rate cards
    if not active_currency_id:
        # Check if customer has any rate cards
        first_rate = RateCard.query.filter_by(customer_id=customer.id).first()
        if first_rate:
            active_currency_id = first_rate.currency_id
        elif currencies:
            active_currency_id = currencies[0].currencyID
    
    # Get the active currency
    active_currency = None
    if active_currency_id:
        active_currency = CurrencyMaster.query.get(active_currency_id)
    
    # Get rate cards for the selected currency
    rate_cards = []
    if active_currency_id:
        rate_cards = RateCard.query.filter_by(
            customer_id=customer.id,
            currency_id=active_currency_id
        ).join(IncomeExpense, RateCard.income_id == IncomeExpense.id)\
        .filter(IncomeExpense.status == True)\
        .order_by(IncomeExpense.description).all()
    
    # Create rate cards dict for easy access in template
    rate_cards_dict = {}
    for rate in rate_cards:
        rate_cards_dict[rate.income_id] = rate.amount
    
    return render_template(
        "masters/customer_view.html", 
        title="View Customer", 
        customer=customer,
        currencies=currencies,
        active_currency=active_currency,
        active_currency_id=active_currency_id,
        rate_cards=rate_cards,
        rate_cards_dict=rate_cards_dict,
        incomes=incomes
    )




# rOUTES FOR CHA COMPANIES TO ADD ATTACHMENTS AND RATECARDS

# API Routes for Rate Card Management
@bp.route("/customer/<int:customer_id>/rate-card/save", methods=["POST"])
@login_required
def save_customer_rate_card(customer_id):
    """Save or update rate card for a customer."""
    try:
        customer = Customer.query.get_or_404(customer_id)
        
        # Get form data
        currency_id = request.form.get('currency_id')
        income_ids = request.form.getlist('rate_card_income_ids[]')
        amounts = request.form.getlist('rate_card_amounts[]')
        
        if not currency_id:
            return jsonify({"success": False, "message": "Currency is required"}), 400
        
        # First, delete existing rate cards for this currency
        RateCard.query.filter_by(
            customer_id=customer.id,
            currency_id=currency_id
        ).delete()
        
        # Create new rate cards for all incomes with non-zero amounts
        for i in range(len(income_ids)):
            if amounts[i] and float(amounts[i]) > 0:
                rate_card = RateCard(
                    customer_id=customer.id,
                    company_id=current_user.company_id,
                    income_id=income_ids[i],
                    currency_id=currency_id,
                    amount=amounts[i]
                )
                db.session.add(rate_card)
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Rate card saved successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving rate card: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/customer/<int:customer_id>/rate-card/get", methods=["GET"])
@login_required
def get_customer_rate_card(customer_id):
    """Get rate card data for a specific currency."""
    try:
        customer = Customer.query.get_or_404(customer_id)
        currency_id = request.args.get('currency_id')
        
        if not currency_id:
            return jsonify({"success": False, "message": "Currency ID is required"}), 400
        
        # Get existing rate cards for the selected currency
        rate_cards = RateCard.query.filter_by(
            customer_id=customer.id,
            currency_id=currency_id
        ).all()
        
        # Create a dict with income_id as key and amount as value
        rate_cards_data = {}
        for rate in rate_cards:
            rate_cards_data[rate.income_id] = float(rate.amount)
        
        return jsonify({
            "success": True,
            "rate_cards": rate_cards_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting rate card: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


# API Routes for Customer Attachments Management
@bp.route("/customer/<int:customer_id>/attachments", methods=["GET"])
@login_required
def get_customer_attachments(customer_id):
    """Get all attachments for a customer."""
    try:
        customer = Customer.query.get_or_404(customer_id)
        
        # Get attachments
        attachments = CustomerAttachment.query.filter_by(
            customer_id=customer_id,
            is_active=True
        ).order_by(CustomerAttachment.uploaded_at.desc()).all()
        
        attachments_data = []
        for att in attachments:
            attachments_data.append({
                'id': att.id,
                'file_name': att.file_name,
                'file_url': f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{att.file_path}",
                'expiry_date': att.expiry_date.strftime('%Y-%m-%d'),
                'description': att.description or '',
                'uploaded_by_name': att.uploader.name,
                'uploaded_at': att.uploaded_at.isoformat()
            })
        
        return jsonify({
            "success": True,
            "attachments": attachments_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting attachments: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/customer/<int:customer_id>/attachment/upload", methods=["POST"])
@login_required
def upload_customer_attachment(customer_id):
    """Upload an attachment for a customer."""
    try:
        customer = Customer.query.get_or_404(customer_id)
        
        # Get form data
        expiry_date = request.form.get('expiry_date')
        description = request.form.get('description', '')
        
        # Validate required fields
        if not expiry_date:
            return jsonify({"success": False, "message": "Expiry date is required"}), 400
        
        # Validate file
        if 'file' not in request.files:
            return jsonify({"success": False, "message": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"success": False, "message": "No file selected"}), 400
        
        # Secure filename
        filename = secure_filename(file.filename)
        file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        # Generate unique filename
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        
        # Create S3 path
        s3_path = f"customer_attachments/{customer_id}/{unique_filename}"
        
        # Upload to S3
        try:
            s3_client = boto3.client(
                's3',
                endpoint_url=current_app.config['S3_ENDPOINT_URL'],
                aws_access_key_id=current_app.config['AWS_ACCESS_KEY_ID'],
                aws_secret_access_key=current_app.config['AWS_SECRET_ACCESS_KEY']
            )
            
            s3_client.upload_fileobj(
                file,
                current_app.config['S3_BUCKET_NAME'],
                s3_path
            )
        except Exception as e:
            current_app.logger.error(f"S3 upload error: {str(e)}")
            return jsonify({"success": False, "message": "Failed to upload file"}), 500
        
        # Create attachment record
        attachment = CustomerAttachment(
            customer_id=customer_id,
            user_id=customer.user_id,
            uploaded_by=current_user.id,
            company_id=current_user.company_id,
            file_path=s3_path,
            file_name=filename,
            expiry_date=datetime.strptime(expiry_date, '%Y-%m-%d').date(),
            description=description
        )
        
        db.session.add(attachment)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Document uploaded successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error uploading attachment: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/customer/<int:customer_id>/attachment/<int:attachment_id>/update", methods=["POST"])
@login_required
def update_customer_attachment(customer_id, attachment_id):
    """Update an existing attachment."""
    try:
        customer = Customer.query.get_or_404(customer_id)
        attachment = CustomerAttachment.query.get_or_404(attachment_id)
        
        # Verify attachment belongs to this customer
        if attachment.customer_id != customer_id:
            return jsonify({"success": False, "message": "Attachment not found"}), 404
        
        # Get form data
        expiry_date = request.form.get('expiry_date')
        description = request.form.get('description', '')
        
        # Update fields
        if expiry_date:
            attachment.expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
        
        attachment.description = description
        attachment.updated_at = datetime.utcnow()
        
        # Handle file update if provided
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '':
                # Delete old file from S3
                try:
                    s3_client = boto3.client(
                        's3',
                        endpoint_url=current_app.config['S3_ENDPOINT_URL'],
                        aws_access_key_id=current_app.config['AWS_ACCESS_KEY_ID'],
                        aws_secret_access_key=current_app.config['AWS_SECRET_ACCESS_KEY']
                    )
                    
                    s3_client.delete_object(
                        Bucket=current_app.config['S3_BUCKET_NAME'],
                        Key=attachment.file_path
                    )
                except Exception as e:
                    current_app.logger.error(f"Error deleting old file: {str(e)}")
                
                # Upload new file
                filename = secure_filename(file.filename)
                file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
                unique_filename = f"{uuid.uuid4()}.{file_extension}"
                s3_path = f"customer_attachments/{customer_id}/{unique_filename}"
                
                try:
                    s3_client.upload_fileobj(
                        file,
                        current_app.config['S3_BUCKET_NAME'],
                        s3_path
                    )
                    
                    # Update attachment record
                    attachment.file_path = s3_path
                    attachment.file_name = filename
                    
                except Exception as e:
                    current_app.logger.error(f"S3 upload error: {str(e)}")
                    return jsonify({"success": False, "message": "Failed to upload new file"}), 500
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Document updated successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating attachment: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/customer/<int:customer_id>/attachment/<int:attachment_id>/delete", methods=["POST"])
@login_required
def delete_customer_attachment(customer_id, attachment_id):
    """Delete an attachment (soft delete)."""
    try:
        customer = Customer.query.get_or_404(customer_id)
        attachment = CustomerAttachment.query.get_or_404(attachment_id)
        
        # Verify attachment belongs to this customer
        if attachment.customer_id != customer_id:
            return jsonify({"success": False, "message": "Attachment not found"}), 404
        
        # Soft delete
        attachment.is_active = False
        attachment.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Document deleted successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting attachment: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


#########################


@bp.route("/customer/<int:id>/delete", methods=["POST"])
@login_required
def delete_customer(id):
    customer = Customer.query.get_or_404(id)    
    try:
        # Get the associated user if exists
        user = customer.user if hasattr(customer, 'user') and customer.user else None
        
        # 1. Delete all shipment-related data for this customer
        shipment_entries = ShipDocumentEntryMaster.query.filter_by(customer_id=customer.id).all()
        
        for entry in shipment_entries:
            # Delete container workflow documents
            ContainerWorkflowDocument.query.filter_by(entry_id=entry.id).delete()
            
            # Delete import containers and their related data
            for container in entry.import_containers:
                ContainerStepCompletion.query.filter_by(container_id=container.id).delete()
                db.session.delete(container)
            
            # Delete export containers
            for container in entry.export_containers:
                db.session.delete(container)
            
            # Delete shipment items
            ShipmentItem.query.filter_by(shipment_id=entry.id).delete()
            
            # Delete shipment expenses and their settlements
            for expense in entry.expenses:
                ExpenseSettlement.query.filter_by(expense_id=expense.id).delete()
                db.session.delete(expense)
            
            # Delete invoice details and headers
            for invoice in entry.invoices:
                InvoiceDetail.query.filter_by(invoice_header_id=invoice.id).delete()
                db.session.delete(invoice)
            
            # Delete expense settlements related to this shipment
            ExpenseSettlement.query.filter_by(shipment_id=entry.id).delete()
            
            # Delete ship document entry documents
            for document in entry.documents:
                db.session.delete(document)
            
            # Delete ship document attachments and their history
            for attachment in entry.attachments:
                ShipDocumentHistory.query.filter_by(attachment_id=attachment.id).delete()
                db.session.delete(attachment)
            
            # Delete entry assignment history
            EntryAssignmentHistory.query.filter_by(entry_id=entry.id).delete()
            
            # Delete clearing agent and company history
            EntryClearingAgentHistory.query.filter_by(entry_id=entry.id).delete()
            EntryClearingCompanyHistory.query.filter_by(entry_id=entry.id).delete()
            
            # Delete order shipment data
            OrderShipment.query.filter_by(ship_doc_entry_id=entry.id).delete()
            
            # Delete the main shipment entry
            db.session.delete(entry)
        
        # 2. Delete document attachments where customer is referenced
        ShipDocumentEntryAttachment.query.filter_by(customer_id=customer.id).delete()
        
        # 3. Delete orders and related data
        orders = Order.query.filter_by(customer_id=customer.id).all()
        for order in orders:
            # Delete order items
            OrderItem.query.filter_by(order_id=order.id).delete()
            # Delete order documents
            OrderDocument.query.filter_by(order_id=order.id).delete()
            # Delete the order
            db.session.delete(order)
        
        # 4. Delete chat-related data
        # Find chat threads where this customer might be involved
        # (This requires checking if customer has a user account)
        if user:
            # Delete chat messages
            ChatMessage.query.filter_by(sender_id=user.id).delete()
            
            # Delete chat participants
            ChatParticipant.query.filter_by(user_id=user.id).delete()
            
            # Delete task-related data if user was involved
            TaskComment.query.filter_by(user_id=user.id).delete()
            TaskAttachment.query.filter_by(uploaded_by=user.id).delete()
            TimeEntry.query.filter_by(user_id=user.id).delete()
            TaskWatcher.query.filter_by(user_id=user.id).delete()
            TaskHistory.query.filter_by(changed_by=user.id).delete()
            TaskVisibility.query.filter_by(current_owner_id=user.id).delete()
            
            # Delete project-related data
            ProjectMember.query.filter_by(user_id=user.id).delete()
            
            # Update tasks where user was assigned or created by
            Task.query.filter_by(assigned_to=user.id).update({'assigned_to': None})
            Task.query.filter_by(created_by=user.id).update({'created_by': None})
            
            # Delete issue-related data
            IssueComment.query.filter_by(created_by=user.id).delete()
            IssueHistory.query.filter_by(changed_by=user.id).delete()
            IssueAttachment.query.filter_by(uploaded_by=user.id).delete()
            IssueLink.query.filter_by(created_by=user.id).delete()
            
            # Update issues where user was assigned or reporter
            Issue.query.filter_by(assignee_id=user.id).update({'assignee_id': None})
            Issue.query.filter_by(reporter_id=user.id).update({'reporter_id': None})
            
            # Delete agent and company assignments
            AgentAssignment.query.filter_by(assigned_by_user_id=user.id).delete()
            AgentAssignment.query.filter_by(assigned_agent_id=user.id).delete()
            CompanyAssignment.query.filter_by(assigned_by_user_id=user.id).delete()
            CompanyAssignment.query.filter_by(assigned_company_id=user.id).delete()
            
            # Delete user company associations
            UserCompany.query.filter_by(user_id=user.id).delete()
            
            # Delete user action permissions
            UserActionPermission.query.filter_by(user_id=user.id).delete()
            
            # Update any other references to this user
            POHeader.query.filter_by(created_by=user.id).update({'created_by': None})
            ShipmentItem.query.filter_by(created_by=user.id).update({'created_by': None})
            ShipmentExpense.query.filter_by(created_by=user.id).update({'created_by': None})
            InvoiceHeader.query.filter_by(created_by=user.id).update({'created_by': None})
            ExpenseSettlement.query.filter_by(created_by=user.id).update({'created_by': None})
            ShipDocumentEntryAttachment.query.filter_by(user_id=user.id).update({'user_id': None})
            ShipDocumentEntryAttachment.query.filter_by(docAccepteUserID=user.id).update({'docAccepteUserID': None})
            
            # Update runner and wharf profile references
            Runner.query.filter_by(user_id=user.id).update({'user_id': None})
            WharfProfile.query.filter_by(user_id=user.id).update({'user_id': None})
        
        # 5. Delete customer attachments
        customer_attachments = CustomerAttachment.query.filter_by(customer_id=customer.id).all()
        
        # Delete files from S3
        if customer_attachments:
            try:
                s3_client = boto3.client(
                    's3',
                    endpoint_url=current_app.config['S3_ENDPOINT_URL'],
                    aws_access_key_id=current_app.config['AWS_ACCESS_KEY_ID'],
                    aws_secret_access_key=current_app.config['AWS_SECRET_ACCESS_KEY']
                )
                
                for attachment in customer_attachments:
                    try:
                        s3_client.delete_object(
                            Bucket=current_app.config['S3_BUCKET_NAME'],
                            Key=attachment.file_path
                        )
                    except Exception as e:
                        current_app.logger.error(f"Error deleting S3 file {attachment.file_path}: {str(e)}")
                        
                    db.session.delete(attachment)
                    
            except Exception as e:
                current_app.logger.error(f"Error initializing S3 client: {str(e)}")
                # Continue with deletion even if S3 fails
                for attachment in customer_attachments:
                    db.session.delete(attachment)
        


        # 5. Delete rate cards for this customer
        RateCard.query.filter_by(customer_id=customer.id).delete()
        
        # 6. Delete the customer record
        db.session.delete(customer)
        
        # 7. Finally, delete the user account if it exists
        if user:
            db.session.delete(user)
        
        # Commit all changes
        db.session.commit()
        
        flash("Customer and all related data have been deleted successfully!", "success")
        
    except Exception as e:
        # Rollback in case of any error
        db.session.rollback()
        flash(f"Error deleting customer", "error")
        print(f"Error deleting customer: {str(e)}", "error")

    return redirect(url_for("masters.customers"))


@bp.route("/customer/<int:id>/create-login", methods=["POST"])
@login_required
def create_customer_login(id):
    try:
        customer = Customer.query.get_or_404(id)


        # Check if customer already has a login
        if customer.user_id:
            return jsonify({"success": False, "message": "This customer already has a login."}), 400

        # Check if email is already registered
        existing_user = User.query.filter_by(email=customer.email).first()
        if existing_user:
            return jsonify({"success": False, "message": "This email is already registered with another user."}), 400

        # Determine role and role_id based on customer type
        if customer.customer_type == 1:  # Company
            role = 'customer'
            role_id = 4
            is_super_admin = 3
        elif customer.customer_type == 3:  # Individual
            role = 'clearing_company'
            role_id = 9
            is_super_admin = 3
        else:  # Clearing Agent
            role = 'clearing_agent'
            role_id = 5
            is_super_admin = 3  # or you can create a new type if needed

        # Create new user
        user = User(
            name=customer.customer_name,
            email=customer.email,
            contact_number=customer.telephone,
            username=customer.email,
            company_id=customer.company_id,
            role=role,
            role_id=role_id,
            is_active=True,
            is_super_admin=is_super_admin,
        )
        user.set_password("welcome1")

        db.session.add(user)
        db.session.flush()

        # Update customer
        customer.user_id = user.id
        db.session.commit()

        # Send email notification
        send_email(
            subject="Your Account Has Been Created",
            recipient=user.email,
            template="email/customer_account_created.html",
            name=user.name,
        )

        return jsonify({"success": True, "message": "Login created and email sent successfully."}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error creating login: {str(e)}"}), 500




# AttachmentType routes
###############################
@bp.route("/attachment-types")
@login_required
def attachment_types():
    """List all attachment types."""
    if current_user.role == 1:
        attachment_types = AttachmentType.query.all()
    else:
        attachment_types = AttachmentType.query.filter_by(company_id=get_company_id()).all()
    
    return render_template(
        "masters/attachment_types.html",
        title="Attachment Types",
        attachment_types=attachment_types,
    )


@bp.route("/attachment-type/add", methods=["GET", "POST"])
@login_required
def add_attachment_type():
    """Add a new attachment type."""
    if request.method == "POST":
        # Get form data
        attachment_code = request.form.get("attachment_code")
        attachment_name = request.form.get("attachment_name")
        role_id = request.form.get("role_id")
        is_active = request.form.get("is_active") == "on"
        
        try:
            # Check if role is already assigned to another attachment type
            existing = AttachmentType.query.filter_by(role_id=role_id).first()
            if existing:
                flash("This role is already assigned to another attachment type.", "danger")
                return redirect(url_for("masters.add_attachment_type"))
            
            # Create new attachment type
            attachment_type = AttachmentType(
                attachment_code=attachment_code,
                attachment_name=attachment_name,
                role_id=role_id,
                is_active=is_active,
                company_id=get_company_id(),
            )
            
            db.session.add(attachment_type)
            db.session.commit()
            
            flash("Attachment type has been created successfully!", "success")
            return redirect(url_for("masters.attachment_types"))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating attachment type: {str(e)}")
            flash("An error occurred while creating the attachment type.", "danger")
            return redirect(url_for("masters.add_attachment_type"))
    
    # GET request - show form
    # Get available roles (excluding user, super_admin, admin)
    excluded_roles = ['user', 'super_admin', 'admin']
    
    # Get roles that are not already assigned
    assigned_role_ids = db.session.query(AttachmentType.role_id).filter(
        AttachmentType.role_id.isnot(None)
    ).subquery()
    
    available_roles = Role.query.filter(
        ~Role.role_name.in_(excluded_roles),
        ~Role.id.in_(assigned_role_ids)
    ).all()
    
    return render_template(
        "masters/attachment_type_form.html",
        title="Add Attachment Type",
        available_roles=available_roles,
        attachment_type=None
    )


@bp.route("/attachment-type/<int:attachment_type_id>/edit", methods=["GET", "POST"])
@login_required
def edit_attachment_type(attachment_type_id):
    """Edit an existing attachment type."""
    attachment_type = AttachmentType.query.get_or_404(attachment_type_id)
    
    if attachment_type.company_id != get_company_id():
        flash("You don't have permission to edit this attachment type.", "danger")
        return redirect(url_for("masters.attachment_types"))
    
    if request.method == "POST":
        # Get form data
        attachment_code = request.form.get("attachment_code")
        attachment_name = request.form.get("attachment_name")
        role_id = request.form.get("role_id")
        is_active = request.form.get("is_active") == "on"
        
        try:
            # Check if role is already assigned to another attachment type (if role changed)
            if int(role_id) != attachment_type.role_id:
                existing = AttachmentType.query.filter_by(role_id=role_id).first()
                if existing:
                    flash("This role is already assigned to another attachment type.", "danger")
                    return redirect(url_for("masters.edit_attachment_type", attachment_type_id=attachment_type_id))
            
            # Update attachment type
            attachment_type.attachment_code = attachment_code
            attachment_type.attachment_name = attachment_name
            attachment_type.role_id = role_id
            attachment_type.is_active = is_active
            
            db.session.commit()
            
            flash("Attachment type has been updated successfully!", "success")
            return redirect(url_for("masters.attachment_types"))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating attachment type: {str(e)}")
            flash("An error occurred while updating the attachment type.", "danger")
            return redirect(url_for("masters.edit_attachment_type", attachment_type_id=attachment_type_id))
    
    # GET request - show form
    # Get available roles (including current role)
    excluded_roles = ['user', 'super_admin', 'admin']
    
    # Get roles that are not already assigned (except current one)
    assigned_role_ids = db.session.query(AttachmentType.role_id).filter(
        AttachmentType.role_id.isnot(None),
        AttachmentType.id != attachment_type_id
    ).subquery()
    
    available_roles = Role.query.filter(
        ~Role.role_name.in_(excluded_roles),
        ~Role.id.in_(assigned_role_ids)
    ).all()
    
    return render_template(
        "masters/attachment_type_form.html",
        title="Edit Attachment Type",
        available_roles=available_roles,
        attachment_type=attachment_type
    )


@bp.route("/attachment-type/<int:attachment_type_id>/delete", methods=["POST"])
@login_required
def delete_attachment_type(attachment_type_id):
    """Delete an attachment type."""
    attachment_type = AttachmentType.query.get_or_404(attachment_type_id)
    
    if attachment_type.company_id != get_company_id():
        flash("You don't have permission to delete this attachment type.", "danger")
        return redirect(url_for("masters.attachment_types"))
    
    try:
        # Delete will cascade to attachment documents due to relationship setup
        db.session.delete(attachment_type)
        db.session.commit()
        
        flash("Attachment type and related documents have been deleted!", "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting attachment type: {str(e)}")
        flash("An error occurred while deleting the attachment type.", "danger")
    
    return redirect(url_for("masters.attachment_types"))


# AttachmentDocument routes
###############################
@bp.route("/attachment-document/add", methods=["POST"])
@login_required
def add_attachment_document():
    """Add a new attachment document with optional sample file."""
    try:
        # Extract form data
        attachment_type_id = request.form.get("attachment_type_id")
        description = request.form.get("description")
        is_mandatory = int(request.form.get("is_mandatory", 0))
        allow_multiple = int(request.form.get("allow_multiple", 0))
        
        print(f"Adding document: Type ID: {attachment_type_id}")
        print(f"Description: {description}, Mandatory: {is_mandatory}, Multiple: {allow_multiple}")
        
        # Verify attachment type belongs to current company
        attachment_type = AttachmentType.query.get(attachment_type_id)

        
        # Initialize sample file path as None
        sample_file_path = None
        sample_file_url = None
        
        # Check if a sample file was uploaded
        print(f"Files in request: {list(request.files.keys())}")
        if 'sampleFile' in request.files:
            file = request.files['sampleFile']
            print(f"File object: {file}")
            print(f"File filename: {file.filename}")
            
            if file.filename != '':
                filename = secure_filename(file.filename)
                print(f"Secured filename: {filename}")
                
                # Reset file pointer
                file.seek(0)
                
                # Create S3 key - match the pattern from ship category
                s3_key = f"{current_app.config['S3_BASE_FOLDER']}/attachments/sample_documents/{attachment_type_id}/{filename}"
                print(f"S3 key: {s3_key}")
                print(f"S3 bucket: {current_app.config['S3_BUCKET_NAME']}")
                
                # Try to match the exact pattern from ship category
                try:
                    # Read file content
                    file_content = file.read()
                    print(f"File size: {len(file_content)} bytes")
                    
                    # Reset for upload
                    file.seek(0)
                    
                    # Upload file to S3
                    upload_result = upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
                    print(f"Upload result type: {type(upload_result)}, value: {upload_result}")
                    
                    if upload_result:
                        sample_file_path = s3_key
                        # Match the URL pattern exactly
                        sample_file_url = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{s3_key}"
                        print(f"File uploaded successfully. Path: {sample_file_path}")
                        print(f"Generated URL: {sample_file_url}")
                    else:
                        print("upload_file_to_s3 returned False/None")
                        # Let's try to construct the URL anyway since S3 showed 200
                        sample_file_path = s3_key
                        sample_file_url = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{s3_key}"
                        print(f"Constructing URL anyway: {sample_file_url}")
                        
                except Exception as upload_error:
                    print(f"Upload exception: {str(upload_error)}")
                    import traceback
                    traceback.print_exc()
            else:
                print("Filename is empty")
        else:
            print("No sampleFile in request.files")
        
        # Create and save the document
        document = AttachmentDocument(
            attachment_type_id=attachment_type_id,
            description=description,
            is_mandatory=bool(is_mandatory),
            allow_multiple=bool(allow_multiple),
            sample_file_path=sample_file_path,
            is_active=True
        )
        
        print(f"Creating document with sample_file_path: {sample_file_path}")
        db.session.add(document)
        db.session.flush()  # Flush to get the ID without committing
        
        print(f"Document ID after flush: {document.id}")
        print(f"Document sample_file_path after flush: {document.sample_file_path}")
        
        db.session.commit()
        
        # Verify the document was saved
        saved_doc = AttachmentDocument.query.get(document.id)
        print(f"Document saved with ID: {saved_doc.id}, Sample path: {saved_doc.sample_file_path}")
        
        # Double-check by querying again
        verify_doc = db.session.query(AttachmentDocument).filter_by(id=document.id).first()
        print(f"Verification query - ID: {verify_doc.id if verify_doc else 'None'}, Path: {verify_doc.sample_file_path if verify_doc else 'None'}")

        return jsonify({
            "success": True,
            "document": {
                "id": document.id,
                "description": document.description,
                "is_mandatory": document.is_mandatory,
                "allow_multiple": document.allow_multiple,
                "sample_file_url": sample_file_url
            }
        })
    except Exception as e:
        db.session.rollback()
        print(f"Error adding document: {str(e)}")
        import traceback
        traceback.print_exc()
        current_app.logger.error(f"Error adding attachment document: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/attachment-documents/<int:attachment_type_id>")
@login_required
def get_attachment_documents(attachment_type_id):
    """Get documents for an attachment type."""
    try:
        # Verify attachment type belongs to current company
        attachment_type = AttachmentType.query.get(attachment_type_id)
      
        documents = AttachmentDocument.query.filter_by(
            attachment_type_id=attachment_type_id
        ).all()
        
        print(f"Found {len(documents)} documents for attachment type ID {attachment_type_id}")
        
        document_list = []
        for doc in documents:
            print(f"Document ID: {doc.id}, Path: {doc.sample_file_path}")
            
            doc_info = {
                "id": doc.id,
                "description": doc.description,
                "is_mandatory": doc.is_mandatory,
                "allow_multiple": doc.allow_multiple,
                "sample_file_url": None
            }
            
            # Generate S3 URL for the sample file if it exists
            if doc.sample_file_path:
                doc_info["sample_file_url"] = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{doc.sample_file_path}"
                print(f"Generated URL: {doc_info['sample_file_url']}")
            else:
                print(f"No sample file path for document ID {doc.id}")
            
            document_list.append(doc_info)
        
        return jsonify({
            "success": True,
            "documents": document_list
        })
    except Exception as e:
        print(f"Error getting documents: {str(e)}")
        current_app.logger.error(f"Error getting attachment documents: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/attachment-document/<int:document_id>/update", methods=["POST"])
@login_required
def update_attachment_document(document_id):
    """Update an existing attachment document with optional sample file."""
    try:
        # Get the document
        document = AttachmentDocument.query.get_or_404(document_id)
        
        # Check if document belongs to the current company
        attachment_type = AttachmentType.query.get(document.attachment_type_id)

        
        # Extract form data
        description = request.form.get("description")
        is_mandatory = int(request.form.get("is_mandatory", 0))
        allow_multiple = int(request.form.get("allow_multiple", 0))
        
        # Update document fields
        document.description = description
        document.is_mandatory = bool(is_mandatory)
        document.allow_multiple = bool(allow_multiple)
        
        # Initialize sample file URL
        sample_file_url = None
        
        # Handle sample file update if provided
        if 'sampleFile' in request.files and request.files['sampleFile'].filename != '':
            file = request.files['sampleFile']
            filename = secure_filename(file.filename)
            
            # Create S3 key with proper structure
            s3_key = f"{current_app.config['S3_BASE_FOLDER']}/attachments/sample_documents/{document.attachment_type_id}/{filename}"
            
            # Reset file pointer to beginning
            file.seek(0)
            
            # Upload the file to S3 (we'll assume success based on S3's 200 response)
            upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
            
            # Update document with new file path
            document.sample_file_path = s3_key
            sample_file_url = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{s3_key}"
        else:
            # If no new file uploaded, keep existing URL if file exists
            if document.sample_file_path:
                sample_file_url = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{document.sample_file_path}"
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Document updated successfully",
            "document": {
                "id": document.id,
                "description": document.description,
                "is_mandatory": document.is_mandatory,
                "allow_multiple": document.allow_multiple,
                "sample_file_url": sample_file_url
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating document: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@bp.route("/attachment-document/<int:document_id>/delete", methods=["POST"])
@login_required
def delete_attachment_document(document_id):
    """Delete an attachment document."""
    try:
        # Get the document
        document = AttachmentDocument.query.get_or_404(document_id)
        
        # Check if document belongs to the current company
        attachment_type = AttachmentType.query.get(document.attachment_type_id)

        # Optional: Delete the file from S3
        # if document.sample_file_path:
        #     delete_file_from_s3(current_app.config["S3_BUCKET_NAME"], document.sample_file_path)
        
        db.session.delete(document)
        db.session.commit()
        
        return jsonify({"success": True, "message": "Document deleted successfully"})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting document: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# CUSTOMER ATTACHMENTS

# Add these routes to your masters blueprint

@bp.route("/customer/<int:customer_id>/attachment-types", methods=["GET"])
@login_required
def get_customer_attachment_types(customer_id):
    """Get attachment types and documents based on customer type."""
    try:
        customer = Customer.query.get_or_404(customer_id)
        
        
        role_id = customer.role_id
        
        # Get attachment types for this role
        # Use == comparison instead of filter_by for the role field
        attachment_types = AttachmentType.query.filter(
            AttachmentType.company_id == get_company_id(),
            AttachmentType.role_id == role_id,
            AttachmentType.is_active == True
        ).all()
        
        # Build response with documents for each type
        types_data = []
        documents_data = {}
        
        for att_type in attachment_types:
            types_data.append({
                'id': att_type.id,
                'name': att_type.name
            })
            
            # Get documents for this type
            documents = AttachmentDocument.query.filter_by(
                attachment_type_id=att_type.id,
                is_active=True
            ).all()
            
            documents_data[att_type.id] = [{
                'id': doc.id,
                'description': doc.description,
                'is_mandatory': doc.is_mandatory,
                'allow_multiple': doc.allow_multiple,
                'sample_file_path': doc.sample_file_path,
                'sample_file_url': f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{doc.sample_file_path}" if doc.sample_file_path else None
            } for doc in documents]
        
        return jsonify({
            "success": True,
            "attachment_types": types_data,
            "attachment_documents": documents_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting attachment types: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    

# @bp.route("/customer/<int:customer_id>/attachments", methods=["GET"])
# @login_required
# def get_customer_attachments(customer_id):
#     """Get all attachments for a customer."""
#     try:
#         customer = Customer.query.get_or_404(customer_id)
        

        
#         # Get attachments
#         attachments = CustomerAttachment.query.filter_by(
#             customer_id=customer_id,
#             is_active=True
#         ).all()
        
#         attachments_data = []
#         for att in attachments:
#             attachments_data.append({
#                 'id': att.id,
#                 'document_type': att.attachment_type.name,
#                 'document_description': att.attachment_document.description,
#                 'file_name': att.file_name,
#                 'file_url': f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{att.file_path}",
#                 'expiry_date': att.expiry_date.strftime('%Y-%m-%d'),
#                 'description': att.description,
#                 'uploaded_by_name': att.uploader.name,
#                 'uploaded_at': att.uploaded_at.isoformat()
#             })
        
#         return jsonify({
#             "success": True,
#             "attachments": attachments_data
#         })
        
#     except Exception as e:
#         current_app.logger.error(f"Error getting attachments: {str(e)}")
#         return jsonify({"success": False, "message": str(e)}), 500


# @bp.route("/customer/<int:customer_id>/upload-attachment", methods=["POST"])
# @login_required
# def upload_customer_attachment(customer_id):
#     """Upload an attachment for a customer."""
#     try:
#         customer = Customer.query.get_or_404(customer_id)
        
        
#         # Get form data
#         attachment_type_id = request.form.get('attachment_type_id')
#         attachment_document_id = request.form.get('attachment_document_id')
#         expiry_date = request.form.get('expiry_date')
#         description = request.form.get('description', '')
        
#         # Validate required fields
#         if not all([attachment_type_id, attachment_document_id, expiry_date]):
#             return jsonify({"success": False, "message": "Missing required fields"}), 400
        
#         # Validate file
#         if 'file' not in request.files:
#             return jsonify({"success": False, "message": "No file provided"}), 400
        
#         file = request.files['file']
#         if file.filename == '':
#             return jsonify({"success": False, "message": "No file selected"}), 400
        
#         # Check if document allows multiple uploads
#         document = AttachmentDocument.query.get(attachment_document_id)
#         if not document.allow_multiple:
#             # Check if attachment already exists
#             existing = CustomerAttachment.query.filter_by(
#                 customer_id=customer_id,
#                 attachment_document_id=attachment_document_id,
#                 is_active=True
#             ).first()
            
#             if existing:
#                 return jsonify({"success": False, "message": "This document type does not allow multiple uploads"}), 400
        
#         # Secure filename
#         filename = secure_filename(file.filename)
#         file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
#         # Generate unique filename
#         unique_filename = f"{uuid.uuid4()}.{file_extension}"
        
#         # Create S3 path
#         s3_path = f"customer_attachments/{customer_id}/{unique_filename}"
        
#         # Upload to S3
#         try:
#             s3_client = boto3.client(
#                 's3',
#                 endpoint_url=current_app.config['S3_ENDPOINT_URL'],
#                 aws_access_key_id=current_app.config['AWS_ACCESS_KEY_ID'],
#                 aws_secret_access_key=current_app.config['AWS_SECRET_ACCESS_KEY']
#             )
            
#             s3_client.upload_fileobj(
#                 file,
#                 current_app.config['S3_BUCKET_NAME'],
#                 s3_path
#             )
#         except Exception as e:
#             current_app.logger.error(f"S3 upload error: {str(e)}")
#             return jsonify({"success": False, "message": "Failed to upload file"}), 500
        
#         # Create attachment record
#         attachment = CustomerAttachment(
#             attachment_type_id=attachment_type_id,
#             attachment_document_id=attachment_document_id,
#             customer_id=customer_id,
#             user_id=customer.user_id,
#             uploaded_by=current_user.id,
#             customer_type=customer.customer_type,
#             company_id=get_company_id(),
#             file_path=s3_path,
#             file_name=filename,
#             expiry_date=datetime.strptime(expiry_date, '%Y-%m-%d').date(),
#             description=description
#         )
        
#         db.session.add(attachment)
#         db.session.commit()
        
#         return jsonify({
#             "success": True,
#             "message": "Document uploaded successfully"
#         })
        
#     except Exception as e:
#         db.session.rollback()
#         current_app.logger.error(f"Error uploading attachment: {str(e)}")
#         return jsonify({"success": False, "message": str(e)}), 500


# @bp.route("/customer/<int:customer_id>/attachment/<int:attachment_id>/update", methods=["POST"])
# @login_required
# def update_customer_attachment(customer_id, attachment_id):
#     """Update an existing attachment."""
#     try:
#         customer = Customer.query.get_or_404(customer_id)
#         attachment = CustomerAttachment.query.get_or_404(attachment_id)
        
        
#         # Get form data
#         expiry_date = request.form.get('expiry_date')
#         description = request.form.get('description', '')
        
#         # Update fields
#         if expiry_date:
#             attachment.expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
        
#         attachment.description = description
#         attachment.updated_at = datetime.utcnow()
        
#         # Handle file update if provided
#         if 'file' in request.files:
#             file = request.files['file']
#             if file and file.filename != '':
#                 # Delete old file from S3
#                 try:
#                     s3_client = boto3.client(
#                         's3',
#                         endpoint_url=current_app.config['S3_ENDPOINT_URL'],
#                         aws_access_key_id=current_app.config['AWS_ACCESS_KEY_ID'],
#                         aws_secret_access_key=current_app.config['AWS_SECRET_ACCESS_KEY']
#                     )
                    
#                     s3_client.delete_object(
#                         Bucket=current_app.config['S3_BUCKET_NAME'],
#                         Key=attachment.file_path
#                     )
#                 except Exception as e:
#                     current_app.logger.error(f"Error deleting old file: {str(e)}")
                
#                 # Upload new file
#                 filename = secure_filename(file.filename)
#                 file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
#                 unique_filename = f"{uuid.uuid4()}.{file_extension}"
#                 s3_path = f"customer_attachments/{customer_id}/{unique_filename}"
                
#                 try:
#                     s3_client.upload_fileobj(
#                         file,
#                         current_app.config['S3_BUCKET_NAME'],
#                         s3_path
#                     )
                    
#                     # Update attachment record
#                     attachment.file_path = s3_path
#                     attachment.file_name = filename
                    
#                 except Exception as e:
#                     current_app.logger.error(f"S3 upload error: {str(e)}")
#                     return jsonify({"success": False, "message": "Failed to upload new file"}), 500
        
#         db.session.commit()
        
#         return jsonify({
#             "success": True,
#             "message": "Document updated successfully"
#         })
        
#     except Exception as e:
#         db.session.rollback()
#         current_app.logger.error(f"Error updating attachment: {str(e)}")
#         return jsonify({"success": False, "message": str(e)}), 500


# @bp.route("/customer/<int:customer_id>/attachment/<int:attachment_id>/delete", methods=["POST"])
# @login_required
# def delete_customer_attachment(customer_id, attachment_id):
#     """Delete an attachment (soft delete)."""
#     try:
#         customer = Customer.query.get_or_404(customer_id)
#         attachment = CustomerAttachment.query.get_or_404(attachment_id)
        
        
#         # Soft delete
#         attachment.is_active = False
#         attachment.updated_at = datetime.utcnow()
        
#         db.session.commit()
        
#         return jsonify({
#             "success": True,
#             "message": "Document deleted successfully"
#         })
        
#     except Exception as e:
#         db.session.rollback()
#         current_app.logger.error(f"Error deleting attachment: {str(e)}")
#         return jsonify({"success": False, "message": str(e)}), 500







# Department routes
##################################
@bp.route("/departments")
@login_required
def departments():
    if current_user.is_super_admin == 1:
        departments = Department.query.all()
    else:
        departments = Department.query.filter_by(company_id=get_company_id()).all()
    return render_template(
        "masters/departments.html", title="Departments", departments=departments
    )


@bp.route("/department/new", methods=["GET", "POST"])
@login_required
def new_department():
    form = DepartmentForm()
    if form.validate_on_submit():
        department = Department(
            department_code=form.department_code.data,
            department_name=form.department_name.data,
            is_active=form.is_active.data,
            company_id=get_company_id(),
        )
        db.session.add(department)
        db.session.commit()
        flash("Department has been created!", "success")
        return redirect(url_for("masters.departments"))
    return render_template(
        "masters/department_form.html",
        title="New Department",
        form=form,
        legend="New Department",
    )


@bp.route("/department/<int:department_id>/edit", methods=["GET", "POST"])
@login_required
def edit_department(department_id):
    department = Department.query.get_or_404(department_id)
    if department.company_id != get_company_id():
        flash("You do not have permission to edit this department.", "danger")
        return redirect(url_for("masters.departments"))

    form = DepartmentForm()
    if form.validate_on_submit():
        department.department_code = form.department_code.data
        department.department_name = form.department_name.data
        department.is_active = form.is_active.data
        db.session.commit()
        flash("Department has been updated!", "success")
        return redirect(url_for("masters.departments"))
    elif request.method == "GET":
        form.department_code.data = department.department_code
        form.department_name.data = department.department_name
        form.is_active.data = department.is_active
    return render_template(
        "masters/department_form.html",
        title="Edit Department",
        form=form,
        legend="Edit Department",
    )


@bp.route("/department/<int:department_id>/delete", methods=["POST"])
@login_required
def delete_department(department_id):
    department = Department.query.get_or_404(department_id)
    db.session.delete(department)
    db.session.commit()
    flash("Department has been deleted!", "success")
    return redirect(url_for("masters.departments"))


# ShipmentType routes
###############################
@bp.route("/shipment-types")
@login_required
def shipment_types():
    if current_user.is_super_admin == 1:
        shipment_types = ShipmentType.query.all()
    else:
        shipment_types = ShipmentType.query.filter_by(company_id=get_company_id()).all()
    return render_template(
        "masters/shipment_types.html",
        title="Shipment Types",
        shipment_types=shipment_types,
    )


@bp.route("/shipment-type/new", methods=["GET", "POST"])
@login_required
def new_shipment_type():
    form = ShipmentTypeForm()
    
    # Populate the dropdown with base shipment types
    form.base_type_id.choices = [(0, 'Select Base Type')] + [
        (base_type.id, base_type.base_code) 
        for base_type in ShipmentTypeBase.query.all()
    ]
    
    if form.validate_on_submit():
        print("Form submitted and validated")
        
        # Get the selected base type to use its code as shipment_name
        base_type = ShipmentTypeBase.query.get(form.base_type_id.data)
        if not base_type:
            flash("Invalid base type selected.", "danger")
            return render_template(
                "masters/shipment_type_form.html",
                title="New Shipment Type",
                form=form,
                legend="New Shipment Type",
            )
        
        # Create the ShipmentType instance
        shipment_type = ShipmentType(
            shipment_code=form.shipment_code.data,
            shipment_name=base_type.base_code,  # Use base_code as shipment_name
            is_active=form.is_active.data,
            company_id=get_company_id(),
            base_type_id=form.base_type_id.data,  # Set the base_type_id
            docCode=form.docCode.data,
            lastDocNumber=0,
        )
        db.session.add(shipment_type)
        db.session.flush()  # Needed to get shipment_type.id before committing
        
        print(f"Flushed ShipmentType with ID: {shipment_type.id}, Name: {shipment_type.shipment_name}")
        
        # Define the 4 DocumentStatus entries
        status_entries = [
            DocumentStatus(
                docType=shipment_type.shipment_name,
                docStatusName="Open",
                docLevel=1,
                isActive=1,
                doctypeid=shipment_type.id,
            ),
            DocumentStatus(
                docType=shipment_type.shipment_name,
                docStatusName="New",
                docLevel=1,
                isActive=0,
                doctypeid=shipment_type.id,
            ),
            DocumentStatus(
                docType=shipment_type.shipment_name,
                docStatusName="Ongoing",
                docLevel=1,
                isActive=0,
                doctypeid=shipment_type.id,
            ),
            DocumentStatus(
                docType=shipment_type.shipment_name,
                docStatusName="Completed",
                docLevel=1,
                isActive=3,
                doctypeid=shipment_type.id,
            ),
        ]
        
        for s in status_entries:
            print(f"Prepared DocumentStatus - Name: {s.docStatusName}, isActive: {s.isActive}, doctypeid: {s.doctypeid}")
        
        db.session.add_all(status_entries)
        db.session.commit()

        print("Shipment Type and related DocumentStatus records committed to database.")
        
        flash("Shipment Type and related statuses have been created!", "success")
        return redirect(url_for("masters.shipment_types"))

    print("Rendering shipment type form")
    
    return render_template(
        "masters/shipment_type_form.html",
        title="New Shipment Type",
        form=form,
        legend="New Shipment Type",
    )


@bp.route("/shipment-type/<int:shipment_type_id>/edit", methods=["GET", "POST"])
@login_required
def edit_shipment_type(shipment_type_id):
    shipment_type = ShipmentType.query.get_or_404(shipment_type_id)
    if shipment_type.company_id != get_company_id():
        flash("You don't have permission to edit this shipment type.", "danger")
        return redirect(url_for("masters.shipment_types"))

    form = ShipmentTypeForm()
    
    # Populate the dropdown with base shipment types
    form.base_type_id.choices = [(0, 'Select Base Type')] + [
        (base_type.id, base_type.base_code) 
        for base_type in ShipmentTypeBase.query.all()
    ]
    
    if form.validate_on_submit():
        # Get the selected base type to use its code as shipment_name
        base_type = ShipmentTypeBase.query.get(form.base_type_id.data)
        if not base_type:
            flash("Invalid base type selected.", "danger")
            return render_template(
                "masters/shipment_type_form.html",
                title="Edit Shipment Type",
                form=form,
                legend="Edit Shipment Type",
            )
            
        shipment_type.shipment_code = form.shipment_code.data
        shipment_type.shipment_name = base_type.base_code  # Use base_code as shipment_name
        shipment_type.docCode = form.docCode.data
        shipment_type.is_active = form.is_active.data
        shipment_type.base_type_id = form.base_type_id.data  # Update base_type_id
        db.session.commit()
        flash("Shipment Type has been updated!", "success")
        return redirect(url_for("masters.shipment_types"))
    elif request.method == "GET":
        form.shipment_code.data = shipment_type.shipment_code
        form.base_type_id.data = shipment_type.base_type_id  # Set the dropdown selection
        form.docCode.data = shipment_type.docCode
        form.is_active.data = shipment_type.is_active
        
    return render_template(
        "masters/shipment_type_form.html",
        title="Edit Shipment Type",
        form=form,
        legend="Edit Shipment Type",
    )


@bp.route("/shipment-type/<int:shipment_type_id>/delete", methods=["POST"])
@login_required
def delete_shipment_type(shipment_type_id):
    shipment_type = ShipmentType.query.get_or_404(shipment_type_id)
    
    if shipment_type.company_id != get_company_id():
        flash("You don't have permission to delete this shipment type.", "danger")
        return redirect(url_for("masters.shipment_types"))
    
    # Delete related DocumentStatus entries first
    DocumentStatus.query.filter_by(doctypeid=shipment_type.id).delete()
    
    db.session.delete(shipment_type)
    db.session.commit()

    flash("Shipment Type and related statuses have been deleted!", "success")
    return redirect(url_for("masters.shipment_types"))


@bp.route("/shipment-type/add", methods=["GET", "POST"])
@login_required
def add_shipment_type():
    """Add a new shipment type."""
    form = ShipmentTypeForm()
    
    # Populate the dropdown with base shipment types
    form.base_type_id.choices = [(0, 'Select Base Type')] + [
        (base_type.id, base_type.base_code) 
        for base_type in ShipmentTypeBase.query.all()
    ]

    if form.validate_on_submit():
        print("Form validated. Preparing to create new ShipmentType...")

        # Get the selected base type to use its code as shipment_name
        base_type = ShipmentTypeBase.query.get(form.base_type_id.data)
        if not base_type:
            flash("Invalid base type selected.", "danger")
            return render_template(
                "masters/add_shipment_type.html", 
                form=form, 
                title="Add Shipment Type"
            )

        shipment_type = ShipmentType(
            shipment_code=form.shipment_code.data,
            shipment_name=base_type.base_code,  # Use base_code as shipment_name
            docCode=form.docCode.data,
            lastDocNumber=0,
            is_active=form.is_active.data,
            company_id=get_company_id(),
            base_type_id=form.base_type_id.data,  # Set the base_type_id
        )

        db.session.add(shipment_type)
        db.session.flush()  # Get ID before commit
        print(f"Flushed ShipmentType with ID: {shipment_type.id}, Name: {shipment_type.shipment_name}")

        # Create 4 DocumentStatus records
        status_entries = [
            DocumentStatus(
                docType=shipment_type.shipment_name,
                docStatusName="Open",
                docLevel=1,
                isActive=1,
                doctypeid=shipment_type.id,
            ),
            DocumentStatus(
                docType=shipment_type.shipment_name,
                docStatusName="New",
                docLevel=1,
                isActive=0,
                doctypeid=shipment_type.id,
            ),
            DocumentStatus(
                docType=shipment_type.shipment_name,
                docStatusName="Ongoing",
                docLevel=1,
                isActive=0,
                doctypeid=shipment_type.id,
            ),
            DocumentStatus(
                docType=shipment_type.shipment_name,
                docStatusName="Completed",
                docLevel=1,
                isActive=3,
                doctypeid=shipment_type.id,
            ),
        ]

        for s in status_entries:
            print(
                f"Prepared DocumentStatus: Name={s.docStatusName}, "
                f"isActive={s.isActive}, doctypeid={s.doctypeid}"
            )

        try:
            db.session.add_all(status_entries)
            db.session.commit()
            print("ShipmentType and DocumentStatus records committed successfully.")
            flash("Shipment type and default statuses added successfully!", "success")
        except Exception as e:
            db.session.rollback()
            print(f"Error during commit: {e}")
            flash("Error occurred while adding shipment type and statuses.", "danger")

        return redirect(url_for("masters.shipment_types"))

    print("Rendering Add Shipment Type form")
    return render_template(
        "masters/add_shipment_type.html", form=form, title="Add Shipment Type"
    )

# Routes for AI Check Fields
############################
@bp.route("/ship-cat-document/<int:document_id>/ai-checks", methods=["GET"])
@login_required
def get_ship_cat_document_ai_checks(document_id):
    """
    Retrieve AI check fields for a specific document
    """
    ai_checks = ShipCatDocumentAICheck.query.filter_by(
        ship_cat_document_id=document_id, 
        company_id=get_company_id()
    ).all()

    return jsonify({
        "success": True,
        "ai_checks": [
            {
                "id": check.id,
                "field_name": check.field_name,
                "condition": check.condition  # Keep as condition in the API
            } for check in ai_checks
        ]
    })

@bp.route("/ship-cat-document/ai-checks/save", methods=["POST"])
@login_required
def save_ship_cat_document_ai_checks():
    """
    Save, update, and delete AI check fields for a document
    """
    data = request.get_json()

    try:
        # First, fetch the shipment type ID from the document
        document = ShipCatDocument.query.get_or_404(data['document_id'])
        shipment_type_id = document.shipmentTypeid
        category_id = document.shipCatid

        # Get existing AI checks for this document
        existing_checks = ShipCatDocumentAICheck.query.filter_by(
            ship_cat_document_id=data['document_id'], 
            company_id=get_company_id()
        ).all()

        # Track existing check IDs to identify which should be deleted
        existing_check_ids = {check.id for check in existing_checks}
        received_check_ids = set()
        
        # List to store processed field data for JSON updating
        key_fields_data = []

        # Process incoming AI check fields
        for field in data.get('ai_check_fields', []):
            # Validate condition value (which will be header, body, or footer)
            condition = field.get('condition', '').lower()
            if condition not in ['header', 'body', 'footer']:
                return jsonify({
                    "success": False,
                    "message": f"Invalid condition value: {condition}. Must be 'header', 'body', or 'footer'."
                }), 400
                
            # Add to key_fields_data for JSON storage
            key_fields_data.append({
                "name": field['field_name'],
                "section": condition  # Use condition value as section in JSON
            })
            
            # Check if this is an existing check (has an ID)
            check_id = field.get('id')
            
            if check_id:
                # Update existing check
                check = ShipCatDocumentAICheck.query.get(check_id)
                if check:
                    check.field_name = field['field_name']
                    check.condition = condition  # Keep as condition in the database
                    received_check_ids.add(check_id)
            else:
                # Create new check
                new_check = ShipCatDocumentAICheck(
                    company_id=get_company_id(),
                    shipment_type_id=shipment_type_id,
                    ship_category_id=category_id,
                    ship_cat_document_id=data['document_id'],
                    document_description=document.description,
                    field_name=field['field_name'],
                    condition=condition  # Keep as condition in the database
                )
                db.session.add(new_check)

        # Delete checks that are no longer present
        checks_to_delete = existing_check_ids - received_check_ids
        if checks_to_delete:
            ShipCatDocumentAICheck.query.filter(
                ShipCatDocumentAICheck.id.in_(checks_to_delete),
                ShipCatDocumentAICheck.company_id == get_company_id()
            ).delete(synchronize_session=False)

        # Update the key_fields JSON in the ShipCatDocument
        document.key_fields = json.dumps(key_fields_data)
        
        # Commit all changes
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "AI Check Fields saved successfully",
            "new_fields_added": len(data.get('ai_check_fields', [])),
            "fields_deleted": len(checks_to_delete)
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving AI Check Fields: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500 

# BL Status routes
####################
@bp.route("/bl-statuses")
@login_required
def bl_statuses():
    if current_user.is_super_admin == 1:
        bl_statuses = BLStatus.query.all()
    else:
        bl_statuses = BLStatus.query.filter_by(company_id=get_company_id()).all()
    return render_template(
        "masters/bl_statuses.html",
        title="BL Statuses",
        bl_statuses=bl_statuses,
    )


@bp.route("/bl-status/new", methods=["GET", "POST"])
@login_required
def new_bl_status():
    form = BLStatusForm()
    if form.validate_on_submit():
        bl_status = BLStatus(
            bl_code=form.bl_code.data,
            bl_name=form.bl_name.data,
            is_active=form.is_active.data,
            company_id=get_company_id(),
        )
        db.session.add(bl_status)
        db.session.commit()
        flash("BL Status has been created!", "success")
        return redirect(url_for("masters.bl_statuses"))
    return render_template(
        "masters/bl_status_form.html",
        title="New BL Status",
        form=form,
        legend="New BL Status",
    )


@bp.route("/bl-status/<int:bl_status_id>/edit", methods=["GET", "POST"])
@login_required
def edit_bl_status(bl_status_id):
    bl_status = BLStatus.query.get_or_404(bl_status_id)
    if bl_status.company_id != get_company_id():
        flash("You don't have permission to edit this BL status.", "danger")
        return redirect(url_for("masters.bl_statuses"))

    form = BLStatusForm()
    if form.validate_on_submit():
        bl_status.bl_code = form.bl_code.data
        bl_status.bl_name = form.bl_name.data
        bl_status.is_active = form.is_active.data
        db.session.commit()
        flash("BL Status has been updated!", "success")
        return redirect(url_for("masters.bl_statuses"))
    elif request.method == "GET":
        form.bl_code.data = bl_status.bl_code
        form.bl_name.data = bl_status.bl_name
        form.is_active.data = bl_status.is_active
    return render_template(
        "masters/bl_status_form.html",
        title="Edit BL Status",
        form=form,
        legend="Edit BL Status",
    )


@bp.route("/bl-status/<int:bl_status_id>/delete", methods=["POST"])
@login_required
def delete_bl_status(bl_status_id):
    bl_status = BLStatus.query.get_or_404(bl_status_id)
    if bl_status.company_id != get_company_id():
        flash("You don't have permission to delete this BL status.", "danger")
        return redirect(url_for("masters.bl_statuses"))

    db.session.delete(bl_status)
    db.session.commit()
    flash("BL Status has been deleted!", "success")
    return redirect(url_for("masters.bl_statuses"))


# Freight Term routes
###########################
@bp.route("/freight-terms")
@login_required
def freight_terms():
    if current_user.is_super_admin == 1:
        freight_terms = FreightTerm.query.all()
    else:
        freight_terms = FreightTerm.query.filter_by(company_id=get_company_id()).all()
    return render_template(
        "masters/freight_terms.html",
        title="Freight Terms",
        freight_terms=freight_terms,
    )


@bp.route("/freight-term/new", methods=["GET", "POST"])
@login_required
def new_freight_term():
    form = FreightTermForm()
    if form.validate_on_submit():
        freight_term = FreightTerm(
            freight_code=form.freight_code.data,
            freight_name=form.freight_name.data,
            is_active=form.is_active.data,
            company_id=get_company_id(),
        )
        db.session.add(freight_term)
        db.session.commit()
        flash("Freight Term has been created!", "success")
        return redirect(url_for("masters.freight_terms"))
    return render_template(
        "masters/freight_term_form.html",
        title="New Freight Term",
        form=form,
        legend="New Freight Term",
    )


@bp.route("/freight-term/<int:freight_term_id>/edit", methods=["GET", "POST"])
@login_required
def edit_freight_term(freight_term_id):
    freight_term = FreightTerm.query.get_or_404(freight_term_id)
    if freight_term.company_id != get_company_id():
        flash("You don't have permission to edit this freight term.", "danger")
        return redirect(url_for("masters.freight_terms"))

    form = FreightTermForm()
    if form.validate_on_submit():
        freight_term.freight_code = form.freight_code.data
        freight_term.freight_name = form.freight_name.data
        freight_term.is_active = form.is_active.data
        db.session.commit()
        flash("Freight Term has been updated!", "success")
        return redirect(url_for("masters.freight_terms"))
    elif request.method == "GET":
        form.freight_code.data = freight_term.freight_code
        form.freight_name.data = freight_term.freight_name
        form.is_active.data = freight_term.is_active
    return render_template(
        "masters/freight_term_form.html",
        title="Edit Freight Term",
        form=form,
        legend="Edit Freight Term",
    )


@bp.route("/freight-term/<int:freight_term_id>/delete", methods=["POST"])
@login_required
def delete_freight_term(freight_term_id):
    freight_term = FreightTerm.query.get_or_404(freight_term_id)
    if freight_term.company_id != get_company_id():
        flash("You don't have permission to delete this freight term.", "danger")
        return redirect(url_for("masters.freight_terms"))

    db.session.delete(freight_term)
    db.session.commit()
    flash("Freight Term has been deleted!", "success")
    return redirect(url_for("masters.freight_terms"))


# Request Type routes
############################
@bp.route("/request-types")
@login_required
def request_types():
    if current_user.is_super_admin == 1:
        request_types = RequestType.query.all()
    else:
        request_types = RequestType.query.filter_by(company_id=get_company_id()).all()
    return render_template(
        "masters/request_types.html",
        title="Request Types",
        request_types=request_types,
    )


@bp.route("/request-type/new", methods=["GET", "POST"])
@login_required
def new_request_type():
    form = RequestTypeForm()
    if form.validate_on_submit():
        request_type = RequestType(
            name=form.name.data,
            is_active=form.is_active.data,
            company_id=get_company_id(),
        )
        db.session.add(request_type)
        db.session.commit()
        flash("Request Type has been created!", "success")
        return redirect(url_for("masters.request_types"))
    return render_template(
        "masters/request_type_form.html",
        title="New Request Type",
        form=form,
        legend="New Request Type",
    )


@bp.route("/request-type/<int:request_type_id>/edit", methods=["GET", "POST"])
@login_required
def edit_request_type(request_type_id):
    request_type = RequestType.query.get_or_404(request_type_id)
    if request_type.company_id != get_company_id():
        flash("You don't have permission to edit this request type.", "danger")
        return redirect(url_for("masters.request_types"))

    form = RequestTypeForm()
    if form.validate_on_submit():
        request_type.name = form.name.data
        request_type.is_active = form.is_active.data
        db.session.commit()
        flash("Request Type has been updated!", "success")
        return redirect(url_for("masters.request_types"))
    elif request.method == "GET":
        form.name.data = request_type.name
        form.is_active.data = request_type.is_active
    return render_template(
        "masters/request_type_form.html",
        title="Edit Request Type",
        form=form,
        legend="Edit Request Type",
    )


@bp.route("/request-type/<int:request_type_id>/delete", methods=["POST"])
@login_required
def delete_request_type(request_type_id):
    request_type = RequestType.query.get_or_404(request_type_id)
    if request_type.company_id != get_company_id():
        flash("You don't have permission to delete this request type.", "danger")
        return redirect(url_for("masters.request_types"))

    db.session.delete(request_type)
    db.session.commit()
    flash("Request Type has been deleted!", "success")
    return redirect(url_for("masters.request_types"))


# Document Type routes
##########################
@bp.route("/document-types")
@login_required
def document_types():
    if current_user.is_super_admin == 1:
        document_types = DocumentType.query.all()
    else:
        document_types = DocumentType.query.filter_by(company_id=get_company_id()).all()
    return render_template(
        "masters/document_types.html",
        title="Document Types",
        document_types=document_types,
    )


@bp.route("/document-type/new", methods=["GET", "POST"])
@login_required
def new_document_type():
    form = DocumentTypeForm()
    if form.validate_on_submit():
        document_type = DocumentType(
            name=form.name.data,
            is_active=form.is_active.data,
            company_id=get_company_id(),
        )
        db.session.add(document_type)
        db.session.commit()
        flash("Document Type has been created!", "success")
        return redirect(url_for("masters.document_types"))
    return render_template(
        "masters/document_type_form.html",
        title="New Document Type",
        form=form,
        legend="New Document Type",
    )


@bp.route("/document-type/<int:document_type_id>/edit", methods=["GET", "POST"])
@login_required
def edit_document_type(document_type_id):
    document_type = DocumentType.query.get_or_404(document_type_id)
    if document_type.company_id != get_company_id():
        flash("You don't have permission to edit this document type.", "danger")
        return redirect(url_for("masters.document_types"))

    form = DocumentTypeForm()
    if form.validate_on_submit():
        document_type.name = form.name.data
        document_type.is_active = form.is_active.data
        db.session.commit()
        flash("Document Type has been updated!", "success")
        return redirect(url_for("masters.document_types"))
    elif request.method == "GET":
        form.name.data = document_type.name
        form.is_active.data = document_type.is_active
    return render_template(
        "masters/document_type_form.html",
        title="Edit Document Type",
        form=form,
        legend="Edit Document Type",
    )


@bp.route("/document-type/<int:document_type_id>/delete", methods=["POST"])
@login_required
def delete_document_type(document_type_id):
    document_type = DocumentType.query.get_or_404(document_type_id)
    if document_type.company_id != get_company_id():
        flash("You don't have permission to delete this document type.", "danger")
        return redirect(url_for("masters.document_types"))

    db.session.delete(document_type)
    db.session.commit()
    flash("Document Type has been deleted!", "success")
    return redirect(url_for("masters.document_types"))


# Shipping Line routes
#########################3
@bp.route("/shipping-lines")
@login_required
def shipping_lines():
    if current_user.is_super_admin == 1:
        shipping_lines = ShippingLine.query.all()
    else:
        shipping_lines = ShippingLine.query.filter_by(company_id=get_company_id()).all()
    return render_template(
        "masters/shipping_lines.html",
        title="Shipping Lines",
        shipping_lines=shipping_lines,
    )


@bp.route("/shipping-line/new", methods=["GET", "POST"])
@login_required
def new_shipping_line():
    form = ShippingLineForm()
    if form.validate_on_submit():
        shipping_line = ShippingLine(
            shipping_line_id=form.shipping_line_id.data,
            name=form.name.data,
            address=form.address.data,
            contact_no=form.contact_no.data,
            email=form.email.data,
            is_active=form.is_active.data,
            company_id=get_company_id(),
        )
        db.session.add(shipping_line)
        db.session.commit()
        flash("Shipping Line has been created!", "success")
        return redirect(url_for("masters.shipping_lines"))
    return render_template(
        "masters/shipping_line_form.html",
        title="New Shipping Line",
        form=form,
        legend="New Shipping Line",
    )


@bp.route("/shipping-line/<int:shipping_line_id>/edit", methods=["GET", "POST"])
@login_required
def edit_shipping_line(shipping_line_id):
    shipping_line = ShippingLine.query.get_or_404(shipping_line_id)
    if shipping_line.company_id != get_company_id():
        flash("You don't have permission to edit this shipping line.", "danger")
        return redirect(url_for("masters.shipping_lines"))

    form = ShippingLineForm()
    if form.validate_on_submit():
        shipping_line.shipping_line_id = form.shipping_line_id.data
        shipping_line.name = form.name.data
        shipping_line.address = form.address.data
        shipping_line.contact_no = form.contact_no.data
        shipping_line.email = form.email.data
        shipping_line.is_active = form.is_active.data
        db.session.commit()
        flash("Shipping Line has been updated!", "success")
        return redirect(url_for("masters.shipping_lines"))
    elif request.method == "GET":
        form.shipping_line_id.data = shipping_line.shipping_line_id
        form.name.data = shipping_line.name
        form.address.data = shipping_line.address
        form.contact_no.data = shipping_line.contact_no
        form.email.data = shipping_line.email
        form.is_active.data = shipping_line.is_active
    return render_template(
        "masters/shipping_line_form.html",
        title="Edit Shipping Line",
        form=form,
        legend="Edit Shipping Line",
    )


@bp.route("/shipping-line/<int:shipping_line_id>/delete", methods=["POST"])
@login_required
def delete_shipping_line(shipping_line_id):
    shipping_line = ShippingLine.query.get_or_404(shipping_line_id)
    if shipping_line.company_id != get_company_id():
        flash("You don't have permission to delete this shipping line.", "danger")
        return redirect(url_for("masters.shipping_lines"))

    db.session.delete(shipping_line)
    db.session.commit()
    flash("Shipping Line has been deleted!", "success")
    return redirect(url_for("masters.shipping_lines"))


# Country routes
######################3
@bp.route("/countries")
@login_required
def countries():
    countries = CountryMaster.query.all()
    return render_template(
        "masters/countries.html",
        title="Countries",
        countries=countries,
    )


@bp.route("/country/new", methods=["GET", "POST"])
@login_required
def new_country():
    form = CountryForm()
    if form.validate_on_submit():
        country = CountryMaster(
            countryCode=form.countryCode.data,
            alpha2Code=form.alpha2Code.data,
            countryName=form.countryName.data,
            nationality=form.nationality.data,
            regionID=int(form.regionID.data) if form.regionID.data else None,
            isLocal=1 if form.isLocal.data else 0,
            countryFlag=form.countryFlag.data,
            currency_code=form.currency_code.data,
            currency_name=form.currency_name.data,
            company_id=get_company_id(),
        )
        db.session.add(country)
        db.session.commit()
        flash("Country has been created!", "success")
        return redirect(url_for("masters.countries"))
    return render_template(
        "masters/country_form.html",
        title="New Country",
        form=form,
        legend="New Country",
    )


@bp.route("/country/<int:country_id>/edit", methods=["GET", "POST"])
@login_required
def edit_country(country_id):
    country = CountryMaster.query.get_or_404(country_id)
    if country.company_id != get_company_id():
        flash("You don't have permission to edit this country.", "danger")
        return redirect(url_for("masters.countries"))

    form = CountryForm()
    if form.validate_on_submit():
        country.countryCode = form.countryCode.data
        country.alpha2Code = form.alpha2Code.data
        country.countryName = form.countryName.data
        country.nationality = form.nationality.data
        country.regionID = int(form.regionID.data) if form.regionID.data else None
        country.isLocal = 1 if form.isLocal.data else 0
        country.countryFlag = form.countryFlag.data
        country.currency_code = form.currency_code.data
        country.currency_name = form.currency_name.data
        db.session.commit()
        flash("Country has been updated!", "success")
        return redirect(url_for("masters.countries"))
    elif request.method == "GET":
        form.countryCode.data = country.countryCode
        form.alpha2Code.data = country.alpha2Code
        form.countryName.data = country.countryName
        form.nationality.data = country.nationality
        form.regionID.data = str(country.regionID) if country.regionID else ""
        form.isLocal.data = bool(country.isLocal)
        form.countryFlag.data = country.countryFlag
        form.currency_code.data = country.currency_code
        form.currency_name.data = country.currency_name
    return render_template(
        "masters/country_form.html",
        title="Edit Country",
        form=form,
        legend="Edit Country",
    )


@bp.route("/country/<int:country_id>/delete", methods=["POST"])
@login_required
def delete_country(country_id):
    country = CountryMaster.query.get_or_404(country_id)
    if country.company_id != get_company_id():
        flash("You don't have permission to delete this country.", "danger")
        return redirect(url_for("masters.countries"))

    db.session.delete(country)
    db.session.commit()
    flash("Country has been deleted!", "success")
    return redirect(url_for("masters.countries"))


# Currency routes
#################3
@bp.route("/currencies")
@login_required
def currencies():
    currencies = CurrencyMaster.query.all()
    return render_template(
        "masters/currencies.html", title="Currencies", currencies=currencies
    )


@bp.route("/currency/new", methods=["GET", "POST"])
@login_required
def new_currency():
    form = CurrencyForm()
    if form.validate_on_submit():
        currency = CurrencyMaster(name=form.name.data, company_id=get_company_id())
        db.session.add(currency)
        db.session.commit()
        flash("Currency has been created!", "success")
        return redirect(url_for("masters.currencies"))
    return render_template(
        "masters/currency_form.html", title="New Currency", form=form
    )


@bp.route("/currency/<int:currency_id>/edit", methods=["GET", "POST"])
@login_required
def edit_currency(currency_id):
    currency = CurrencyMaster.query.get_or_404(currency_id)
    if currency.company_id != get_company_id():
        flash("You do not have permission to edit this currency.", "danger")
        return redirect(url_for("masters.currencies"))

    form = CurrencyForm()
    if form.validate_on_submit():
        currency.name = form.name.data
        db.session.commit()
        flash("Currency has been updated!", "success")
        return redirect(url_for("masters.currencies"))
    elif request.method == "GET":
        form.name.data = currency.name
    return render_template(
        "masters/currency_form.html", title="Edit Currency", form=form
    )


# Terminal routes
#####################33
@bp.route("/terminals")
@login_required
def terminals():
    if current_user.is_super_admin == 1:
        terminals = Terminal.query.all()
    else:
        terminals = Terminal.query.filter_by(company_id=get_company_id()).all()
    return render_template(
        "masters/terminals.html", title="Terminals", terminals=terminals
    )


@bp.route("/terminal/new", methods=["GET", "POST"])
@login_required
def new_terminal():
    form = TerminalForm()
    if form.validate_on_submit():
        terminal = Terminal(
            terminal_id=form.terminal_id.data,
            name=form.name.data,
            address=form.address.data,
            contact_no=form.contact_no.data,
            email=form.email.data,
            is_active=form.is_active.data,
            company_id=get_company_id(),
        )
        db.session.add(terminal)
        db.session.commit()
        flash("Terminal has been created!", "success")
        return redirect(url_for("masters.terminals"))
    return render_template(
        "masters/terminal_form.html",
        title="New Terminal",
        form=form,
        legend="New Terminal",
    )


@bp.route("/terminal/<int:terminal_id>/edit", methods=["GET", "POST"])
@login_required
def edit_terminal(terminal_id):
    terminal = Terminal.query.get_or_404(terminal_id)
    if terminal.company_id != get_company_id():
        flash("You don't have permission to edit this terminal.", "danger")
        return redirect(url_for("masters.terminals"))

    form = TerminalForm()
    if form.validate_on_submit():
        terminal.terminal_id = form.terminal_id.data
        terminal.name = form.name.data
        terminal.address = form.address.data
        terminal.contact_no = form.contact_no.data
        terminal.email = form.email.data
        terminal.is_active = form.is_active.data
        db.session.commit()
        flash("Terminal has been updated!", "success")
        return redirect(url_for("masters.terminals"))
    elif request.method == "GET":
        form.terminal_id.data = terminal.terminal_id
        form.name.data = terminal.name
        form.address.data = terminal.address
        form.contact_no.data = terminal.contact_no
        form.email.data = terminal.email
        form.is_active.data = terminal.is_active
    return render_template(
        "masters/terminal_form.html",
        title="Edit Terminal",
        form=form,
        legend="Edit Terminal",
    )


@bp.route("/terminal/<int:terminal_id>/delete", methods=["POST"])
@login_required
def delete_terminal(terminal_id):
    terminal = Terminal.query.get_or_404(terminal_id)
    if terminal.company_id != get_company_id():
        flash("You don't have permission to delete this terminal.", "danger")
        return redirect(url_for("masters.terminals"))

    db.session.delete(terminal)
    db.session.commit()
    flash("Terminal has been deleted!", "success")
    return redirect(url_for("masters.terminals"))


# Runner routes
###############################
@bp.route("/runners")
@login_required
def runners():
    if current_user.is_super_admin == 1:
        runners = Runner.query.all()
    else:
        runners = Runner.query.filter_by(company_id=get_company_id()).all()
    return render_template(
        "masters/runners.html", title="Runners Profile", runners=runners
    )


@bp.route("/runner/new", methods=["GET", "POST"])
@login_required
def new_runner():
    form = RunnerForm()
    if form.validate_on_submit():
        # Handle profile image upload
        profile_image = "default.jpg"
        if form.profile_image.data:
            profile_image = save_profile_picture(form.profile_image.data)

        # Convert string dates to datetime.date objects
        date_of_birth = datetime.strptime(form.date_of_birth.data, "%Y-%m-%d").date()
        driving_license_expiry = datetime.strptime(
            form.driving_license_expiry.data, "%Y-%m-%d"
        ).date()
        insurance_expiry = (
            datetime.strptime(form.insurance_expiry.data, "%Y-%m-%d").date()
            if form.insurance_expiry.data
            else None
        )
        medical_insurance_expiry = (
            datetime.strptime(form.medical_insurance_expiry.data, "%Y-%m-%d").date()
            if form.medical_insurance_expiry.data
            else None
        )

        runner = Runner(
            runner_id=form.runner_id.data,
            profile_image=profile_image,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            nic_no=form.nic_no.data,
            email=form.email.data,
            mobile=form.mobile.data,
            date_of_birth=date_of_birth,
            driving_license_no=form.driving_license_no.data,
            driving_license_expiry=driving_license_expiry,
            assigned_area=form.assigned_area.data,
            is_active=form.is_active.data,
            registration_no=form.registration_no.data,
            vehicle_type=form.vehicle_type.data,
            vehicle_model=form.vehicle_model.data,
            vehicle_color=form.vehicle_color.data,
            engine_no=form.engine_no.data,
            chassis_no=form.chassis_no.data,
            insurance_no=form.insurance_no.data,
            insurance_company=form.insurance_company.data,
            insurance_expiry=insurance_expiry,
            blood_group=form.blood_group.data,
            allergies=form.allergies.data,
            medical_insurance=form.medical_insurance.data,
            medical_insurance_company=form.medical_insurance_company.data,
            medical_insurance_no=form.medical_insurance_no.data,
            medical_insurance_expiry=medical_insurance_expiry,
            emergency_contact_name=form.emergency_contact_name.data,
            emergency_contact_relationship=form.emergency_contact_relationship.data,
            emergency_contact_telephone=form.emergency_contact_telephone.data,
            emergency_contact_mobile=form.emergency_contact_mobile.data,
            company_id=get_company_id(),
        )
        db.session.add(runner)
        db.session.commit()
        flash("Runner has been created!", "success")
        return redirect(url_for("masters.runners"))
    return render_template("masters/runner_form.html", title="New Runner", form=form)


@bp.route("/runner/<int:runner_id>/edit", methods=["GET", "POST"])
@login_required
def edit_runner(runner_id):
    runner = Runner.query.get_or_404(runner_id)
    if runner.company_id != get_company_id():
        flash("You do not have permission to edit this runner.", "danger")
        return redirect(url_for("masters.runners"))

    form = RunnerForm()
    if form.validate_on_submit():
        # Handle profile image upload
        if form.profile_image.data:
            profile_image = save_profile_picture(form.profile_image.data)
            # Delete old profile picture if it's not the default
            if runner.profile_image != "default.jpg":
                delete_profile_picture(runner.profile_image)
            runner.profile_image = profile_image

        # Convert string dates to datetime.date objects
        runner.date_of_birth = datetime.strptime(
            form.date_of_birth.data, "%Y-%m-%d"
        ).date()
        runner.driving_license_expiry = datetime.strptime(
            form.driving_license_expiry.data, "%Y-%m-%d"
        ).date()
        runner.insurance_expiry = (
            datetime.strptime(form.insurance_expiry.data, "%Y-%m-%d").date()
            if form.insurance_expiry.data
            else None
        )
        runner.medical_insurance_expiry = (
            datetime.strptime(form.medical_insurance_expiry.data, "%Y-%m-%d").date()
            if form.medical_insurance_expiry.data
            else None
        )

        runner.runner_id = form.runner_id.data
        runner.first_name = form.first_name.data
        runner.last_name = form.last_name.data
        runner.nic_no = form.nic_no.data
        runner.email = form.email.data
        runner.mobile = form.mobile.data
        runner.driving_license_no = form.driving_license_no.data
        runner.assigned_area = form.assigned_area.data
        runner.is_active = form.is_active.data
        runner.registration_no = form.registration_no.data
        runner.vehicle_type = form.vehicle_type.data
        runner.vehicle_model = form.vehicle_model.data
        runner.vehicle_color = form.vehicle_color.data
        runner.engine_no = form.engine_no.data
        runner.chassis_no = form.chassis_no.data
        runner.insurance_no = form.insurance_no.data
        runner.insurance_company = form.insurance_company.data
        runner.blood_group = form.blood_group.data
        runner.allergies = form.allergies.data
        runner.medical_insurance = form.medical_insurance.data
        runner.medical_insurance_company = form.medical_insurance_company.data
        runner.medical_insurance_no = form.medical_insurance_no.data
        runner.emergency_contact_name = form.emergency_contact_name.data
        runner.emergency_contact_relationship = form.emergency_contact_relationship.data
        runner.emergency_contact_telephone = form.emergency_contact_telephone.data
        runner.emergency_contact_mobile = form.emergency_contact_mobile.data

        db.session.commit()
        flash("Runner has been updated!", "success")
        return redirect(url_for("masters.runners"))
    elif request.method == "GET":
        # Convert string dates to datetime objects if needed before populating form
        if isinstance(runner.date_of_birth, str) and runner.date_of_birth:
            runner.date_of_birth = datetime.strptime(
                runner.date_of_birth, "%Y-%m-%d"
            ).date()

        if (
            isinstance(runner.driving_license_expiry, str)
            and runner.driving_license_expiry
        ):
            runner.driving_license_expiry = datetime.strptime(
                runner.driving_license_expiry, "%Y-%m-%d"
            ).date()

        if isinstance(runner.insurance_expiry, str) and runner.insurance_expiry:
            runner.insurance_expiry = datetime.strptime(
                runner.insurance_expiry, "%Y-%m-%d"
            ).date()

        if (
            isinstance(runner.medical_insurance_expiry, str)
            and runner.medical_insurance_expiry
        ):
            runner.medical_insurance_expiry = datetime.strptime(
                runner.medical_insurance_expiry, "%Y-%m-%d"
            ).date()

        form.runner_id.data = runner.runner_id
        form.first_name.data = runner.first_name
        form.last_name.data = runner.last_name
        form.nic_no.data = runner.nic_no
        form.email.data = runner.email
        form.mobile.data = runner.mobile
        form.date_of_birth.data = (
            runner.date_of_birth.strftime("%Y-%m-%d") if runner.date_of_birth else ""
        )
        form.driving_license_no.data = runner.driving_license_no
        form.driving_license_expiry.data = (
            runner.driving_license_expiry.strftime("%Y-%m-%d")
            if runner.driving_license_expiry
            else ""
        )
        form.assigned_area.data = runner.assigned_area
        form.is_active.data = runner.is_active
        form.registration_no.data = runner.registration_no
        form.vehicle_type.data = runner.vehicle_type
        form.vehicle_model.data = runner.vehicle_model
        form.vehicle_color.data = runner.vehicle_color
        form.engine_no.data = runner.engine_no
        form.chassis_no.data = runner.chassis_no
        form.insurance_no.data = runner.insurance_no
        form.insurance_company.data = runner.insurance_company
        form.insurance_expiry.data = (
            runner.insurance_expiry.strftime("%Y-%m-%d")
            if runner.insurance_expiry
            else ""
        )
        form.blood_group.data = runner.blood_group
        form.allergies.data = runner.allergies
        form.medical_insurance.data = runner.medical_insurance
        form.medical_insurance_company.data = runner.medical_insurance_company
        form.medical_insurance_no.data = runner.medical_insurance_no
        form.medical_insurance_expiry.data = (
            runner.medical_insurance_expiry.strftime("%Y-%m-%d")
            if runner.medical_insurance_expiry
            else ""
        )
        form.emergency_contact_name.data = runner.emergency_contact_name
        form.emergency_contact_relationship.data = runner.emergency_contact_relationship
        form.emergency_contact_telephone.data = runner.emergency_contact_telephone
        form.emergency_contact_mobile.data = runner.emergency_contact_mobile

    return render_template(
        "masters/runner_form.html", title="Edit Runner", form=form, runner=runner
    )


@bp.route("/runner/<int:runner_id>/view")
@login_required
def view_runner(runner_id):
    runner = Runner.query.get_or_404(runner_id)
    if runner.company_id != get_company_id():
        flash("You do not have permission to view this runner.", "danger")
        return redirect(url_for("masters.runners"))

    try:
        # Convert string dates to datetime objects if needed
        if runner.date_of_birth:
            if isinstance(runner.date_of_birth, str):
                runner.date_of_birth = datetime.strptime(
                    runner.date_of_birth, "%Y-%m-%d"
                ).date()

        if runner.driving_license_expiry:
            if isinstance(runner.driving_license_expiry, str):
                runner.driving_license_expiry = datetime.strptime(
                    runner.driving_license_expiry, "%Y-%m-%d"
                ).date()

        if runner.insurance_expiry:
            if isinstance(runner.insurance_expiry, str):
                runner.insurance_expiry = datetime.strptime(
                    runner.insurance_expiry, "%Y-%m-%d"
                ).date()

        if runner.medical_insurance_expiry:
            if isinstance(runner.medical_insurance_expiry, str):
                runner.medical_insurance_expiry = datetime.strptime(
                    runner.medical_insurance_expiry, "%Y-%m-%d"
                ).date()
    except (ValueError, TypeError):
        # If any date conversion fails, set it to None
        if isinstance(runner.date_of_birth, str):
            runner.date_of_birth = None
        if isinstance(runner.driving_license_expiry, str):
            runner.driving_license_expiry = None
        if isinstance(runner.insurance_expiry, str):
            runner.insurance_expiry = None
        if isinstance(runner.medical_insurance_expiry, str):
            runner.medical_insurance_expiry = None

    return render_template(
        "masters/runner_view.html", title="View Runner", runner=runner
    )


@bp.route("/runner/<int:runner_id>/delete", methods=["POST"])
@login_required
def delete_runner(runner_id):
    runner = Runner.query.get_or_404(runner_id)
    if runner.company_id != get_company_id():
        flash("You do not have permission to delete this runner.", "danger")
        return redirect(url_for("masters.runners"))
    db.session.delete(runner)
    db.session.commit()
    flash("Runner has been deleted!", "success")
    return redirect(url_for("masters.runners"))


@bp.route("/runner/<int:runner_id>/create-login", methods=["POST"])
@login_required
def create_runner_login(runner_id):
    try:
        print("\n=== Starting Login Creation Process ===")
        print(f"Attempting to create login for runner ID: {runner_id}")

        # Get runner
        runner = Runner.query.get_or_404(runner_id)
        print(f"Found runner: {runner.first_name} {runner.last_name}")
        print(f"Runner email: {runner.email}")
        print(f"Runner company_id: {runner.company_id}")
        print(f"Current user company_id: {get_company_id()}")
        print(f"Current user: {current_user.username}")

        # Check if user has permission
        if runner.company_id != get_company_id():
            print(
                f"Permission denied. Runner company_id: {runner.company_id}, User company_id: {get_company_id()}"
            )
            return (
                jsonify(
                    {
                        "error": "You don't have permission to create login for this runner"
                    }
                ),
                403,
            )

        # Check if runner already has a login
        if runner.user_id:
            print(f"Runner already has a user_id: {runner.user_id}")
            return jsonify({"error": "Runner already has a login"}), 400

        # Check if email is already in use
        existing_user = User.query.filter_by(email=runner.email).first()
        if existing_user:
            print(
                f"Email {runner.email} is already in use by user ID: {existing_user.id}"
            )
            return jsonify({"error": "Email address is already in use"}), 400

        # Create new user
        user = User(
            name=f"{runner.first_name} {runner.last_name}",
            email=runner.email,
            contact_number=runner.mobile,
            username=runner.email,
            company_id=runner.company_id,
            is_active=True,
            is_super_admin=False,
        )

        # Set password and verify it works
        try:
            print("\n=== Setting Password ===")
            user.set_password("welcome1")
            print("Password set successfully")
            # Verify password was set correctly
            if not user.check_password("welcome1"):
                raise Exception("Password verification failed after setting")
            print("Password verification successful")
        except Exception as e:
            print(f"Error setting password: {str(e)}")
            print(f"Password hash: {user.password_hash}")
            raise

        # Save user and update runner
        try:
            print("\n=== Saving to Database ===")
            db.session.add(user)
            db.session.flush()  # This will assign an ID to the user
            print(f"Created user with ID: {user.id}")

            runner.user_id = user.id
            db.session.commit()
            print("Successfully committed changes to database")
            return jsonify({"message": "Login created successfully"}), 200
        except Exception as e:
            print(f"Database error: {str(e)}")
            print("Rolling back transaction...")
            db.session.rollback()
            raise

    except Exception as e:
        print("\n=== Error Creating Login ===")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        import traceback

        print("\nFull traceback:")
        print(traceback.format_exc())
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


#Wharf Profile
##################################
@bp.route("/wharf_profiles")
@login_required
def wharf_profiles():
    page = request.args.get("page", 1, type=int)
    if current_user.is_super_admin == 1:
        wharf_profiles = WharfProfile.query.order_by(
            WharfProfile.created_at.desc()
        ).paginate(page=page, per_page=10)
    else:
        wharf_profiles = (
            WharfProfile.query.filter_by(company_id=current_user.company_id)
            .order_by(WharfProfile.created_at.desc())
            .paginate(page=page, per_page=10)
        )
    return render_template(
        "masters/wharf_profiles.html",
        title="Wharf Profiles",
        wharf_profiles=wharf_profiles,
    )


@bp.route("/wharf_profile/new", methods=["GET", "POST"])
@login_required
def new_wharf_profile():
    print("=== Starting new_wharf_profile function ===")
    form = WharfProfileForm()
    print(f"Request method: {request.method}")

    if form.validate_on_submit():
        print("Form validated successfully")
        try:
            # Generate wharf ID
            # wharf_id = generate_wharf_id()
            # print(f"Generated wharf_id: {wharf_id}")

            # Create new wharf profile
            print("Creating new wharf profile with data:")
            print(f"first_name: {form.first_name.data}")
            print(f"last_name: {form.last_name.data}")
            print(f"nic_no: {form.nic_no.data}")
            print(f"contact_number: {form.contact_number.data}")
            print(f"email: {form.email.data}")
            print(f"status: {form.status.data}")
            print(f"company_id: {current_user.company_id}")
            
            wharf_profile = WharfProfile(
                wharf_id=form.wharf_id.data,
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                nic_no=form.nic_no.data,
                contact_number=form.contact_number.data,
                email=form.email.data,
                address=form.address.data,
                company_id=current_user.company_id,
                status=form.status.data,
            )

            # Set date fields
            print("Processing date fields:")
            if form.date_of_birth.data:
                print(f"date_of_birth raw data: {form.date_of_birth.data}")
                wharf_profile.date_of_birth = datetime.strptime(
                    form.date_of_birth.data, "%Y-%m-%d"
                ).date()
                print(f"Parsed date_of_birth: {wharf_profile.date_of_birth}")
            else:
                print("No date_of_birth provided")
                
            if form.driving_license_expiry.data:
                print(f"driving_license_expiry raw data: {form.driving_license_expiry.data}")
                wharf_profile.driving_license_expiry = datetime.strptime(
                    form.driving_license_expiry.data, "%Y-%m-%d"
                ).date()
                print(f"Parsed driving_license_expiry: {wharf_profile.driving_license_expiry}")
            else:
                print("No driving_license_expiry provided")
                
            if form.insurance_expiry.data:
                print(f"insurance_expiry raw data: {form.insurance_expiry.data}")
                wharf_profile.insurance_expiry = datetime.strptime(
                    form.insurance_expiry.data, "%Y-%m-%d"
                ).date()
                print(f"Parsed insurance_expiry: {wharf_profile.insurance_expiry}")
            else:
                print("No insurance_expiry provided")
                
            if form.medical_insurance_expiry.data:
                print(f"medical_insurance_expiry raw data: {form.medical_insurance_expiry.data}")
                wharf_profile.medical_insurance_expiry = datetime.strptime(
                    form.medical_insurance_expiry.data, "%Y-%m-%d"
                ).date()
                print(f"Parsed medical_insurance_expiry: {wharf_profile.medical_insurance_expiry}")
            else:
                print("No medical_insurance_expiry provided")

            # Set vehicle information
            print("Setting vehicle information:")
            print(f"driving_license_number: {form.driving_license_number.data}")
            print(f"registration_no: {form.registration_no.data}")
            print(f"vehicle_type: {form.vehicle_type.data}")
            print(f"vehicle_model: {form.vehicle_model.data}")
            
            wharf_profile.driving_license_number = form.driving_license_number.data
            wharf_profile.registration_no = form.registration_no.data
            wharf_profile.vehicle_type = form.vehicle_type.data
            wharf_profile.vehicle_model = form.vehicle_model.data
            wharf_profile.vehicle_color = form.vehicle_color.data
            wharf_profile.engine_no = form.engine_no.data
            wharf_profile.chassis_no = form.chassis_no.data

            # Set insurance information
            print("Setting insurance information:")
            print(f"insurance_number: {form.insurance_number.data}")
            print(f"insurance_company: {form.insurance_company.data}")
            print(f"medical_insurance_number: {form.medical_insurance_number.data}")
            
            wharf_profile.insurance_number = form.insurance_number.data
            wharf_profile.insurance_company = form.insurance_company.data
            wharf_profile.medical_insurance_number = form.medical_insurance_number.data

            # Handle profile image
            if form.profile_image.data:
                print("Profile image provided, processing...")
                try:
                    # Generate filename
                    random_hex = secrets.token_hex(8)
                    _, f_ext = os.path.splitext(form.profile_image.data.filename)
                    picture_fn = random_hex + f_ext
                    print(f"Generated filename: {picture_fn}")
                    
                    s3_key = f"{current_app.config['S3_BASE_FOLDER']}/profile_pics/{picture_fn}"
                    print(f"S3 key: {s3_key}")

                    # Resize image
                    print("Resizing image...")
                    output_size = (400, 400)
                    i = Image.open(form.profile_image.data)
                    i.thumbnail(output_size)

                    # Save to temp file
                    temp_path = os.path.join(
                        current_app.root_path, "static", "temp", picture_fn
                    )
                    print(f"Temp path: {temp_path}")
                    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                    i.save(temp_path)
                    print("Image saved to temp location")

                    # Upload to S3
                    print("Uploading to S3...")
                    with open(temp_path, "rb") as f:
                        upload_file_to_s3(
                            f, current_app.config["S3_BUCKET_NAME"], s3_key
                        )
                    print("Upload to S3 successful")

                    # Clean up temp file
                    os.remove(temp_path)
                    print("Temp file removed")

                    # Set profile image path
                    wharf_profile.profile_image = s3_key
                    print(f"Profile image path set: {s3_key}")
                except Exception as e:
                    print(f"Error handling profile image: {str(e)}")
                    print(f"Exception type: {type(e).__name__}")
                    print(f"Exception traceback: {traceback.format_exc()}")
                    flash("Error uploading profile image. Please try again.", "danger")
                    return redirect(url_for("masters.new_wharf_profile"))
            else:
                print("No profile image provided, using default")
                wharf_profile.profile_image = "default.jpg"

            # Handle NIC document
            if form.nic_document.data:
                print("NIC document provided, processing...")
                try:
                    # Generate filename
                    random_hex = secrets.token_hex(8)
                    _, f_ext = os.path.splitext(form.nic_document.data.filename)
                    document_fn = random_hex + f_ext
                    print(f"Generated filename: {document_fn}")
                    
                    s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/nic/{document_fn}"
                    print(f"S3 key: {s3_key}")

                    # Upload to S3
                    print("Uploading to S3...")
                    upload_file_to_s3(
                        form.nic_document.data,
                        current_app.config["S3_BUCKET_NAME"],
                        s3_key,
                    )
                    print("Upload to S3 successful")

                    # Set document path
                    wharf_profile.nic_document = s3_key
                    print(f"NIC document path set: {s3_key}")
                except Exception as e:
                    print(f"Error handling NIC document: {str(e)}")
                    print(f"Exception type: {type(e).__name__}")
                    print(f"Exception traceback: {traceback.format_exc()}")
                    flash("Error uploading NIC document. Please try again.", "danger")
                    return redirect(url_for("masters.new_wharf_profile"))
            else:
                print("No NIC document provided")

            # Handle insurance document
            if form.insurance_document.data:
                print("Insurance document provided, processing...")
                try:
                    # Generate filename
                    random_hex = secrets.token_hex(8)
                    _, f_ext = os.path.splitext(form.insurance_document.data.filename)
                    document_fn = random_hex + f_ext
                    print(f"Generated filename: {document_fn}")
                    
                    s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/insurance/{document_fn}"
                    print(f"S3 key: {s3_key}")

                    # Upload to S3
                    print("Uploading to S3...")
                    upload_file_to_s3(
                        form.insurance_document.data,
                        current_app.config["S3_BUCKET_NAME"],
                        s3_key,
                    )
                    print("Upload to S3 successful")

                    # Set document path
                    wharf_profile.insurance_document = s3_key
                    print(f"Insurance document path set: {s3_key}")
                except Exception as e:
                    print(f"Error handling insurance document: {str(e)}")
                    print(f"Exception type: {type(e).__name__}")
                    print(f"Exception traceback: {traceback.format_exc()}")
                    flash(
                        "Error uploading insurance document. Please try again.",
                        "danger",
                    )
                    return redirect(url_for("masters.new_wharf_profile"))
            else:
                print("No insurance document provided")

            # Add to database
            print("Adding wharf profile to database...")
            db.session.add(wharf_profile)
            db.session.commit()
            print("Database commit successful")

            print("Wharf profile creation completed successfully")
            flash("Wharf Profile has been created successfully!", "success")
            return redirect(url_for("masters.wharf_profiles"))

        except Exception as e:
            db.session.rollback()
            print(f"Error creating wharf profile: {str(e)}")
            print(f"Exception type: {type(e).__name__}")
            print(f"Exception traceback: {traceback.format_exc()}")
            flash(f"Error creating wharf profile", "danger")
            return redirect(url_for("masters.new_wharf_profile"))
    else:
        if request.method == "POST":
            print("Form validation failed")
            print(f"Form errors: {form.errors}")

    print("Rendering template for new wharf profile")
    return render_template(
        "masters/wharf_profile_form.html",
        title="New Wharf Profile",
        form=form,
        legend="New Wharf Profile",
    )


@bp.route("/wharf_profile/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_wharf_profile(id):
    # Get the wharf profile
    wharf_profile = WharfProfile.query.get_or_404(id)

    # Check permissions
    if wharf_profile.company_id != current_user.company_id:
        abort(403)

    # Initialize form
    form = WharfProfileForm()

    if form.validate_on_submit():
        try:
            # Update basic information
            wharf_profile.first_name = form.first_name.data
            wharf_profile.last_name = form.last_name.data
            wharf_profile.nic_no = form.nic_no.data
            wharf_profile.contact_number = form.contact_number.data
            wharf_profile.email = form.email.data
            wharf_profile.address = form.address.data

            # Update date fields
            if form.date_of_birth.data:
                wharf_profile.date_of_birth = datetime.strptime(
                    form.date_of_birth.data, "%Y-%m-%d"
                ).date()
            if form.driving_license_expiry.data:
                wharf_profile.driving_license_expiry = datetime.strptime(
                    form.driving_license_expiry.data, "%Y-%m-%d"
                ).date()
            if form.insurance_expiry.data:
                wharf_profile.insurance_expiry = datetime.strptime(
                    form.insurance_expiry.data, "%Y-%m-%d"
                ).date()
            if form.medical_insurance_expiry.data:
                wharf_profile.medical_insurance_expiry = datetime.strptime(
                    form.medical_insurance_expiry.data, "%Y-%m-%d"
                ).date()

            # Update vehicle information
            wharf_profile.driving_license_number = form.driving_license_number.data
            wharf_profile.registration_no = form.registration_no.data
            wharf_profile.vehicle_type = form.vehicle_type.data
            wharf_profile.vehicle_model = form.vehicle_model.data
            wharf_profile.vehicle_color = form.vehicle_color.data
            wharf_profile.engine_no = form.engine_no.data
            wharf_profile.chassis_no = form.chassis_no.data

            # Update insurance information
            wharf_profile.insurance_number = form.insurance_number.data
            wharf_profile.insurance_company = form.insurance_company.data
            wharf_profile.medical_insurance_number = form.medical_insurance_number.data

            # Update status
            wharf_profile.status = form.status.data

            # Handle profile image
            if form.profile_image.data:
                try:
                    # Delete old image if exists
                    if (
                        wharf_profile.profile_image
                        and wharf_profile.profile_image != "default.jpg"
                    ):
                        delete_file_from_s3(
                            current_app.config["S3_BUCKET_NAME"],
                            wharf_profile.profile_image,
                        )

                    # Generate new filename
                    random_hex = secrets.token_hex(8)
                    _, f_ext = os.path.splitext(form.profile_image.data.filename)
                    picture_fn = random_hex + f_ext
                    s3_key = f"{current_app.config['S3_BASE_FOLDER']}/profile_pics/{picture_fn}"

                    # Resize image
                    output_size = (400, 400)
                    i = Image.open(form.profile_image.data)
                    i.thumbnail(output_size)

                    # Save to temp file
                    temp_path = os.path.join(
                        current_app.root_path, "static", "temp", picture_fn
                    )
                    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                    i.save(temp_path)

                    # Upload to S3
                    with open(temp_path, "rb") as f:
                        upload_file_to_s3(
                            f, current_app.config["S3_BUCKET_NAME"], s3_key
                        )

                    # Clean up temp file
                    os.remove(temp_path)

                    # Update profile image path
                    wharf_profile.profile_image = s3_key
                except Exception as e:
                    print(f"Error handling profile image: {str(e)}")
                    flash("Error updating profile image. Please try again.", "danger")
                    return redirect(url_for("masters.edit_wharf_profile", id=id))

            # Handle NIC document
            if form.nic_document.data:
                try:
                    # Delete old document if exists
                    if wharf_profile.nic_document:
                        delete_file_from_s3(
                            current_app.config["S3_BUCKET_NAME"],
                            wharf_profile.nic_document,
                        )

                    # Generate new filename
                    random_hex = secrets.token_hex(8)
                    _, f_ext = os.path.splitext(form.nic_document.data.filename)
                    document_fn = random_hex + f_ext
                    s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/nic/{document_fn}"

                    # Upload to S3
                    upload_file_to_s3(
                        form.nic_document.data,
                        current_app.config["S3_BUCKET_NAME"],
                        s3_key,
                    )

                    # Update document path
                    wharf_profile.nic_document = s3_key
                except Exception as e:
                    print(f"Error handling NIC document: {str(e)}")
                    flash("Error updating NIC document. Please try again.", "danger")
                    return redirect(url_for("masters.edit_wharf_profile", id=id))

            # Handle insurance document
            if form.insurance_document.data:
                try:
                    # Delete old document if exists
                    if wharf_profile.insurance_document:
                        delete_file_from_s3(
                            current_app.config["S3_BUCKET_NAME"],
                            wharf_profile.insurance_document,
                        )

                    # Generate new filename
                    random_hex = secrets.token_hex(8)
                    _, f_ext = os.path.splitext(form.insurance_document.data.filename)
                    document_fn = random_hex + f_ext
                    s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/insurance/{document_fn}"

                    # Upload to S3
                    upload_file_to_s3(
                        form.insurance_document.data,
                        current_app.config["S3_BUCKET_NAME"],
                        s3_key,
                    )

                    # Update document path
                    wharf_profile.insurance_document = s3_key
                except Exception as e:
                    print(f"Error handling insurance document: {str(e)}")
                    flash(
                        "Error updating insurance document. Please try again.", "danger"
                    )
                    return redirect(url_for("masters.edit_wharf_profile", id=id))

            # Commit all changes
            db.session.commit()
            flash("Wharf Profile has been updated successfully!", "success")
            return redirect(url_for("masters.wharf_profiles"))

        except Exception as e:
            db.session.rollback()
            print(f"Error updating wharf profile: {str(e)}")
            flash(f"Error updating wharf profile", "danger")
            return redirect(url_for("masters.edit_wharf_profile", id=id))

    elif request.method == "GET":
        # Populate form with current data
        form.wharf_id.data = wharf_profile.wharf_id
        form.first_name.data = wharf_profile.first_name
        form.last_name.data = wharf_profile.last_name
        form.nic_no.data = wharf_profile.nic_no
        form.contact_number.data = wharf_profile.contact_number
        form.email.data = wharf_profile.email
        form.address.data = wharf_profile.address
        form.date_of_birth.data = (
            wharf_profile.date_of_birth.strftime("%Y-%m-%d")
            if wharf_profile.date_of_birth
            else None
        )
        form.driving_license_number.data = wharf_profile.driving_license_number
        form.driving_license_expiry.data = (
            wharf_profile.driving_license_expiry.strftime("%Y-%m-%d")
            if wharf_profile.driving_license_expiry
            else None
        )
        form.registration_no.data = wharf_profile.registration_no
        form.vehicle_type.data = wharf_profile.vehicle_type
        form.vehicle_model.data = wharf_profile.vehicle_model
        form.vehicle_color.data = wharf_profile.vehicle_color
        form.engine_no.data = wharf_profile.engine_no
        form.chassis_no.data = wharf_profile.chassis_no
        form.insurance_number.data = wharf_profile.insurance_number
        form.insurance_company.data = wharf_profile.insurance_company
        form.insurance_expiry.data = (
            wharf_profile.insurance_expiry.strftime("%Y-%m-%d")
            if wharf_profile.insurance_expiry
            else None
        )
        form.medical_insurance_number.data = wharf_profile.medical_insurance_number
        form.medical_insurance_expiry.data = (
            wharf_profile.medical_insurance_expiry.strftime("%Y-%m-%d")
            if wharf_profile.medical_insurance_expiry
            else None
        )
        form.status.data = wharf_profile.status

    return render_template(
        "masters/wharf_profile_form.html",
        title="Edit Wharf Profile",
        form=form,
        legend="Edit Wharf Profile",
        wharf_profile=wharf_profile,
    )


@bp.route("/wharf_profile/<int:id>/view")
@login_required
def view_wharf_profile(id):
    wharf_profile = WharfProfile.query.get_or_404(id)
    if wharf_profile.company_id != current_user.company_id:
        abort(403)
    return render_template(
        "masters/wharf_profile_view.html",
        title="View Wharf Profile",
        wharf_profile=wharf_profile,
    )


@bp.route("/wharf_profile/<int:id>/delete", methods=["POST"])
@login_required
def delete_wharf_profile(id):
    wharf_profile = WharfProfile.query.get_or_404(id)
    if wharf_profile.company_id != current_user.company_id:
        abort(403)
    if wharf_profile.profile_image != "default.jpg":
        delete_profile_picture(wharf_profile.profile_image)
    db.session.delete(wharf_profile)
    db.session.commit()
    flash("Wharf Profile has been deleted successfully!", "success")
    return redirect(url_for("masters.wharf_profiles"))


@bp.route("/wharf_profile/<int:id>/create-login", methods=["POST"])
@login_required
def create_wharf_login(id):
    try:
        print("\n=== Starting Wharf Login Creation Process ===")
        print(f"Attempting to create login for wharf profile ID: {id}")

        # Get wharf profile
        wharf_profile = WharfProfile.query.get_or_404(id)
        print(
            f"Found wharf profile: {wharf_profile.first_name} {wharf_profile.last_name}"
        )
        print(f"Wharf profile email: {wharf_profile.email}")
        print(f"Wharf profile company_id: {wharf_profile.company_id}")
        print(f"Current user company_id: {get_company_id()}")
        print(f"Current user: {current_user.username}")

        # Check if user has permission
        if wharf_profile.company_id != get_company_id():
            print(
                f"Permission denied. Wharf profile company_id: {wharf_profile.company_id}, User company_id: {get_company_id()}"
            )
            return (
                jsonify(
                    {
                        "error": "You don't have permission to create login for this wharf profile"
                    }
                ),
                403,
            )

        # Check if wharf profile already has a login
        if wharf_profile.user_id:
            print(f"Wharf profile already has a user_id: {wharf_profile.user_id}")
            return jsonify({"error": "Wharf profile already has a login"}), 400

        # Check if email is already in use
        existing_user = User.query.filter_by(email=wharf_profile.email).first()
        if existing_user:
            print(
                f"Email {wharf_profile.email} is already in use by user ID: {existing_user.id}"
            )
            return jsonify({"error": "Email address is already in use"}), 400

        print("\n=== Creating New User ===")
        print(
            f"Creating new user for wharf profile: {wharf_profile.first_name} {wharf_profile.last_name}"
        )
        print(f"Email: {wharf_profile.email}")
        print(f"Company ID: {wharf_profile.company_id}")

        # Create new user
        user = User(
            name=f"{wharf_profile.first_name} {wharf_profile.last_name}",
            email=wharf_profile.email,
            username=wharf_profile.email,
            contact_number=wharf_profile.contact_number,
            company_id=wharf_profile.company_id,
            is_active=True,
            is_super_admin=False,
        )

        # Set password and verify it works
        try:
            print("\n=== Setting Password ===")
            user.set_password("wharf123")
            print("Password set successfully")
            # Verify password was set correctly
            if not user.check_password("wharf123"):
                raise Exception("Password verification failed after setting")
            print("Password verification successful")
        except Exception as e:
            print(f"Error setting password: {str(e)}")
            print(f"Password hash: {user.password_hash}")
            raise

        # Save user and update wharf profile
        try:
            print("\n=== Saving to Database ===")
            db.session.add(user)
            db.session.flush()  # This will assign an ID to the user
            print(f"Created user with ID: {user.id}")

            wharf_profile.user_id = user.id
            db.session.commit()
            print("Successfully committed changes to database")
            return jsonify({"message": "Login created successfully"}), 200
        except Exception as e:
            print(f"Database error: {str(e)}")
            print("Rolling back transaction...")
            db.session.rollback()
            raise

    except Exception as e:
        db.session.rollback()
        print(f"Error creating wharf login: {str(e)}")
        return jsonify({"error": "Failed to create login. Please try again."}), 500


# Branch routes
############################
@bp.route("/branches")
@login_required
def branches():
    if current_user.is_super_admin == 1:
        branches = Branch.query.all()
    else:
        branches = Branch.query.filter_by(company_id=get_company_id()).all()
    return render_template("masters/branches.html", title="Branches", branches=branches)


@bp.route("/branch/new", methods=["GET", "POST"])
@login_required
def new_branch():
    form = BranchForm()
    if form.validate_on_submit():
        branch = Branch(
            branch_id=form.branch_id.data,
            name=form.name.data,
            address=form.address.data,
            contact_no=form.contact_no.data,
            email=form.email.data,
            is_active=form.is_active.data,
            company_id=get_company_id(),
        )
        db.session.add(branch)
        db.session.commit()
        flash("Branch has been created!", "success")
        return redirect(url_for("masters.branches"))
    return render_template(
        "masters/branch_form.html",
        title="New Branch",
        form=form,
        legend="New Branch",
    )


@bp.route("/branch/<int:branch_id>/edit", methods=["GET", "POST"])
@login_required
def edit_branch(branch_id):
    branch = Branch.query.get_or_404(branch_id)
    if branch.company_id != get_company_id():
        flash("You don't have permission to edit this branch.", "danger")
        return redirect(url_for("masters.branches"))

    form = BranchForm()
    if form.validate_on_submit():
        branch.branch_id = form.branch_id.data
        branch.name = form.name.data
        branch.address = form.address.data
        branch.contact_no = form.contact_no.data
        branch.email = form.email.data
        branch.is_active = form.is_active.data
        db.session.commit()
        flash("Branch has been updated!", "success")
        return redirect(url_for("masters.branches"))
    elif request.method == "GET":
        form.branch_id.data = branch.branch_id
        form.name.data = branch.name
        form.address.data = branch.address
        form.contact_no.data = branch.contact_no
        form.email.data = branch.email
        form.is_active.data = branch.is_active
    return render_template(
        "masters/branch_form.html",
        title="Edit Branch",
        form=form,
        legend="Edit Branch",
    )


@bp.route("/branch/<int:branch_id>/delete", methods=["POST"])
@login_required
def delete_branch(branch_id):
    branch = Branch.query.get_or_404(branch_id)
    if branch.company_id != get_company_id():
        flash("You don't have permission to delete this branch.", "danger")
        return redirect(url_for("masters.branches"))

    db.session.delete(branch)
    db.session.commit()
    flash("Branch has been deleted!", "success")
    return redirect(url_for("masters.branches"))

# ===============================
# CONTAINER DOCUMENTS ROUTES
# ===============================

@bp.route("/container-documents")
@login_required
def container_documents():
    """List all container documents"""
    # Get filter parameters
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    per_page = int(request.args.get('per_page', 10))
    page = int(request.args.get('page', 1))
    
    # Base query
    if current_user.is_super_admin == 1:
        query = ContainerDocument.query
    else:
        query = ContainerDocument.query.filter_by(company_id=get_company_id())
    
    # Apply filters
    if search:
        query = query.filter(
            db.or_(
                ContainerDocument.document_code.ilike(f'%{search}%'),
                ContainerDocument.document_name.ilike(f'%{search}%')
            )
        )
    
    if status == 'active':
        query = query.filter(ContainerDocument.is_active == True)
    elif status == 'inactive':
        query = query.filter(ContainerDocument.is_active == False)
    
    # Order by created date descending
    query = query.order_by(ContainerDocument.created_at.desc())
    
    # Paginate
    documents = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template(
        "masters/container_documents.html",
        title="Container Documents",
        documents=documents
    )

@bp.route("/container-document/new", methods=["GET", "POST"])
@login_required
def new_container_document():
    """Create a new container document"""
    if request.method == "POST":
        try:
            # Extract form data
            document_code = request.form.get("document_code", "").strip()
            document_name = request.form.get("document_name", "").strip()
            is_active = bool(request.form.get("is_active"))
            
            # Validate required fields
            if not document_code or not document_name:
                flash("Document code and name are required!", "danger")
                return render_template("masters/container_document_form.html", title="New Container Document")
            
            # Check for duplicate document code within company
            company_id = get_company_id()
            existing = ContainerDocument.query.filter_by(
                document_code=document_code,
                company_id=company_id
            ).first()
            
            if existing:
                flash("Document code already exists!", "danger")
                return render_template("masters/container_document_form.html", title="New Container Document")
            
            # Initialize sample file path as None
            sample_file_path = None
            
            # Check if a sample file was uploaded
            if 'sample_file' in request.files and request.files['sample_file'].filename != '':
                file = request.files['sample_file']
                filename = secure_filename(file.filename)
                
                # Create S3 key with proper structure
                s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/container_documents/{company_id}/{filename}"
                
                # Upload file to S3
                upload_result = upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
                sample_file_path = s3_key
            
            # Create new container document
            document = ContainerDocument(
                document_code=document_code,
                document_name=document_name,
                sample_file_path=sample_file_path,
                is_active=is_active,
                company_id=company_id
            )
            
            db.session.add(document)
            db.session.commit()
            
            flash("Container document has been created!", "success")
            return redirect(url_for("masters.container_documents"))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating container document: {str(e)}")
            flash("An error occurred while creating the document.", "danger")
            return render_template("masters/container_document_form.html", title="New Container Document")
    
    return render_template(
        "masters/container_document_form.html",
        title="New Container Document",
        document=None
    )

@bp.route("/container-document/<int:document_id>/edit", methods=["GET", "POST"])
@login_required
def edit_container_document(document_id):
    """Edit an existing container document"""
    document = ContainerDocument.query.get_or_404(document_id)
    
    # Check permissions
    if not current_user.is_super_admin and document.company_id != get_company_id():
        flash("You do not have permission to edit this document.", "danger")
        return redirect(url_for("masters.container_documents"))
    
    if request.method == "POST":
        try:
            # Extract form data
            document_code = request.form.get("document_code", "").strip()
            document_name = request.form.get("document_name", "").strip()
            is_active = bool(request.form.get("is_active"))
            
            # Validate required fields
            if not document_code or not document_name:
                flash("Document code and name are required!", "danger")
                return render_template("masters/container_document_form.html", 
                                     title="Edit Container Document", document=document)
            
            # Check for duplicate document code (excluding current document)
            existing = ContainerDocument.query.filter(
                ContainerDocument.document_code == document_code,
                ContainerDocument.company_id == document.company_id,
                ContainerDocument.id != document_id
            ).first()
            
            if existing:
                flash("Document code already exists!", "danger")
                return render_template("masters/container_document_form.html", 
                                     title="Edit Container Document", document=document)
            
            # Update basic fields
            document.document_code = document_code
            document.document_name = document_name
            document.is_active = is_active
            
            # Handle file upload
            if 'sample_file' in request.files and request.files['sample_file'].filename != '':
                file = request.files['sample_file']
                filename = secure_filename(file.filename)
                
                # Create S3 key with proper structure
                s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/container_documents/{document.company_id}/{filename}"
                
                # Upload new file to S3
                upload_result = upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
                document.sample_file_path = s3_key
            
            db.session.commit()
            flash("Container document has been updated!", "success")
            return redirect(url_for("masters.container_documents"))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error updating container document: {str(e)}")
            flash("An error occurred while updating the document.", "danger")
    
    return render_template(
        "masters/container_document_form.html",
        title="Edit Container Document",
        document=document
    )

@bp.route("/container-document/<int:document_id>/delete", methods=["POST"])
@login_required
def delete_container_document(document_id):
    """Delete a container document"""
    try:
        document = ContainerDocument.query.get_or_404(document_id)
        
        # Check permissions
        if not current_user.is_super_admin and document.company_id != get_company_id():
            flash("You do not have permission to delete this document.", "danger")
            return redirect(url_for("masters.container_documents"))
        
        db.session.delete(document)
        db.session.commit()
        flash("Container document has been deleted!", "success")
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting container document: {str(e)}")
        flash("An error occurred while deleting the document.", "danger")
    
    return redirect(url_for("masters.container_documents"))

@bp.route("/container-document/<int:document_id>/download")
@login_required
def download_container_document(document_id):
    """Download sample file for a container document"""
    document = ContainerDocument.query.get_or_404(document_id)
    
    # Check permissions
    if not current_user.is_super_admin and document.company_id != get_company_id():
        flash("You do not have permission to access this document.", "danger")
        return redirect(url_for("masters.container_documents"))
    
    if not document.sample_file_path:
        flash("No sample file available for this document.", "info")
        return redirect(url_for("masters.container_documents"))
    
    try:
        # Generate S3 download URL
        file_url = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{document.sample_file_path}"
        return redirect(file_url)
    except Exception as e:
        print(f"Error generating download URL: {str(e)}")
        flash("Unable to download file at this time.", "danger")
        return redirect(url_for("masters.container_documents"))



# ===============================
# CONTAINER DEPOSIT WORKFLOWS ROUTES
# ===============================


@bp.route("/container-deposit-workflows")
@login_required
def container_deposit_workflows():
    print("Accessed: /container-deposit-workflows")

    search = request.args.get('search', '')
    status = request.args.get('status', '')
    per_page = int(request.args.get('per_page', 10))
    page = int(request.args.get('page', 1))

    print(f"Filters - Search: '{search}', Status: '{status}', Page: {page}, Per Page: {per_page}")

    if current_user.is_super_admin == 1:
        query = ContainerDepositWorkflow.query
        print("User is Super Admin")
    else:
        query = ContainerDepositWorkflow.query.filter_by(company_id=get_company_id())
        print(f"User company_id: {get_company_id()}")

    if search:
        print("Applying search filter...")
        query = query.filter(
            db.or_(
                ContainerDepositWorkflow.workflow_code.ilike(f'%{search}%'),
                ContainerDepositWorkflow.workflow_name.ilike(f'%{search}%')
            )
        )

    if status == 'active':
        print("Filtering active workflows...")
        query = query.filter(ContainerDepositWorkflow.is_active == True)
    elif status == 'inactive':
        print("Filtering inactive workflows...")
        query = query.filter(ContainerDepositWorkflow.is_active == False)

    query = query.order_by(ContainerDepositWorkflow.created_at.desc())
    workflows = query.paginate(page=page, per_page=per_page, error_out=False)

    print(f"Fetched {len(workflows.items)} workflows")
    return render_template("masters/container_deposit_workflows.html", title="Container Deposit Workflows", workflows=workflows)


@bp.route("/container-deposit-workflow/new", methods=["GET", "POST"])
@login_required
def new_container_deposit_workflow():
    print("Accessed: /container-deposit-workflow/new")
    
    if request.method == "POST":
        print("Received POST request to create workflow")
        try:
            workflow_code = request.form.get("workflow_code", "").strip()
            workflow_name = request.form.get("workflow_name", "").strip()
            is_active = bool(request.form.get("is_active"))
            step_names = request.form.getlist("step_names[]")
            step_descriptions = request.form.getlist("step_descriptions[]")

            print(f"Form Data - Code: {workflow_code}, Name: {workflow_name}, Active: {is_active}, Steps Count: {len(step_names)}")

            if not workflow_code or not workflow_name:
                print("Validation failed: Missing workflow code or name")
                flash("Workflow code and name are required!", "danger")
                return redirect(request.url)

            if not step_names or len(step_names) == 0:
                print("Validation failed: No steps provided")
                flash("At least one workflow step is required!", "danger")
                return redirect(request.url)

            company_id = get_company_id()
            existing = ContainerDepositWorkflow.query.filter_by(workflow_code=workflow_code, company_id=company_id).first()
            if existing:
                print("Duplicate workflow code found")
                flash("Workflow code already exists!", "danger")
                return redirect(request.url)

            workflow = ContainerDepositWorkflow(
                workflow_code=workflow_code,
                workflow_name=workflow_name,
                is_active=is_active,
                company_id=company_id,
                created_by=current_user.id
            )
            db.session.add(workflow)
            db.session.flush()
            print(f"Created workflow ID: {workflow.id}")

            for step_number, step_name in enumerate(step_names, 1):
                if not step_name.strip():
                    continue

                step_description = step_descriptions[step_number - 1] if len(step_descriptions) >= step_number else ""
                step = ContainerDepositWorkflowStep(
                    workflow_id=workflow.id,
                    step_number=step_number,
                    step_name=step_name.strip(),
                    description=step_description.strip()
                )
                db.session.add(step)
                db.session.flush()
                print(f"  Added step {step_number}: {step_name.strip()}")

                # Get documents for this step
                step_documents_key = f"step_documents_{step_number}"
                step_document_ids = request.form.getlist(f"{step_documents_key}[]")

                # Process each document with its corresponding mandatory flag
                for doc_index, doc_id in enumerate(step_document_ids):
                    if doc_id:
                        # Look for the specific mandatory checkbox for this document
                        mandatory_key = f"step_doc_mandatory_{step_number}_{doc_index}"
                        is_mandatory = bool(request.form.get(mandatory_key))
                        
                        step_document = ContainerDepositWorkflowStepDocument(
                            step_id=step.id,
                            document_id=int(doc_id),
                            is_mandatory=is_mandatory
                        )
                        db.session.add(step_document)
                        print(f"    Linked document {doc_id} at index {doc_index} (Mandatory: {is_mandatory})")

            db.session.commit()
            print("Workflow creation committed successfully.")
            flash("Container deposit workflow has been created!", "success")
            return redirect(url_for("masters.container_deposit_workflows"))

        except Exception as e:
            db.session.rollback()
            print(f"Error creating workflow: {str(e)}")
            flash("An error occurred while creating the workflow.", "danger")
            return redirect(request.url)

    company_id = get_company_id()
    if current_user.is_super_admin == 1:
        available_documents = ContainerDocument.query.filter_by(is_active=True).all()
    else:
        available_documents = ContainerDocument.query.filter_by(company_id=company_id, is_active=True).all()

    print(f"Loaded {len(available_documents)} available documents for form")
    return render_template("masters/container_deposit_workflow_form.html", title="New Container Deposit Workflow", workflow=None, available_documents=available_documents)


@bp.route("/container-deposit-workflow/<int:workflow_id>/edit", methods=["GET", "POST"])
@login_required
def edit_container_deposit_workflow(workflow_id):
    """Edit an existing step-based container deposit workflow"""
    workflow = ContainerDepositWorkflow.query.get_or_404(workflow_id)
    
    # Check permissions
    if not current_user.is_super_admin and workflow.company_id != get_company_id():
        flash("You do not have permission to edit this workflow.", "danger")
        return redirect(url_for("masters.container_deposit_workflows"))
    
    if request.method == "POST":
        try:
            # Extract form data
            workflow_code = request.form.get("workflow_code", "").strip()
            workflow_name = request.form.get("workflow_name", "").strip()
            is_active = bool(request.form.get("is_active"))
            
            # Get step data
            step_names = request.form.getlist("step_names[]")
            step_descriptions = request.form.getlist("step_descriptions[]")
            
            # Get existing step IDs if they exist (for tracking which steps are being updated vs new)
            existing_step_ids = request.form.getlist("existing_step_ids[]")
            
            # Validate required fields
            if not workflow_code or not workflow_name:
                flash("Workflow code and name are required!", "danger")
                return redirect(request.url)
            
            if not step_names or len(step_names) == 0:
                flash("At least one workflow step is required!", "danger")
                return redirect(request.url)
            
            # Check for duplicate workflow code (excluding current workflow)
            existing = ContainerDepositWorkflow.query.filter(
                ContainerDepositWorkflow.workflow_code == workflow_code,
                ContainerDepositWorkflow.company_id == workflow.company_id,
                ContainerDepositWorkflow.id != workflow_id
            ).first()
            
            if existing:
                flash("Workflow code already exists!", "danger")
                return redirect(request.url)
            
            # Update basic workflow fields
            workflow.workflow_code = workflow_code
            workflow.workflow_name = workflow_name
            workflow.is_active = is_active
            
            # Get all existing steps for reference
            existing_steps = {step.id: step for step in workflow.workflow_steps.all()}
            processed_step_ids = set()
            
            # Process each step from the form
            for step_index, step_name in enumerate(step_names):
                if not step_name.strip():
                    continue
                
                step_number = step_index + 1
                step_description = step_descriptions[step_index] if len(step_descriptions) > step_index else ""
                
                # Check if this is an existing step or a new one
                existing_step_id = existing_step_ids[step_index] if len(existing_step_ids) > step_index and existing_step_ids[step_index] else None
                
                if existing_step_id and int(existing_step_id) in existing_steps:
                    # UPDATE EXISTING STEP
                    step = existing_steps[int(existing_step_id)]
                    processed_step_ids.add(step.id)
                    
                    # Update step details (only if changed)
                    step_changed = False
                    if step.step_number != step_number:
                        step.step_number = step_number
                        step_changed = True
                    
                    if step.step_name != step_name.strip():
                        step.step_name = step_name.strip()
                        step_changed = True
                    
                    new_description = step_description.strip() if step_description else None
                    if step.description != new_description:
                        step.description = new_description
                        step_changed = True
                    
                    # Get new document configuration for this step
                    step_documents_key = f"step_documents_{step_number}"
                    step_document_ids = request.form.getlist(f"{step_documents_key}[]")
                    
                    # Check if documents changed by comparing with existing
                    existing_step_docs = {sd.document_id: sd for sd in step.step_documents.all()}
                    new_document_config = []
                    
                    # Process each document with its corresponding mandatory flag
                    for doc_index, doc_id in enumerate(step_document_ids):
                        if doc_id:
                            # Look for the specific mandatory checkbox for this document
                            mandatory_key = f"step_doc_mandatory_{step_number}_{doc_index}"
                            is_mandatory = bool(request.form.get(mandatory_key))
                            
                            new_document_config.append({
                                'document_id': int(doc_id),
                                'is_mandatory': is_mandatory
                            })
                    
                    # Check if document configuration changed
                    documents_changed = False
                    
                    # First check if the number of documents changed
                    if len(new_document_config) != len(existing_step_docs):
                        documents_changed = True
                    else:
                        # Check if any document or its mandatory status changed
                        new_doc_dict = {doc['document_id']: doc['is_mandatory'] for doc in new_document_config}
                        existing_doc_dict = {doc_id: doc.is_mandatory for doc_id, doc in existing_step_docs.items()}
                        
                        # Compare the dictionaries
                        if new_doc_dict != existing_doc_dict:
                            documents_changed = True
                    
                    print(f"    Documents changed: {documents_changed}")

                    
                    # Only update documents if they changed
                    if documents_changed:
                        # Get existing step documents for proper update/create/delete operations
                        existing_step_docs_list = step.step_documents.all()
                        existing_step_docs_dict = {sd.document_id: sd for sd in existing_step_docs_list}
                        
                        # Track which document IDs are in the new configuration
                        new_document_ids = {doc['document_id'] for doc in new_document_config}
                        
                        # Update or create documents
                        for new_doc in new_document_config:
                            doc_id = new_doc['document_id']
                            is_mandatory = new_doc['is_mandatory']
                            
                            if doc_id in existing_step_docs_dict:
                                # UPDATE existing document relationship
                                existing_doc = existing_step_docs_dict[doc_id]
                                if existing_doc.is_mandatory != is_mandatory:
                                    existing_doc.is_mandatory = is_mandatory
                                    print(f"    Updated document {doc_id} mandatory status to {is_mandatory}")
                            else:
                                # CREATE new document relationship
                                step_document = ContainerDepositWorkflowStepDocument(
                                    step_id=step.id,
                                    document_id=doc_id,
                                    is_mandatory=is_mandatory
                                )
                                db.session.add(step_document)
                                print(f"    Added new document {doc_id} (Mandatory: {is_mandatory})")
                        
                        # DELETE documents that are no longer in the configuration
                        for existing_doc_id, existing_doc in existing_step_docs_dict.items():
                            if existing_doc_id not in new_document_ids:
                                # Check if this document has any uploaded files
                                uploaded_files_count = ContainerWorkflowDocument.query.filter_by(
                                    step_document_id=existing_doc.id
                                ).count()
                                
                                if uploaded_files_count > 0:
                                    flash(f"Cannot remove document '{existing_doc.document.document_name}' from Step '{step.step_name}' because it has {uploaded_files_count} uploaded file(s).", "danger")
                                    return redirect(request.url)
                                else:
                                    db.session.delete(existing_doc)
                                    print(f"    Removed document {existing_doc_id} from step")
                    
                    if step_changed or documents_changed:
                        print(f"Updated existing step {step.id}: {step.step_name}")
                    
                else:
                    # CREATE NEW STEP
                    step = ContainerDepositWorkflowStep(
                        workflow_id=workflow.id,
                        step_number=step_number,
                        step_name=step_name.strip(),
                        description=step_description.strip() if step_description else None
                    )
                    
                    db.session.add(step)
                    db.session.flush()  # To get the step ID
                    processed_step_ids.add(step.id)
                    
                    # Add documents to this new step
                    step_documents_key = f"step_documents_{step_number}"
                    step_document_ids = request.form.getlist(f"{step_documents_key}[]")
                    
                    # Process each document with its corresponding mandatory flag
                    for doc_index, doc_id in enumerate(step_document_ids):
                        if doc_id:
                            # Look for the specific mandatory checkbox for this document
                            mandatory_key = f"step_doc_mandatory_{step_number}_{doc_index}"
                            is_mandatory = bool(request.form.get(mandatory_key))
                            
                            step_document = ContainerDepositWorkflowStepDocument(
                                step_id=step.id,
                                document_id=int(doc_id),
                                is_mandatory=is_mandatory
                            )
                            db.session.add(step_document)
                    
                    print(f"Created new step: {step.step_name}")
            
            # REMOVE STEPS THAT WERE DELETED (only if explicitly removed by user)
            # Steps that existed before but are not in processed_step_ids were removed
            steps_to_remove = set(existing_steps.keys()) - processed_step_ids
            
            for step_id in steps_to_remove:
                step_to_remove = existing_steps[step_id]
                
                # Check if this step has any uploaded documents
                uploaded_doc_count = ContainerWorkflowDocument.query.filter_by(step_id=step_id).count()
                
                if uploaded_doc_count > 0:
                    # Cannot delete step with uploaded documents
                    flash(f"Cannot remove Step '{step_to_remove.step_name}' because it has {uploaded_doc_count} uploaded document(s). Please delete the uploaded documents first.", "danger")
                    return redirect(request.url)
                else:
                    # Safe to delete - no uploaded documents
                    print(f"Removing step: {step_to_remove.step_name}")
                    ContainerDepositWorkflowStepDocument.query.filter_by(step_id=step_id).delete()
                    db.session.delete(step_to_remove)
            
            db.session.commit()
            flash("Container deposit workflow has been updated successfully!", "success")
            return redirect(url_for("masters.container_deposit_workflows"))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error updating workflow: {str(e)}")
            flash("An error occurred while updating the workflow.", "danger")
            return redirect(request.url)
    
    # GET request - show form with current data
    company_id = workflow.company_id
    if current_user.is_super_admin == 1:
        available_documents = ContainerDocument.query.filter_by(is_active=True).all()
    else:
        available_documents = ContainerDocument.query.filter_by(
            company_id=company_id, 
            is_active=True
        ).all()
    
    return render_template(
        "masters/container_deposit_workflow_form.html",
        title="Edit Container Deposit Workflow",
        workflow=workflow,
        available_documents=available_documents
    )

@bp.route("/container-deposit-workflow/<int:workflow_id>/delete", methods=["POST"])
@login_required
def delete_container_deposit_workflow(workflow_id):
    print(f"Accessed: /container-deposit-workflow/{workflow_id}/delete")
    try:
        workflow = ContainerDepositWorkflow.query.get_or_404(workflow_id)

        if not current_user.is_super_admin and workflow.company_id != get_company_id():
            print("Permission denied for deletion")
            flash("You do not have permission to delete this workflow.", "danger")
            return redirect(url_for("masters.container_deposit_workflows"))

        db.session.delete(workflow)
        db.session.commit()
        print("Workflow deleted successfully")
        flash("Container deposit workflow has been deleted!", "success")

    except Exception as e:
        db.session.rollback()
        print(f"Error deleting workflow: {str(e)}")
        flash("An error occurred while deleting the workflow.", "danger")

    return redirect(url_for("masters.container_deposit_workflows"))



@bp.route("/container-deposit-workflow/<int:workflow_id>/view")
@login_required
def view_container_deposit_workflow(workflow_id):
    print(f"Accessed: /container-deposit-workflow/{workflow_id}/view")
    workflow = ContainerDepositWorkflow.query.get_or_404(workflow_id)

    if not current_user.is_super_admin and workflow.company_id != get_company_id():
        print("Permission denied for view")
        flash("You do not have permission to view this workflow.", "danger")
        return redirect(url_for("masters.container_deposit_workflows"))

    # Get workflow steps with documents
    workflow_steps = workflow.get_steps_with_documents()
    
    # Flatten documents for the template (to maintain compatibility)
    workflow_documents = []
    for step_data in workflow_steps:
        for doc_data in step_data['documents']:
            # Create tuple (step_document, document) for template compatibility
            workflow_documents.append((doc_data['step_document'], doc_data['document']))
    
    print(f"Viewing workflow with {len(workflow_steps)} steps and {len(workflow_documents)} total documents")

    return render_template(
        "masters/container_deposit_workflow_view.html", 
        title="View Workflow", 
        workflow=workflow, 
        workflow_steps=workflow_steps,
        workflow_documents=workflow_documents  # Add this for template compatibility
    )


#SHIP CATEGORY
#####################################

@bp.route("/ship-category/<int:shipment_type_id>/add", methods=["POST"])
@login_required
def add_ship_category(shipment_type_id):
    """Add a new ship category."""
    try:
        cat_code = request.form.get("catCode")
        cat_name = request.form.get("catname")

        # Create new ship category
        category = ShipCategory(
            catCode=cat_code,
            shipmentType=shipment_type_id,
            catname=cat_name,
            isActive=1,
        )
        db.session.add(category)
        db.session.commit()

        return jsonify(
            {
                "success": True,
                "category": {
                    "id": category.id,
                    "catCode": category.catCode,
                    "catname": category.catname,
                },
            }
        )
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})


@bp.route("/ship-category/<int:category_id>/delete", methods=["POST"])
@login_required
def delete_ship_category(category_id):
    """Delete a ship category."""
    try:
        category = ShipCategory.query.get_or_404(category_id)
        db.session.delete(category)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})

# Updated routes to handle confidence_level for ShipCatDocument
@bp.route("/ship-cat-document/add", methods=["POST"])
@login_required
def add_ship_cat_document():
    """Add a new ship category document with optional sample file."""
    try:
        # Extract form data
        ship_cat_id = request.form.get("shipCatId")
        shipment_type_id = request.form.get("shipmentTypeId")
        description = request.form.get("description")
        is_mandatory = int(request.form.get("isMandatory", 0))
        confidence_level = float(request.form.get("confidence_level", 0.0))
        
        # New fields
        content_similarity = float(request.form.get("content_similarity", 0.0))
        ai_validate = int(request.form.get("ai_validate", 0))
        multiple_document = int(request.form.get("multiple_document", 0))
        
        print(f"Adding document: Category ID: {ship_cat_id}, Type ID: {shipment_type_id}")
        print(f"Description: {description}, Mandatory: {is_mandatory}, Confidence: {confidence_level}%")
        print(f"Content Similarity: {content_similarity}%, AI Validate: {ai_validate}, Multiple Document: {multiple_document}")
        
        # Initialize sample file path as None
        sample_file_path = None
        sample_file_url = None
        
        # Check if a sample file was uploaded
        if 'sampleFile' in request.files and request.files['sampleFile'].filename != '':
            file = request.files['sampleFile']
            filename = secure_filename(file.filename)
            print(f"File uploaded: {filename}, Content Type: {file.content_type}")
            
            # Create S3 key with proper structure
            s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/sample_documents/{ship_cat_id}/{filename}"
            print(f"S3 key: {s3_key}")
            
            # Debug: Check what the upload_file_to_s3 function is returning
            upload_result = upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
            print(f"Upload result type: {type(upload_result)}, Value: {upload_result}")
            
            # Force the success path for testing (since we know the upload is working)
            # Remove this in production, just for testing
            print("Forcing sample file path to be set regardless of function return value")
            sample_file_path = s3_key
            sample_file_url = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{s3_key}"
            print(f"File URL: {sample_file_url}")
            print(f"Sample file path: {sample_file_path}")
        else:
            print("No file uploaded or filename is empty")
        
        # Create and save the document
        document = ShipCatDocument(
            shipCatid=ship_cat_id,
            shipmentTypeid=shipment_type_id,
            description=description,
            isMandatory=is_mandatory,
            sample_file_path=sample_file_path,
            confidence_level=confidence_level,
            content_similarity=content_similarity,  # New field
            ai_validate=ai_validate,  # New field
            multiple_document=multiple_document  # New field
        )
        
        print(f"Creating document with sample_file_path: {sample_file_path}, confidence_level: {confidence_level}")
        print(f"Content similarity: {content_similarity}, AI validate: {ai_validate}, Multiple document: {multiple_document}")
        db.session.add(document)
        db.session.commit()
        
        # Verify the document was saved with the correct values
        saved_doc = ShipCatDocument.query.get(document.id)
        print(f"Document saved with ID: {saved_doc.id}, Sample path: {saved_doc.sample_file_path}")
        print(f"Confidence: {saved_doc.confidence_level}, Content similarity: {saved_doc.content_similarity}")
        print(f"AI validate: {saved_doc.ai_validate}, Multiple document: {saved_doc.multiple_document}")

        return jsonify({
            "success": True,
            "document": {
                "id": document.id,
                "description": document.description,
                "isMandatory": document.isMandatory,
                "sample_file_url": sample_file_url,
                "confidence_level": document.confidence_level,
                "content_similarity": document.content_similarity,  # Include in response
                "ai_validate": document.ai_validate,  # Include in response
                "multiple_document": document.multiple_document  # Include in response
            }
        })
    except Exception as e:
        db.session.rollback()
        print(f"Error adding document: {str(e)}")
        return jsonify({"success": False, "error": str(e)})


@bp.route("/ship-cat-document/<int:category_id>")
@login_required
def get_ship_cat_documents(category_id):
    """Get documents for a ship category"""
    try:
        documents = ShipCatDocument.query.filter_by(shipCatid=category_id).all()
        print(f"Found {len(documents)} documents for category ID {category_id}")
        
        document_list = []
        for doc in documents:
            print(f"Document ID: {doc.id}, Path: {doc.sample_file_path}, Confidence: {doc.confidence_level}")
            print(f"Content Similarity: {doc.content_similarity}, AI Validate: {doc.ai_validate}, Multiple Document: {doc.multiple_document}")
            
            doc_info = {
                "id": doc.id,
                "description": doc.description,
                "isMandatory": doc.isMandatory,
                "sample_file_url": None,
                "confidence_level": doc.confidence_level,
                "content_similarity": doc.content_similarity,  # Include content similarity
                "ai_validate": doc.ai_validate,  # Include AI validate flag
                "multiple_document": doc.multiple_document,  # Include multiple document flag
                "shipment_type_id": doc.shipmentTypeid  # Include for the AI check functionality
            }
            
            # Generate S3 URL for the sample file if it exists
            if doc.sample_file_path:
                doc_info["sample_file_url"] = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{doc.sample_file_path}"
                print(f"Generated URL: {doc_info['sample_file_url']}")
            else:
                print(f"No sample file path for document ID {doc.id}")
            
            document_list.append(doc_info)
        
        return jsonify({
            "success": True,
            "documents": document_list
        })
    except Exception as e:
        print(f"Error getting documents: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
       


@bp.route("/ship-cat-document/<int:document_id>/delete", methods=["POST"])
@login_required
def delete_ship_cat_document(document_id):
    """Delete a ship category document."""
    try:
        document = ShipCatDocument.query.get_or_404(document_id)
        db.session.delete(document)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})



@bp.route("/ship-cat-document/<int:document_id>/update", methods=["POST"])
@login_required
def update_ship_cat_document(document_id):
    """Update an existing ship category document with optional sample file."""
    try:
        # Get the document
        document = ShipCatDocument.query.get_or_404(document_id)
        
        # Check if document belongs to the current company
        shipment_type = ShipmentType.query.get(document.shipmentTypeid)

        
        # Extract form data
        description = request.form.get("description")
        is_mandatory = int(request.form.get("isMandatory", 0))
        confidence_level = float(request.form.get("confidence_level", document.confidence_level))
        
        # New fields
        content_similarity = float(request.form.get("content_similarity", document.content_similarity))
        ai_validate = int(request.form.get("ai_validate", document.ai_validate))
        multiple_document = int(request.form.get("multiple_document", document.multiple_document))
        
        # Update document fields
        document.description = description
        document.isMandatory = is_mandatory
        document.confidence_level = confidence_level
        document.content_similarity = content_similarity  # New field
        document.ai_validate = ai_validate  # New field
        document.multiple_document = multiple_document  # New field
        
        # Handle sample file update if provided
        if 'sampleFile' in request.files and request.files['sampleFile'].filename != '':
            file = request.files['sampleFile']
            filename = secure_filename(file.filename)
            
            # Create S3 key with proper structure
            s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/sample_documents/{document.shipCatid}/{filename}"
            
            # Upload the file to S3
            upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
            
            # Update document with new file path
            document.sample_file_path = s3_key
        
        db.session.commit()
        
        # Generate sample file URL if exists
        sample_file_url = None
        if document.sample_file_path:
            sample_file_url = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{document.sample_file_path}"
        
        return jsonify({
            "success": True,
            "message": "Document updated successfully",
            "document": {
                "id": document.id,
                "description": document.description,
                "isMandatory": document.isMandatory,
                "sample_file_url": sample_file_url,
                "confidence_level": document.confidence_level,
                "content_similarity": document.content_similarity,  # Include in response
                "ai_validate": document.ai_validate,  # Include in response
                "multiple_document": document.multiple_document  # Include in response
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating document: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@bp.route("/ship-category/<int:category_id>/update", methods=["POST"])
@login_required
def update_ship_category(category_id):
    """Update an existing ship category."""
    try:
        # Get the category
        category = ShipCategory.query.get_or_404(category_id)
        
        # Check if category belongs to the current company
        shipment_type = ShipmentType.query.get(category.shipmentType)
        
        # Extract form data
        cat_code = request.form.get("catCode")
        cat_name = request.form.get("catname")
        
        # Update category
        category.catCode = cat_code
        category.catname = cat_name
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Category updated successfully",
            "category": {
                "id": category.id,
                "catCode": category.catCode,
                "catname": category.catname
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating category: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


#ORDERS
#######################################
from sqlalchemy.orm import aliased

@bp.route("/orders", methods=["GET", "POST"])
@login_required
def orders():
    print("Accessed /orders route")
    
    form = ShipDocumentEntryForm()
    form.csrf_token.data = form.csrf_token._value()

    shipment_types = ShipmentType.query.filter_by(company_id=current_user.company_id).all()
    form.shipTypeid.choices = [(st.id, st.shipment_name) for st in shipment_types]
    print(f"Loaded shipment types: {shipment_types}")

    customers = Customer.query.filter_by(company_id=current_user.company_id).order_by(Customer.customer_name).all()
    form.customer_id.choices = [
        (c.id, f"{c.customer_name} ({c.customer_id})") for c in customers
    ]
    print(f"Loaded customers: {customers}")

    if request.method == "POST":
        print("POST request received")
        shipment_type_id = request.form.get('shipTypeid', type=int)
        if shipment_type_id:
            # Load ship categories for the selected shipment type
            ship_categories = ShipCategory.query.filter_by(
                shipmentType=shipment_type_id
            ).all()
            form.shipCategory.choices = [(sc.id, sc.catname) for sc in ship_categories]
            
            # Load document statuses for the selected shipment type
            doc_statuses = DocumentStatus.query.filter_by(
                doctypeid=shipment_type_id
            ).all()
            form.docStatusID.choices = [(ds.docStatusID, ds.docStatusName) for ds in doc_statuses]

            new_status = DocumentStatus.query.filter(
                DocumentStatus.docStatusName.ilike('new')
            ).first()
            
            if new_status:
                # Set the default value for docStatusID to the "New" status
                form.docStatusID.data = new_status.docStatusID
                
                # Add this as the only choice
                form.docStatusID.choices = [(new_status.docStatusID, new_status.docStatusName)]

        if form.validate_on_submit():
            print("Form validated successfully")
            try:
                last_doc = (
                    ShipDocumentEntryMaster.query.filter_by(
                        shipTypeid=form.shipTypeid.data
                    )
                    .order_by(ShipDocumentEntryMaster.docnum.desc())
                    .first()
                )
                print(f"Last document: {last_doc}")

                new_doc_num = 1 if not last_doc else last_doc.docnum + 1
                print(f"New document number: {new_doc_num}")

                shipment_type = ShipmentType.query.get(form.shipTypeid.data)
                doc_code = shipment_type.docCode
                doc_serial = f"{doc_code}{new_doc_num:04d}"
                print(f"Generated doc serial: {doc_serial}")

                entry = ShipDocumentEntryMaster(
                    shipTypeid=form.shipTypeid.data,
                    docCode=doc_code,
                    docnum=new_doc_num,
                    docserial=doc_serial,
                    dateCreated=get_sri_lanka_time(),
                    dateSubmitted=get_sri_lanka_time(),  # Added this line to ensure dateSubmitted is set
                    dealineDate=form.dealineDate.data,
                    docStatusID=form.docStatusID.data,
                    custComment=form.custComment.data,
                    cusOriginalReady=form.cusOriginalReady.data if hasattr(form, 'cusOriginalReady') else False,
                    shipCategory=form.shipCategory.data,
                    customer_id=form.customer_id.data,
                    user_id=current_user.id,
                    company_id=current_user.company_id,
                    docLevel=1  # Set docLevel to 1 (Submitted) to ensure it appears in the list
                )

                db.session.add(entry)
                db.session.commit()
                print("Document entry committed to database")

                # For AJAX requests, return JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': True,
                        'message': 'Document entry created successfully!',
                        'entry_id': entry.id
                    })
                
                flash("Document entry created successfully!", "success")
                return redirect(url_for("masters.orders"))
            except Exception as e:
                db.session.rollback()
                print(f"Error during document entry creation: {e}")
                
                # For AJAX requests, return JSON error
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'message': f'Error creating document entry: {str(e)}'
                    })
                
                flash(f"Error creating document entry", "error")
                print(f"Error creating document entry: {str(e)}")

        else:
            print(f"Form validation failed: {form.errors}")
            # For AJAX requests, return JSON with validation errors
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'Form validation failed',
                    'errors': form.errors
                })
            
            # For regular form submissions, flash the errors
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error in {getattr(form, field).label.text}", "error")
                    print(f"Error in {getattr(form, field).label.text}: {error}")


    # Get filter parameters
    status_filter = request.args.get('status', '')  # NEW: Add status filter
    shipment_type_filter = request.args.get('ship_type', type=int)  # Keep existing name
    doc_level_filter = request.args.get('doc_level', type=int)  
    search_term = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    print(f"Filter params - Status: '{status_filter}', Ship Type: {shipment_type_filter}, Doc Level: {doc_level_filter}, Search: '{search_term}', Page: {page}, Per Page: {per_page}")

    # Create alias for clearing agent user to avoid conflicts
    ClearingAgentUser = aliased(User)

    # Build the query - ADD CLEARING AGENT JOINS
    query = (
        ShipDocumentEntryMaster.query.join(
            ShipmentType, ShipDocumentEntryMaster.shipTypeid == ShipmentType.id
        )
        .join(ShipCategory, ShipDocumentEntryMaster.shipCategory == ShipCategory.id)
        .join(
            DocumentStatus,
            ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID,
        )
        .join(  # NEW: Add INNER JOIN with CompanyAssignment
            CompanyAssignment,
            db.and_(
                ShipDocumentEntryMaster.company_id == CompanyAssignment.company_id,
                CompanyAssignment.assigned_company_id == current_user.company_id,
                CompanyAssignment.is_active == True
            )
        )
        .outerjoin(Customer, ShipDocumentEntryMaster.customer_id == Customer.id)
        .outerjoin(  # Existing join for current user assignment
            EntryAssignmentHistory,
            db.and_(
                ShipDocumentEntryMaster.id == EntryAssignmentHistory.entry_id,
                EntryAssignmentHistory.currently_assigned == True
            )
        )
        .outerjoin(  # Existing join for assigned user
            User,
            EntryAssignmentHistory.assigned_to_user_id == User.id
        )
        .outerjoin(  # Existing join for current clearing agent assignment
            EntryClearingAgentHistory,
            db.and_(
                ShipDocumentEntryMaster.id == EntryClearingAgentHistory.entry_id,
                EntryClearingAgentHistory.currently_assigned == True
            )
        )
        .outerjoin(  # Existing join for assigned clearing agent (using alias to avoid conflict)
            ClearingAgentUser,
            EntryClearingAgentHistory.assigned_to_clearing_agent_id == ClearingAgentUser.id
        )
        .options(
            db.joinedload(ShipDocumentEntryMaster.shipment_type),
            db.joinedload(ShipDocumentEntryMaster.ship_category_rel),
            db.joinedload(ShipDocumentEntryMaster.document_status),
            db.joinedload(ShipDocumentEntryMaster.customer),
        )
        .filter(
            ShipDocumentEntryMaster.docLevel != 0,
            ShipDocumentEntryMaster.assigned_clearing_company_id == current_user.company_id  # Existing filter
            # CompanyAssignment filters are now handled in the JOIN condition above
        )
        .add_columns(  # Add assigned user AND clearing agent information
            User.name.label('assigned_user_name'),
            User.username.label('assigned_user_username'),
            EntryAssignmentHistory.assigned_date.label('assignment_date'),
            # Existing clearing agent information
            ClearingAgentUser.name.label('assigned_clearing_agent_name'),
            EntryClearingAgentHistory.assigned_date.label('clearing_agent_assignment_date')
        )
    )
    
    if status_filter:
        print(f"Applying status filter: '{status_filter}'")
        if status_filter.lower() == 'new':
            query = query.filter(db.func.lower(DocumentStatus.docStatusName).like('%new%'))
        elif status_filter.lower() == 'ongoing':
            query = query.filter(
                ~db.func.lower(DocumentStatus.docStatusName).like('%new%'),
                ~db.func.lower(DocumentStatus.docStatusName).like('%complete%'),
                ~db.func.lower(DocumentStatus.docStatusName).like('%done%')
            )
        elif status_filter.lower() == 'completed':
            query = query.filter(
                db.or_(
                    db.func.lower(DocumentStatus.docStatusName).like('%complete%'),
                    db.func.lower(DocumentStatus.docStatusName).like('%done%')
                )
            )

    # Apply ship_type filter if specified
    if shipment_type_filter:
        print(f"Applying ship type filter: {shipment_type_filter}")
        query = query.filter(ShipDocumentEntryMaster.shipTypeid == shipment_type_filter)

    # Apply doc level filter if specified - NEW
    if doc_level_filter is not None:  # Use 'is not None' because 0 is a valid doc level
        print(f"Applying doc level filter: {doc_level_filter}")
        query = query.filter(ShipDocumentEntryMaster.docLevel == doc_level_filter)

    # Apply search filter if specified - ADD CLEARING AGENT TO SEARCH
    if search_term:
        print(f"Applying search filter: '{search_term}'")
        search_pattern = f"%{search_term}%"
        query = query.filter(
            db.or_(
                ShipDocumentEntryMaster.docserial.ilike(search_pattern),
                Customer.customer_name.ilike(search_pattern),
                ShipCategory.catname.ilike(search_pattern),
                ShipmentType.shipment_name.ilike(search_pattern),
                User.name.ilike(search_pattern),
                # NEW: Add clearing agent to search
                ClearingAgentUser.name.ilike(search_pattern)
            )
        )

    # Get total count for pagination
    total_entries = query.count()
    print(f"Total filtered entries: {total_entries}")

    # Apply sorting and pagination
    query = query.order_by(ShipDocumentEntryMaster.id.desc())
    query_results = query.limit(per_page).offset((page - 1) * per_page).all()
    print(f"Retrieved {len(query_results)} entries for current page")

    # Process the results to extract entries and assignment info
    paginated_entries = []
    for result in query_results:
        entry = result[0]  # The ShipDocumentEntryMaster object
        
        # Add assignment information to the entry object
        if result.assigned_user_name:
            entry.assigned_user_name = result.assigned_user_name
            entry.assigned_user_username = result.assigned_user_username
            entry.assignment_date = result.assignment_date
        else:
            entry.assigned_user_name = None
            entry.assigned_user_username = None
            entry.assignment_date = None
        
        # NEW: Add clearing agent assignment information
        if result.assigned_clearing_agent_name:
            entry.assigned_clearing_agent_name = result.assigned_clearing_agent_name
            entry.clearing_agent_assignment_date = result.clearing_agent_assignment_date
        else:
            entry.assigned_clearing_agent_name = None
            entry.clearing_agent_assignment_date = None
        
        paginated_entries.append(entry)

    # Calculate pagination variables
    max_pages = (total_entries + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page * per_page < total_entries
    prev_num = page - 1 if has_prev else None
    next_num = page + 1 if has_next else None
    current_page = page
    
    # Create a list of page numbers for pagination
    page_nums = []
    if max_pages <= 7:
        page_nums = list(range(1, max_pages + 1))
    else:
        if page <= 4:
            page_nums = list(range(1, 6)) + [None, max_pages]
        elif page >= max_pages - 3:
            page_nums = [1, None] + list(range(max_pages - 4, max_pages + 1))
        else:
            page_nums = [1, None, page-1, page, page+1, None, max_pages]

    # Calculate document counts for paginated entries
    for entry in paginated_entries:
        required_documents = ShipCatDocument.query.filter_by(
            shipCatid=entry.shipCategory, shipmentTypeid=entry.shipTypeid
        ).all()
        existing_attachments = ShipDocumentEntryAttachment.query.filter_by(
            shipDocEntryMasterID=entry.id
        ).all()

        entry.mandatory_docs_count = len(
            [doc for doc in required_documents if doc.isMandatory == 1]
        )
        entry.attached_docs_count = len(existing_attachments)

        entry.accepted_docs_count = len(
            [doc for doc in existing_attachments if doc.docAccepted == 'accepted']
        )
        
        entry.rejected_docs_count = len(
            [doc for doc in existing_attachments if doc.docAccepted == 'rejected']
        )

        entry.resubmission_stats = entry.get_resubmission_stats()

        print(
            f"Entry ID {entry.id}: Mandatory docs={entry.mandatory_docs_count}, "
            f"Attached={entry.attached_docs_count}, Accepted={entry.accepted_docs_count}, "
            f"Rejected={entry.rejected_docs_count}",
            f"Resubmissions={entry.resubmission_stats['resubmitted_count']}/{entry.resubmission_stats['rejected_count']}, "
            f"Assigned User={entry.assigned_user_name}, Clearing Agent={entry.assigned_clearing_agent_name}"
        )

    # Get all shipment types for filter dropdown
    shipment_types = ShipmentType.query.filter_by(company_id=current_user.company_id).all()

    base_query = (
        ShipDocumentEntryMaster.query.join(
            ShipmentType, ShipDocumentEntryMaster.shipTypeid == ShipmentType.id
        )
        .join(ShipCategory, ShipDocumentEntryMaster.shipCategory == ShipCategory.id)
        .join(
            DocumentStatus,
            ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID,
        )
        .join(
            CompanyAssignment,
            db.and_(
                ShipDocumentEntryMaster.company_id == CompanyAssignment.company_id,
                CompanyAssignment.assigned_company_id == current_user.company_id,
                CompanyAssignment.is_active == True
            )
        )
        .filter(
            ShipDocumentEntryMaster.docLevel != 0,
            ShipDocumentEntryMaster.assigned_clearing_company_id == current_user.company_id
        )
    )

    # Calculate counts for each status
    status_counts = {
        'total': base_query.count(),
        'new': base_query.filter(db.func.lower(DocumentStatus.docStatusName).like('%new%')).count(),
        'open': base_query.filter(db.func.lower(DocumentStatus.docStatusName).like('%open%')).count(),
        'ongoing': base_query.filter(
            ~db.func.lower(DocumentStatus.docStatusName).like('%new%'),
            ~db.func.lower(DocumentStatus.docStatusName).like('%complete%'),
            ~db.func.lower(DocumentStatus.docStatusName).like('%done%'),
            ~db.func.lower(DocumentStatus.docStatusName).like('%open%')
        ).count(),
        'completed': base_query.filter(
            db.or_(
                db.func.lower(DocumentStatus.docStatusName).like('%complete%'),
                db.func.lower(DocumentStatus.docStatusName).like('%done%')
            )
        ).count()
    }
    
    # Pass the current date/time for deadline calculations
    now = get_sri_lanka_time()
    
    return render_template(
        "masters/orders.html",
        title="Orders",
        form=form,
        entries=paginated_entries,  # Use paginated entries instead of all entries
        shipment_types=shipment_types,
        total_entries=total_entries,
        has_prev=has_prev,
        has_next=has_next,
        prev_num=prev_num,
        next_num=next_num,
        page_nums=page_nums,
        current_page=current_page,
        now=now,
        status_filter=status_filter,  # NEW: Pass status filter to template
        status_counts=status_counts # NEW: Pass status counts to template
        )

@bp.route("/assigned_orders", methods=["GET", "POST"])
@login_required
def assigned_orders():
    print("Accessed /assigned_orders route")
    
    form = ShipDocumentEntryForm()
    form.csrf_token.data = form.csrf_token._value()

    shipment_types = ShipmentType.query.filter_by(company_id=current_user.company_id).all()
    form.shipTypeid.choices = [(st.id, st.shipment_name) for st in shipment_types]
    print(f"Loaded shipment types: {shipment_types}")

    customers = Customer.query.filter_by(company_id=current_user.company_id).order_by(Customer.customer_name).all()
    form.customer_id.choices = [
        (c.id, f"{c.customer_name} ({c.customer_id})") for c in customers
    ]
    print(f"Loaded customers: {customers}")

    if request.method == "POST":
        print("POST request received")
        shipment_type_id = request.form.get('shipTypeid', type=int)
        if shipment_type_id:
            # Load ship categories for the selected shipment type
            ship_categories = ShipCategory.query.filter_by(
                shipmentType=shipment_type_id
            ).all()
            form.shipCategory.choices = [(sc.id, sc.catname) for sc in ship_categories]
            
            # Load document statuses for the selected shipment type
            doc_statuses = DocumentStatus.query.filter_by(
                doctypeid=shipment_type_id
            ).all()
            form.docStatusID.choices = [(ds.docStatusID, ds.docStatusName) for ds in doc_statuses]

            new_status = DocumentStatus.query.filter(
                DocumentStatus.docStatusName.ilike('new')
            ).first()
            
            if new_status:
                # Set the default value for docStatusID to the "New" status
                form.docStatusID.data = new_status.docStatusID
                
                # Add this as the only choice
                form.docStatusID.choices = [(new_status.docStatusID, new_status.docStatusName)]

        if form.validate_on_submit():
            print("Form validated successfully")
            try:
                last_doc = (
                    ShipDocumentEntryMaster.query.filter_by(
                        shipTypeid=form.shipTypeid.data
                    )
                    .order_by(ShipDocumentEntryMaster.docnum.desc())
                    .first()
                )
                print(f"Last document: {last_doc}")

                new_doc_num = 1 if not last_doc else last_doc.docnum + 1
                print(f"New document number: {new_doc_num}")

                shipment_type = ShipmentType.query.get(form.shipTypeid.data)
                doc_code = shipment_type.docCode
                doc_serial = f"{doc_code}{new_doc_num:04d}"
                print(f"Generated doc serial: {doc_serial}")

                entry = ShipDocumentEntryMaster(
                    shipTypeid=form.shipTypeid.data,
                    docCode=doc_code,
                    docnum=new_doc_num,
                    docserial=doc_serial,
                    dateCreated=get_sri_lanka_time(),
                    dateSubmitted=get_sri_lanka_time(),  # Added this line to ensure dateSubmitted is set
                    dealineDate=form.dealineDate.data,
                    docStatusID=form.docStatusID.data,
                    custComment=form.custComment.data,
                    cusOriginalReady=form.cusOriginalReady.data if hasattr(form, 'cusOriginalReady') else False,
                    shipCategory=form.shipCategory.data,
                    customer_id=form.customer_id.data,
                    user_id=current_user.id,
                    company_id=current_user.company_id,
                    docLevel=1  # Set docLevel to 1 (Submitted) to ensure it appears in the list
                )

                db.session.add(entry)
                db.session.commit()
                print("Document entry committed to database")

                # For AJAX requests, return JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': True,
                        'message': 'Document entry created successfully!',
                        'entry_id': entry.id
                    })
                
                flash("Document entry created successfully!", "success")
                return redirect(url_for("masters.assigned_orders"))
            except Exception as e:
                db.session.rollback()
                print(f"Error during document entry creation: {e}")
                
                # For AJAX requests, return JSON error
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'message': f'Error creating document entry: {str(e)}'
                    })
                
                flash(f"Error creating document entry", "error")
                print(f"Error creating document entry: {str(e)}")

        else:
            print(f"Form validation failed: {form.errors}")
            # For AJAX requests, return JSON with validation errors
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'Form validation failed',
                    'errors': form.errors
                })
            
            # For regular form submissions, flash the errors
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error in {getattr(form, field).label.text}", "error")
                    print(f"Error in {getattr(form, field).label.text}: {error}")

    # Get assigned entry IDs for the current user
    assigned_entry_ids = db.session.query(EntryAssignmentHistory.entry_id).filter(
        EntryAssignmentHistory.assigned_to_user_id == current_user.id,
        EntryAssignmentHistory.currently_assigned == True
    ).subquery()
    
    print(f"Found assigned entries for user {current_user.id}")

    # Get filter parameters
    status_filter = request.args.get('status', '')  # NEW: Add status filter
    ship_type = request.args.get('ship_type', type=int)
    search_term = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    print(f"Filter params - Status: '{status_filter}', Ship Type: {ship_type}, Search: '{search_term}', Page: {page}, Per Page: {per_page}")

    # Build the query with assignment filter
    query = (
        ShipDocumentEntryMaster.query.join(
            ShipmentType, ShipDocumentEntryMaster.shipTypeid == ShipmentType.id
        )
        .join(ShipCategory, ShipDocumentEntryMaster.shipCategory == ShipCategory.id)
        .join(
            DocumentStatus,
            ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID,
        )
        .join(
            CompanyAssignment,
            ShipDocumentEntryMaster.company_id == CompanyAssignment.company_id
        )
        .outerjoin(Customer, ShipDocumentEntryMaster.customer_id == Customer.id)
        .options(
            db.joinedload(ShipDocumentEntryMaster.shipment_type),
            db.joinedload(ShipDocumentEntryMaster.ship_category_rel),
            db.joinedload(ShipDocumentEntryMaster.document_status),
            db.joinedload(ShipDocumentEntryMaster.customer),
        )
        .filter(
            ShipDocumentEntryMaster.docLevel != 0,
            ShipDocumentEntryMaster.assigned_clearing_company_id == current_user.company_id,  # Existing filter
            ShipDocumentEntryMaster.id.in_(assigned_entry_ids),  # Filter by assigned entries
            CompanyAssignment.assigned_company_id == current_user.company_id,  # New filter
            CompanyAssignment.is_active == True  # New filter
        )
    )

     # ADD STATUS FILTERING LOGIC
    if status_filter:
        print(f"Applying status filter: '{status_filter}'")
        if status_filter.lower() == 'open':
            query = query.filter(db.func.lower(DocumentStatus.docStatusName).like('%open%'))
        elif status_filter.lower() == 'new':
            query = query.filter(db.func.lower(DocumentStatus.docStatusName).like('%new%'))
        elif status_filter.lower() == 'ongoing':
            query = query.filter(
                ~db.func.lower(DocumentStatus.docStatusName).like('%new%'),
                ~db.func.lower(DocumentStatus.docStatusName).like('%complete%'),
                ~db.func.lower(DocumentStatus.docStatusName).like('%done%'),
                ~db.func.lower(DocumentStatus.docStatusName).like('%open%')
            )
        elif status_filter.lower() == 'completed':
            query = query.filter(
                db.or_(
                    db.func.lower(DocumentStatus.docStatusName).like('%complete%'),
                    db.func.lower(DocumentStatus.docStatusName).like('%done%')
                )
            )
    
    
    # Apply ship_type filter if specified
    if ship_type:
        print(f"Applying ship type filter: {ship_type}")
        query = query.filter(ShipDocumentEntryMaster.shipTypeid == ship_type)

    # Apply search filter if specified
    if search_term:
        print(f"Applying search filter: '{search_term}'")
        search_pattern = f"%{search_term}%"
        query = query.filter(
            db.or_(
                ShipDocumentEntryMaster.docserial.ilike(search_pattern),
                Customer.customer_name.ilike(search_pattern),
                ShipCategory.catname.ilike(search_pattern)
                # Add more fields to search as needed
            )
        )

    # Get total count for pagination
    total_entries = query.count()
    print(f"Total filtered assigned entries: {total_entries}")

    # Apply sorting and pagination
    query = query.order_by(ShipDocumentEntryMaster.id.desc())
    paginated_entries = query.limit(per_page).offset((page - 1) * per_page).all()
    print(f"Retrieved {len(paginated_entries)} assigned entries for current page")

    # Calculate pagination variables
    max_pages = (total_entries + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page * per_page < total_entries
    prev_num = page - 1 if has_prev else None
    next_num = page + 1 if has_next else None
    current_page = page
    
    # Create a list of page numbers for pagination
    page_nums = []
    if max_pages <= 7:
        page_nums = list(range(1, max_pages + 1))
    else:
        if page <= 4:
            page_nums = list(range(1, 6)) + [None, max_pages]
        elif page >= max_pages - 3:
            page_nums = [1, None] + list(range(max_pages - 4, max_pages + 1))
        else:
            page_nums = [1, None, page-1, page, page+1, None, max_pages]

    # Calculate document counts for paginated entries
    for entry in paginated_entries:
        required_documents = ShipCatDocument.query.filter_by(
            shipCatid=entry.shipCategory, shipmentTypeid=entry.shipTypeid
        ).all()
        existing_attachments = ShipDocumentEntryAttachment.query.filter_by(
            shipDocEntryMasterID=entry.id
        ).all()

        entry.mandatory_docs_count = len(
            [doc for doc in required_documents if doc.isMandatory == 1]
        )
        entry.attached_docs_count = len(existing_attachments)

        entry.accepted_docs_count = len(
            [doc for doc in existing_attachments if doc.docAccepted == 'accepted']
        )
        
        entry.rejected_docs_count = len(
            [doc for doc in existing_attachments if doc.docAccepted == 'rejected']
        )

        print(
            f"Entry ID {entry.id}: Mandatory docs={entry.mandatory_docs_count}, "
            f"Attached={entry.attached_docs_count}, Accepted={entry.accepted_docs_count}, "
            f"Rejected={entry.rejected_docs_count}"
        )

    # ADD STATUS COUNTS CALCULATION
    base_query = (
        ShipDocumentEntryMaster.query.join(
            ShipmentType, ShipDocumentEntryMaster.shipTypeid == ShipmentType.id
        )
        .join(ShipCategory, ShipDocumentEntryMaster.shipCategory == ShipCategory.id)
        .join(
            DocumentStatus,
            ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID,
        )
        .join(
            CompanyAssignment,
            ShipDocumentEntryMaster.company_id == CompanyAssignment.company_id
        )
        .filter(
            ShipDocumentEntryMaster.docLevel != 0,
            ShipDocumentEntryMaster.assigned_clearing_company_id == current_user.company_id,
            ShipDocumentEntryMaster.id.in_(assigned_entry_ids),
            CompanyAssignment.assigned_company_id == current_user.company_id,
            CompanyAssignment.is_active == True
        )
    )    

    # Calculate counts for each status
    status_counts = {
        'total': base_query.count(),
        'open': base_query.filter(db.func.lower(DocumentStatus.docStatusName).like('%open%')).count(),
        'new': base_query.filter(db.func.lower(DocumentStatus.docStatusName).like('%new%')).count(),
        'ongoing': base_query.filter(
            ~db.func.lower(DocumentStatus.docStatusName).like('%open%'),
            ~db.func.lower(DocumentStatus.docStatusName).like('%new%'),
            ~db.func.lower(DocumentStatus.docStatusName).like('%complete%'),
            ~db.func.lower(DocumentStatus.docStatusName).like('%done%')
        ).count(),
        'completed': base_query.filter(
            db.or_(
                db.func.lower(DocumentStatus.docStatusName).like('%complete%'),
                db.func.lower(DocumentStatus.docStatusName).like('%done%')
            )
        ).count()
    }

    # Get all shipment types for filter dropdown
    shipment_types = ShipmentType.query.filter_by(company_id=current_user.company_id).all()
    
    # Pass the current date/time for deadline calculations
    now = get_sri_lanka_time()
    
    return render_template(
        "masters/assigned_orders.html",  # Different template name
        title="Assigned Orders",
        form=form,
        entries=paginated_entries,  # Use paginated entries instead of all entries
        shipment_types=shipment_types,
        total_entries=total_entries,
        has_prev=has_prev,
        has_next=has_next,
        prev_num=prev_num,
        next_num=next_num,
        page_nums=page_nums,
        current_page=current_page,
        now=now,
        status_filter=status_filter,  # NEW: Pass status filter to template
        status_counts=status_counts  # NEW: Pass status counts to template
    )


from sqlalchemy.orm import aliased

@bp.route("/assigned_agents", methods=["GET", "POST"])
@login_required
def assigned_agents():
    print("Accessed /assigned_agents route")
    
    form = ShipDocumentEntryForm()
    form.csrf_token.data = form.csrf_token._value()

    shipment_types = ShipmentType.query.filter_by(company_id=current_user.company_id).all()
    form.shipTypeid.choices = [(st.id, st.shipment_name) for st in shipment_types]
    print(f"Loaded shipment types: {shipment_types}")

    customers = Customer.query.filter_by(company_id=current_user.company_id).order_by(Customer.customer_name).all()
    form.customer_id.choices = [
        (c.id, f"{c.customer_name} ({c.customer_id})") for c in customers
    ]
    print(f"Loaded customers: {customers}")

    if request.method == "POST":
        print("POST request received")
        shipment_type_id = request.form.get('shipTypeid', type=int)
        if shipment_type_id:
            # Load ship categories for the selected shipment type
            ship_categories = ShipCategory.query.filter_by(
                shipmentType=shipment_type_id
            ).all()
            form.shipCategory.choices = [(sc.id, sc.catname) for sc in ship_categories]
            
            # Load document statuses for the selected shipment type
            doc_statuses = DocumentStatus.query.filter_by(
                doctypeid=shipment_type_id
            ).all()
            form.docStatusID.choices = [(ds.docStatusID, ds.docStatusName) for ds in doc_statuses]

            new_status = DocumentStatus.query.filter(
                DocumentStatus.docStatusName.ilike('new')
            ).first()
            
            if new_status:
                # Set the default value for docStatusID to the "New" status
                form.docStatusID.data = new_status.docStatusID
                
                # Add this as the only choice
                form.docStatusID.choices = [(new_status.docStatusID, new_status.docStatusName)]

        if form.validate_on_submit():
            print("Form validated successfully")
            try:
                last_doc = (
                    ShipDocumentEntryMaster.query.filter_by(
                        shipTypeid=form.shipTypeid.data
                    )
                    .order_by(ShipDocumentEntryMaster.docnum.desc())
                    .first()
                )
                print(f"Last document: {last_doc}")

                new_doc_num = 1 if not last_doc else last_doc.docnum + 1
                print(f"New document number: {new_doc_num}")

                shipment_type = ShipmentType.query.get(form.shipTypeid.data)
                doc_code = shipment_type.docCode
                doc_serial = f"{doc_code}{new_doc_num:04d}"
                print(f"Generated doc serial: {doc_serial}")

                entry = ShipDocumentEntryMaster(
                    shipTypeid=form.shipTypeid.data,
                    docCode=doc_code,
                    docnum=new_doc_num,
                    docserial=doc_serial,
                    dateCreated=get_sri_lanka_time(),
                    dateSubmitted=get_sri_lanka_time(),  # Added this line to ensure dateSubmitted is set
                    dealineDate=form.dealineDate.data,
                    docStatusID=form.docStatusID.data,
                    custComment=form.custComment.data,
                    cusOriginalReady=form.cusOriginalReady.data if hasattr(form, 'cusOriginalReady') else False,
                    shipCategory=form.shipCategory.data,
                    customer_id=form.customer_id.data,
                    user_id=current_user.id,
                    company_id=current_user.company_id,
                    docLevel=1  # Set docLevel to 1 (Submitted) to ensure it appears in the list
                )

                db.session.add(entry)
                db.session.commit()
                print("Document entry committed to database")

                # For AJAX requests, return JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': True,
                        'message': 'Document entry created successfully!',
                        'entry_id': entry.id
                    })
                
                flash("Document entry created successfully!", "success")
                return redirect(url_for("masters.assigned_agents"))
            except Exception as e:
                db.session.rollback()
                print(f"Error during document entry creation: {e}")
                
                # For AJAX requests, return JSON error
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'message': f'Error creating document entry: {str(e)}'
                    })
                
                flash(f"Error creating document entry", "error")
                print(f"Error creating document entry: {str(e)}")

        else:
            print(f"Form validation failed: {form.errors}")
            # For AJAX requests, return JSON with validation errors
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'Form validation failed',
                    'errors': form.errors
                })
            
            # For regular form submissions, flash the errors
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error in {getattr(form, field).label.text}", "error")
                    print(f"Error in {getattr(form, field).label.text}: {error}")

    # Get assigned entry IDs for the current clearing agent
    assigned_clearing_agent_entry_ids = db.session.query(EntryClearingAgentHistory.entry_id).filter(
        EntryClearingAgentHistory.assigned_to_clearing_agent_id == current_user.id,
        EntryClearingAgentHistory.currently_assigned == True
    ).subquery()
    
    print(f"Found assigned clearing agent entries for user {current_user.id}")

    # Get filter parameters
    ship_type = request.args.get('ship_type', type=int)
    search_term = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    print(f"Filter params - Ship Type: {ship_type}, Search: '{search_term}', Page: {page}, Per Page: {per_page}")

    # Create alias for assigned user to get assignment info
    AssignedUser = aliased(User)

    # Build the query with clearing agent assignment filter
    query = (
        ShipDocumentEntryMaster.query.join(
            ShipmentType, ShipDocumentEntryMaster.shipTypeid == ShipmentType.id
        )
        .join(ShipCategory, ShipDocumentEntryMaster.shipCategory == ShipCategory.id)
        .join(
            DocumentStatus,
            ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID,
        )
        .outerjoin(Customer, ShipDocumentEntryMaster.customer_id == Customer.id)
        .outerjoin(  # Join for current user assignment
            EntryAssignmentHistory,
            db.and_(
                ShipDocumentEntryMaster.id == EntryAssignmentHistory.entry_id,
                EntryAssignmentHistory.currently_assigned == True
            )
        )
        .outerjoin(  # Join for assigned user info
            AssignedUser,
            EntryAssignmentHistory.assigned_to_user_id == AssignedUser.id
        )
        .options(
            db.joinedload(ShipDocumentEntryMaster.shipment_type),
            db.joinedload(ShipDocumentEntryMaster.ship_category_rel),
            db.joinedload(ShipDocumentEntryMaster.document_status),
            db.joinedload(ShipDocumentEntryMaster.customer),
        )
        .filter(
            ShipDocumentEntryMaster.docLevel != 0,
            ShipDocumentEntryMaster.id.in_(assigned_clearing_agent_entry_ids)  # Filter by clearing agent assignments
        )
        .add_columns(  # Add assigned user information
            AssignedUser.name.label('assigned_user_name'),
            AssignedUser.username.label('assigned_user_username'),
            EntryAssignmentHistory.assigned_date.label('assignment_date')
        )
    )

    # Apply ship_type filter if specified
    if ship_type:
        print(f"Applying ship type filter: {ship_type}")
        query = query.filter(ShipDocumentEntryMaster.shipTypeid == ship_type)

    # Apply search filter if specified
    if search_term:
        print(f"Applying search filter: '{search_term}'")
        search_pattern = f"%{search_term}%"
        query = query.filter(
            db.or_(
                ShipDocumentEntryMaster.docserial.ilike(search_pattern),
                Customer.customer_name.ilike(search_pattern),
                ShipCategory.catname.ilike(search_pattern),
                AssignedUser.name.ilike(search_pattern)
                # Add more fields to search as needed
            )
        )

    # Get total count for pagination
    total_entries = query.count()
    print(f"Total filtered assigned clearing agent entries: {total_entries}")

    # Apply sorting and pagination
    query = query.order_by(ShipDocumentEntryMaster.id.desc())
    query_results = query.limit(per_page).offset((page - 1) * per_page).all()
    print(f"Retrieved {len(query_results)} assigned clearing agent entries for current page")

    # Process the results to extract entries and assignment info
    paginated_entries = []
    for result in query_results:
        entry = result[0]  # The ShipDocumentEntryMaster object
        
        # Add assignment information to the entry object
        if result.assigned_user_name:
            entry.assigned_user_name = result.assigned_user_name
            entry.assigned_user_username = result.assigned_user_username
            entry.assignment_date = result.assignment_date
        else:
            entry.assigned_user_name = None
            entry.assigned_user_username = None
            entry.assignment_date = None
        
        paginated_entries.append(entry)

    # Calculate pagination variables
    max_pages = (total_entries + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page * per_page < total_entries
    prev_num = page - 1 if has_prev else None
    next_num = page + 1 if has_next else None
    current_page = page
    
    # Create a list of page numbers for pagination
    page_nums = []
    if max_pages <= 7:
        page_nums = list(range(1, max_pages + 1))
    else:
        if page <= 4:
            page_nums = list(range(1, 6)) + [None, max_pages]
        elif page >= max_pages - 3:
            page_nums = [1, None] + list(range(max_pages - 4, max_pages + 1))
        else:
            page_nums = [1, None, page-1, page, page+1, None, max_pages]

    # Calculate document counts for paginated entries
    for entry in paginated_entries:
        required_documents = ShipCatDocument.query.filter_by(
            shipCatid=entry.shipCategory, shipmentTypeid=entry.shipTypeid
        ).all()
        existing_attachments = ShipDocumentEntryAttachment.query.filter_by(
            shipDocEntryMasterID=entry.id
        ).all()

        entry.mandatory_docs_count = len(
            [doc for doc in required_documents if doc.isMandatory == 1]
        )
        entry.attached_docs_count = len(existing_attachments)

        entry.accepted_docs_count = len(
            [doc for doc in existing_attachments if doc.docAccepted == 'accepted']
        )
        
        entry.rejected_docs_count = len(
            [doc for doc in existing_attachments if doc.docAccepted == 'rejected']
        )

        entry.resubmission_stats = entry.get_resubmission_stats()

        print(
            f"Entry ID {entry.id}: Mandatory docs={entry.mandatory_docs_count}, "
            f"Attached={entry.attached_docs_count}, Accepted={entry.accepted_docs_count}, "
            f"Rejected={entry.rejected_docs_count}, "
            f"Resubmissions={entry.resubmission_stats['resubmitted_count']}/{entry.resubmission_stats['rejected_count']}, "
            f"Assigned User={entry.assigned_user_name}"
        )

    # Get all shipment types for filter dropdown
    shipment_types = ShipmentType.query.filter_by(company_id=current_user.company_id).all()
    
    # Pass the current date/time for deadline calculations
    now = get_sri_lanka_time()
    
    return render_template(
        "masters/assigned_agents.html",  # Different template name
        title="Assigned Clearing Agent Orders",
        form=form,
        entries=paginated_entries,  # Use paginated entries instead of all entries
        shipment_types=shipment_types,
        total_entries=total_entries,
        has_prev=has_prev,
        has_next=has_next,
        prev_num=prev_num,
        next_num=next_num,
        page_nums=page_nums,
        current_page=current_page,
        now=now
    )


@bp.route("/clearing_company", methods=["GET", "POST"])
@login_required
def clearing_company():
    print("Accessed /clearing_company route")
    
    form = ShipDocumentEntryForm()
    form.csrf_token.data = form.csrf_token._value()

    shipment_types = ShipmentType.query.filter_by(company_id=current_user.company_id).all()
    form.shipTypeid.choices = [(st.id, st.shipment_name) for st in shipment_types]
    print(f"Loaded shipment types: {shipment_types}")

    customers = Customer.query.filter_by(company_id=current_user.company_id).order_by(Customer.customer_name).all()
    form.customer_id.choices = [
        (c.id, f"{c.customer_name} ({c.customer_id})") for c in customers
    ]
    print(f"Loaded customers: {customers}")

    if request.method == "POST":
        print("POST request received")
        shipment_type_id = request.form.get('shipTypeid', type=int)
        if shipment_type_id:
            # Load ship categories for the selected shipment type
            ship_categories = ShipCategory.query.filter_by(
                shipmentType=shipment_type_id
            ).all()
            form.shipCategory.choices = [(sc.id, sc.catname) for sc in ship_categories]
            
            # Load document statuses for the selected shipment type
            doc_statuses = DocumentStatus.query.filter_by(
                doctypeid=shipment_type_id
            ).all()
            form.docStatusID.choices = [(ds.docStatusID, ds.docStatusName) for ds in doc_statuses]

            new_status = DocumentStatus.query.filter(
                DocumentStatus.docStatusName.ilike('new')
            ).first()
            
            if new_status:
                # Set the default value for docStatusID to the "New" status
                form.docStatusID.data = new_status.docStatusID
                
                # Add this as the only choice
                form.docStatusID.choices = [(new_status.docStatusID, new_status.docStatusName)]

        if form.validate_on_submit():
            print("Form validated successfully")
            try:
                last_doc = (
                    ShipDocumentEntryMaster.query.filter_by(
                        shipTypeid=form.shipTypeid.data
                    )
                    .order_by(ShipDocumentEntryMaster.docnum.desc())
                    .first()
                )
                print(f"Last document: {last_doc}")

                new_doc_num = 1 if not last_doc else last_doc.docnum + 1
                print(f"New document number: {new_doc_num}")

                shipment_type = ShipmentType.query.get(form.shipTypeid.data)
                doc_code = shipment_type.docCode
                doc_serial = f"{doc_code}{new_doc_num:04d}"
                print(f"Generated doc serial: {doc_serial}")

                entry = ShipDocumentEntryMaster(
                    shipTypeid=form.shipTypeid.data,
                    docCode=doc_code,
                    docnum=new_doc_num,
                    docserial=doc_serial,
                    dateCreated=get_sri_lanka_time(),
                    dateSubmitted=get_sri_lanka_time(),
                    dealineDate=form.dealineDate.data,
                    docStatusID=form.docStatusID.data,
                    custComment=form.custComment.data,
                    cusOriginalReady=form.cusOriginalReady.data if hasattr(form, 'cusOriginalReady') else False,
                    shipCategory=form.shipCategory.data,
                    customer_id=form.customer_id.data,
                    user_id=current_user.id,
                    company_id=current_user.company_id,
                    docLevel=1,
                    # NEW: Assign the document to the current clearing company
                    assigned_clearing_company_id=current_user.id
                )

                db.session.add(entry)
                db.session.commit()
                print("Document entry committed to database")

                # For AJAX requests, return JSON
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': True,
                        'message': 'Document entry created successfully!',
                        'entry_id': entry.id
                    })
                
                flash("Document entry created successfully!", "success")
                return redirect(url_for("masters.clearing_company"))
            except Exception as e:
                db.session.rollback()
                print(f"Error during document entry creation: {e}")
                
                # For AJAX requests, return JSON error
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'message': f'Error creating document entry: {str(e)}'
                    })
                
                flash(f"Error creating document entry", "error")
                print(f"Error creating document entry: {str(e)}")

        else:
            print(f"Form validation failed: {form.errors}")
            # For AJAX requests, return JSON with validation errors
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'Form validation failed',
                    'errors': form.errors
                })
            
            # For regular form submissions, flash the errors
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error in {getattr(form, field).label.text}", "error")
                    print(f"Error in {getattr(form, field).label.text}: {error}")

    # MODIFIED: Get entries assigned to this clearing company
    # Method 1: Direct assignment via assigned_clearing_company_id
    directly_assigned_entry_ids = db.session.query(ShipDocumentEntryMaster.id).filter(
        ShipDocumentEntryMaster.assigned_clearing_company_id == current_user.id
    ).subquery()
    
    # Method 2: Historical assignment via EntryClearingCompanyHistory (for backward compatibility)
    historically_assigned_entry_ids = db.session.query(EntryClearingCompanyHistory.entry_id).filter(
        EntryClearingCompanyHistory.assigned_to_clearing_company_id == current_user.id,
        EntryClearingCompanyHistory.currently_assigned == True
    ).subquery()
    
    print(f"Found directly assigned entries for clearing company {current_user.id}")
    print(f"Found historically assigned entries for clearing company {current_user.id}")

    # Get filter parameters
    ship_type = request.args.get('ship_type', type=int)
    search_term = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    print(f"Filter params - Ship Type: {ship_type}, Search: '{search_term}', Page: {page}, Per Page: {per_page}")

    # Create alias for assigned user to get assignment info
    AssignedUser = aliased(User)

    # Build the query with BOTH assignment methods
    query = (
        ShipDocumentEntryMaster.query.join(
            ShipmentType, ShipDocumentEntryMaster.shipTypeid == ShipmentType.id
        )
        .join(ShipCategory, ShipDocumentEntryMaster.shipCategory == ShipCategory.id)
        .join(
            DocumentStatus,
            ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID,
        )
        .outerjoin(Customer, ShipDocumentEntryMaster.customer_id == Customer.id)
        .outerjoin(  # Join for current user assignment
            EntryAssignmentHistory,
            db.and_(
                ShipDocumentEntryMaster.id == EntryAssignmentHistory.entry_id,
                EntryAssignmentHistory.currently_assigned == True
            )
        )
        .outerjoin(  # Join for assigned user info
            AssignedUser,
            EntryAssignmentHistory.assigned_to_user_id == AssignedUser.id
        )
        .options(
            db.joinedload(ShipDocumentEntryMaster.shipment_type),
            db.joinedload(ShipDocumentEntryMaster.ship_category_rel),
            db.joinedload(ShipDocumentEntryMaster.document_status),
            db.joinedload(ShipDocumentEntryMaster.customer),
        )
        .filter(
            ShipDocumentEntryMaster.docLevel != 0,
            ShipDocumentEntryMaster.company_id == current_user.company_id,
            # MODIFIED: Filter by EITHER direct assignment OR historical assignment
            db.or_(
                ShipDocumentEntryMaster.id.in_(directly_assigned_entry_ids),
                ShipDocumentEntryMaster.id.in_(historically_assigned_entry_ids)
            )
        )
        .add_columns(  # Add assigned user information
            AssignedUser.name.label('assigned_user_name'),
            AssignedUser.username.label('assigned_user_username'),
            EntryAssignmentHistory.assigned_date.label('assignment_date')
        )
    )

    # Apply ship_type filter if specified
    if ship_type:
        print(f"Applying ship type filter: {ship_type}")
        query = query.filter(ShipDocumentEntryMaster.shipTypeid == ship_type)

    # Apply search filter if specified
    if search_term:
        print(f"Applying search filter: '{search_term}'")
        search_pattern = f"%{search_term}%"
        query = query.filter(
            db.or_(
                ShipDocumentEntryMaster.docserial.ilike(search_pattern),
                Customer.customer_name.ilike(search_pattern),
                ShipCategory.catname.ilike(search_pattern),
                AssignedUser.name.ilike(search_pattern)
                # Add more fields to search as needed
            )
        )

    # Get total count for pagination
    total_entries = query.count()
    print(f"Total filtered assigned clearing company entries: {total_entries}")

    # Apply sorting and pagination
    query = query.order_by(ShipDocumentEntryMaster.id.desc())
    query_results = query.limit(per_page).offset((page - 1) * per_page).all()
    print(f"Retrieved {len(query_results)} assigned clearing company entries for current page")

    # Process the results to extract entries and assignment info
    paginated_entries = []
    for result in query_results:
        entry = result[0]  # The ShipDocumentEntryMaster object
        
        # Add assignment information to the entry object
        if result.assigned_user_name:
            entry.assigned_user_name = result.assigned_user_name
            entry.assigned_user_username = result.assigned_user_username
            entry.assignment_date = result.assignment_date
        else:
            entry.assigned_user_name = None
            entry.assigned_user_username = None
            entry.assignment_date = None
        
        # Add clearing company assignment info
        if entry.assigned_clearing_company_id == current_user.id:
            entry.assignment_method = "Direct Assignment"
        else:
            entry.assignment_method = "Historical Assignment"
        
        paginated_entries.append(entry)

    # Calculate pagination variables
    max_pages = (total_entries + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page * per_page < total_entries
    prev_num = page - 1 if has_prev else None
    next_num = page + 1 if has_next else None
    current_page = page
    
    # Create a list of page numbers for pagination
    page_nums = []
    if max_pages <= 7:
        page_nums = list(range(1, max_pages + 1))
    else:
        if page <= 4:
            page_nums = list(range(1, 6)) + [None, max_pages]
        elif page >= max_pages - 3:
            page_nums = [1, None] + list(range(max_pages - 4, max_pages + 1))
        else:
            page_nums = [1, None, page-1, page, page+1, None, max_pages]

    # Calculate document counts for paginated entries
    for entry in paginated_entries:
        required_documents = ShipCatDocument.query.filter_by(
            shipCatid=entry.shipCategory, shipmentTypeid=entry.shipTypeid
        ).all()
        existing_attachments = ShipDocumentEntryAttachment.query.filter_by(
            shipDocEntryMasterID=entry.id
        ).all()

        entry.mandatory_docs_count = len(
            [doc for doc in required_documents if doc.isMandatory == 1]
        )
        entry.attached_docs_count = len(existing_attachments)

        entry.accepted_docs_count = len(
            [doc for doc in existing_attachments if doc.docAccepted == 'accepted']
        )
        
        entry.rejected_docs_count = len(
            [doc for doc in existing_attachments if doc.docAccepted == 'rejected']
        )

        entry.resubmission_stats = entry.get_resubmission_stats()

        print(
            f"Entry ID {entry.id}: Mandatory docs={entry.mandatory_docs_count}, "
            f"Attached={entry.attached_docs_count}, Accepted={entry.accepted_docs_count}, "
            f"Rejected={entry.rejected_docs_count}, "
            f"Resubmissions={entry.resubmission_stats['resubmitted_count']}/{entry.resubmission_stats['rejected_count']}, "
            f"Assignment Method={entry.assignment_method}"
        )

    # Get all shipment types for filter dropdown
    shipment_types = ShipmentType.query.filter_by(company_id=current_user.company_id).all()
    
    # Pass the current date/time for deadline calculations
    now = get_sri_lanka_time()
    
    return render_template(
        "masters/clearing_company.html",
        title="Assigned Clearing Company Orders",
        form=form,
        entries=paginated_entries,
        shipment_types=shipment_types,
        total_entries=total_entries,
        has_prev=has_prev,
        has_next=has_next,
        prev_num=prev_num,
        next_num=next_num,
        page_nums=page_nums,
        current_page=current_page,
        now=now
    )


@bp.route("/s/<int:order_id>", methods=["GET", "POST"])
@login_required
def edit_order(order_id):
    print(f"Accessed /s/{order_id} route")

    order = Order.query.get_or_404(order_id)
    form = OrderForm(obj=order)
    print(f"Loaded order: {order}")

    form.customer_id.choices = [(c.id, c.name) for c in Customer.query.all()]
    print("Customer choices populated")

    if form.validate_on_submit():
        print("Form validated successfully")
        try:
            order.customer_id = form.customer_id.data
            order.order_date = form.order_date.data
            order.status = form.status.data
            order.description = form.description.data

            order.items = []
            total_amount = 0
            print("Processing order items")

            for item in form.items.data:
                total_price = item["quantity"] * item["unit_price"]
                order_item = OrderItem(
                    item_name=item["item_name"],
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    total_price=total_price,
                    description=item["description"],
                )
                order.items.append(order_item)
                total_amount += total_price
                print(f"Added item: {order_item}")

            order.total_amount = total_amount
            print(f"Total order amount: {total_amount}")

            db.session.commit()
            print("Order updated and committed to database")
            flash("Order updated successfully!", "success")
            return redirect(url_for("masters.orders"))

        except Exception as e:
            db.session.rollback()
            print(f"Error updating order: {e}")
            flash(f"Error updating order", "danger")

    return render_template("masters/edit_order.html", form=form, order=order)


@bp.route("/orders/<int:order_id>/delete", methods=["POST"])
@login_required
def delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    try:
        db.session.delete(order)
        db.session.commit()
        flash("Order deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting order", "danger")
        print(f"Error deleting order: {str(e)}")

    return redirect(url_for("masters.orders"))


@bp.route("/orders/<int:order_id>/documents", methods=["POST"])
@login_required
def upload_order_document(order_id):
    order = Order.query.get_or_404(order_id)

    if "document" not in request.files:
        flash("No file selected", "danger")
        return redirect(url_for("masters.edit_order", order_id=order_id))

    file = request.files["document"]
    if file.filename == "":
        flash("No file selected", "danger")
        return redirect(url_for("masters.edit_order", order_id=order_id))

    try:
        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"

        # Upload to S3
        s3_client = get_s3_client()
        s3_client.upload_fileobj(
            file,
            current_app.config["S3_BUCKET"],
            f"order_documents/{unique_filename}",
            ExtraArgs={"ContentType": file.content_type},
        )

        # Create document record
        document = OrderDocument(
            order_id=order_id,
            document_name=filename,
            document_type=request.form.get("document_type", "Other"),
            file_path=f"order_documents/{unique_filename}",
            uploaded_by=current_user.id,
        )

        db.session.add(document)
        db.session.commit()

        flash("Document uploaded successfully!", "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error uploading document", "danger")
        print(f"Error uploading document: {str(e)}")

    return redirect(url_for("masters.edit_order", order_id=order_id))


@bp.route("/orders/<int:order_id>/documents/<int:doc_id>/delete", methods=["POST"])
@login_required
def delete_order_document(order_id, doc_id):
    document = OrderDocument.query.get_or_404(doc_id)
    try:
        # Delete from S3
        s3_client = get_s3_client()
        s3_client.delete_object(
            Bucket=current_app.config["S3_BUCKET"], Key=document.file_path
        )

        # Delete from database
        db.session.delete(document)
        db.session.commit()

        flash("Document deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting document", "danger")
        print(f"Error deleting document: {str(e)}")

    return redirect(url_for("masters.edit_order", order_id=order_id))


@bp.route("/orders/<int:entry_id>/edit", methods=["GET", "POST"])
@login_required
def edit_entry(entry_id):
    entry = ShipDocumentEntryMaster.query.options(
        db.joinedload(ShipDocumentEntryMaster.customer)
    ).get_or_404(entry_id)

    doc_statuses = DocumentStatus.query.filter_by(doctypeid=entry.shipTypeid).all()

    form = ShipDocumentEntryForm()
    form.docStatusID.choices = [(ds.docStatusID, ds.docStatusName) for ds in doc_statuses]

    # Load eligible users for assignment (role='user')
    eligible_users = User.query.filter(
        User.company_id == entry.assigned_clearing_company_id,
        User.role.in_(["user", "base_user"])
    ).all()

    
    # Load clearing agents (role_id=5)
    clearing_agents = User.query.filter_by(company_id=entry.company_id, role_id=5).all()

    if request.method == "POST":
        form.docStatusID.process(request.form)
        assigned_user_id = request.form.get("assigned_to")
        assigned_clearing_agent_id = request.form.get("assigned_clearing_agent")

        try:
            entry.docStatusID = form.docStatusID.data
            db.session.commit()

            # Regular User Assignment Logic
            if assigned_user_id:
                assigned_user_id = int(assigned_user_id)

                # Get current assignment
                current_assignment = EntryAssignmentHistory.query.filter_by(
                    entry_id=entry.id, currently_assigned=True
                ).first()

                if not current_assignment or current_assignment.assigned_to_user_id != assigned_user_id:
                    # Mark previous assignment inactive
                    if current_assignment:
                        current_assignment.currently_assigned = False
                        current_assignment.till_date = get_sri_lanka_time()

                    # Add new assignment
                    new_assignment = EntryAssignmentHistory(
                        entry_id=entry.id,
                        assigned_to_user_id=assigned_user_id,
                        company_id=entry.company_id,
                        assigned_date=get_sri_lanka_time(),
                        currently_assigned=True
                    )
                    db.session.add(new_assignment)

                    # Send email notification
                    assigned_user = User.query.get(assigned_user_id)
                    entry_docserial = entry.docserial
                    customer = entry.customer.short_name

                    send_email(
                        subject=f"{entry_docserial} - A New Entry Has Been Assigned to You",
                        recipient=assigned_user.email,
                        template="email/new_entry_assignment.html",
                        name=assigned_user.name,
                        entry_docserial=entry_docserial,
                        customer=customer,
                    )

            # Clearing Agent Assignment Logic
            if assigned_clearing_agent_id:
                assigned_clearing_agent_id = int(assigned_clearing_agent_id)

                # Get current clearing agent assignment
                current_clearing_assignment = EntryClearingAgentHistory.query.filter_by(
                    entry_id=entry.id, currently_assigned=True
                ).first()

                if not current_clearing_assignment or current_clearing_assignment.assigned_to_clearing_agent_id != assigned_clearing_agent_id:
                    # Mark previous clearing agent assignment inactive
                    if current_clearing_assignment:
                        current_clearing_assignment.currently_assigned = False
                        current_clearing_assignment.till_date = get_sri_lanka_time()

                    # Add new clearing agent assignment
                    new_clearing_assignment = EntryClearingAgentHistory(
                        entry_id=entry.id,
                        assigned_to_clearing_agent_id=assigned_clearing_agent_id,
                        company_id=entry.assigned_clearing_company_id,
                        assigned_date=get_sri_lanka_time(),
                        currently_assigned=True
                    )
                    db.session.add(new_clearing_assignment)

                    # Update the master record
                    entry.assigned_clearing_agent_id = assigned_clearing_agent_id

                    # Send email notification to clearing agent
                    assigned_clearing_agent = User.query.get(assigned_clearing_agent_id)
                    entry_docserial = entry.docserial
                    customer = entry.customer.short_name

                    send_email(
                        subject=f"{entry_docserial} - A New Entry Has Been Assigned to You (Clearing Agent)",
                        recipient=assigned_clearing_agent.email,
                        template="email/new_clearing_agent_assignment.html",
                        name=assigned_clearing_agent.name,
                        entry_docserial=entry_docserial,
                        customer=customer,
                    )

            db.session.commit()
            flash("Document status and assignments updated successfully!", "success")
            return redirect(url_for("masters.orders"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error updating document status or assignments", "error")
            print(f"Error updating document status or assignments: {str(e)}")

    form.docStatusID.data = entry.docStatusID

    # Get current assignments
    current_assignment = EntryAssignmentHistory.query.filter_by(entry_id=entry.id, currently_assigned=True).first()
    current_user_id = current_assignment.assigned_to_user_id if current_assignment else None

    current_clearing_assignment = EntryClearingAgentHistory.query.filter_by(entry_id=entry.id, currently_assigned=True).first()
    current_clearing_agent_id = current_clearing_assignment.assigned_to_clearing_agent_id if current_clearing_assignment else None

    return render_template(
        "masters/edit_entry.html",
        title="Edit Entry",
        form=form,
        entry=entry,
        eligible_users=eligible_users,
        clearing_agents=clearing_agents,
        current_user_id=current_user_id,
        current_clearing_agent_id=current_clearing_agent_id
    )




@bp.route("/orders/<int:entry_id>/attachments")
@login_required
def entry_attachments(entry_id):
    entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
    return render_template(
        "masters/entry_attachments.html", title="Entry Attachments", entry=entry
    )


@bp.route("/orders/document/<int:attachment_id>/status", methods=["POST"])
@login_required
def update_document_status(attachment_id):
    """Update the status (accept/reject) of a document attachment and maintain history"""
    try:
        # Get the attachment
        attachment = ShipDocumentEntryAttachment.query.get_or_404(attachment_id)
        
        # Get data from request
        data = request.json
        status = data.get("status")  # "accepted" or "rejected"
        comments = data.get("comments", "")
        
        # Validate input
        if status not in ["accepted", "rejected"]:
            return jsonify(
                {"success": False, "message": "Invalid status. Use 'accepted' or 'rejected'."}
            ), 200  # Using 200 to prevent Promise rejection
            
        # Comments are required for rejected documents
        if status == "rejected" and not comments:
            return jsonify(
                {"success": False, "message": "Comments are required when rejecting a document."}
            ), 200  # Using 200 to prevent Promise rejection
        
        # Create history record - reference the original file path
        history_entry = ShipDocumentHistory(
            attachment_id=attachment.id,
            shipDocEntryMasterID=attachment.shipDocEntryMasterID,
            description=attachment.description,
            document_path=attachment.attachement_path,  # Use the original path
            action=status,
            note=attachment.note,
            action_comments=comments,
            user_id=current_user.id,
            customer_id=attachment.customer_id,
            created_at=get_sri_lanka_time()
        )
        
        db.session.add(history_entry)
        
        # Update the attachment
        attachment.docAccepted = status
        attachment.docAccepteDate = get_sri_lanka_time().date()
        attachment.docAccepteComments = comments
        attachment.docAccepteUserID = current_user.id

        # Only update docLevel if the document is rejected
        if status == "rejected":
            ship_doc_entry = ShipDocumentEntryMaster.query.get(attachment.shipDocEntryMasterID)
            if ship_doc_entry:
                ship_doc_entry.docLevel = 2
                print("Doc Level set to Referred Back")
        
        # Save to database
        db.session.commit()
        
        # Send email notification to customer
        try:
            # Get the shipment entry to access customer details
            ship_doc_entry = ShipDocumentEntryMaster.query.get(attachment.shipDocEntryMasterID)
            
            if ship_doc_entry and ship_doc_entry.customer and ship_doc_entry.customer.email:
                # Prepare email data
                email_data = {
                    'customer_name': ship_doc_entry.customer.customer_name,
                    'document_name': attachment.description,
                    'document_status': status,
                    'status_date': attachment.docAccepteDate.strftime('%Y-%m-%d'),
                    'comments': comments,
                    'entry_id': ship_doc_entry.id,
                    'docserial': ship_doc_entry.docserial,
                    'company_name': ship_doc_entry.company.company_name if ship_doc_entry.company else 'Your Service Provider',
                    'reviewer_name': current_user.name or current_user.username,
                    'has_comments': bool(comments.strip())
                }
                
                # Determine subject based on status
                subject = f"Document {'Accepted' if status == 'accepted' else 'Rejected'} - Entry {ship_doc_entry.docserial}"
                
                # Send email
                send_email(
                    subject=subject,
                    recipient=ship_doc_entry.customer.email,
                    template="email/document_status_notification.html",
                    **email_data
                )
                
                print(f"Status update email sent to customer: {ship_doc_entry.customer.email}")
                
        except Exception as email_error:
            # Log email error but don't fail the status update
            print(f"Error sending status update email: {str(email_error)}")
            import traceback
            traceback.print_exc()
        
        return jsonify({
            "success": True,
            "message": f"Document has been {status} successfully with history recorded.",
            "data": {
                "status": status,
                "date": attachment.docAccepteDate.isoformat(),
                "user": current_user.username,
                "history_id": history_entry.id
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating document status: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify(
            {"success": False, "message": f"An error occurred: {str(e)}"}
        ), 200  # Using 200 to prevent Promise rejection   



#ORDER SHIPMENT
#################################
@bp.route("/orders/shipment/<int:entry_id>", methods=["GET", "POST"])
@login_required
def order_shipment(entry_id):
    """Enhanced order shipment with step-based workflow selection"""
    # Print statement to log the start of the function
    print(f"Entering order_shipment route - Method: {request.method}")
    print(f"Entry ID: {entry_id}")

    os_shipment_types = OsShipmentType.query.all()
    sub_types = OsSubType.query.all()
    customer_categories = OsCustomerCategory.query.all()
    business_types = OsBusinessType.query.all()
    container_sizes = OsContainerSize.query.all()
    container_types = OsContainerType.query.all()
    job_types = OsJobType.query.all()

    # Get the entry and verify it belongs to the current user's company
    entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
    
    # Verify company access
    if entry.assigned_clearing_company_id != current_user.company_id:
        abort(403)  # Forbidden if trying to access entry from another company

    # Check if an OrderShipment already exists for this entry
    existing_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=entry_id).first()

    # Initialize variables
    shipment = existing_shipment
    import_containers = []
    export_containers = []
    expenses = []
    invoices = []
    documents = []
    containers_with_workflows = []
    selected_workflow_data = None
    available_workflows = []
    active_tab = request.args.get('tab', 'details')

    # Handle form submission
    if request.method == "POST":
        try:
            # Prepare shipment data from form
            shipment_data = {
                'ship_doc_entry_id': entry_id,
                'branch_id': request.form.get('branch_id') if request.form.get('branch_id') else None,
                'import_id': request.form.get('import_id') ,
                'shipment_deadline': request.form.get('shipment_deadline'),
                'bl_no': request.form.get('bl_no'),
                'license_number': request.form.get('license_number'),
                'primary_job_yn': request.form.get('primary_job_yn', 'N'),
                'primary_job': request.form.get('primary_job'),
                'shipment_type_id': request.form.get('shipment_type_id') if request.form.get('shipment_type_id') else None,
                'sub_type_id': request.form.get('sub_type') if request.form.get('sub_type') else None,
                'customer_category_id': request.form.get('customer_category') if request.form.get('customer_category') else None,
                'business_type_id': request.form.get('business_type') if request.form.get('business_type') else None,
                'customer_id': request.form.get('customer_id') if request.form.get('customer_id') else None,
                'billing_party_id': request.form.get('billing_party_id') if request.form.get('billing_party_id') else None,
                'clearing_agent': request.form.get('clearing_agent'),
                'contact_person': request.form.get('contact_person'),
                'sales_person_id': request.form.get('sales_person_id') if request.form.get('sales_person_id') else None,
                'cs_executive_id': request.form.get('cs_executive_id') if request.form.get('cs_executive_id') else None,
                'wharf_clerk_id': request.form.get('wharf_clerk_id') if request.form.get('wharf_clerk_id') else None,
                'po_no': request.form.get('po_no') if request.form.get('po_no') else None,
                'invoice_no': request.form.get('invoice_no') if request.form.get('invoice_no') else None,
                'customer_ref_no': request.form.get('customer_ref_no') if request.form.get('customer_ref_no') else None,
                'customs_dti_no': request.form.get('customs_dti_no') if request.form.get('customs_dti_no') else None,
                'mbl_number': request.form.get('mbl_number') if request.form.get('mbl_number') else None,
                'vessel': request.form.get('vessel') if request.form.get('vessel') else None,
                'voyage': request.form.get('voyage') if request.form.get('voyage') else None,
                'eta': request.form.get('eta') if request.form.get('eta') and request.form.get('eta').strip() else None,
                'shipper': request.form.get('shipper') if request.form.get('shipper') else None,
                'port_of_loading': request.form.get('port_of_loading') if request.form.get('port_of_loading') else None,
                'port_of_discharge': request.form.get('port_of_discharge') if request.form.get('port_of_discharge') else None,
                'job_type': request.form.get('job_type') if request.form.get('job_type') else None,
                'fcl_gate_out_date': request.form.get('fcl_gate_out_date') if request.form.get('fcl_gate_out_date') else None,
                'pod_datetime': request.form.get('pod_datetime') if request.form.get('pod_datetime') else None,
                'no_of_packages': request.form.get('no_of_packages') if request.form.get('no_of_packages') else None,
                'package_type': request.form.get('package_type') if request.form.get('package_type') else None,
                'cbm': request.form.get('cbm') if request.form.get('cbm') else None,
                'gross_weight': request.form.get('gross_weight') if request.form.get('gross_weight') else None,
                'cargo_description': request.form.get('cargo_description') if request.form.get('cargo_description') else None,
                'liner': request.form.get('liner') if request.form.get('liner') else None,
                'entrepot': request.form.get('entrepot') if request.form.get('entrepot') else None,
                'job_currency': request.form.get('job_currency') if request.form.get('job_currency') else None,
                'ex_rating_buying': request.form.get('ex_rating_buying') if request.form.get('ex_rating_buying') else None,
                'ex_rating_selling': request.form.get('ex_rating_selling') if request.form.get('ex_rating_selling') else None,
                'remarks': request.form.get('remarks') if request.form.get('remarks') else None,
                'onhold_yn': request.form.get('onhold_yn', 'N') if request.form.get('onhold_yn') else 'N',
                'onhold_reason': request.form.get('onhold_reason') if request.form.get('onhold_reason') else None,
                'cleared_date': request.form.get('cleared_date') if request.form.get('cleared_date') else None,
                'estimated_job_closing_date': request.form.get('estimated_job_closing_date') if request.form.get('estimated_job_closing_date') else None,
                'company_id': current_user.company_id,
                'created_at': get_sri_lanka_time(),
                'updated_at': get_sri_lanka_time()
            }


            FREE_DAYS = 5

            # ... inside your route where you update shipment.cleared_date ...
            FREE_DAYS = 5

            # ... inside your route where you update shipment.cleared_date ...
            cleared_date = request.form.get('cleared_date')
            print(f"Raw cleared_date from form: {cleared_date} (type: {type(cleared_date)})")

            if cleared_date:
                # Convert to date object if necessary
                if isinstance(cleared_date, str):
                    try:
                        cleared_date = datetime.strptime(cleared_date, "%Y-%m-%d").date()  # adjust format if needed
                        print(f"Parsed cleared_date: {cleared_date} (type: {type(cleared_date)})")
                    except Exception as e:
                        print(f"Error parsing cleared_date: {e}")
                        cleared_date = None

                shipment.cleared_date = cleared_date

                print(f"Shipment ETA: {shipment.eta} (type: {type(shipment.eta)})")
                print(f"Shipment Cleared Date: {shipment.cleared_date} (type: {type(shipment.cleared_date)})")

                if shipment.eta and shipment.cleared_date:
                    # Ensure both are date objects
                    eta_date = shipment.eta.date() if isinstance(shipment.eta, datetime) else shipment.eta
                    cleared = shipment.cleared_date

                    print(f"Converted ETA: {eta_date}, Cleared: {cleared}")
                    days = (cleared - eta_date).days
                    print(f"Days between ETA and clearance: {days}")

                    if days > FREE_DAYS:
                        print("Demurrage applies.")
                        shipment.is_demurrage = True
                    else:
                        print("No demurrage.")
                        shipment.is_demurrage = False
                else:
                    print("Missing ETA or Cleared Date — cannot evaluate demurrage.")
                    shipment.is_demurrage = False



            # Create or update shipment
            if existing_shipment:
                # Update existing shipment
                for key, value in shipment_data.items():
                    setattr(existing_shipment, key, value)
                shipment = existing_shipment
            else:
                # Create new shipment
                shipment = OrderShipment(**shipment_data)
                db.session.add(shipment)

# Replace the entire container handling section in your order_shipment route

            # In your order_shipment route, update the container handling section:

            # Handle import containers - UPDATED FOR FOREIGN KEYS
            import_container_numbers = request.form.getlist('import_container_numbers[]')
            import_container_sizes = request.form.getlist('import_container_sizes[]')
            import_container_types = request.form.getlist('import_container_types[]')
            import_container_remarks = request.form.getlist('import_container_remarks[]')
            import_container_ids = request.form.getlist('import_container_ids[]')

            existing_containers = ImportContainer.query.filter_by(shipment_id=entry_id).all()
            existing_container_dict = {c.id: c for c in existing_containers}
            processed_container_ids = []

            # Process each container from the form
            for i in range(len(import_container_numbers)):
                container_number = import_container_numbers[i].strip()
                if not container_number:
                    continue
                    
                # UPDATED: Use foreign key field names and ensure proper type conversion
                size_value = import_container_sizes[i] if i < len(import_container_sizes) and import_container_sizes[i] else None
                type_value = import_container_types[i] if i < len(import_container_types) and import_container_types[i] else None
                
                # Convert to integers, handle empty strings
                container_size_id = None
                container_type_id = None
                
                if size_value and size_value.strip():
                    try:
                        container_size_id = int(size_value)
                    except (ValueError, TypeError):
                        print(f"Invalid container size value: {size_value}")
                        container_size_id = None
                
                if type_value and type_value.strip():
                    try:
                        container_type_id = int(type_value)
                    except (ValueError, TypeError):
                        print(f"Invalid container type value: {type_value}")
                        container_type_id = None
                
                container_data = {
                    'container_number': container_number,
                    'container_size_id': container_size_id,
                    'container_type_id': container_type_id,
                    'remarks': import_container_remarks[i] if i < len(import_container_remarks) else ""
                }
                
                print(f"Container data: {container_data}")  # Debug output
                
                # Check if this is an existing container (has ID) or new container
                container_id = import_container_ids[i] if i < len(import_container_ids) and import_container_ids[i] else None
                
                if container_id and int(container_id) in existing_container_dict:
                    # Update existing container
                    container = existing_container_dict[int(container_id)]
                    for key, value in container_data.items():
                        setattr(container, key, value)
                    processed_container_ids.append(int(container_id))
                    print(f"Updated existing import container: {container_number}")
                else:
                    # Add new container
                    container = ImportContainer(
                        shipment_id=entry_id,
                        **container_data
                    )
                    db.session.add(container)
                    db.session.flush()  # Get the ID immediately
                    processed_container_ids.append(container.id)
                    print(f"Added new import container: {container_number}")

            # Remove containers that were deleted from the form
            for container_id, container in existing_container_dict.items():
                if container_id not in processed_container_ids:
                    # This container was removed from the form, delete it
                    # First clean up related records
                    ContainerWorkflowDocument.query.filter_by(container_id=container.id).delete()
                    ContainerStepCompletion.query.filter_by(container_id=container.id).delete()
                    db.session.delete(container)
                    print(f"Removed import container: {container.container_number}")

            # Handle export containers - SAME DYNAMIC LOGIC
            export_container_numbers = request.form.getlist('export_container_numbers[]')
            export_container_sizes = request.form.getlist('export_container_sizes[]')
            export_container_types = request.form.getlist('export_container_types[]')
            export_container_weights = request.form.getlist('export_container_weights[]')
            export_container_dg = request.form.getlist('export_container_dg[]')
            export_container_remarks = request.form.getlist('export_container_remarks[]')
            export_container_ids = request.form.getlist('export_container_ids[]')  # Add this to your form

            existing_export_containers = ExportContainer.query.filter_by(shipment_id=entry_id).all()
            existing_export_container_dict = {c.id: c for c in existing_export_containers}
            processed_export_container_ids = []

            # Process each export container from the form
            for i in range(len(export_container_numbers)):
                container_number = export_container_numbers[i].strip()
                if not container_number:
                    continue
                    
                container_data = {
                    'container_number': container_number,
                    'container_size': export_container_sizes[i] if i < len(export_container_sizes) else "",
                    'container_type': export_container_types[i] if i < len(export_container_types) else "",
                    'gross_weight': export_container_weights[i] if i < len(export_container_weights) else None,
                    'is_dangerous_goods': 'Y' if i < len(export_container_dg) and export_container_dg[i] else 'N',
                    'remarks': export_container_remarks[i] if i < len(export_container_remarks) else ""
                }
                
                # Check if this is an existing container (has ID) or new container
                container_id = export_container_ids[i] if i < len(export_container_ids) and export_container_ids[i] else None
                
                if container_id and int(container_id) in existing_export_container_dict:
                    # Update existing container
                    container = existing_export_container_dict[int(container_id)]
                    for key, value in container_data.items():
                        setattr(container, key, value)
                    processed_export_container_ids.append(int(container_id))
                    print(f"Updated existing export container: {container_number}")
                else:
                    # Add new container
                    container = ExportContainer(
                        shipment_id=entry_id,
                        **container_data
                    )
                    db.session.add(container)
                    db.session.flush()  # Get the ID immediately
                    processed_export_container_ids.append(container.id)
                    print(f"Added new export container: {container_number}")

            # Remove export containers that were deleted from the form
            for container_id, container in existing_export_container_dict.items():
                if container_id not in processed_export_container_ids:
                    # This container was removed from the form, delete it
                    # First clean up related records (if export containers have any)
                    # Add cleanup for export container related tables here if needed
                    db.session.delete(container)
                    print(f"Removed export container: {container.container_number}")

            # Handle workflow selection
            selected_workflow_id = request.form.get('selected_workflow_id')
            if selected_workflow_id:
                entry.selected_workflow_id = int(selected_workflow_id)
            else:
                entry.selected_workflow_id = None

            db.session.commit()
            flash("Shipment has been saved!", "success")
            return redirect(url_for('masters.order_shipment', entry_id=entry_id))

        except Exception as e:
            db.session.rollback()
            print(f"Error saving shipment: {str(e)}")
            import traceback
            traceback.print_exc()
            flash(f"An error occurred while saving the shipment", "danger")
            print(f"An error occurred while saving the shipment: {str(e)}")

    # GET request - load data for display
    # Fetch data for dropdown lists
    try:
        print("Fetching dropdown data")
        
        # Dropdowns
        shipment_types = ShipmentType.query.all()
        customers = Customer.query.all()
        billing_parties = User.query.filter_by(company_id=current_user.company_id).all()
        sales_people = User.query.filter_by(company_id=current_user.company_id).all()
        cs_executives = User.query.filter_by(company_id=current_user.company_id).all()
        wharf_clerks = WharfProfile.query.filter_by(company_id=current_user.company_id).all()
        branches = Branch.query.all()

        # In your existing order_shipment route, add this in the GET request section:
        shipment_items, available_po_items, available_suppliers = load_shipment_items_data(entry_id)
        print(f"Loaded items tab data: {len(shipment_items)} items, {len(available_po_items)} PO items")
        
        # Currencies and Expense Types
        currencies = CurrencyMaster.query.all()
        income_expenses = IncomeExpense.query.filter_by(
            company_id=current_user.company_id, 
            type='expense'
        ).all()

        # Fetch related data
        expenses = ShipmentExpense.query.filter_by(
            shipment_id=entry_id,
            company_id=current_user.company_id
        ).order_by(ShipmentExpense.created_at.desc()).all()

        import_containers = ImportContainer.query.filter_by(shipment_id=entry_id).all()
        export_containers = ExportContainer.query.filter_by(shipment_id=entry_id).all()

        # Get available workflows for this company
        company_id = current_user.company_id
        if current_user.is_super_admin == 1:
            available_workflows = ContainerDepositWorkflow.query.filter_by(is_active=True).all()
        else:
            available_workflows = ContainerDepositWorkflow.query.filter_by(
                company_id=company_id, 
                is_active=True
            ).all()
        
        print(f"Found {len(available_workflows)} available workflows for company {company_id}")

        # Get step-based workflow data if a workflow is selected
        if entry.selected_workflow_id:
            selected_workflow = ContainerDepositWorkflow.query.get(entry.selected_workflow_id)
            if selected_workflow:
                selected_workflow_data = {
                    'id': selected_workflow.id,
                    'workflow_code': selected_workflow.workflow_code,
                    'workflow_name': selected_workflow.workflow_name,
                    'steps': []
                }
                
                # Load workflow steps with documents
                for step in selected_workflow.workflow_steps.order_by(ContainerDepositWorkflowStep.step_number):
                    step_data = {
                        'id': step.id,
                        'step_number': step.step_number,
                        'step_name': step.step_name,
                        'description': step.description,
                        'documents': []
                    }
                    
                    # Load documents for this step
                    for step_doc in step.step_documents:
                        document = step_doc.document
                        
                        # Get uploaded files for this document across all containers
                        uploaded_files = ContainerWorkflowDocument.query.filter_by(
                            entry_id=entry_id,
                            step_id=step.id,
                            container_document_id=document.id
                        ).all()
                        
                        step_data['documents'].append({
                            'id': document.id,
                            'document_code': document.document_code,
                            'document_name': document.document_name,
                            'sample_file_path': document.sample_file_path,
                            'is_mandatory': step_doc.is_mandatory,
                            'uploaded_files': [
                                {
                                    'id': f.id,
                                    'container_id': f.container_id,
                                    'original_filename': f.original_filename,
                                    'narration': f.narration,
                                    'uploaded_time': f.uploaded_time.strftime('%Y-%m-%d %H:%M') if f.uploaded_time else None,
                                    'uploaded_by_id': f.uploaded_by_id
                                } for f in uploaded_files
                            ]
                        })
                    
                    selected_workflow_data['steps'].append(step_data)
                
                print(f"Loaded selected workflow data: {selected_workflow_data['workflow_name']} with {len(selected_workflow_data['steps'])} steps")

        # Get containers with enhanced workflow data
        containers_with_workflows = []
        containers = ImportContainer.query.filter_by(shipment_id=entry_id).all()
        print(f"Found {len(containers)} containers")

        for container in containers:
            # FIX: Convert SQLAlchemy objects to plain dictionaries for JSON serialization
            container_data = {
                'id': container.id,
                'container_number': container.container_number,
                'container_size_id': container.container_size_id,
                'container_type_id': container.container_type_id,
                # FIX: Add the actual names for display
                'container_size_name': container.container_size.name if container.container_size else None,
                'container_type_name': container.container_type.name if container.container_type else None,
                'size_type': f"{container.container_size.name if container.container_size else ''} {container.container_type.name if container.container_type else ''}".strip(),
                'remarks': container.remarks,
                'created_at': container.created_at.strftime('%Y-%m-%d %H:%M') if container.created_at else None,
                'workflows': []
            }
            
            # For backward compatibility, also include the old workflow format
            for workflow in available_workflows:
                # Get documents associated with this workflow
                workflow_documents = db.session.query(
                    ContainerDepositWorkflowDocument,
                    ContainerDocument
                ).join(
                    ContainerDocument, 
                    ContainerDepositWorkflowDocument.document_id == ContainerDocument.id
                ).filter(
                    ContainerDepositWorkflowDocument.workflow_id == workflow.id
                ).all()
                
                documents = []
                for workflow_doc, document in workflow_documents:
                    # Check if there are uploaded documents for this container and document
                    uploaded_docs = ContainerWorkflowDocument.query.filter_by(
                        container_id=container.id,
                        workflow_id=workflow.id,
                        container_document_id=document.id
                    ).all()
                    
                    documents.append({
                        'id': document.id,
                        'document_code': document.document_code,
                        'document_name': document.document_name,
                        'sample_file_path': document.sample_file_path,
                        'is_mandatory': workflow_doc.is_mandatory,
                        'uploaded_count': len(uploaded_docs),
                        'uploaded_files': [
                            {
                                'id': doc.id,
                                'original_filename': doc.original_filename,
                                'narration': doc.narration,
                                'uploaded_time': doc.uploaded_time.strftime('%Y-%m-%d %H:%M') if doc.uploaded_time else None,
                                'uploaded_by_id': doc.uploaded_by_id
                            } for doc in uploaded_docs
                        ]
                    })
                
                # Add workflow data
                container_data['workflows'].append({
                    'id': workflow.id,
                    'workflow_code': workflow.workflow_code,
                    'workflow_name': workflow.workflow_name,
                    'documents': documents
                })
            
            containers_with_workflows.append(container_data)

        print(f"Prepared containers with workflows data: {len(containers_with_workflows)} containers")

        # Invoices
        if entry:
            try:
                # Query invoices sorted by created date descending
                raw_invoices = InvoiceHeader.query.filter_by(
                    ship_doc_entry_id=entry_id,
                    company_id=current_user.company_id
                ).order_by(InvoiceHeader.created_at.desc()).all()
                
                # Process invoices in the same format as the API endpoint
                invoices = []
                for invoice in raw_invoices:
                    # Get customer name - use relationships if defined, otherwise fetch
                    customer_name = "Unknown"
                    if hasattr(invoice, 'customer') and invoice.customer:
                        customer_name = invoice.customer.customer_name
                    elif hasattr(invoice, 'customer_id') and invoice.customer_id:
                        customer = Customer.query.get(invoice.customer_id)
                        if customer:
                            customer_name = customer.customer_name
                    
                    # Get creator name - use relationships if defined, otherwise fetch
                    creator_name = "Unknown"
                    created_at_formatted = None
                    if hasattr(invoice, 'creator') and invoice.creator:
                        creator_name = invoice.creator.name
                        created_at_formatted = invoice.created_at.strftime('%d %b, %Y') if invoice.created_at else None
                    elif hasattr(invoice, 'created_by') and invoice.created_by:
                        creator = User.query.get(invoice.created_by)
                        if creator:
                            creator_name = creator.name
                        created_at_formatted = invoice.created_at.strftime('%d %b, %Y') if invoice.created_at else None
                    
                    # Format for display
                    invoice_data = {
                        "id": invoice.id,
                        "invoice_number": invoice.invoice_number,
                        "invoice_date": invoice.invoice_date.strftime('%d %b, %Y') if invoice.invoice_date else None,
                        "narration": invoice.narration if hasattr(invoice, 'narration') else "",
                        "customer_name": customer_name,
                        "total": invoice.total if hasattr(invoice, 'total') else 0,
                        "formatted_total": f"LKR {invoice.total:,.2f}" if hasattr(invoice, 'total') and invoice.total else "LKR 0.00",
                        "payment_status": invoice.payment_status if hasattr(invoice, 'payment_status') else 0,
                        "submitted": bool(invoice.submitted) if hasattr(invoice, 'submitted') and invoice.submitted is not None else False,
                        "created_by": creator_name,
                        "created_at": created_at_formatted
                    }
                    invoices.append(invoice_data)
                
                print(f"Fetched and formatted {len(invoices)} invoices for shipment")
            except Exception as e:
                print(f"Error fetching invoices: {str(e)}")
                import traceback
                print(f"Full error details: {traceback.format_exc()}")
                invoices = []
        else:
            invoices = []

        # Tasks
        tasks = Task.query.filter_by(shipment_id=entry_id).all()

        # Projects for tasks
        projects = Project.query.filter_by(
            company_id=current_user.company_id, 
            project_type_id=2
        ).all()

        # Documents
        documents = ShipDocumentEntryDocument.query.filter_by(
            ship_doc_entry_id=entry_id
        ).order_by(ShipDocumentEntryDocument.created_at.desc()).all()
        
        # Add user information to documents
        for doc in documents:
            if doc.uploaded_by:
                user = User.query.get(doc.uploaded_by)
                doc.uploaded_by_user = user
            else:
                doc.uploaded_by_user = None
        
        print(f"Fetched {len(documents)} documents for entry {entry_id}")

    except Exception as e:
        print(f"Error fetching dropdown data: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Set default empty lists to prevent template rendering errors
        shipment_types, customers, billing_parties = [], [], []
        sales_people, cs_executives, wharf_clerks = [], [], []
        branches, currencies, income_expenses = [], [], []
        expenses, import_containers, export_containers = [], [], []
        invoices, tasks, projects = [], [], []
        documents = []
        containers_with_workflows = []
        available_workflows = []
        selected_workflow_data = None
        shipment_items, available_po_items, available_suppliers = [], [], []

        flash("Error loading dropdown data", "danger")

    # Render the template with all data
    return render_template(
        "masters/order_shipment.html",
        title="Order Shipment",
        entry=entry,
        shipment=shipment,
        documents=documents,
        expenses=expenses,
        import_containers=import_containers,
        export_containers=export_containers,
        containers_with_workflows=containers_with_workflows,
        available_workflows=available_workflows,
        selected_workflow_data=selected_workflow_data,
        shipment_types=shipment_types,
        customers=customers,
        billing_parties=billing_parties,
        sales_people=sales_people,
        cs_executives=cs_executives,
        wharf_clerks=wharf_clerks,
        branches=branches,
        currencies=currencies,
        income_expenses=income_expenses,
        invoices=invoices,
        tasks=tasks,
        projects=projects,
        active_tab=active_tab,
        shipment_items=shipment_items,
        available_po_items=available_po_items,
        available_suppliers=available_suppliers,
        os_shipment_types=os_shipment_types,
        sub_types=sub_types,
        customer_categories=customer_categories,
        business_types=business_types,
        container_sizes=container_sizes,
        container_types=container_types,
        job_types=job_types
    )


@bp.route("/orders/<int:entry_id>/chat")
@login_required
def entry_chat(entry_id):
    entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
    return render_template("masters/entry_chat.html", title="Entry Chat", entry=entry)


@bp.route("/orders/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_entry(entry_id):
    entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
    try:
        db.session.delete(entry)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/get-ship-categories/<int:shipment_type_id>")
@login_required
def get_ship_categories(shipment_type_id):
    categories = ShipCategory.query.filter_by(shipmentType=shipment_type_id).all()
    return jsonify([{"id": cat.id, "name": cat.catname} for cat in categories])


@bp.route("/get-document-statuses/<int:shipment_type_id>")
@login_required
def get_document_statuses(shipment_type_id):
    statuses = DocumentStatus.query.filter_by(doctypeid=shipment_type_id).all()
    return jsonify(
        [
            {"id": status.docStatusID, "name": status.docStatusName}
            for status in statuses
        ]
    )


@bp.route("/orders/<int:entry_id>/get-attachments")
@login_required
def get_entry_attachments(entry_id):
    """Get attachments for an entry"""
    try:
        # Get all attachments for this entry
        attachments = (
            ShipDocumentEntryAttachment.query.filter_by(shipDocEntryMasterID=entry_id)
            .order_by(ShipDocumentEntryAttachment.created_at.desc())
            .all()
        )

        # Make sure attachments is never None
        attachments = attachments or []

        return jsonify(
            {
                "success": True,
                "attachments": [
                    {
                        "id": att.id,
                        "description": att.description,
                        "attachement_path": att.attachement_path,
                        "docAccepted": att.docAccepted,
                        "ai_validated": att.ai_validated,
                        "validation_percentage": att.validation_percentage,
                        "created_at": (
                            att.created_at.isoformat() if att.created_at else None
                        ),
                        "note": att.note,
                        "user_id": att.user_id,
                        # Additional fields for document acceptance/rejection
                        "docAccepteDate": (
                            att.docAccepteDate.isoformat() if att.docAccepteDate else None
                        ),
                        "docAccepteComments": att.docAccepteComments,
                        "docAccepteUserID": att.docAccepteUserID,
                        # Add username if user exists
                        "accepte_user_name": (
                            att.accepte_user.username if att.accepte_user else None
                        ),
                    }
                    for att in attachments
                ],
            }
        )
    except Exception as e:
        print(f"Error getting attachments: {str(e)}")  # Add logging
        return (
            jsonify({"success": False, "error": str(e), "attachments": []}),
            200,
        )  # Return 200 instead of 500 to prevent Promise rejection

@bp.route("/orders/<int:entry_id>/upload-attachment", methods=["POST"])
@login_required
def upload_entry_attachment(entry_id):
    """Upload an attachment for an entry"""
    try:
        if "document" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files["document"]
        if file.filename == "":
            return jsonify({"success": False, "error": "No file selected"}), 400

        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"

        # Get the entry to ensure it exists
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)

        # Create S3 key
        s3_key = f"document_attachments/{entry.docserial}/{unique_filename}"

        # Upload to S3
        try:
            upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
        except Exception as e:
            return (
                jsonify({"success": False, "error": f"Error uploading file: {str(e)}"}),
                500,
            )

        # Create attachment record
        attachment = ShipDocumentEntryAttachment(
            shipDocEntryMasterID=entry_id,
            description=request.form.get("description"),
            attachement_path=s3_key,
            note=request.form.get("note"),
            user_id=current_user.id,
            created_at=get_sri_lanka_time(),
            docAccepted=False,
        )

        db.session.add(attachment)
        db.session.commit()

        return jsonify({"success": True, "message": "Attachment uploaded successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route(
    "/orders/<int:entry_id>/delete-attachment/<int:attachment_id>", methods=["POST"]
)
@login_required
def delete_entry_attachment(entry_id, attachment_id):
    """Delete an attachment"""
    try:
        attachment = ShipDocumentEntryAttachment.query.get_or_404(attachment_id)


        # Delete from S3
        try:
            delete_file_from_s3(
                current_app.config["S3_BUCKET_NAME"], attachment.attachement_path
            )
        except Exception as e:
            print(f"Error deleting file from S3: {str(e)}")

        # Delete from database
        db.session.delete(attachment)
        db.session.commit()

        return jsonify({"success": True, "message": "Attachment deleted successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/view-document/<path:file_path>")
@login_required
def view_document(file_path):
    """SECURE: Serve document through app proxy instead of presigned URLs"""
    try:
        
        print(f"Attempting to view document: {file_path}")

        # Normalize the S3 key path
        s3_key = file_path.replace("\\", "/")  # Normalize path separators
        
        # Optional: Add user permission checks here if needed
        # For example, verify user owns this document:
        # document = ShipDocumentEntryAttachment.query.filter_by(
        #     attachement_path=s3_key, 
        #     user_id=current_user.id
        # ).first()
        # if not document:
        #     return jsonify({
        #         "success": False, 
        #         "message": "Document not found or access denied"
        #     }), 403

        print(f"Serving document securely: {s3_key}")
        
        # REMOVED: Presigned URL generation and redirect
        # url = get_s3_url(current_app.config["S3_BUCKET_NAME"], file_path, expires_in=3600)
        # return redirect(url)
        
        # ADDED: Direct secure serving through app proxy
        return serve_s3_file(s3_key)

    except ClientError as e:
        # Handle S3-specific errors
        print(f"S3 error accessing document: {str(e)}")
        if e.response['Error']['Code'] == 'NoSuchKey':
            return jsonify({
                "success": False,
                "message": "File not found",
                "details": f"Document does not exist: {file_path}"
            }), 404
        else:
            return jsonify({
                "success": False,
                "message": "Error accessing file from storage",
                "details": str(e)
            }), 500
            
    except Exception as e:
        print(f"Error serving document: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False, 
            "message": "Error accessing file", 
            "details": str(e)
        }), 500
    

@bp.errorhandler(UnauthorizedAccessError)
def handle_unauthorized(error):
    """Handle unauthorized access errors with a proper UI message"""
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Your session has expired. Please log in again.",
                    "redirect": url_for("auth.login"),
                }
            ),
            401,
        )
    return render_template("errors/unauthorized.html", message=str(error)), 401


@bp.errorhandler(401)
def handle_401(error):
    """Handle 401 errors with a proper UI message"""
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Your session has expired. Please log in again.",
                    "redirect": url_for("auth.login"),
                }
            ),
            401,
        )
    return (
        render_template(
            "errors/unauthorized.html", message="Please log in to access this page."
        ),
        401,
    )


@bp.route("/orders/<int:entry_id>/chat-history")
@login_required
def get_chat_history(entry_id):
    try:
        # Find chat thread for this entry
        thread = ChatThread.query.filter_by(reference_id=entry_id).first()

        if not thread:
            return jsonify({"success": True, "messages": [], "thread_id": None})

        # Get all messages for this thread
        messages = (
            ChatMessage.query.filter_by(thread_id=thread.id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )

        # Format messages for response
        formatted_messages = []
        for msg in messages:
            sender = User.query.get(msg.sender_id)
            reply_to = None
            if msg.parent_message_id:
                parent_msg = ChatMessage.query.get(msg.parent_message_id)
                if parent_msg:
                    parent_sender = User.query.get(parent_msg.sender_id)
                    reply_to = {
                        "id": parent_msg.id,
                        "message": parent_msg.message,
                        "sender_name": (
                            parent_sender.username if parent_sender else "Unknown"
                        ),
                    }

            # Get attachments for this message
            attachments = []
            for att in msg.attachments:
                attachments.append(
                    {
                        "id": att.id,
                        "file_path": att.file_path,
                        "file_name": att.file_name,
                        "file_type": att.file_type,
                    }
                )

            formatted_messages.append(
                {
                    "id": msg.id,
                    "message": msg.message,
                    "message_type": msg.message_type,
                    "timestamp": msg.created_at.isoformat(),
                    "is_sender": msg.sender_id == current_user.id,
                    "sender_name": sender.username if sender else "Unknown",
                    "reply_to": reply_to,
                    "attachments": attachments,
                }
            )

        return jsonify(
            {"success": True, "messages": formatted_messages, "thread_id": thread.id}
        )

    except Exception as e:
        print(f"Error in get_chat_history: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/orders/<int:entry_id>/send-message", methods=["POST"])
@login_required
def send_message(entry_id):
    try:
        print(f"\n--- Sending Message for Entry {entry_id} ---")
        
        # Print all form data
        print("Form Data:")
        for key, value in request.form.items():
            print(f"{key}: {value}")
        
        # Print file information
        print("\nFiles:")
        for key, file in request.files.items():
            print(f"{key}: {file.filename if file else 'No file'}")

        # Find or create chat thread
        thread = ChatThread.query.filter_by(reference_id=entry_id).first()
        if not thread:
            print("Creating new chat thread")
            thread = ChatThread(module_name="orders", reference_id=entry_id)
            db.session.add(thread)
            db.session.commit()

        # Get message details
        message = request.form.get("message", "")
        reply_to = request.form.get("reply_to")

        print(f"Message: {message}")
        print(f"Reply To: {reply_to}")

        # Create new message
        new_message = ChatMessage(
            thread_id=thread.id,
            sender_id=current_user.id,
            message=message,
            message_type="text",
            parent_message_id=reply_to if reply_to else None,
        )
        db.session.add(new_message)
        db.session.flush()

        # Handle file upload first
        attachment = None
        file = request.files.get('file')
        
        if file and file.filename:
            print(f"File received: {file.filename}")
            
            # Upload to S3 or your storage solution
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            s3_key = f"{current_app.config['S3_BASE_FOLDER']}/chat/attachments/{entry_id}/{unique_filename}"
            
            print(f"Uploading file to S3 key: {s3_key}")
            
            try:
                # Ensure the file is at the beginning of the stream
                file.seek(0)
                
                # Get file size
                file.seek(0, 2)  # Seek to end
                file_size = file.tell()
                file.seek(0)  # Reset to beginning
                
                # Upload to S3
                upload_result = upload_file_to_s3(
                    file, 
                    current_app.config["S3_BUCKET_NAME"], 
                    s3_key,
                    extra_args={'ContentType': mimetypes.guess_type(filename)[0] or 'application/octet-stream'}
                )
                
                if upload_result:
                    print("File uploaded successfully to S3")
                    attachment = ChatAttachment(
                        message_id=new_message.id,
                        file_type=determine_file_type(filename),
                        file_path=s3_key,
                        file_name=filename,
                        file_size=file_size,
                    )
                    db.session.add(attachment)
                    
                    # Update message type
                    new_message.message_type = "document"
                else:
                    print("Failed to upload file to S3")
            except Exception as upload_error:
                print(f"Error uploading file: {str(upload_error)}")
                # Log the full traceback
                import traceback
                traceback.print_exc()

        db.session.commit()
        print("Message and attachment saved successfully")

        return jsonify({
            "success": True, 
            "message_id": new_message.id,
            "attachment_id": attachment.id if attachment else None,
            "attachment_path": attachment.file_path if attachment else None
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error in send_message: {str(e)}")
        import traceback
        traceback.print_exc()  # This will print the full stack trace
        return jsonify({"success": False, "error": str(e)}), 500

def determine_file_type(filename):
    """Determine file type based on extension"""
    filename = filename.lower()
    if filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
        return "image"
    elif filename.endswith(('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx')):
        return "document"
    elif filename.endswith(('.mp3', '.wav', '.ogg', '.m4a')):
        return "audio"
    elif filename.endswith(('.mp4', '.avi', '.mov', '.wmv')):
        return "video"
    else:
        return "file"
    

@bp.route("/orders/<int:entry_id>/check-new-messages")
@login_required
def check_new_messages(entry_id):
    try:
        # First find the thread for this entry
        thread = ChatThread.query.filter_by(reference_id=entry_id).first()
        
        if not thread:
            return jsonify({
                "success": True,
                "unread_count": 0
            })
        
        # Query for unread messages in this thread sent to current user
        unread_count = ChatMessage.query.filter(
            ChatMessage.thread_id == thread.id,
            ChatMessage.is_read == False,
            ChatMessage.sender_id != current_user.id  # Messages not sent by current user
        ).count()
        
        return jsonify({
            "success": True,
            "unread_count": unread_count
        })
    except Exception as e:
        print(f"Error in check_new_messages: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/orders/<int:entry_id>/mark-messages-read", methods=["POST"])
@login_required
def mark_messages_read(entry_id):
    try:
        # Mark all messages for this entry as read for current user
        unread_messages = ChatMessage.query.filter_by(
            entry_id=entry_id, 
            is_read=False,
            recipient_id=current_user.id
        ).all()
        
        for message in unread_messages:
            message.is_read = True
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Messages marked as read"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@bp.route("/orders/<int:entry_id>/upload-voice", methods=["POST"])
@login_required
def upload_voice_note(entry_id):
    """Upload a voice note for chat"""
    try:
        if "voice" not in request.files:
            return jsonify({"success": False, "message": "No voice file provided"}), 400

        voice_file = request.files["voice"]
        if not voice_file.filename:
            return jsonify({"success": False, "message": "No file selected"}), 400

        # Generate unique filename
        filename = secure_filename(voice_file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        s3_key = f"{current_app.config['S3_BASE_FOLDER']}/chat/voice/{entry_id}/{unique_filename}"

        # Upload to S3
        if upload_file_to_s3(voice_file, current_app.config["S3_BUCKET_NAME"], s3_key):
            return jsonify(
                {"success": True, "path": s3_key, "name": filename, "type": "voice"}
            )
        else:
            return (
                jsonify({"success": False, "message": "Error uploading voice note"}),
                500,
            )

    except Exception as e:
        print(f"Error uploading voice note: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/orders/<int:entry_id>/upload-attachment", methods=["POST"])
@login_required
def upload_chat_attachment(entry_id):
    """Upload a chat attachment"""
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file provided"}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"success": False, "message": "No file selected"}), 400

        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        s3_key = f"{current_app.config['S3_BASE_FOLDER']}/chat/attachments/{entry_id}/{unique_filename}"

        # Upload to S3
        if upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key):
            return jsonify(
                {
                    "success": True,
                    "path": s3_key,
                    "name": filename,
                    "type": "document",
                    "size": file.content_length,
                }
            )
        else:
            return (
                jsonify({"success": False, "message": "Error uploading attachment"}),
                500,
            )

    except Exception as e:
        print(f"Error uploading attachment: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/masters/orders/<int:order_id>/edit", methods=["POST"])
def update_order_status(order_id):
    data = request.json
    status = data.get("status")

    # Logic to update the order status in the database
    order = Order.query.get(order_id)
    if order:
        order.status = status
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False)



# ATTACHMENTS IN SHIPMENT ORDER
########################################


# Update existing routes and add missing ones

@bp.route("/entries/<int:entry_id>/documents", methods=["POST"])
@login_required
def create_shipment_document(entry_id):
    """Create a new document for a shipment"""
    try:
        # Check if document file was provided
        if "document" not in request.files:
            if request.is_json or request.headers.get('Content-Type', '').startswith('application/json'):
                return jsonify({
                    "success": False, 
                    "message": "No file selected"
                }), 400
            else:
                flash("No file selected", "danger")
                return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab="attachments"))
        
        file = request.files["document"]
        if file.filename == "":
            if request.is_json or request.headers.get('Content-Type', '').startswith('application/json'):
                return jsonify({
                    "success": False, 
                    "message": "No file selected"
                }), 400
            else:
                flash("No file selected", "danger")
                return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab="attachments"))
        
        # Get document metadata
        document_type = request.form.get('document_type', 'other')
        description = request.form.get('description', '')
        is_confidential = request.form.get('is_confidential') == 'on'
        redirect_tab = request.form.get('redirect_tab', 'attachments')
        
        # Generate a unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        
        # Create S3 key 
        s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/shipments/{entry_id}/{unique_filename}"
        
        # Upload to S3
        try:
            upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
        except Exception as s3_error:
            if request.is_json or request.headers.get('Content-Type', '').startswith('application/json'):
                return jsonify({
                    "success": False, 
                    "message": f"Error uploading file: {str(s3_error)}"
                }), 500
            else:
                flash(f"Error uploading file", "danger")
                print(f"Error uploading file: {str(s3_error)}")
                return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab="attachments"))
        
        # Create document record in database
        try:
            document = ShipDocumentEntryDocument(
                ship_doc_entry_id=entry_id,
                document_name=filename,
                document_type=document_type,
                description=description,
                is_confidential=is_confidential,
                file_path=s3_key,
                uploaded_by=current_user.id,
                created_at=get_sri_lanka_time()
            )
            
            db.session.add(document)
            db.session.commit()
            
            if request.is_json or request.headers.get('Content-Type', '').startswith('application/json'):
                return jsonify({
                    "success": True, 
                    "message": "Document uploaded successfully",
                    "document": {
                        "id": document.id,
                        "name": document.document_name,
                        "type": document.document_type,
                        "description": document.description,
                        "uploaded_by": current_user.name,
                        "upload_date": document.created_at.isoformat()
                    }
                }), 201
            else:
                flash("Document uploaded successfully", "success")
                return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab=redirect_tab))
            
        except Exception as db_error:
            db.session.rollback()
            if request.is_json or request.headers.get('Content-Type', '').startswith('application/json'):
                return jsonify({
                    "success": False, 
                    "message": f"Error saving document metadata: {str(db_error)}"
                }), 500
            else:
                flash(f"Error saving document metadata", "danger")
                print(f"Error saving document metadata: {str(db_error)}")
                return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab="attachments"))
        
    except Exception as e:
        if request.is_json or request.headers.get('Content-Type', '').startswith('application/json'):
            return jsonify({
                "success": False, 
                "message": f"Unexpected error"
            }), 500
        else:
            flash(f"Unexpected error", "danger")
            print(f"Unexpected error: {str(e)}")
            return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab="attachments"))


@bp.route("/entries/<int:entry_id>/documents", methods=["GET"])
@login_required
def get_shipment_documents(entry_id):
    """Get all documents for a shipment"""
    try:
        # Base query
        query = ShipDocumentEntryDocument.query.filter_by(ship_doc_entry_id=entry_id)
        
        # If user is a customer, restrict confidential docs
        if current_user.role == "customer":
            query = query.filter_by(is_confidential=False)
        
        # Execute the query
        documents = query.all()
        
        # Format the response
        docs_list = []
        for doc in documents:
            user = User.query.get(doc.uploaded_by)
            docs_list.append({
                "id": doc.id,
                "document_name": doc.document_name,
                "document_type": doc.document_type,
                "description": doc.description or "",
                "is_confidential": doc.is_confidential,
                "file_path": doc.file_path,
                "uploaded_by": doc.uploaded_by,
                "uploaded_by_name": user.name if user else "Unknown",
                "created_at": doc.created_at.isoformat() if doc.created_at else None
            })
        
        return jsonify({"success": True, "documents": docs_list})
    
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500



@bp.route("/entries/<int:entry_id>/documents/<int:document_id>", methods=["GET"])
@login_required
def get_shipment_document_details(entry_id, document_id):
    """Get details of a specific document"""
    try:
        # Get the specific document
        document = ShipDocumentEntryDocument.query.filter_by(
            id=document_id, 
            ship_doc_entry_id=entry_id
        ).first_or_404()
        
        # Get uploader information
        user = User.query.get(document.uploaded_by)
        
        return jsonify({
            "success": True,
            "document": {
                "id": document.id,
                "document_name": document.document_name,
                "document_type": document.document_type,
                "description": document.description or "",
                "is_confidential": document.is_confidential,
                "file_path": document.file_path,
                "uploaded_by": document.uploaded_by,
                "uploaded_by_name": user.name if user else "Unknown",
                "created_at": document.created_at.isoformat() if document.created_at else None
            }
        })
    
    except Exception as e:
        return jsonify({
            "success": False, 
            "message": str(e)
        }), 500


@bp.route("/entries/<int:entry_id>/documents/<int:document_id>", methods=["PUT"])
@login_required
def update_shipment_document(entry_id, document_id):
    """Update a document for a shipment"""
    try:
        # Get the document
        document = ShipDocumentEntryDocument.query.filter_by(
            id=document_id, 
            ship_doc_entry_id=entry_id
        ).first_or_404()
        
        # Get form data
        document_type = request.form.get('document_type', document.document_type)
        description = request.form.get('description', document.description)
        is_confidential = request.form.get('is_confidential') == 'on'
        
        # Check if a new file is uploaded
        if 'document' in request.files:
            file = request.files['document']
            if file.filename:
                # Generate a unique filename
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                
                # Create S3 key 
                s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/shipments/{entry_id}/{unique_filename}"
                
                # Upload to S3
                try:
                    # Delete old file from S3 if it exists
                    if document.file_path:
                        delete_file_from_s3(current_app.config["S3_BUCKET_NAME"], document.file_path)
                    
                    # Upload new file
                    upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
                    
                    # Update document details
                    document.document_name = filename
                    document.file_path = s3_key
                except Exception as s3_error:
                    return jsonify({
                        "success": False, 
                        "message": f"Error uploading file: {str(s3_error)}"
                    }), 500
        
        # Update other document details
        document.document_type = document_type
        document.description = description
        document.is_confidential = is_confidential
        
        # Save changes
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": "Document updated successfully",
            "document": {
                "id": document.id,
                "name": document.document_name,
                "type": document.document_type,
                "description": document.description,
                "uploaded_by": current_user.name,
                "upload_date": document.created_at.isoformat()
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False, 
            "message": f"Unexpected error"
        }), 500


# Fix the delete route - change redirect destination
@bp.route("/entries/<int:entry_id>/document/<int:document_id>/delete", methods=["POST"])
@login_required
def delete_ship_document(entry_id, document_id):
    """Delete a document"""
    try:
        print(f"Deleting document ID {document_id} for entry {entry_id}")
        
        # Get the document
        document = ShipDocumentEntryDocument.query.get_or_404(document_id)
        
        # Verify the document belongs to the entry
        if document.ship_doc_entry_id != entry_id:
            print(f"Document does not belong to entry")
            flash("Document not found", "danger")
            return redirect(url_for("masters.order_shipment", entry_id=entry_id, tab="attachments"))
        
        # Delete file from S3
        try:
            print(f"Deleting file from S3: {document.file_path}")
            delete_file_from_s3(current_app.config["S3_BUCKET_NAME"], document.file_path)
            print("S3 deletion successful")
        except Exception as s3_error:
            print(f"Error deleting from S3: {str(s3_error)}")
            # Continue with deletion even if S3 deletion fails
        
        # Delete from database
        db.session.delete(document)
        db.session.commit()
        print("Document deleted from database")
        
        flash("Document deleted successfully", "success")
        return redirect(url_for("masters.order_shipment", entry_id=entry_id, tab="attachments"))
    
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting document: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f"Error deleting document", "danger")
        print(f"Error deleting document: {str(e)}")
        return redirect(url_for("masters.order_shipment", entry_id=entry_id, tab="attachments"))



@bp.route("/entries/<int:entry_id>/document/<int:document_id>/view", methods=["GET"])
@login_required
def view_ship_document(entry_id, document_id):
    """SECURE: View a document through app proxy instead of direct S3 URL."""
    try:
        
        # Get the document
        document = ShipDocumentEntryDocument.query.get_or_404(document_id)
        
        # Verify the document belongs to the entry
        if document.ship_doc_entry_id != entry_id:
            abort(404)
        
        # Check if file path exists
        if not document.file_path:
            return render_template('document_error.html', 
                                  message='No file path found for this document'), 404
        
        # Optional: Add additional permission checks here
        # For example, verify user has access to this entry:
        # entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        # if entry.user_id != current_user.id:
        #     return render_template('document_error.html', 
        #                           message='Access denied'), 403
        
        # Normalize the S3 key path
        s3_key = document.file_path.replace("\\", "/")  # Normalize path separators
        
        print(f"Serving ship document securely: {s3_key}")
        
        # REMOVED: Direct S3 URL construction and redirect
        # direct_url = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{document.file_path}"
        # return redirect(direct_url)
        
        # ADDED: Direct secure serving through app proxy
        return serve_s3_file(s3_key)
    
    except ClientError as e:
        # Handle S3-specific errors
        current_app.logger.error(f"S3 error viewing ship document: {str(e)}")
        print(f"S3 error viewing ship document: {str(e)}")
        
        if e.response['Error']['Code'] == 'NoSuchKey':
            return render_template('document_error.html', 
                                  message='Document file not found in storage'), 404
        else:
            return render_template('document_error.html', 
                                  message='Error accessing document from storage'), 500
    
    except Exception as e:
        current_app.logger.error(f"Error viewing ship document: {str(e)}")
        print(f"Error viewing ship document: {str(e)}")
        return render_template('document_error.html', 
                              message='An error occurred while accessing the document'), 500


# INCOME EXPENSE MASTER

@bp.route('/income-expenses', methods=['GET'])
@login_required
def income_expenses():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '')
    type_filter = request.args.get('type', '')
    status_filter = request.args.get('status', '')
    
    query = IncomeExpense.query.filter_by(company_id=current_user.company_id)
    
    # Apply type filter
    if type_filter:
        query = query.filter(IncomeExpense.type == type_filter)
    
    # Apply status filter
    if status_filter:
        status_bool = (status_filter == 'active')
        query = query.filter(IncomeExpense.status == status_bool)
    
    # Apply search filter
    if search:
        query = query.filter(or_(
            IncomeExpense.description.ilike(f'%{search}%'),
            IncomeExpense.gl_code.ilike(f'%{search}%')
        ))
    
    # Order by creation date
    query = query.order_by(IncomeExpense.created_date.desc())
    
    # Paginate the results
    income_expenses = query.paginate(page=page, per_page=per_page)
    
    return render_template('masters/income_expense.html', income_expenses=income_expenses)

# Show form to add new income/expense
@bp.route('/income-expense/new', methods=['GET'])
@login_required
def new_income_expense():
    return render_template('masters/income_expense_form.html', income_expense=None)

# Show form to edit existing income/expense
@bp.route('/income-expense/edit/<int:id>', methods=['GET'])
@login_required
def edit_income_expense(id):
    income_expense = IncomeExpense.query.filter_by(id=id, company_id=current_user.company_id).first_or_404()
    return render_template('masters/income_expense_form.html', income_expense=income_expense)

# Save new or updated income/expense
@bp.route('/income-expense/save', methods=['POST'])
@login_required
def save_income_expense():
    id = request.form.get('id', None)
    
    if id:  # Update existing record
        income_expense = IncomeExpense.query.filter_by(id=id, company_id=current_user.company_id).first_or_404()
        flash_message = 'Income/Expense updated successfully!'
    else:  # Create new record
        income_expense = IncomeExpense(
            company_id=current_user.company_id,
            created_date=get_sri_lanka_time()
        )
        flash_message = 'Income/Expense added successfully!'
    
    # Update fields from form data
    income_expense.type = request.form.get('type')
    income_expense.description = request.form.get('description')
    income_expense.gl_code = request.form.get('gl_code')
    income_expense.status = 'status' in request.form  # Convert checkbox to boolean
    
    # Save to database
    if not id:  # Only add if it's a new record
        db.session.add(income_expense)
    
    try:
        db.session.commit()
        flash(flash_message, 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error saving record', 'danger')
        print(f"Error saving record: {str(e)}")
    
    return redirect(url_for('masters.income_expenses'))

# Delete income/expense
@bp.route('/income-expense/delete/<int:id>', methods=['POST'])
@login_required
def delete_income_expense(id):
    income_expense = IncomeExpense.query.filter_by(id=id, company_id=current_user.company_id).first_or_404()
    
    try:
        db.session.delete(income_expense)
        db.session.commit()
        flash('Income/Expense deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting record', 'danger')
        print(f"Error deleting record: {str(e)}")
    
    return redirect(url_for('masters.income_expenses'))


# NEW EXPENSE TAB ROUTES
############################################

@bp.route("/entries/<int:entry_id>/expenses/save", methods=["POST"])
@login_required
def save_shipment_expense(entry_id):
    try:
        # Verify entry exists
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        # Get form data
        data = request.form
        
        # Check if this is an update or new expense
        expense_id = data.get('expense_id')
        
        if expense_id:
            # This is an update - fetch existing expense
            expense = ShipmentExpense.query.get_or_404(expense_id)
            
        else:
            # This is a new expense - create new object
            expense = ShipmentExpense(
                shipment_id=entry_id,
                company_id=current_user.company_id,
                created_by=current_user.id
            )
        
        # Validate required fields
        required_fields = ['expense_type', 'currency_id', 'narration', 'value']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "success": False,
                    "message": f"Missing required field: {field}"
                }), 400
        
        def safe_float(value, default=0.0):
            """Convert string to float, return default if empty or invalid"""
            if not value or value.strip() == '':
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        # Calculate amounts with safe conversion
        value_amount = safe_float(data.get('value', 0))
        vat_amount = safe_float(data.get('vat_amount', 0))
        margin = safe_float(data.get('margin', 0))
        
        # Calculate net and chargeable amounts
        net_amount = value_amount + vat_amount
        margin_amount = (net_amount * margin) / 100
        chargeable_amount = net_amount + margin_amount
        
        # Handle file upload if exists
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file.filename:
                # Delete old attachment if exists (for update only)
                if expense_id and expense.attachment_path:
                    try:
                        delete_file_from_s3(
                            current_app.config["S3_BUCKET_NAME"],
                            expense.attachment_path
                        )
                    except Exception as e:
                        current_app.logger.error(f"Error deleting old attachment: {str(e)}")
                
                # Generate unique filename
                unique_filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
                s3_key = f"expenses/{entry_id}/{unique_filename}"
                
                # Upload to S3
                upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
                expense.attachment_path = s3_key
        
        # Check for attachment removal flag (for edit only)
        if expense_id and data.get('remove_attachment') == '1' and expense.attachment_path:
            try:
                delete_file_from_s3(
                    current_app.config["S3_BUCKET_NAME"],
                    expense.attachment_path
                )
                expense.attachment_path = None
            except Exception as e:
                current_app.logger.error(f"Error removing attachment: {str(e)}")
        
        # Update expense fields
        expense.expense_type_id = data.get('expense_type')
        expense.currency_id = data.get('currency_id')
        expense.narration = data.get('narration')
        expense.value_amount = value_amount
        expense.vat_amount = vat_amount
        expense.amount = net_amount
        expense.margin = margin
        expense.margin_amount = margin_amount
        expense.chargeable_amount = chargeable_amount
        expense.document_number = data.get('document_number')
        expense.supplier_name = data.get('supplier_name')
        expense.reference = data.get('reference', '')
        expense.doc_date = datetime.strptime(data.get('date_from'), '%Y-%m-%d').date() if data.get('date_from') else None
        expense.visible_to_customer = data.get('visible_to_customer') == '1'
        expense.attachment_visible_to_customer = data.get('attachment_visible_to_customer') == '1'
        
        # For new records, set the balance amount
        if not expense_id:
            expense.charged_amount = 0
            expense.balance_amount = chargeable_amount
        else:
            # For updates, recalculate balance amount
            expense.balance_amount = expense.chargeable_amount - expense.charged_amount
        
        # Add to session if new, otherwise just commit
        if not expense_id:
            db.session.add(expense)
        
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return jsonify({
                "success": True,
                "message": "Expense saved successfully",
                "expense_id": expense.id
            })
        else:
            flash("Expense saved successfully", "success")
            return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab="expenses"))
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving expense: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.content_type == 'application/json':
            return jsonify({
                "success": False,
                "message": str(e)
            }), 500
        
        # For regular form submissions, flash error and redirect
        else:
            flash(f"Error saving expense", "danger")
            print(f"Error saving expense: {str(e)}")
            return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab="expenses"))
        

@bp.route("/entries/<int:entry_id>/generate-expense-number", methods=["GET"])
@login_required
def generate_expense_number(entry_id):
    """Generate a new expense document number"""
    try:
        # Verify entry exists and belongs to user's company
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        # Get the highest existing expense number for this company
        latest_expense = db.session.query(ShipmentExpense)\
            .filter_by(company_id=current_user.company_id)\
            .filter(ShipmentExpense.document_number.like('EXP%'))\
            .order_by(desc(ShipmentExpense.document_number))\
            .first()
        
        if latest_expense and latest_expense.document_number:
            # Extract the numeric part and increment
            try:
                # Try to extract number from the format EXP00001
                num_part = latest_expense.document_number[3:]  # Remove "EXP"
                next_num = int(num_part) + 1
            except (ValueError, IndexError):
                # If format is unexpected, start from 1
                next_num = 1
        else:
            # No existing expense numbers, start from 1
            next_num = 1
        
        # Format with leading zeros (EXP00001, EXP00002, etc.)
        document_number = f"EXP{next_num:05d}"
        
        return jsonify({
            "success": True,
            "document_number": document_number
        })
        
    except Exception as e:
        current_app.logger.error(f"Error generating expense number: {str(e)}")
        return jsonify({"success": False, "error": str(e)})
         

@bp.route("/shipments/<int:shipment_id>/edit-expense/<int:expense_id>", methods=["GET"])
@login_required
def edit_shipment_expense(shipment_id, expense_id):
    """Return expense data as JSON for editing in modal"""
    try:
        # Get expense
        expense = ShipmentExpense.query.get_or_404(expense_id)
        
        
        # Format expense data as JSON-safe dictionary
        expense_data = {
            "id": expense.id,
            "expense_type_id": expense.expense_type_id,
            "currency_id": expense.currency_id,
            "document_number": expense.document_number or "",
            "supplier_name": expense.supplier_name or "",
            "reference": expense.reference or "",
            "narration": expense.narration or "",
            "doc_date": expense.doc_date.strftime('%Y-%m-%d') if expense.doc_date else "",
            "value_amount": float(expense.value_amount) if expense.value_amount is not None else 0,
            "vat_amount": float(expense.vat_amount) if expense.vat_amount is not None else 0,
            "amount": float(expense.amount) if expense.amount is not None else 0,
            "margin": float(expense.margin) if expense.margin is not None else 0,
            "margin_amount": float(expense.margin_amount) if expense.margin_amount is not None else 0,
            "chargeable_amount": float(expense.chargeable_amount) if expense.chargeable_amount is not None else 0,
            "charged_amount": float(expense.charged_amount) if expense.charged_amount is not None else 0,
            "balance_amount": float(expense.balance_amount) if expense.balance_amount is not None else 0,
            "visible_to_customer": bool(expense.visible_to_customer),
            "attachment_visible_to_customer": bool(expense.attachment_visible_to_customer),
            "attachment_path": expense.attachment_path or ""
        }
        
        # Add creator and creation date info if available
        if hasattr(expense, 'created_by') and expense.created_by:
            creator = User.query.get(expense.created_by)
            expense_data["created_by_name"] = creator.name if creator else "Unknown"
        else:
            expense_data["created_by_name"] = "Unknown"
            
        if hasattr(expense, 'created_at') and expense.created_at:
            expense_data["created_at"] = expense.created_at.strftime("%d %b %Y, %I:%M %p")
        else:
            expense_data["created_at"] = "Unknown"
        
        return jsonify({"success": True, "expense": expense_data})
        
    except Exception as e:
        current_app.logger.error(f"Error loading expense form: {str(e)}")
        return jsonify({"success": False, "error": str(e)})   


@bp.route("/entries/<int:entry_id>/delete-expense/<int:expense_id>", methods=["POST"])
@login_required
def delete_shipment_expense(entry_id, expense_id):
    """Delete an expense"""
    try:
        # Get expense
        expense = ShipmentExpense.query.get_or_404(expense_id)
        
        
        # Check if the expense has any settlements
        has_settlements = ExpenseSettlement.query.filter_by(expense_id=expense_id).first() is not None
        if has_settlements:
            flash("Cannot delete expense with existing settlements. Remove invoices that reference this expense first.", "danger")
            return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab="expenses"))
        
        # Delete attachment from S3 if it exists
        if expense.attachment_path:
            try:
                delete_file_from_s3(
                    current_app.config["S3_BUCKET_NAME"],
                    expense.attachment_path
                )
            except Exception as e:
                current_app.logger.error(f"Error deleting expense attachment: {str(e)}")
        
        # Delete expense from database
        db.session.delete(expense)
        db.session.commit()
        
        flash("Expense deleted successfully", "success")
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting expense: {str(e)}")
        flash(f"Error deleting expense", "danger")
        print(f"Error deleting expense: {str(e)}")  
    
    # Redirect back to expenses tab
    return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab="expenses"))



@bp.route("/expenses/<int:expense_id>/attachment", methods=["GET"])
@login_required
def view_expense_attachment(expense_id):
    """SECURE: Serve expense attachment through app proxy instead of presigned URLs"""
    try:
        # Get the expense
        expense = ShipmentExpense.query.get_or_404(expense_id)

        # Check if attachment exists
        if not expense.attachment_path:
            flash("No attachment found for this expense", "warning")
            return redirect(url_for('masters.order_shipment', shipment_id=expense.shipment_id, tab="expenses"))

        # Normalize the S3 key path
        s3_key = expense.attachment_path.replace("\\", "/")
        print(f"Serving expense attachment securely: {s3_key}")

        # Securely serve the file through app proxy
        return serve_s3_file(s3_key)

    except ClientError as e:
        print(f"S3 error accessing expense attachment: {str(e)}")
        if e.response['Error']['Code'] == 'NoSuchKey':
            flash("File not found in storage", "warning")
            return redirect(url_for('masters.order_shipment', shipment_id=expense.shipment_id, tab="expenses"))
        else:
            flash("Error accessing file from storage", "danger")
            return redirect(url_for('masters.order_shipment', shipment_id=expense.shipment_id, tab="expenses"))

    except Exception as e:
        print(f"Error serving expense attachment: {str(e)}")
        import traceback
        traceback.print_exc()
        flash("Error viewing attachment", "danger")
        return redirect(url_for('masters.order_shipment', shipment_id=expense.shipment_id, tab="expenses"))

    
@bp.route("/entries/<int:entry_id>/expenses", methods=["GET"])
@login_required
def get_shipment_expenses(entry_id):
    try:
        # Verify entry exists and belongs to user's company
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        
        # Fetch expenses for this entry
        expenses = ShipmentExpense.query.filter_by(
            shipment_id=entry_id,
            company_id=current_user.company_id
        ).order_by(ShipmentExpense.created_at.desc()).all()
        
        # Prepare formatted expense data
        expense_data = []
        for expense in expenses:
            expense_info = {
                'id': expense.id,
                'expense_type': expense.expense_type.description if expense.expense_type else 'Unknown',
                'narration': expense.narration,
                'amount': float(expense.amount),
                'currency': expense.currency.CurrencyCode if expense.currency else '$',
                'document_number': expense.document_number,
                'created_at': expense.created_at.isoformat() if expense.created_at else None
            }
            expense_data.append(expense_info)
        
        return jsonify({
            "success": True,
            "expenses": expense_data
        })
    
    except Exception as e:
        current_app.logger.error(f"Error fetching expenses: {str(e)}")
        return jsonify({
            "success": False,
            "message": "Error fetching expenses"
        }), 500
     

@bp.route("/shipments/<int:shipment_id>/expenses/<int:expense_id>/settlements", methods=["GET"])
@login_required
def view_expense_settlements(shipment_id, expense_id):
    """View settlement history for an expense"""
    try:
        # Verify expense exists and belongs to shipment and user's company
        expense = ShipmentExpense.query.get_or_404(expense_id)
        
        
        # Get all settlements for this expense
        settlements = ExpenseSettlement.query.filter_by(
            expense_id=expense_id
        ).order_by(ExpenseSettlement.created_at.desc()).all()
        
        # Format settlement data
        formatted_settlements = []
        for settlement in settlements:
            # Get invoice
            invoice = InvoiceHeader.query.get(settlement.invoice_id) if settlement.invoice_id else None
            
            # Get creator
            creator = User.query.get(settlement.created_by) if settlement.created_by else None
            
            # Format data
            settlement_data = {
                "id": settlement.id,
                "invoice_number": invoice.invoice_number if invoice else "Unknown",
                "amount_charged": settlement.amount_charged,
                "formatted_amount": f"{expense.currency.CurrencyCode} {settlement.amount_charged:,.2f}" if expense.currency else f"${settlement.amount_charged:,.2f}",
                "created_by": creator.name if creator else "Unknown",
                "created_at": settlement.created_at.strftime("%d %b %Y, %I:%M %p") if settlement.created_at else "Unknown"
            }
            formatted_settlements.append(settlement_data)
        
        # Calculate settlement summary
        charged_amount = expense.charged_amount or 0
        chargeable_amount = expense.chargeable_amount or 0
        balance_amount = expense.balance_amount or 0
        
        # Calculate settlement percentage
        settlement_percentage = 0
        if chargeable_amount > 0:
            settlement_percentage = round((charged_amount / chargeable_amount) * 100)
        
        # Format currency values for summary
        currency_code = expense.currency.CurrencyCode if expense.currency else "$"
        formatted_chargeable = f"{currency_code} {chargeable_amount:,.2f}"
        formatted_charged = f"{currency_code} {charged_amount:,.2f}"
        formatted_balance = f"{currency_code} {balance_amount:,.2f}"
        
        return render_template(
            "masters/expense_settlements.html",
            title="Expense Settlements",
            expense=expense,
            shipment_id=shipment_id,
            settlements=formatted_settlements,
            settlement_percentage=settlement_percentage,
            formatted_chargeable=formatted_chargeable,
            formatted_charged=formatted_charged,
            formatted_balance=formatted_balance
        )
        
    except Exception as e:
        current_app.logger.error(f"Error viewing expense settlements: {str(e)}")
        flash(f"Error viewing settlements", "danger")
        print(f"Error viewing expense settlements: {str(e)}")
        return redirect(url_for('masters.order_shipment', shipment_id=shipment_id, tab="expenses"))
    

@bp.route("/entries/<int:entry_id>/expenses/<int:expense_id>", methods=["GET", "PUT", "DELETE"])
@login_required
def manage_shipment_expense(entry_id, expense_id):
    try:
        # Verify entry and expense exist
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        expense = ShipmentExpense.query.get_or_404(expense_id)
        
        
        if request.method == "GET":
            # Return expense details
            return jsonify({
                "success": True,
                "expense": {
                    'id': expense.id,
                    'expense_type_id': expense.expense_type_id,
                    'currency_id': expense.currency_id,
                    'narration': expense.narration,
                    'value_amount': float(expense.value_amount),
                    'vat_amount': float(expense.vat_amount),
                    'amount': float(expense.amount),
                    'margin': float(expense.margin),
                    'margin_amount': float(expense.margin_amount),
                    'chargeable_amount': float(expense.chargeable_amount),
                    'charged_amount': float(expense.charged_amount),
                    'balance_amount': float(expense.balance_amount),
                    'document_number': expense.document_number,
                    'supplier_name': expense.supplier_name,
                    'doc_date': expense.doc_date.isoformat() if expense.doc_date else None,
                    'attachment_path': expense.attachment_path,
                    'visible_to_customer': expense.visible_to_customer
                }
            })
        
        elif request.method == "PUT":
            # Update expense
            data = request.form
            
            # Handle file upload if exists
            if 'attachment' in request.files:
                file = request.files['attachment']
                if file.filename:
                    # Delete old attachment if exists
                    if expense.attachment_path:
                        delete_file_from_s3(
                            current_app.config["S3_BUCKET_NAME"], 
                            expense.attachment_path
                        )
                    
                    # Generate unique filename
                    unique_filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
                    s3_key = f"expenses/{entry_id}/{unique_filename}"
                    
                    # Upload to S3
                    upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
                    expense.attachment_path = s3_key
            
            # Update other fields
            expense.expense_type_id = data.get('expense_type', expense.expense_type_id)
            expense.currency_id = data.get('currency_id', expense.currency_id)
            expense.narration = data.get('narration', expense.narration)
            
            # Recalculate amounts if value or VAT changes
            value_amount = float(data.get('value', expense.value_amount))
            vat_amount = float(data.get('vat_amount', expense.vat_amount))
            margin = float(data.get('margin', expense.margin))
            
            net_amount = value_amount + vat_amount
            margin_amount = (net_amount * margin) / 100
            chargeable_amount = net_amount + margin_amount
            
            expense.value_amount = value_amount
            expense.vat_amount = vat_amount
            expense.amount = net_amount
            expense.margin = margin
            expense.margin_amount = margin_amount
            expense.chargeable_amount = chargeable_amount
            
            # Update other details
            expense.document_number = data.get('document_number', expense.document_number)
            expense.supplier_name = data.get('supplier_name', expense.supplier_name)
            expense.doc_date = datetime.strptime(data.get('date_from'), '%Y-%m-%d').date() if data.get('date_from') else expense.doc_date
            expense.visible_to_customer = data.get('visible_to_customer') == '1'
            
            db.session.commit()
            
            return jsonify({
                "success": True,
                "message": "Expense updated successfully"
            })
        
        elif request.method == "DELETE":
            # Check if expense has any settlements
            settlements = ExpenseSettlement.query.filter_by(expense_id=expense_id).count()
            if settlements > 0:
                return jsonify({
                    "success": False,
                    "message": "Cannot delete expense with existing settlements"
                }), 400
            
            # Delete attachment if exists
            if expense.attachment_path:
                delete_file_from_s3(
                    current_app.config["S3_BUCKET_NAME"], 
                    expense.attachment_path
                )
            
            # Delete expense
            db.session.delete(expense)
            db.session.commit()
            
            return jsonify({
                "success": True,
                "message": "Expense deleted successfully"
            })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error managing expense: {str(e)}")
        return jsonify({
            "success": False,
            "message": 'Error'
        }), 500


# ###############################################





# invoices

# Routes for invoice functionality

@bp.route("/entries/<int:entry_id>/invoices", methods=["GET"])
@login_required
def get_shipment_invoices(entry_id):
    """Get all invoices for a shipment."""
    try:
        # Verify shipment exists and belongs to user's company
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        # Query invoices sorted by created date descending
        invoices = InvoiceHeader.query.filter_by(
            ship_doc_entry_id=entry_id,
            company_id=current_user.company_id
        ).order_by(InvoiceHeader.created_at.desc()).all()
        
        # Process invoices for the response
        invoice_list = []
        for invoice in invoices:
            invoice_data = {
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
                "narration": invoice.narration,
                "customer_name": invoice.customer.customer_name if invoice.customer else "Unknown",
                "total": invoice.total,
                "formatted_total": f"LKR {invoice.total:,.2f}",
                "payment_status": invoice.payment_status,
                "payment_status_text": get_payment_status_text(invoice.payment_status),
                "created_by": invoice.creator.name if invoice.creator else "Unknown",
                "created_at": invoice.created_at.isoformat() if invoice.created_at else None
            }
            invoice_list.append(invoice_data)
        
        # Create summary object
        summary = {
            "invoice_count": len(invoices),
            "total_amount": f"${sum(invoice.total for invoice in invoices):,.2f}",
            "pending_payment_count": sum(1 for invoice in invoices if invoice.payment_status == 0)
        }
        
        # Return invoices and summary
        return jsonify({
            "success": True,
            "invoices": invoice_list,
            "summary": summary
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting shipment invoices: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred while retrieving the invoices"
        }), 500


@bp.route("/entries/<int:entry_id>/invoices/<int:invoice_id>", methods=["GET"])
@login_required
def get_shipment_invoice(entry_id, invoice_id):
    """Get a specific invoice with its details including VAT information."""
    try:
        # Get invoice and verify it belongs to the shipment and company
        invoice = InvoiceHeader.query.get_or_404(invoice_id)
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)

        
        # Get invoice details
        details = []
        for detail in invoice.details:
            # Common detail data
            detail_data = {
                "id": detail.id,
                "description": detail.description,
                "original_amount": detail.original_amount,
                "margin": detail.margin,
                "final_amount": detail.final_amount,
                "item_type": detail.item_type
            }
            
            # Add specific fields based on item type
            if detail.item_type == 'rate_card':
                detail_data.update({
                    "rate_card_id": detail.rate_card_id,
                    "expense_type": detail.rate_card.income.description if detail.rate_card and detail.rate_card.income else "Rate Card Item"
                })
            elif detail.item_type == 'expense':
                detail_data.update({
                    "expense_id": detail.expense_id,
                    "original_chargeable_amount": detail.original_chargeable_amount,
                    "expense_type": detail.expense.expense_type.description if detail.expense and detail.expense.expense_type else "Unknown",
                    # Add VAT fields
                    "charged_amount_before_vat": detail.charged_amount_before_vat,
                    "vat_percentage": detail.vat_percentage,
                    "vat_amount": detail.vat_amount,
                    "formatted_vat_amount": f"${getattr(detail, 'vat_amount', 0):,.2f}" if hasattr(detail, 'vat_amount') else "$0.00",
                    "formatted_charged_before_vat": f"${getattr(detail, 'charged_amount_before_vat', 0):,.2f}" if hasattr(detail, 'charged_amount_before_vat') else "$0.00"
                })
            elif detail.item_type == 'income':
                detail_data.update({
                    "expense_type": "Income Item" 
                })
            
            details.append(detail_data)
        
        # Format invoice data
        invoice_data = {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            "narration": invoice.narration,
            "customer_id": invoice.customer_id,
            "customer_name": invoice.customer.customer_name if invoice.customer else "Unknown",
            "ship_doc_entry_id": invoice.ship_doc_entry_id,
            "total": invoice.total,
            "formatted_total": f"LKR {invoice.total:,.2f}",
            "payment_status": invoice.payment_status,
            "payment_status_text": get_payment_status_text(invoice.payment_status),
            "created_by": invoice.creator.name if invoice.creator else "Unknown",
            "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
            "details": details
        }
        
        return jsonify({
            "success": True,
            "invoice": invoice_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting shipment invoice: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred while retrieving the invoice"
        }), 500


@bp.route("/entries/<int:entry_id>/invoices/next-number", methods=["GET"])
@login_required
def get_next_invoice_number(entry_id):
    """Get the next invoice number to be used."""
    try:
        # Verify shipment exists and belongs to user's company
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        # Generate next invoice number
        next_number = InvoiceHeader.generate_invoice_number(current_user.company_id)
        
        return jsonify({
            "success": True,
            "next_invoice_number": next_number
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting next invoice number: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred while generating the invoice number"
        }), 500


@bp.route("/entries/<int:entry_id>/invoices", methods=["POST"])
@login_required
def create_shipment_invoice(entry_id):
    """Create a new invoice for a shipment with expense settlements, rate card items, and income items."""
    try:
        # Verify shipment exists and belongs to user's company
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        customer_id = entry.customer_id
        
        # Parse request data
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        # Validate required fields
        if not data.get('invoice_date'):
            return jsonify({"success": False, "message": "Invoice date is required"}), 400
        
        # Check that at least one item (expense, rate card, or income) is included
        expense_items = data.get('expense_items', [])
        rate_card_items = data.get('rate_card_items', [])
        income_items = data.get('income_items', [])
        
        if not expense_items and not rate_card_items and not income_items:
            return jsonify({
                "success": False, 
                "message": "At least one expense, rate card, or income item is required"
            }), 400
        
        # Log all incoming items for debugging
        current_app.logger.info(f"Creating invoice for entry_id: {entry_id}")
        current_app.logger.info(f"Invoice Date: {data.get('invoice_date')}")
        current_app.logger.info(f"Expense Items: {expense_items}")
        current_app.logger.info(f"Rate Card Items: {rate_card_items}")
        current_app.logger.info(f"Income Items: {income_items}")
        
        # Parse invoice date
        try:
            invoice_date = datetime.strptime(data.get('invoice_date'), "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"success": False, "message": "Invalid date format for invoice date"}), 400
        
        # Generate invoice number
        invoice_number = InvoiceHeader.generate_invoice_number(current_user.company_id)
        
        # Calculate total from provided items (using final amounts with VAT)
        expense_total = sum(float(item.get('final_amount', 0)) for item in expense_items)
        rate_card_total = sum(float(item.get('final_amount', 0)) for item in rate_card_items)
        income_total = sum(float(item.get('amount', 0)) for item in income_items)
        total = expense_total + rate_card_total + income_total
        
        # Create new invoice header
        new_invoice = InvoiceHeader(
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            narration=data.get('narration', ''),
            ship_doc_entry_id=entry.id,
            customer_id=customer_id,
            company_id=current_user.company_id,
            total=total,
            created_by=current_user.id
        )
        
        db.session.add(new_invoice)
        db.session.flush()  # Get the new invoice ID before adding details
        
        # Process expense items (with VAT settlements)
        for item in expense_items:
            expense_id = item.get('expense_id')
            charged_amount_before_vat = float(item.get('charged_amount_before_vat', 0))
            vat_percentage = float(item.get('vat_percentage', 0))
            vat_amount = float(item.get('vat_amount', 0))
            final_amount = float(item.get('final_amount', 0))
            
            # Validate VAT calculation
            expected_vat = (charged_amount_before_vat * vat_percentage) / 100 if vat_percentage > 0 else 0
            expected_final = charged_amount_before_vat + expected_vat
            
            # Allow small rounding differences (0.01)
            if abs(expected_vat - vat_amount) > 0.01 or abs(expected_final - final_amount) > 0.01:
                current_app.logger.warning(f"VAT calculation mismatch for expense {expense_id}")
                # Recalculate to ensure consistency
                vat_amount = expected_vat
                final_amount = expected_final
            
            expense = ShipmentExpense.query.get(expense_id)
            if not expense:
                current_app.logger.warning(f"Expense ID {expense_id} not found. Skipping.")
                continue
            
            # Validate against available balance (using charged amount before VAT)
            if hasattr(expense, 'balance_amount') and expense.balance_amount is not None:
                if charged_amount_before_vat > expense.balance_amount:
                    raise ValueError(f"Charged amount {charged_amount_before_vat} exceeds available balance {expense.balance_amount} for expense {expense_id}")
            else:
                if not hasattr(expense, 'charged_amount') or expense.charged_amount is None:
                    expense.charged_amount = 0
                expense.balance_amount = expense.chargeable_amount if expense.chargeable_amount is not None else expense.amount
                
                if charged_amount_before_vat > expense.balance_amount:
                    raise ValueError(f"Charged amount {charged_amount_before_vat} exceeds available balance {expense.balance_amount} for expense {expense_id}")
            
            # Create settlement record (using charged amount before VAT)
            settlement = ExpenseSettlement(
                expense_id=expense_id,
                invoice_id=new_invoice.id,
                shipment_id=entry.id,
                amount_charged=charged_amount_before_vat,  # Settlement tracks pre-VAT amount
                created_by=current_user.id
            )
            db.session.add(settlement)
            db.session.flush()
            
            # Create invoice detail with VAT information
            detail = InvoiceDetail(
                invoice_header_id=new_invoice.id,
                expense_id=expense_id,
                description=expense.narration,
                original_amount=expense.amount,
                margin=expense.margin,
                original_chargeable_amount=expense.chargeable_amount,
                charged_amount_before_vat=charged_amount_before_vat,  # New field
                vat_percentage=vat_percentage,  # New field
                vat_amount=vat_amount,  # New field
                final_amount=final_amount,  # This now includes VAT
                settlement_id=settlement.id,
                item_type='expense'
            )
            
            db.session.add(detail)
            
            # Update expense balances (using charged amount before VAT)
            expense.charged_amount += charged_amount_before_vat
            expense.balance_amount = expense.chargeable_amount - expense.charged_amount
        
        # Process rate card items (no changes needed for rate cards)
        for item in rate_card_items:
            rate_card_id = item.get('rate_card_id')
            final_amount = float(item.get('final_amount', 0))
            description = item.get('description', '')
            
            rate_card = RateCard.query.get(rate_card_id)
            if not rate_card:
                current_app.logger.warning(f"Rate Card ID {rate_card_id} not found. Skipping.")
                continue
            
            detail = InvoiceDetail(
                invoice_header_id=new_invoice.id,
                rate_card_id=rate_card_id,
                description=description or rate_card.income.description if rate_card.income else "Rate Card Item",
                original_amount=float(rate_card.amount),
                final_amount=final_amount,
                item_type='rate_card'
            )
            
            db.session.add(detail)
            
        # Process custom income items (no changes needed for income)
        for item in income_items:
            description = item.get('description', '')
            amount = float(item.get('amount', 0))
            
            if not description or amount <= 0:
                current_app.logger.warning(f"Invalid income item: {item}. Skipping.")
                continue
            
            detail = InvoiceDetail(
                invoice_header_id=new_invoice.id,
                description=description,
                original_amount=amount,
                final_amount=amount,
                item_type='income'
            )
            
            db.session.add(detail)
        
        db.session.commit()
        
        current_app.logger.info(f"Invoice {new_invoice.invoice_number} created successfully with ID {new_invoice.id}")
        
        return jsonify({
            "success": True,
            "message": "Invoice created successfully",
            "invoice_id": new_invoice.id,
            "invoice_number": new_invoice.invoice_number
        })
        
    except ValueError as e:
        db.session.rollback()
        current_app.logger.error(f"Validation error creating invoice: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating shipment invoice: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred while creating the invoice"
        }), 500
    


@bp.route("/entries/<int:entry_id>/invoices/<int:invoice_id>", methods=["PUT"])
@login_required
def update_shipment_invoice(entry_id, invoice_id):
    """Update an existing invoice with all item types including VAT."""
    try:
        # Get invoice and verify it belongs to the shipment and company
        invoice = InvoiceHeader.query.get_or_404(invoice_id)
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        
        # Parse request data
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        # Update invoice header fields
        if 'invoice_date' in data:
            try:
                invoice.invoice_date = datetime.strptime(data.get('invoice_date'), "%Y-%m-%d").date()
            except ValueError:
                return jsonify({"success": False, "message": "Invalid date format for invoice date"}), 400
        
        if 'narration' in data:
            invoice.narration = data.get('narration')
        
        # Handle invoice details update
        if 'expense_items' in data or 'rate_card_items' in data or 'income_items' in data:
            # Remove existing details and reverse settlements
            for detail in invoice.details:
                # If it's an expense item with settlement, handle the settlement
                if detail.item_type == 'expense' and detail.settlement:
                    # Get the expense to reverse the settlement
                    expense = detail.expense
                    if expense:
                        # Update expense charged and balance amounts (using pre-VAT amount)
                        settlement_amount = detail.charged_amount_before_vat or detail.final_amount
                        expense.charged_amount -= settlement_amount
                        expense.balance_amount = expense.chargeable_amount - expense.charged_amount
                    
                    # Delete the settlement
                    db.session.delete(detail.settlement)
                
                # Delete the detail
                db.session.delete(detail)
            
            # Calculate new total (using final amounts with VAT)
            expense_total = sum(float(item.get('final_amount', 0)) for item in data.get('expense_items', []))
            rate_card_total = sum(float(item.get('final_amount', 0)) for item in data.get('rate_card_items', []))
            income_total = sum(float(item.get('amount', 0)) for item in data.get('income_items', []))
            total = expense_total + rate_card_total + income_total
            
            invoice.total = total
            
            # Add new expense items with VAT
            for item in data.get('expense_items', []):
                expense_id = item.get('expense_id')
                charged_amount_before_vat = float(item.get('charged_amount_before_vat', 0))
                vat_percentage = float(item.get('vat_percentage', 0))
                vat_amount = float(item.get('vat_amount', 0))
                final_amount = float(item.get('final_amount', 0))
                
                # Validate VAT calculation
                expected_vat = (charged_amount_before_vat * vat_percentage) / 100 if vat_percentage > 0 else 0
                expected_final = charged_amount_before_vat + expected_vat
                
                # Allow small rounding differences
                if abs(expected_vat - vat_amount) > 0.01 or abs(expected_final - final_amount) > 0.01:
                    vat_amount = expected_vat
                    final_amount = expected_final
                
                # Get the expense to copy its original data
                expense = ShipmentExpense.query.get(expense_id)
                if not expense:
                    continue  # Skip if expense not found
                
                # Create settlement record (using pre-VAT amount)
                settlement = ExpenseSettlement(
                    expense_id=expense_id,
                    invoice_id=invoice.id,
                    shipment_id=entry.id,
                    amount_charged=charged_amount_before_vat,
                    created_by=current_user.id
                )
                db.session.add(settlement)
                db.session.flush()
                
                # Create invoice detail for expense with VAT
                detail = InvoiceDetail(
                    invoice_header_id=invoice.id,
                    expense_id=expense_id,
                    description=expense.narration,
                    original_amount=expense.amount,
                    margin=expense.margin,
                    original_chargeable_amount=expense.chargeable_amount,
                    charged_amount_before_vat=charged_amount_before_vat,
                    vat_percentage=vat_percentage,
                    vat_amount=vat_amount,
                    final_amount=final_amount,
                    settlement_id=settlement.id,
                    item_type='expense'
                )
                
                db.session.add(detail)
                
                # Update expense charged and balance amounts (using pre-VAT amount)
                expense.charged_amount += charged_amount_before_vat
                expense.balance_amount = expense.chargeable_amount - expense.charged_amount
            
            # Add new rate card items (no changes needed)
            for item in data.get('rate_card_items', []):
                rate_card_id = item.get('rate_card_id')
                final_amount = float(item.get('final_amount', 0))
                description = item.get('description', '')
                
                # Get the rate card to copy its original data
                rate_card = RateCard.query.get(rate_card_id)
                if not rate_card:
                    continue  # Skip if rate card not found
                
                # Create invoice detail for rate card
                detail = InvoiceDetail(
                    invoice_header_id=invoice.id,
                    rate_card_id=rate_card_id,
                    description=description or rate_card.income.description if rate_card.income else "Rate Card Item",
                    original_amount=float(rate_card.amount),
                    final_amount=final_amount,
                    item_type='rate_card'
                )
                
                db.session.add(detail)
            
            # Add new income items (no changes needed)
            for item in data.get('income_items', []):
                description = item.get('description', '')
                amount = float(item.get('amount', 0))
                
                if not description or amount <= 0:
                    continue  # Skip if invalid
                
                detail = InvoiceDetail(
                    invoice_header_id=invoice.id,
                    description=description,
                    original_amount=amount,
                    final_amount=amount,
                    item_type='income'
                )
                
                db.session.add(detail)
        
        # Commit all changes
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Invoice updated successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating shipment invoice: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred while updating the invoice"
        }), 500



@bp.route("/entries/<int:entry_id>/invoices/<int:invoice_id>", methods=["DELETE"])
@login_required
def delete_shipment_invoice(entry_id, invoice_id):
    """Delete an invoice and reverse all expense settlements."""
    try:
        # Get invoice and verify it belongs to the shipment and company
        invoice = InvoiceHeader.query.get_or_404(invoice_id)
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        
        # First, handle expense settlements and update expense balances
        for settlement in invoice.expense_settlements:
            expense = settlement.expense
            if expense:
                # Update expense charged and balance amounts
                expense.charged_amount -= settlement.amount_charged
                expense.balance_amount = expense.chargeable_amount - expense.charged_amount
                
            # Delete each settlement manually
            db.session.delete(settlement)
        
        # Now delete the invoice, which will automatically delete details
        # due to the cascade="all, delete-orphan" relationship
        db.session.delete(invoice)
        
        # Commit all changes
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Invoice deleted successfully and expense settlements reversed"
        })
        
    except Exception as e:
        # Rollback in case of error
        db.session.rollback()
        current_app.logger.error(f"Error deleting shipment invoice: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Error deleting invoice"
        }), 500
        


@bp.route("/entries/<int:entry_id>/invoices/<int:invoice_id>/status", methods=["PUT"])
@login_required
def update_invoice_status(entry_id, invoice_id):
    """Update the payment status of an invoice."""
    try:
        # Get invoice and verify it belongs to the shipment and company
        invoice = InvoiceHeader.query.get_or_404(invoice_id)

        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)

        
        # Parse request data
        data = request.json
        if not data or 'payment_status' not in data:
            return jsonify({"success": False, "message": "Payment status is required"}), 400
        
        # Update payment status
        try:
            new_status = int(data.get('payment_status'))
            if new_status not in [0, 1, 2, 3]:  # Assuming status codes: 0=Pending, 1=Partial, 2=Paid, 3=Cancelled
                return jsonify({"success": False, "message": "Invalid payment status value"}), 400
            
            invoice.payment_status = new_status
            db.session.commit()
            
            return jsonify({
                "success": True,
                "message": "Invoice status updated successfully",
                "new_status": new_status,
                "status_text": get_payment_status_text(new_status)
            })
            
        except ValueError:
            return jsonify({"success": False, "message": "Payment status must be a number"}), 400
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating invoice status: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred while updating the invoice status"
        }), 500


@bp.route("/entries/<int:entry_id>/expenses/<int:expense_id>/settlements", methods=["GET"])
@login_required
def get_expense_settlements(entry_id, expense_id):
    """Get settlement history for a specific expense."""
    try:
        # Verify expense exists and belongs to the shipment and company
        expense = ShipmentExpense.query.get_or_404(expense_id)
        
        
        # Get all settlements for this expense
        settlements = ExpenseSettlement.query.filter_by(expense_id=expense_id).order_by(ExpenseSettlement.created_at.desc()).all()
        
        # Format settlement data
        settlement_list = []
        for settlement in settlements:
            settlement_data = {
                "id": settlement.id,
                "invoice_id": settlement.invoice_id,
                "invoice_number": settlement.invoice.invoice_number if settlement.invoice else "Unknown",
                "amount_charged": settlement.amount_charged,
                "formatted_amount": f"{expense.currency.CurrencyCode} {settlement.amount_charged:,.2f}" if expense.currency else f"{settlement.amount_charged:,.2f}",
                "created_by": settlement.creator.name if settlement.creator else "Unknown",
                "created_at": settlement.created_at.isoformat() if settlement.created_at else None
            }
            settlement_list.append(settlement_data)
        
        # Add summary data
        summary = {
            "total_chargeable": expense.chargeable_amount,
            "total_charged": expense.charged_amount,
            "balance_remaining": expense.balance_amount,
            "is_fully_settled": expense.is_fully_settled,
            "settlement_count": len(settlements)
        }
        
        return jsonify({
            "success": True,
            "expense_id": expense_id,
            "settlements": settlement_list,
            "summary": summary
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting expense settlements: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred while retrieving the expense settlements"
        }), 500


@bp.route("/entries/<int:entry_id>/available-expenses", methods=["GET"])
@login_required
def get_available_expenses(entry_id):
    """Get all expenses with available balance for invoicing."""
    try:
        # Verify shipment exists and belongs to user's company        
        
        # Get all expenses for this shipment that have available balance
        expenses = ShipmentExpense.query.filter_by(
            shipment_id=entry_id,
            company_id=current_user.company_id
        ).filter(ShipmentExpense.balance_amount > 0).all()
        
        # Prepare the response data
        available_expenses = []
        for expense in expenses:
            expense_data = {
                "id": expense.id,
                "expense_type_id": expense.expense_type_id,
                "expense_type_description": expense.expense_description,
                "gl_code": expense.expense_type.gl_code if expense.expense_type else None,
                "narration": expense.narration,
                "amount": expense.amount,
                "margin": expense.margin if expense.margin is not None else 0,
                "chargeable_amount": expense.chargeable_amount,
                "charged_amount": expense.charged_amount,
                "balance_amount": expense.balance_amount,
                "formatted_amount": expense.formatted_amount,
                "formatted_chargeable_amount": expense.formatted_chargeable_amount,
                "formatted_balance": f"{expense.currency.CurrencyCode} {expense.balance_amount:,.2f}" if expense.currency else f"{expense.balance_amount:,.2f}",
                "currency_id": expense.currency_id,
                "currency_code": expense.currency.CurrencyCode if expense.currency else None,
                "reference": expense.reference,
                "doc_date": expense.doc_date.isoformat() if expense.doc_date else None,
            }
            available_expenses.append(expense_data)
        
        return jsonify({
            "success": True,
            "expenses": available_expenses
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting available expenses: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred while retrieving available expenses"
        }), 500


@bp.route("/entries/<int:entry_id>/expenses/<int:expense_id>", methods=["GET"])
@login_required
def get_shipment_expense(shipment_id, expense_id):
    """Get a specific expense for a shipment."""
    try:
        # Verify expense exists and belongs to the shipment and company
        expense = ShipmentExpense.query.get_or_404(expense_id)
        
        
        # Format expense data for the response
        expense_data = {
            "id": expense.id,
            "expense_type_id": expense.expense_type_id,
            "expense_type_description": expense.expense_description,
            "narration": expense.narration,
            "amount": expense.amount,
            "margin": expense.margin,
            "chargeable_amount": expense.chargeable_amount,
            "charged_amount": expense.charged_amount,
            "balance_amount": expense.balance_amount,
            # Add other fields as needed
        }
        
        return jsonify({
            "success": True,
            "expense": expense_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting shipment expense: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred while retrieving the expense"
        }), 500

# Helper function for payment status text
def get_payment_status_text(status_code):
    """Return human-readable text for payment status code."""
    status_map = {
        0: "Pending",
        1: "Partially Paid",
        2: "Paid",
        3: "Cancelled"
    }
    return status_map.get(status_code, "Unknown")

@bp.route("/entries/<int:entry_id>/validate-vat", methods=["POST"])
@login_required
def validate_vat_calculation(entry_id):
    """Validate VAT calculation on the server side."""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        base_amount = float(data.get('base_amount', 0))
        vat_percentage = float(data.get('vat_percentage', 0))
        vat_amount = float(data.get('vat_amount', 0))
        
        # Server-side calculation
        expected_vat_amount = (base_amount * vat_percentage) / 100
        expected_final_amount = base_amount + expected_vat_amount
        
        # Check if provided values match server calculation (allow 0.01 rounding difference)
        vat_amount_valid = abs(expected_vat_amount - vat_amount) <= 0.01
        
        return jsonify({
            "success": True,
            "validation": {
                "vat_amount_valid": vat_amount_valid,
                "expected_vat_amount": round(expected_vat_amount, 2),
                "expected_final_amount": round(expected_final_amount, 2)
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error validating VAT calculation: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred while validating VAT calculation"
        }), 500

# Rate Cards
@bp.route("/entries/<int:entry_id>/rate-cards", methods=["GET"])
@login_required
def get_customer_rate_cards(entry_id):
    """Get all rate card items for a shipment's customer."""
    try:
        # Verify shipment exists and belongs to user's company
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        
        # Get the customer_id from the entry
        customer_id = entry.customer_id
        
        if not customer_id:
            return jsonify({
                "success": False,
                "message": "Shipment doesn't have a customer assigned"
            }), 400
        
        # Get all rate cards for this customer
        rate_cards = RateCard.query.filter_by(
            customer_id=customer_id,
            company_id=current_user.company_id
        ).all()
        
        # Format the rate card data
        rate_card_items = []
        for rate in rate_cards:
            item = {
                "id": rate.id,
                "income_id": rate.income_id,
                "income_description": rate.income.description if rate.income else "Unknown",
                "gl_code": rate.income.gl_code if rate.income else None,
                "amount": float(rate.amount),
                "currency_id": rate.currency_id,
                "currency_code": rate.currency.CurrencyCode if rate.currency else None,
                "formatted_amount": f"{rate.currency.CurrencyCode} {float(rate.amount):,.2f}" if rate.currency else f"${float(rate.amount):,.2f}"
            }
            rate_card_items.append(item)
        
        return jsonify({
            "success": True,
            "rate_cards": rate_card_items,
            "customer_id": customer_id,
            "customer_name": entry.customer.customer_name if entry.customer else "Unknown"
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting customer rate cards: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred while retrieving rate card items"
        }), 500

# Add this route to your Flask application (likely in your masters blueprint)

@bp.route('/entries/<int:entry_id>/invoices/<int:invoice_id>/submit', methods=['PUT'])
@login_required
def submit_invoice(entry_id, invoice_id):
    """Submit an invoice - marks it as submitted"""
    try:
        # Verify company access
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)


        # Get the invoice
        invoice = InvoiceHeader.query.filter_by(
            id=invoice_id, 
            ship_doc_entry_id=entry_id,
            company_id=current_user.company_id
        ).first()
        
        if not invoice:
            return jsonify({'success': False, 'message': 'Invoice not found'}), 404

        # Check if already submitted
        if invoice.submitted:
            return jsonify({'success': False, 'message': 'Invoice is already submitted'}), 400

        # Update the submitted status
        invoice.submitted = True
        invoice.submitted_at = get_sri_lanka_time()  # If you have this field
        invoice.submitted_by = current_user.id  # If you have this field
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Invoice submitted successfully',
            'invoice_id': invoice_id,
            'submitted': True
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error submitting invoice: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Failed to submit invoice'
        }), 500

@bp.route("/get-document-validation/<int:doc_id>")
@login_required
def get_company_document_validation(doc_id):
    try:
        # Get the document attachment
        document = ShipDocumentEntryAttachment.query.get_or_404(doc_id)
        
        # Check if document has been validated
        if document.ai_validated not in [1, 2]:
            return jsonify({
                "success": False,
                "message": "Document has not been validated yet"
            })
        
        # Parse the validation results and extracted content
        validation_results = {}
        extracted_content = {}
        document_similarity = 0
        
        if document.validation_results:
            try:
                validation_results = json.loads(document.validation_results)
                # If document_similarity is present at the root of validation_results, save it
                if isinstance(validation_results, dict) and 'document_similarity' in validation_results:
                    document_similarity = validation_results['document_similarity']
            except:
                validation_results = {}
                
        if document.extracted_content:
            try:
                extracted_content = json.loads(document.extracted_content)
            except:
                extracted_content = {}
        
        return jsonify({
            "success": True,
            "results": {
                "validation_results": validation_results,
                "extracted_content": extracted_content,
                "match_percentage": document.validation_percentage,
                "document_similarity": document_similarity,
                "validation_status": document.ai_validated,
                "error": False
            }
        })
    except Exception as e:
        print(f"Error in get_company_document_validation: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)})




# ===============================
# STEP DOCUMENT UPLOAD ROUTES
# ===============================

@bp.route("/container-step-document/upload", methods=["POST"])
@login_required
def upload_container_step_document():
    """Upload a document for a specific container workflow step"""
    try:
        # Extract form data
        entry_id = request.form.get('entry_id')
        container_id = request.form.get('container_id')
        step_id = request.form.get('step_id')
        container_document_id = request.form.get('container_document_id')
        narration = request.form.get('narration', '').strip()
        
        # Validate required fields
        if not all([entry_id, container_id, step_id, container_document_id]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Check if file was uploaded
        if 'document_file' not in request.files or request.files['document_file'].filename == '':
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['document_file']
        original_filename = secure_filename(file.filename)
        
        # Validate file size (10MB limit)
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        
        if file_size > 10 * 1024 * 1024:  # 10MB
            return jsonify({'success': False, 'error': 'File size exceeds 10MB limit'}), 400
        
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{original_filename}"
        
        # Create S3 key
        company_id = get_company_id()
        s3_key = f"{current_app.config['S3_BASE_FOLDER']}/container_step_documents/{company_id}/{entry_id}/{container_id}/{unique_filename}"
        
        print(f"Uploading file: {original_filename} to S3 key: {s3_key}")
        
        # Upload file to S3
        upload_result = upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
        print(f"Upload result: {upload_result}")
        
        # Get workflow_id from step
        step = ContainerDepositWorkflowStep.query.get(step_id)
        if not step:
            return jsonify({'success': False, 'error': 'Invalid step ID'}), 400
        
        # Create database record
        step_document = ContainerWorkflowDocument(
            company_id=company_id,
            entry_id=entry_id,
            container_id=container_id,
            workflow_id=step.workflow_id,
            step_id=step_id,
            container_document_id=container_document_id,
            uploaded_by_id=current_user.id,
            uploaded_file_path=s3_key,
            original_filename=original_filename,
            narration=narration
        )
        
        db.session.add(step_document)
        db.session.commit()
        
        print(f"Step document saved with ID: {step_document.id}")
        
        return jsonify({
            'success': True,
            'message': 'Document uploaded successfully',
            'document': {
                'id': step_document.id,
                'original_filename': step_document.original_filename,
                'narration': step_document.narration,
                'uploaded_time': step_document.uploaded_time.strftime('%Y-%m-%d %H:%M'),
                'uploaded_by_id': step_document.uploaded_by_id
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error uploading step document: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route("/container-step-document/<int:document_id>/download")
@login_required
def download_container_step_document(document_id):
    """SECURE: Download a container step document through app proxy"""
    try:
        
        document = ContainerWorkflowDocument.query.get_or_404(document_id)
        
        # Check permissions (same authorization logic maintained)
        company_id = get_company_id()
        if not current_user.is_super_admin and document.company_id != company_id:
            flash("You do not have permission to access this document.", "danger")
            return redirect(request.referrer or url_for('masters.orders'))
        
        # Check if file path exists
        if not document.uploaded_file_path:
            flash("No file path found for this document.", "danger")
            return redirect(request.referrer or url_for('masters.orders'))
        
        # Normalize the S3 key path
        s3_key = document.uploaded_file_path.replace("\\", "/")
        
        print(f"Downloading container step document securely: {s3_key}")
        
        # REMOVED: Direct S3 URL construction and redirect
        # file_url = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{document.uploaded_file_path}"
        # return redirect(file_url)
        
        # ADDED: Secure serving through app proxy with download headers
        response = serve_s3_file(s3_key)
        
        # Modify headers to force download instead of inline viewing
        if response and hasattr(response, 'headers'):
            # Get filename from S3 key or use a default
            filename = os.path.basename(s3_key) or f"document_{document_id}"
            
            # Force download by changing Content-Disposition header
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            response.headers['Content-Type'] = 'application/octet-stream'
        
        return response
        
    except ClientError as e:
        # Handle S3-specific errors
        print(f"S3 error downloading container step document: {str(e)}")
        
        if e.response['Error']['Code'] == 'NoSuchKey':
            flash("Document file not found in storage.", "danger")
        else:
            flash("Error accessing document from storage.", "danger")
            
        return redirect(request.referrer or url_for('masters.orders'))
        
    except Exception as e:
        print(f"Error downloading container step document: {str(e)}")
        flash("Unable to download file at this time.", "danger")
        return redirect(request.referrer or url_for('masters.orders'))

@bp.route("/container-step-document/<int:document_id>/delete", methods=["POST"])
@login_required
def delete_container_step_document(document_id):
    """Delete a container step document"""
    try:
        document = ContainerWorkflowDocument.query.get_or_404(document_id)
        
        # Check permissions
        company_id = get_company_id()
        
        # TODO: Optionally delete the file from S3 here
        # delete_file_from_s3(current_app.config["S3_BUCKET_NAME"], document.uploaded_file_path)
        
        db.session.delete(document)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Document deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting step document: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ===============================
# API ROUTES FOR FRONTEND
# ===============================

def calculate_container_workflow_progress(container):
    """Calculate workflow progress based on manual step completion only"""
    if not container.workflow_id:
        return None
    
    workflow = ContainerDepositWorkflow.query.get(container.workflow_id)
    if not workflow:
        return None
    
    steps = workflow.workflow_steps.order_by(ContainerDepositWorkflowStep.step_number).all()
    total_steps = len(steps)
    completed_steps = 0
    
    step_details = []
    
    for step in steps:
        # Check for manual completion
        step_completion = ContainerStepCompletion.query.filter_by(
            container_id=container.id,
            step_id=step.id
        ).first()
        
        is_completed = step_completion is not None
        if is_completed:
            completed_steps += 1
        
        # Check if step has any documents (for UI purposes)
        has_documents = step.step_documents.count() > 0
        
        step_details.append({
            'step_id': step.id,
            'step_number': step.step_number,
            'step_name': step.step_name,
            'description': step.description,
            'completed': is_completed,
            'completed_at': step_completion.completed_at.isoformat() if step_completion and step_completion.completed_at else None,
            'completed_by': step_completion.completed_by.full_name if step_completion and step_completion.completed_by else None,
            'completion_notes': step_completion.completion_notes if step_completion else None,
            'has_documents': has_documents
        })
    
    percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0
    
    return {
        'workflow_id': workflow.id,
        'workflow_name': workflow.workflow_name,
        'total_steps': total_steps,
        'completed_steps': completed_steps,
        'percentage': round(percentage, 1),
        'steps': step_details
    }


# Simplified API endpoint for step status update
@bp.route("/api/container/<int:container_id>/step/<int:step_id>/update-status", methods=["POST"])
@login_required
def update_container_step_status(container_id, step_id):
    """API endpoint to manually update container step status"""
    try:
        data = request.get_json()
        action = data.get('action')  # 'complete' or 'incomplete'
        notes = data.get('notes', '')
        
        # Validate input
        if action not in ['complete', 'incomplete']:
            return jsonify({'success': False, 'error': 'Invalid action'})
        
        # Get the container and verify permissions
        container = ImportContainer.query.get_or_404(container_id)
        
        # Get the entry to access the selected workflow
        entry = ShipDocumentEntryMaster.query.get(container.shipment_id)
        if not entry:
            return jsonify({'success': False, 'error': 'Entry not found'})
        
        # Check permissions

        
        # Verify that there's a selected workflow
        if not entry.selected_workflow_id:
            return jsonify({'success': False, 'error': 'No workflow selected for this container'})
        
        # Get the step from the selected workflow
        step = ContainerDepositWorkflowStep.query.filter_by(
            workflow_id=entry.selected_workflow_id,  # Use entry.selected_workflow_id instead of container.workflow_id
            id=step_id
        ).first()
        
        if not step:
            return jsonify({'success': False, 'error': 'Step not found in the selected workflow'})
        
        # Handle step completion
        step_completion = ContainerStepCompletion.query.filter_by(
            container_id=container_id,
            step_id=step_id
        ).first()
        
        if action == 'complete':
            if not step_completion:
                # Create new completion record
                step_completion = ContainerStepCompletion(
                    container_id=container_id,
                    step_id=step_id,
                    completed_at=datetime.utcnow(),
                    completed_by_id=current_user.id,
                    completion_notes=notes
                )
                db.session.add(step_completion)
            else:
                # Update existing record
                step_completion.completed_at = datetime.utcnow()
                step_completion.completed_by_id = current_user.id
                step_completion.completion_notes = notes
        
        elif action == 'incomplete':
            if step_completion:
                db.session.delete(step_completion)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Step marked as {action}',
            'step_id': step_id,
            'container_id': container_id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating step status: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': 'An error occurred while updating step status'})
    

@bp.route("/api/workflow/<int:workflow_id>/details")
@login_required
def get_workflow_details(workflow_id):
    """Get workflow details for frontend display"""
    try:
        workflow = ContainerDepositWorkflow.query.get_or_404(workflow_id)
        
        return jsonify({
            'success': True,
            'workflow': {
                'id': workflow.id,
                'workflow_code': workflow.workflow_code,
                'workflow_name': workflow.workflow_name,
                'step_count': workflow.workflow_steps.count()
            }
        })
        
    except Exception as e:
        print(f"Error fetching workflow details: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route("/api/container/<int:container_id>/workflow-progress")
@login_required
def get_container_workflow_progress(container_id):
    """Get workflow progress for a specific container"""
    try:
        container = ImportContainer.query.get_or_404(container_id)
        
        # Get the entry and selected workflow
        entry = ShipDocumentEntryMaster.query.get(container.shipment_id)
        if not entry or not entry.selected_workflow_id:
            return jsonify({'success': False, 'error': 'No workflow selected for this container'}), 400
        
        workflow = ContainerDepositWorkflow.query.get(entry.selected_workflow_id)
        if not workflow:
            return jsonify({'success': False, 'error': 'Workflow not found'}), 404
        
        # Calculate progress
        total_steps = workflow.workflow_steps.count()
        completed_steps = 0
        
        step_progress = []
        
        for step in workflow.workflow_steps.order_by(ContainerDepositWorkflowStep.step_number):
            # Check for manual completion - THIS IS THE ONLY COMPLETION CRITERIA
            step_completion = ContainerStepCompletion.query.filter_by(
                container_id=container_id,
                step_id=step.id
            ).first()
            
            is_manually_completed = step_completion is not None
            
            # Check if step has any documents (for UI display purposes only)
            has_documents = step.step_documents.count() > 0
            
            # For UI information only - document upload status
            mandatory_docs = step.step_documents.filter_by(is_mandatory=True).all()
            total_mandatory = len(mandatory_docs)
            uploaded_mandatory = 0
            
            for step_doc in mandatory_docs:
                uploaded_count = ContainerWorkflowDocument.query.filter_by(
                    container_id=container_id,
                    step_id=step.id,
                    container_document_id=step_doc.document_id
                ).count()
                
                if uploaded_count > 0:
                    uploaded_mandatory += 1
            
            # SIMPLIFIED LOGIC: Step completion is ONLY based on manual marking
            step_completed = is_manually_completed
            
            if step_completed:
                completed_steps += 1
            
            step_progress.append({
                'step_id': step.id,
                'step_number': step.step_number,
                'step_name': step.step_name,
                'description': step.description,
                'completed': step_completed,
                'manually_completed': is_manually_completed,
                'completed_at': step_completion.completed_at.isoformat() if step_completion and step_completion.completed_at else None,
                'completed_by': step_completion.completed_by.name if step_completion and step_completion.completed_by else None,
                'completion_notes': step_completion.completion_notes if step_completion else None,
                'has_documents': has_documents,
                'mandatory_uploaded': uploaded_mandatory,
                'mandatory_total': total_mandatory
            })
        
        overall_percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0
        
        return jsonify({
            'success': True,
            'progress': {
                'container_id': container_id,
                'workflow_id': workflow.id,
                'workflow_name': workflow.workflow_name,
                'total_steps': total_steps,
                'completed_steps': completed_steps,
                'percentage': round(overall_percentage, 2),
                'steps': step_progress
            }
        })
        
    except Exception as e:
        print(f"Error fetching container progress: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
      


@bp.route("/api/entry/<int:entry_id>/workflow-summary")
@login_required
def get_entry_workflow_summary(entry_id):
    """Get overall workflow summary for all containers in an entry"""
    try:
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        if not entry.selected_workflow_id:
            return jsonify({'success': False, 'error': 'No workflow selected for this entry'}), 400
        
        workflow = ContainerDepositWorkflow.query.get(entry.selected_workflow_id)
        if not workflow:
            return jsonify({'success': False, 'error': 'Workflow not found'}), 404
        
        containers = ImportContainer.query.filter_by(shipment_id=entry_id).all()
        
        summary = {
            'entry_id': entry_id,
            'workflow': {
                'id': workflow.id,
                'code': workflow.workflow_code,
                'name': workflow.workflow_name,
                'total_steps': workflow.workflow_steps.count()
            },
            'containers': {
                'total': len(containers),
                'completed': 0,
                'in_progress': 0,
                'not_started': 0
            },
            'overall_percentage': 0
        }
        
        total_percentage = 0
        
        for container in containers:
            # Get container progress
            completed_steps = 0
            total_steps = workflow.workflow_steps.count()
            
            for step in workflow.workflow_steps:
                mandatory_docs = step.step_documents.filter_by(is_mandatory=True).all()
                step_completed = True
                
                for step_doc in mandatory_docs:
                    uploaded_count = ContainerWorkflowDocument.query.filter_by(
                        container_id=container.id,
                        step_id=step.id,
                        container_document_id=step_doc.document_id
                    ).count()
                    
                    if uploaded_count == 0:
                        step_completed = False
                        break
                
                if step_completed:
                    completed_steps += 1
            
            container_percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0
            total_percentage += container_percentage
            
            if container_percentage == 100:
                summary['containers']['completed'] += 1
            elif container_percentage > 0:
                summary['containers']['in_progress'] += 1
            else:
                summary['containers']['not_started'] += 1
        
        summary['overall_percentage'] = round(total_percentage / len(containers), 2) if containers else 0
        
        return jsonify({
            'success': True,
            'summary': summary
        })
        
    except Exception as e:
        print(f"Error fetching entry workflow summary: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route("/api/entry/<int:entry_id>/containers-with-workflow")
@login_required
def get_containers_with_workflow_data(entry_id):
    """Get containers with their workflow progress data"""
    try:
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        # Check permissions
        company_id = get_company_id()
        
        containers = ImportContainer.query.filter_by(shipment_id=entry_id).all()
        containers_data = []
        
        for container in containers:
            container_data = {
                'id': container.id,
                'container_number': container.container_number,
                'container_size': container.container_size.name if container.container_size else None,
                'container_type': container.container_type.name if container.container_type else None,
                'remarks': container.remarks,
                'progress': {
                    'completed_steps': 0,
                    'total_steps': 0,
                    'percentage': 0
                }
            }
            
            # Calculate progress if workflow is selected
            if entry.selected_workflow_id:
                workflow = ContainerDepositWorkflow.query.get(entry.selected_workflow_id)
                if workflow:
                    total_steps = workflow.workflow_steps.count()
                    completed_steps = 0
                    
                    for step in workflow.workflow_steps:
                        # FIXED: Only check for manual completion, not document uploads
                        step_completion = ContainerStepCompletion.query.filter_by(
                            container_id=container.id,
                            step_id=step.id
                        ).first()
                        
                        # Step is completed ONLY if manually marked complete
                        if step_completion is not None:
                            completed_steps += 1
                    
                    container_data['progress'] = {
                        'completed_steps': completed_steps,
                        'total_steps': total_steps,
                        'percentage': round((completed_steps / total_steps * 100), 2) if total_steps > 0 else 0
                    }
            
            containers_data.append(container_data)
        
        return jsonify({
            'success': True,
            'containers': containers_data
        })
        
    except Exception as e:
        print(f"Error fetching containers with workflow data: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    
# Add this route to save workflow selection to the entry
@bp.route("/api/entry/<int:entry_id>/save-workflow", methods=["POST"])
@login_required
def save_entry_workflow(entry_id):
    """Save selected workflow for an entry"""
    try:
        print(f"[DEBUG] Received request to save workflow for entry_id: {entry_id}")
        
        workflow_id = request.json.get('workflow_id') if request.is_json else request.form.get('workflow_id')
        print(f"[DEBUG] Extracted workflow_id: {workflow_id}")
        
        if not workflow_id:
            print("[ERROR] No workflow_id provided in request")
            return jsonify({'success': False, 'error': 'Workflow ID is required'}), 400
        
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        print(f"[DEBUG] Retrieved entry: ID={entry.id}, Company_ID={entry.company_id}")
        
        # Check permissions
        company_id = get_company_id()
        
        # Verify workflow exists and belongs to company
        workflow = ContainerDepositWorkflow.query.get(workflow_id)
        if not workflow:
            print("[ERROR] Workflow not found in DB")
            return jsonify({'success': False, 'error': 'Workflow not found'}), 404
        
        print(f"[DEBUG] Retrieved workflow: ID={workflow.id}, Company_ID={workflow.company_id}")
        

        # Update entry with selected workflow
        entry.selected_workflow_id = workflow_id
        db.session.commit()
        print(f"[SUCCESS] Workflow ID {workflow_id} saved to entry ID {entry_id}")
        
        return jsonify({
            'success': True,
            'message': 'Workflow saved successfully',
            'workflow': {
                'id': workflow.id,
                'workflow_code': workflow.workflow_code,
                'workflow_name': workflow.workflow_name,
                'step_count': workflow.workflow_steps.count()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"[EXCEPTION] Error saving workflow selection: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Add this route to your existing Flask routes

@bp.route("/api/container/<int:container_id>/step/<int:step_id>/documents")
@login_required
def get_container_step_documents(container_id, step_id):
    """Get step information and uploaded documents for a specific workflow step"""
    try:
        # Get the container and verify access
        container = ImportContainer.query.get_or_404(container_id)
        
        # Check permissions
        company_id = get_company_id()
        entry = ShipDocumentEntryMaster.query.get(container.shipment_id)
        
        # Get the workflow step information
        step = ContainerDepositWorkflowStep.query.get_or_404(step_id)
        
        # Verify the step belongs to the selected workflow
        if not entry.selected_workflow_id or step.workflow_id != entry.selected_workflow_id:
            return jsonify({
                'success': False,
                'error': 'Step does not belong to the selected workflow'
            }), 400
        
        # Get required documents for this step
        required_documents = []
        for step_doc in step.step_documents.all():
            # Get uploaded documents for this specific requirement
            uploaded_docs = ContainerWorkflowDocument.query.filter_by(
                container_id=container_id,
                step_id=step_id,
                container_document_id=step_doc.document_id
            ).all()
            
            required_documents.append({
                'id': step_doc.document_id,
                'document_name': step_doc.document.document_name,
                'document_code': step_doc.document.document_code,
                'is_mandatory': step_doc.is_mandatory,
                'uploaded_documents': [{
                    'id': doc.id,
                    'original_filename': doc.original_filename,
                    'narration': doc.narration,
                    'uploaded_time': doc.uploaded_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'uploaded_by_id': doc.uploaded_by_id
                } for doc in uploaded_docs]
            })
        
        # Count mandatory documents
        mandatory_total = sum(1 for doc in required_documents if doc['is_mandatory'])
        mandatory_uploaded = sum(1 for doc in required_documents 
                               if doc['is_mandatory'] and len(doc['uploaded_documents']) > 0)
        
        step_data = {
            'step_number': step.step_number,
            'step_name': step.step_name,
            'description': step.description,
            'mandatory_total': mandatory_total,
            'mandatory_uploaded': mandatory_uploaded,
            'completed': mandatory_uploaded >= mandatory_total,
            'required_documents': required_documents
        }
        
        return jsonify({
            'success': True,
            'step_info': step_data,
            'documents': []  # Keep for backward compatibility, but data is in step_info.required_documents
        })
        
    except Exception as e:
        print(f"Error getting container step documents: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while loading document information'
        }), 500






# PO MASTERS
#####################

# Add these routes to your app/po/routes.py file

# SUPPLIERS ROUTES
@bp.route('/suppliers')
@login_required
def suppliers():
    """List all suppliers"""
    
    # Get filter parameters
    search = request.args.get('search', '', type=str)
    status = request.args.get('status', '', type=str)
    per_page = request.args.get('per_page', 10, type=int)
    page = request.args.get('page', 1, type=int)
    
    # Base query
    query = POSupplier.query.filter_by(company_id=current_user.company_id)
    
    # Apply search filter
    if search:
        query = query.filter(
            db.or_(
                POSupplier.supplier_code.contains(search),
                POSupplier.supplier_name.contains(search)
            )
        )
    
    # Order by creation date (newest first)
    query = query.order_by(POSupplier.created_at.desc())
    
    # Get all suppliers (or paginate if needed)
    suppliers = query.all()
    
    return render_template('masters/suppliers.html', suppliers=suppliers)

@bp.route('/suppliers/new', methods=['GET', 'POST'])
@login_required
def new_supplier():
    """Create new supplier"""
    
    if request.method == 'POST':
        supplier_code = request.form.get('supplier_code', '').strip()
        supplier_name = request.form.get('supplier_name', '').strip()
        
        # Validation
        if not supplier_code:
            flash('Supplier Code is required', 'danger')
            return render_template('masters/supplier_form.html')
        
        if not supplier_name:
            flash('Supplier Name is required', 'danger')
            return render_template('masters/supplier_form.html')
        
        # Check if supplier code already exists
        existing = POSupplier.query.filter_by(
            supplier_code=supplier_code,
            company_id=current_user.company_id
        ).first()
        
        if existing:
            flash('Supplier Code already exists', 'danger')
            return render_template('masters/supplier_form.html')
        
        # Create new supplier
        supplier = POSupplier(
            supplier_code=supplier_code,
            supplier_name=supplier_name,
            company_id=current_user.company_id
        )
        
        try:
            db.session.add(supplier)
            db.session.commit()
            flash('Supplier created successfully', 'success')
            return redirect(url_for('masters.suppliers'))
        except Exception as e:
            db.session.rollback()
            flash('Error creating supplier', 'danger')
    
    return render_template('masters/supplier_form.html')

@bp.route('/suppliers/edit/<int:supplier_id>', methods=['GET', 'POST'])
@login_required
def edit_supplier(supplier_id):
    """Edit supplier"""
    
    supplier = POSupplier.query.filter_by(
        id=supplier_id,
        company_id=current_user.company_id
    ).first_or_404()
    
    if request.method == 'POST':
        supplier_code = request.form.get('supplier_code', '').strip()
        supplier_name = request.form.get('supplier_name', '').strip()
        
        # Validation
        if not supplier_code:
            flash('Supplier Code is required', 'danger')
            return render_template('masters/supplier_form.html', supplier=supplier)
        
        if not supplier_name:
            flash('Supplier Name is required', 'danger')
            return render_template('masters/supplier_form.html', supplier=supplier)
        
        # Check if supplier code already exists (excluding current)
        existing = POSupplier.query.filter(
            POSupplier.supplier_code == supplier_code,
            POSupplier.company_id == current_user.company_id,
            POSupplier.id != supplier_id
        ).first()
        
        if existing:
            flash('Supplier Code already exists', 'danger')
            return render_template('masters/supplier_form.html', supplier=supplier)
        
        # Update supplier
        supplier.supplier_code = supplier_code
        supplier.supplier_name = supplier_name
        
        try:
            db.session.commit()
            flash('Supplier updated successfully', 'success')
            return redirect(url_for('masters.suppliers'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating supplier', 'danger')
    
    return render_template('masters/supplier_form.html', supplier=supplier)

@bp.route('/suppliers/delete/<int:supplier_id>', methods=['POST'])
@login_required
def delete_supplier(supplier_id):
    """Delete supplier"""
    
    supplier = POSupplier.query.filter_by(
        id=supplier_id,
        company_id=current_user.company_id
    ).first_or_404()
    
    try:
        db.session.delete(supplier)
        db.session.commit()
        flash('Supplier deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting supplier', 'danger')
    
    return redirect(url_for('masters.suppliers'))





# MATERIALS ROUTES
@bp.route('/materials')
@login_required
def materials():
    """List all materials with HS code information and expiry status"""
    
    # Get filter parameters
    search = request.args.get('search', '', type=str)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Base query with explicit HS code join
    query = POMaterial.query.filter_by(company_id=current_user.company_id).outerjoin(
        HSCode, POMaterial.hs_code_id == HSCode.id
    )
    
    # Apply search filter
    if search:
        query = query.filter(
            db.or_(
                POMaterial.material_code.contains(search),
                POMaterial.material_name.contains(search),
                HSCode.code.contains(search)
            )
        )
    
    # Order by creation date (newest first)
    query = query.order_by(POMaterial.created_at.desc())
    
    # Get all materials
    materials = query.all()
    
    # Calculate expiry status for each material
    today = datetime.now().date()
    warning_date = today + timedelta(days=30)
    
    for material in materials:
        material.expiry_status = 'none'  # Default: no documents
        
        if material.hs_code_id:
            # Get all uploaded documents for this material
            uploaded_docs = MaterialHSDocuments.query.filter_by(
                material_id=material.id,
                hs_code_id=material.hs_code_id,
                company_id=current_user.company_id
            ).all()
            
            if uploaded_docs:
                # Check if any document expires within 30 days
                has_expiring_docs = False
                for doc in uploaded_docs:
                    if doc.expiry_date and doc.expiry_date <= warning_date:
                        has_expiring_docs = True
                        break
                
                material.expiry_status = 'warning' if has_expiring_docs else 'good'
    
    return render_template('masters/materials.html', materials=materials)


from urllib.parse import unquote

@bp.route('/materials/new', methods=['GET', 'POST'])
@login_required
def new_material():
   """Create new material"""
   
   if request.method == 'POST':
       material_code = request.form.get('material_code', '').strip()
       material_name = request.form.get('material_name', '').strip()
       
       # Validation
       if not material_code:
           flash('Material Code is required', 'danger')
           return render_template('masters/material_form.html')
       
       if not material_name:
           flash('Material Name is required', 'danger')
           return render_template('masters/material_form.html')
       
       # Check if material code already exists
       existing = POMaterial.query.filter_by(
           material_code=material_code,
           company_id=current_user.company_id
       ).first()
       
       if existing:
           flash('Material Code already exists', 'danger')
           return render_template('masters/material_form.html')
       
       # Create new material
       material = POMaterial(
           material_code=material_code,
           material_name=material_name,
           company_id=current_user.company_id
       )
       
       try:
           db.session.add(material)
           db.session.commit()
           flash('Material created successfully', 'success')
           return redirect(url_for('masters.materials'))
       except Exception as e:
           db.session.rollback()
           flash('Error creating material', 'danger')
   
   return render_template('masters/material_form.html')


@bp.route('/download-material-document/<int:document_id>')
@login_required
def download_material_document(document_id):
    """SECURE: Download material document through app proxy"""
    try:
        # Get document
        material_doc = MaterialHSDocuments.query.filter_by(
            id=document_id
        ).first_or_404()
        
        # Optional: Add permission checks here if needed
        # For example, check if user has access to this material:
        # if not user_can_access_material(current_user, material_doc):
        #     flash('Access denied to this material document', 'danger')
        #     return redirect(url_for('masters.materials'))
        
        # Check if file path exists
        if not material_doc.file_path:
            flash('No file path found for this document', 'danger')
            return redirect(url_for('masters.materials'))
        
        # Normalize the S3 key path
        s3_key = material_doc.file_path.replace("\\", "/")
        
        print(f"Downloading material document securely: {s3_key}")
        
        # REMOVED: Presigned URL generation and redirect
        # s3_bucket = current_app.config['S3_BUCKET_NAME']
        # file_url = get_s3_url(s3_bucket, material_doc.file_path)
        # return redirect(file_url)
        
        # ADDED: Secure serving through app proxy with download headers
        response = serve_s3_file(s3_key)
        
        # Modify headers to force download instead of inline viewing
        if response and hasattr(response, 'headers'):
            # Get filename from S3 key or create a meaningful name
            filename = os.path.basename(s3_key) or f"material_document_{document_id}"
            
            # Add file extension if not present
            if not os.path.splitext(filename)[1]:
                filename += ".pdf"  # Default to PDF, adjust based on your needs
            
            # Force download by changing Content-Disposition header
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            response.headers['Content-Type'] = 'application/octet-stream'
        
        return response
        
    except ClientError as e:
        # Handle S3-specific errors
        current_app.logger.error(f"S3 error downloading material document: {str(e)}")
        print(f"S3 error downloading material document: {str(e)}")
        
        if e.response['Error']['Code'] == 'NoSuchKey':
            flash('Document file not found in storage', 'danger')
        else:
            flash('Error accessing document from storage', 'danger')
            
        return redirect(url_for('masters.materials'))
        
    except Exception as e:
        current_app.logger.error(f"Error downloading material document: {str(e)}")
        print(f"Error downloading material document: {str(e)}")
        flash('Error downloading document', 'danger')
        return redirect(url_for('masters.materials'))
    


@bp.route('/delete-material-document/<int:document_id>', methods=['POST'])
@login_required
def delete_material_document(document_id):
    """Delete material document"""
    try:
        # Get document
        material_doc = MaterialHSDocuments.query.filter_by(
            id=document_id,
            company_id=current_user.company_id
        ).first_or_404()
        
        # Delete from S3 using existing utility
        s3_bucket = current_app.config['S3_BUCKET_NAME']
        delete_result = delete_file_from_s3(s3_bucket, material_doc.file_path)
        
        if not delete_result:
            current_app.logger.warning(f"Failed to delete file from S3: {material_doc.file_path}")
            # Continue with database deletion even if S3 deletion fails
        
        # Delete from database
        db.session.delete(material_doc)
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": "Document deleted successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting material document: {str(e)}")
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

@bp.route('/material-hs-summary/<int:material_id>')
@login_required
def material_hs_summary(material_id):
    """Get summary of material HS code and documents"""
    material = POMaterial.query.filter_by(
        id=material_id,
        company_id=current_user.company_id
    ).first_or_404()
    
    if not material.hs_code_id:
        return jsonify({
            'success': True,
            'has_hs_code': False,
            'documents_required': 0,
            'documents_uploaded': 0
        })
    
    # Count required documents
    required_count = HSCodeDocument.query.filter_by(
        hscode_id=material.hs_code_id
    ).count()
    
    # Count uploaded documents
    uploaded_count = MaterialHSDocuments.query.filter_by(
        material_id=material_id,
        hs_code_id=material.hs_code_id,
        company_id=current_user.company_id
    ).count()
    
    return jsonify({
        'success': True,
        'has_hs_code': True,
        'hs_code': material.hs_code.code,
        'documents_required': required_count,
        'documents_uploaded': uploaded_count,
        'completion_percentage': (uploaded_count / required_count * 100) if required_count > 0 else 100
    })

@bp.route('/view-sample-document/<path:file_path>')
@login_required
def view_sample_document(file_path):
    """SECURE: View sample document through app proxy"""
    try:
        from urllib.parse import unquote
        
        # Decode the file path (handles URL encoding)
        decoded_path = unquote(file_path)
        
        # Normalize the S3 key path
        s3_key = decoded_path.replace("\\", "/")  # Normalize path separators
        
        print(f"Attempting to view sample document: {s3_key}")
        
        # Optional: Add permission checks for sample documents if needed
        # For example, check if user has access to sample documents:
        # if not user_can_access_samples(current_user):
        #     flash('Access denied to sample documents', 'danger')
        #     return redirect(url_for('masters.materials'))
        
        # REMOVED: Presigned URL generation and redirect
        # s3_bucket = current_app.config['S3_BUCKET_NAME']
        # file_url = get_s3_url(s3_bucket, decoded_path)
        # return redirect(file_url)
        
        # ADDED: Direct secure serving through app proxy
        return serve_s3_file(s3_key)
        
    except ClientError as e:
        # Handle S3-specific errors
        print(f"S3 error accessing sample document: {str(e)}")
        current_app.logger.error(f"S3 error viewing sample document: {str(e)}")
        
        if e.response['Error']['Code'] == 'NoSuchKey':
            flash('Sample document not found', 'danger')
        else:
            flash('Error accessing sample document from storage', 'danger')
            
        return redirect(url_for('masters.materials'))
        
    except Exception as e:
        current_app.logger.error(f"Error viewing sample document: {str(e)}")
        print(f"Error serving sample document: {str(e)}")
        flash('Error viewing sample document', 'danger')
        return redirect(url_for('masters.materials'))
   

@bp.route('/materials/edit/<int:material_id>', methods=['GET', 'POST'])
@login_required
def edit_material(material_id):
    """Edit material"""
    
    material = POMaterial.query.filter_by(
        id=material_id,
        company_id=current_user.company_id
    ).first_or_404()
    
    if request.method == 'POST':
        material_code = request.form.get('material_code', '').strip()
        material_name = request.form.get('material_name', '').strip()
        
        # Validation
        if not material_code:
            flash('Material Code is required', 'danger')
            return render_template('masters/material_form.html', material=material)
        
        if not material_name:
            flash('Material Name is required', 'danger')
            return render_template('masters/material_form.html', material=material)
        
        # Check if material code already exists (excluding current)
        existing = POMaterial.query.filter(
            POMaterial.material_code == material_code,
            POMaterial.company_id == current_user.company_id,
            POMaterial.id != material_id
        ).first()
        
        if existing:
            flash('Material Code already exists', 'danger')
            return render_template('masters/material_form.html', material=material)
        
        # Update material
        material.material_code = material_code
        material.material_name = material_name
        
        try:
            db.session.commit()
            flash('Material updated successfully', 'success')
            return redirect(url_for('masters.materials'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating material', 'danger')
    
    return render_template('masters/material_form.html', material=material)

@bp.route('/materials/delete/<int:material_id>', methods=['POST'])
@login_required
def delete_material(material_id):
    """Delete material"""
    material = POMaterial.query.filter_by(
        id=material_id,
        company_id=current_user.company_id
    ).first_or_404()
    
    try:
        # Delete associated documents first
        MaterialHSDocuments.query.filter_by(
            material_id=material_id,
            company_id=current_user.company_id
        ).delete()
        
        # Delete material
        db.session.delete(material)
        db.session.commit()
        
        flash('Material deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting material', 'danger')
    
    return redirect(url_for('masters.materials'))

@bp.route('/get-hs-codes')
@login_required
def get_hs_codes():
    """Get HS codes for selection with search"""
    search = request.args.get('search', '', type=str)
    
    # Base query - ignore company_id as per requirement
    query = HSCode.query
    
    # Apply search filter with explicit joins
    if search:
        search_term = f"%{search}%"
        query = query.outerjoin(
            HSCodeCategory, HSCode.category_id == HSCodeCategory.id
        ).outerjoin(
            HSCodeDocument, HSCodeDocument.hscode_id == HSCode.id
        ).outerjoin(
            HSCodeIssueBody, HSCodeDocument.issuing_body_id == HSCodeIssueBody.id
        ).filter(
            db.or_(
                HSCode.code.ilike(search_term),
                HSCode.description.ilike(search_term),
                HSCodeCategory.name.ilike(search_term),
                HSCodeIssueBody.name.ilike(search_term)
            )
        ).distinct()
    
    # Get HS codes with their document counts
    hs_codes = query.all()
    
    # Format response
    hs_codes_data = []
    for hs_code in hs_codes:
        hs_codes_data.append({
            'id': hs_code.id,
            'code': hs_code.code,
            'description': hs_code.description,
            'category': hs_code.category.name if hs_code.category else None,
            'documents_count': len(hs_code.documents)
        })
    
    return jsonify({
        'success': True,
        'hs_codes': hs_codes_data
    })

@bp.route('/connect-hs-code', methods=['POST'])
@login_required
def connect_hs_code():
    """Connect HS code to material"""
    try:
        data = request.get_json()
        material_id = data.get('material_id')
        hs_code_id = data.get('hs_code_id')
        
        if not material_id or not hs_code_id:
            return jsonify({
                'success': False,
                'message': 'Material ID and HS Code ID are required'
            }), 400
        
        # Verify material belongs to user's company
        material = POMaterial.query.filter_by(
            id=material_id,
            company_id=current_user.company_id
        ).first()
        
        if not material:
            return jsonify({
                'success': False,
                'message': 'Material not found'
            }), 404
        
        # Verify HS code exists
        hs_code = HSCode.query.get(hs_code_id)
        if not hs_code:
            return jsonify({
                'success': False,
                'message': 'HS Code not found'
            }), 404
        
        # Update material with HS code
        material.hs_code_id = hs_code_id
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'HS Code {hs_code.code} connected successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@bp.route('/disconnect-hs-code', methods=['POST'])
@login_required
def disconnect_hs_code():
    """Disconnect HS code from material"""
    try:
        data = request.get_json()
        material_id = data.get('material_id')
        
        if not material_id:
            return jsonify({
                'success': False,
                'message': 'Material ID is required'
            }), 400
        
        # Verify material belongs to user's company
        material = POMaterial.query.filter_by(
            id=material_id,
            company_id=current_user.company_id
        ).first()
        
        if not material:
            return jsonify({
                'success': False,
                'message': 'Material not found'
            }), 404
        
        # Delete associated documents first
        if material.hs_code_id:
            MaterialHSDocuments.query.filter_by(
                material_id=material_id,
                hs_code_id=material.hs_code_id,
                company_id=current_user.company_id
            ).delete()
        
        # Disconnect HS code
        material.hs_code_id = None
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'HS Code disconnected successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@bp.route('/get-material-documents')
@login_required
def get_material_documents():
    """Get material documents with upload status - works for both customer and CHA sides"""
    material_id = request.args.get('material_id', type=int)
    print(f"Requested material_id: {material_id}")
    
    if not material_id:
        print("Material ID not provided.")
        return jsonify({
            'success': False,
            'message': 'Material ID is required'
        }), 400
    
    # Check if user is from customer side or CHA side based on role
    is_customer_user = current_user.role == 'customer'
    is_cha_user = current_user.role == 'user'  # Assuming 'user' is CHA role
    
    print(f"User role: {current_user.role}, is_customer: {is_customer_user}, is_cha: {is_cha_user}")
    
    # Query material based on user role
    if is_customer_user:
        # Customer side: filter by company_id
        material = POMaterial.query.filter_by(
            id=material_id,
            company_id=current_user.company_id
        ).first()
        print(f"Customer query - Material found: {material is not None}")
    elif is_cha_user:
        # CHA side: no company filter (can access all materials)
        material = POMaterial.query.filter_by(id=material_id).first()
        print(f"CHA query - Material found: {material is not None}")
    else:
        # Other user types: restrict access or handle as needed
        print(f"Access denied for user role: {current_user.role}")
        return jsonify({
            'success': False,
            'message': 'Access denied'
        }), 403
    
    if not material:
        print("Material not found.")
        return jsonify({
            'success': False,
            'message': 'Material not found'
        }), 404
    
    if not material.hs_code_id:
        print("HS Code not assigned to the material.")
        return jsonify({
            'success': True,
            'hs_code': None,
            'material_code': material.material_code,
            'material_name': material.material_name,
            'required_documents': [],
            'uploaded_documents': []
        })
    
    hs_code = HSCode.query.get(material.hs_code_id)
    print(f"HS Code found: {hs_code is not None}")
    
    if not hs_code:
        print("HS Code not found.")
        return jsonify({
            'success': False,
            'message': 'HS Code not found'
        }), 404
    
    required_documents = []
    print(f"Fetching required documents for HS Code ID: {hs_code.id}")
    for doc in hs_code.documents:
        issuing_body_name = doc.issuing_body.name if doc.issuing_body else 'Unknown Issuing Body'
        document_category_name = doc.document_category.name if doc.document_category else 'Unknown Category'
        
        print(f"Required Document: ID={doc.id}, Issuing Body={issuing_body_name}, Category={document_category_name}")
        
        required_documents.append({
            'id': doc.id,
            'issuing_body_name': issuing_body_name,
            'document_category_name': document_category_name,
            'display_name': f"{issuing_body_name} > {document_category_name}",
            'is_mandatory': doc.is_mandatory,
            'sample_file_path': doc.sample_doc
        })
    
    # Query uploaded documents based on user role
    if is_customer_user:
        # Customer side: filter by company_id
        material_docs = MaterialHSDocuments.query.filter_by(
            material_id=material_id,
            hs_code_id=hs_code.id,
            company_id=current_user.company_id
        ).all()
        print(f"Customer query - Found {len(material_docs)} uploaded documents")
    elif is_cha_user:
        # CHA side: filter by material's company_id (show documents for the material's owner company)
        material_docs = MaterialHSDocuments.query.filter_by(
            material_id=material_id,
            hs_code_id=hs_code.id
        ).all()
        print(f"CHA query - Found {len(material_docs)} uploaded documents for company {material.company_id}")
    else:
        # Other roles: no documents
        material_docs = []
    
    uploaded_documents = []
    today = datetime.now().date()
    warning_date = today + timedelta(days=30)
    
    for doc in material_docs:
        required_doc = next((req_doc for req_doc in required_documents if req_doc['id'] == doc.document_id), None)
        
        expiry_status = 'none'
        days_until_expiry = None
        if doc.expiry_date:
            days_until_expiry = (doc.expiry_date - today).days
            if doc.expiry_date <= today:
                expiry_status = 'expired'
            elif doc.expiry_date <= warning_date:
                expiry_status = 'warning'
            else:
                expiry_status = 'good'
        
        print(f"Uploaded Document: ID={doc.id}, Expiry={doc.expiry_date}, Status={expiry_status}")
        
        uploaded_documents.append({
            'id': doc.id,
            'document_id': doc.document_id,
            'file_name': doc.file_name,
            'file_path': doc.file_path,
            'expiry_date': doc.expiry_date.strftime('%Y-%m-%d') if doc.expiry_date else None,
            'expiry_status': expiry_status,
            'days_until_expiry': days_until_expiry,
            'comment': doc.comment,
            'uploaded_at': doc.uploaded_at.strftime('%Y-%m-%d %H:%M'),
            'issuing_body_name': required_doc['issuing_body_name'] if required_doc else 'Unknown',
            'document_category_name': required_doc['document_category_name'] if required_doc else 'Unknown',
            'display_name': required_doc['display_name'] if required_doc else 'Unknown Document',
            'sample_file_path': required_doc['sample_file_path'] if required_doc else None
        })
    
    print("Response ready to be returned.")
    
    return jsonify({
        'success': True,
        'material_code': material.material_code,
        'material_name': material.material_name,
        'hs_code': {
            'id': hs_code.id,
            'code': hs_code.code,
            'description': hs_code.description
        },
        'required_documents': required_documents,
        'uploaded_documents': uploaded_documents
    })


@bp.route('/upload-material-document', methods=['POST'])
@login_required
def upload_material_document():
    """Upload document for material HS code with mandatory expiry date"""
    try:
        material_id = request.form.get('material_id', type=int)
        
        if not material_id:
            return jsonify({
                "success": False, 
                "message": "Material ID is required"
            }), 400
        
        # Verify material belongs to user's company
        material = POMaterial.query.filter_by(
            id=material_id,
            company_id=current_user.company_id
        ).first()
        
        if not material:
            return jsonify({
                "success": False, 
                "message": "Material not found"
            }), 404
        
        # Check if material has HS code
        if not material.hs_code_id:
            return jsonify({
                "success": False, 
                "message": "Material does not have an HS code connected"
            }), 400

        # Process multiple document uploads
        uploaded_count = 0
        errors = []
        
        # Get all required documents for this HS code
        required_docs = HSCodeDocument.query.filter_by(hscode_id=material.hs_code_id).all()
        
        for doc in required_docs:
            file_key = f'document_{doc.id}'
            expiry_key = f'expiry_date_{doc.id}'
            comment_key = f'comment_{doc.id}'
            
            # Check if file was uploaded for this document
            if file_key in request.files:
                file = request.files[file_key]
                if file.filename != '':
                    try:
                        # Get additional form data
                        expiry_date = request.form.get(expiry_key)
                        comment = request.form.get(comment_key, '')
                        
                        # MANDATORY EXPIRY DATE VALIDATION
                        if not expiry_date or not expiry_date.strip():
                            errors.append(f"Expiry date is required for {doc.issuing_body.name if doc.issuing_body else 'Unknown'} > {doc.document_category.name if doc.document_category else 'Unknown'}")
                            continue
                        
                        # Parse expiry date
                        expiry_date_obj = None
                        try:
                            expiry_date_obj = datetime.strptime(expiry_date, '%Y-%m-%d').date()
                            
                            # Check if expiry date is in the future
                            if expiry_date_obj <= datetime.now().date():
                                errors.append(f"Expiry date must be in the future for {doc.issuing_body.name if doc.issuing_body else 'Unknown'} > {doc.document_category.name if doc.document_category else 'Unknown'}")
                                continue
                                
                        except ValueError:
                            errors.append(f"Invalid expiry date format for {doc.issuing_body.name if doc.issuing_body else 'Unknown'} > {doc.document_category.name if doc.document_category else 'Unknown'}")
                            continue
                        
                        # Upload to S3 using existing utility
                        s3_bucket = current_app.config['S3_BUCKET_NAME']
                        s3_base_folder = current_app.config.get('S3_BASE_FOLDER', '')
                        
                        if s3_base_folder:
                            s3_key = f"{s3_base_folder}/material_hs_docs/{uuid.uuid4()}_{secure_filename(file.filename)}"
                        else:
                            s3_key = f"material_hs_docs/{uuid.uuid4()}_{secure_filename(file.filename)}"
                        
                        # Upload to S3
                        file.seek(0)
                        try:
                            upload_result = upload_file_to_s3(file, s3_bucket, s3_key)
                            current_app.logger.info(f"upload_file_to_s3 returned: {upload_result}")
                            
                            if upload_result is False:
                                current_app.logger.error("S3 upload explicitly returned False")
                                errors.append(f"Failed to upload {doc.issuing_body.name if doc.issuing_body else 'Unknown'} > {doc.document_category.name if doc.document_category else 'Unknown'} to S3")
                                continue
                            
                        except Exception as s3_error:
                            current_app.logger.error(f"Exception during S3 upload: {str(s3_error)}")
                            errors.append(f"S3 upload failed for {doc.issuing_body.name if doc.issuing_body else 'Unknown'} > {doc.document_category.name if doc.document_category else 'Unknown'}: {str(s3_error)}")
                            continue
                        
                        # Check if document already exists (for re-upload)
                        existing_doc = MaterialHSDocuments.query.filter_by(
                            material_id=material_id,
                            hs_code_id=material.hs_code_id,
                            document_id=doc.id,
                            company_id=current_user.company_id
                        ).first()
                        
                        if existing_doc:
                            # Update existing document
                            existing_doc.file_path = s3_key
                            existing_doc.file_name = file.filename
                            existing_doc.expiry_date = expiry_date_obj
                            existing_doc.comment = comment
                            existing_doc.uploaded_by = current_user.id
                            existing_doc.uploaded_at = datetime.utcnow()
                        else:
                            # Create new document record
                            material_doc = MaterialHSDocuments(
                                material_id=material_id,
                                hs_code_id=material.hs_code_id,
                                document_id=doc.id,
                                file_path=s3_key,
                                file_name=file.filename,
                                expiry_date=expiry_date_obj,
                                comment=comment,
                                uploaded_by=current_user.id,
                                company_id=current_user.company_id
                            )
                            db.session.add(material_doc)
                        
                        uploaded_count += 1
                        
                    except Exception as e:
                        errors.append(f"Error uploading {doc.issuing_body.name if doc.issuing_body else 'Unknown'} > {doc.document_category.name if doc.document_category else 'Unknown'}: {str(e)}")
                        continue
        
        if uploaded_count == 0:
            return jsonify({
                "success": False,
                "message": "No files were uploaded. " + "; ".join(errors) if errors else "No files selected."
            }), 400
        
        db.session.commit()
        
        message = f"Successfully uploaded {uploaded_count} document(s)"
        if errors:
            message += f". Some errors occurred: {'; '.join(errors)}"

        return jsonify({
            "success": True,
            "message": message
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error uploading material documents: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    

# ORDER UNITS ROUTES
@bp.route('/order-units')
@login_required
def order_units():
    """List all order units"""
    
    # Get filter parameters
    search = request.args.get('search', '', type=str)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Base query
    query = POOrderUnit.query
    
    # Apply search filter
    if search:
        query = query.filter(POOrderUnit.order_unit.contains(search))
    
    # Order by creation date (newest first)
    query = query.order_by(POOrderUnit.created_at.desc())
    
    # Get all order units
    order_units = query.all()
    
    return render_template('masters/order_units.html', order_units=order_units)

@bp.route('/order-units/new', methods=['GET', 'POST'])
@login_required
def new_order_unit():
    """Create new order unit"""
    
    if request.method == 'POST':
        order_unit = request.form.get('order_unit', '').strip()
        
        # Validation
        if not order_unit:
            flash('Order Unit is required', 'danger')
            return render_template('masters/order_unit_form.html')
        
        # Check if order unit already exists
        existing = POOrderUnit.query.filter_by(order_unit=order_unit).first()
        
        if existing:
            flash('Order Unit already exists', 'danger')
            return render_template('masters/order_unit_form.html')
        
        # Create new order unit
        new_unit = POOrderUnit(order_unit=order_unit)
        
        try:
            db.session.add(new_unit)
            db.session.commit()
            flash('Order Unit created successfully', 'success')
            return redirect(url_for('masters.order_units'))
        except Exception as e:
            db.session.rollback()
            flash('Error creating order unit', 'danger')
    
    return render_template('masters/order_unit_form.html')

@bp.route('/order-units/edit/<int:unit_id>', methods=['GET', 'POST'])
@login_required
def edit_order_unit(unit_id):
    """Edit order unit"""
    
    unit = POOrderUnit.query.get_or_404(unit_id)
    
    if request.method == 'POST':
        order_unit = request.form.get('order_unit', '').strip()
        
        # Validation
        if not order_unit:
            flash('Order Unit is required', 'danger')
            return render_template('masters/order_unit_form.html', order_unit=unit)
        
        # Check if order unit already exists (excluding current)
        existing = POOrderUnit.query.filter(
            POOrderUnit.order_unit == order_unit,
            POOrderUnit.id != unit_id
        ).first()
        
        if existing:
            flash('Order Unit already exists', 'danger')
            return render_template('masters/order_unit_form.html', order_unit=unit)
        
        # Update order unit
        unit.order_unit = order_unit
        
        try:
            db.session.commit()
            flash('Order Unit updated successfully', 'success')
            return redirect(url_for('masters.order_units'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating order unit', 'danger')
    
    return render_template('masters/order_unit_form.html', order_unit=unit)

@bp.route('/order-units/delete/<int:unit_id>', methods=['POST'])
@login_required
def delete_order_unit(unit_id):
    """Delete order unit"""
    
    unit = POOrderUnit.query.get_or_404(unit_id)
    
    try:
        db.session.delete(unit)
        db.session.commit()
        flash('Order Unit deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting order unit', 'danger')
    
    return redirect(url_for('masters.order_units'))



# ===============================
# ITEMS TAB
# ===============================

@bp.route("/orders/shipment/<int:entry_id>/items/manual", methods=["POST"])
@login_required
def add_manual_item(entry_id):
    """Add manual item to shipment"""
    try:
        # Verify entry belongs to current user's company
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        # Get form data
        material_code = request.form.get('material_code', '').strip()
        material_name = request.form.get('material_name', '').strip()
        quantity = request.form.get('quantity')
        order_unit = request.form.get('order_unit', '').strip()
        net_price = request.form.get('net_price')
        supplier_name = request.form.get('supplier_name', '').strip()
        po_number = request.form.get('po_number', '').strip()  # New field
        delivery_date = request.form.get('delivery_date')
        remarks = request.form.get('remarks', '').strip()
        line_total = request.form.get('line_total')
        submit_action = request.form.get('submit_action', 'save_close')
        
        # Validate required fields
        if not all([material_code, material_name, quantity, order_unit]):
            flash("Please fill in all required fields", "danger")
            return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab='items'))
        
        # Prepare item data
        item_data = {
            'shipment_id': entry_id,
            'source_type': 'manual',
            'material_code': material_code,
            'material_name': material_name,
            'quantity': Decimal(quantity),
            'order_unit': order_unit,
            'net_price': Decimal(net_price) if net_price else None,
            'line_total': Decimal(line_total) if line_total else None,
            'supplier_name': supplier_name if supplier_name else None,
            'po_number': po_number if po_number else None,  # New field
            'delivery_date': datetime.strptime(delivery_date, '%Y-%m-%d').date() if delivery_date else None,
            'remarks': remarks if remarks else None,
            'company_id': current_user.company_id,
            'created_by': current_user.id
        }
        
        # Create and save item
        item = ShipmentItem(**item_data)
        db.session.add(item)
        db.session.commit()
        
        flash(f"Item '{material_code}' added successfully!", "success")
        
        # Redirect based on submit action
        if submit_action == 'add_another':
            return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab='items', action='add_another'))
        else:
            return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab='items'))
            
    except Exception as e:
        db.session.rollback()
        print(f"Error adding manual item: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f"Error adding item", "danger")
        return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab='items'))


@bp.route("/api/shipment-item/<int:item_id>", methods=["GET"])
@login_required
def get_shipment_item_api(item_id):
    """Get shipment item data via API"""
    try:
        # Get item and verify access
        item = ShipmentItem.query.get_or_404(item_id)

        
        # Convert item to dictionary
        item_data = {
            'id': item.id,
            'material_code': item.material_code,
            'material_name': item.material_name,
            'quantity': float(item.quantity) if item.quantity else 0,
            'order_unit': item.order_unit,
            'net_price': float(item.net_price) if item.net_price else 0,
            'line_total': float(item.line_total) if item.line_total else 0,
            'supplier_name': item.supplier_name,
            'po_number': item.po_number,
            'delivery_date': item.delivery_date.strftime('%Y-%m-%d') if item.delivery_date else None,
            'remarks': item.remarks,
            'source_type': item.source_type
        }
        
        return jsonify(item_data)
        
    except Exception as e:
        print(f"Error getting item data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route("/api/shipment-item/<int:item_id>/edit", methods=["POST"])
@login_required
def edit_shipment_item_api(item_id):
    """Edit shipment item via API"""
    try:
        # Get item and verify access
        item = ShipmentItem.query.get_or_404(item_id)

        
        # Only allow editing of manual items
        if item.source_type != 'manual':
            return jsonify({'success': False, 'error': 'Only manual items can be edited'}), 400
        
        # Update item data
        item.material_code = request.form.get('material_code', '').strip()
        item.material_name = request.form.get('material_name', '').strip()
        item.quantity = Decimal(request.form.get('quantity'))
        item.order_unit = request.form.get('order_unit', '').strip()
        
        net_price = request.form.get('net_price')
        item.net_price = Decimal(net_price) if net_price else None
        
        line_total = request.form.get('line_total')
        item.line_total = Decimal(line_total) if line_total else None
        
        item.supplier_name = request.form.get('supplier_name', '').strip() or None
        item.po_number = request.form.get('po_number', '').strip() or None
        
        delivery_date = request.form.get('delivery_date')
        item.delivery_date = datetime.strptime(delivery_date, '%Y-%m-%d').date() if delivery_date else None
        
        item.remarks = request.form.get('remarks', '').strip() or None
        item.updated_at = get_sri_lanka_time()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Item '{item.material_code}' updated successfully!"
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error editing item: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route("/api/shipment-item/<int:item_id>/delete", methods=["DELETE"])
@login_required
def delete_shipment_item_api(item_id):
    """Delete shipment item via API"""
    try:
        # Get item and verify access
        item = ShipmentItem.query.get_or_404(item_id)
        
        
        material_code = item.material_code
        
        db.session.delete(item)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Item '{material_code}' deleted successfully!"
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting item: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route("/orders/shipment/<int:entry_id>/items/po", methods=["POST"])
@login_required
def add_po_items(entry_id):
    """Add items from PO to shipment"""
    try:
        # Verify entry belongs to current user's company
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)

        
        # Get selected PO item IDs
        selected_po_items = request.form.getlist('selected_po_items')
        
        if not selected_po_items:
            flash("Please select at least one item to add", "warning")
            return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab='items'))
        
        added_count = 0
        
        for po_detail_id in selected_po_items:
            # Get PO detail
            po_detail = PODetail.query.get(int(po_detail_id))
      
            
            # Check if this item is already added to this shipment
            existing_item = ShipmentItem.query.filter_by(
                shipment_id=entry_id,
                po_detail_id=po_detail.id
            ).first()
            
            if existing_item:
                continue  # Skip if already added
            
            # Create shipment item from PO detail
            item_data = {
                'shipment_id': entry_id,
                'source_type': 'po',
                'po_detail_id': po_detail.id,
                'po_header_id': po_detail.po_header_id,
                'po_number': po_detail.po_number,
                'material_code': po_detail.material_code,
                'material_name': po_detail.material_name,
                'quantity': po_detail.quantity_pending,  # Use pending quantity
                'order_unit': po_detail.order_unit,
                'net_price': po_detail.net_price,
                'line_total': po_detail.quantity_pending * po_detail.net_price,
                'supplier_name': po_detail.supplier_name,
                'delivery_date': po_detail.delivery_date,
                'company_id': current_user.company_id,
                'created_by': current_user.id
            }
            
            item = ShipmentItem(**item_data)
            db.session.add(item)
            added_count += 1
        
        db.session.commit()
        
        if added_count > 0:
            flash(f"Successfully added {added_count} item(s) from PO", "success")
        else:
            flash("No new items were added (items may already exist in this shipment)", "info")
        
        return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab='items'))
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding PO items: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f"Error adding PO items", "danger")
        return redirect(url_for('masters.order_shipment', entry_id=entry_id, tab='items'))



def load_shipment_items_data(entry_id):
    """Load shipment items and related data for the items tab - Enhanced with HS code and document info"""
    try:
        # Get shipment items with PO currency, HS code, and document information
        shipment_items_query = db.session.query(
            ShipmentItem,
            POHeader.currency.label('po_currency'),
            POMaterial,
            HSCode
        ).outerjoin(
            PODetail, ShipmentItem.po_detail_id == PODetail.id
        ).outerjoin(
            POHeader, PODetail.po_header_id == POHeader.id
        ).outerjoin(
            POMaterial, db.or_(
                PODetail.material_id == POMaterial.id,  # For PO items
                db.and_(
                    ShipmentItem.source_type == 'manual',
                    POMaterial.material_code == ShipmentItem.material_code,
                    POMaterial.company_id == current_user.company_id
                )  # For manual items, try to match by material code
            )
        ).outerjoin(
            HSCode, POMaterial.hs_code_id == HSCode.id
        ).filter(
            ShipmentItem.shipment_id == entry_id
        ).order_by(ShipmentItem.created_at.desc())
        
        shipment_items_data = shipment_items_query.all()
        
        # Process items to include currency, HS code, and document information
        shipment_items = []
        for item_data in shipment_items_data:
            item = item_data[0]  # ShipmentItem object
            po_currency = item_data[1] or 'LKR'  # Default to LKR if no PO currency
            po_material = item_data[2]  # POMaterial object
            hs_code = item_data[3]  # HSCode object
            
            # Add currency information to the item object
            item.po_currency = po_currency
            
            # Add HS code information
            item.hs_code = hs_code
            item.po_material = po_material
            
            # Get document count if HS code exists
            if hs_code:
                # Get required documents count
                required_docs_count = HSCodeDocument.query.filter_by(
                    hscode_id=hs_code.id
                ).count()
                
                # Get uploaded documents count for this material
                if po_material:
                    uploaded_docs_count = MaterialHSDocuments.query.filter_by(
                        material_id=po_material.id,
                        hs_code_id=hs_code.id
                    ).count()
                else:
                    uploaded_docs_count = 0
                
                item.required_docs_count = required_docs_count
                item.uploaded_docs_count = uploaded_docs_count
            else:
                item.required_docs_count = 0
                item.uploaded_docs_count = 0
            
            shipment_items.append(item)
        
        # Get available PO items for this company that haven't been added to this shipment
        existing_po_detail_ids = [item.po_detail_id for item in shipment_items if item.po_detail_id]
        
        po_items_query = db.session.query(
            PODetail,
            POHeader.currency.label('currency'),
            POMaterial,
            HSCode
        ).join(
            POHeader, PODetail.po_header_id == POHeader.id
        ).outerjoin(
            POMaterial, PODetail.material_id == POMaterial.id
        ).outerjoin(
            HSCode, POMaterial.hs_code_id == HSCode.id
        ).filter(
            PODetail.quantity_pending > 0
        )
        
        if existing_po_detail_ids:
            po_items_query = po_items_query.filter(
                ~PODetail.id.in_(existing_po_detail_ids)
            )
        
        available_po_items_data = po_items_query.order_by(
            PODetail.po_number.desc(),
            PODetail.material_code
        ).all()
        
        # Process PO items to include currency, HS code, and document counts
        available_po_items = []
        for po_data in available_po_items_data:
            po_item = po_data[0]  # PODetail object
            currency = po_data[1] or 'LKR'  # Default to LKR
            po_material = po_data[2]  # POMaterial object
            hs_code = po_data[3]  # HSCode object
            
            # Add currency and HS code to the PO item object
            po_item.currency = currency
            po_item.hs_code = hs_code
            po_item.po_material = po_material
            
            # Get document counts for PO items too
            if hs_code and po_material:
                required_docs_count = HSCodeDocument.query.filter_by(
                    hscode_id=hs_code.id
                ).count()
                
                uploaded_docs_count = MaterialHSDocuments.query.filter_by(
                    material_id=po_material.id,
                    hs_code_id=hs_code.id,
                    company_id=current_user.company_id
                ).count()
                
                po_item.required_docs_count = required_docs_count
                po_item.uploaded_docs_count = uploaded_docs_count
            else:
                po_item.required_docs_count = 0
                po_item.uploaded_docs_count = 0
            
            available_po_items.append(po_item)
        
        # Get unique suppliers for filter
        available_suppliers = db.session.query(PODetail.supplier_name).filter(
            PODetail.quantity_pending > 0
        ).distinct().order_by(PODetail.supplier_name).all()
        available_suppliers = [s[0] for s in available_suppliers if s[0]]
        
        print(f"Loaded {len(shipment_items)} shipment items and {len(available_po_items)} available PO items with HS code and document data")
        
        return shipment_items, available_po_items, available_suppliers
        
    except Exception as e:
        print(f"Error loading shipment items data: {str(e)}")
        import traceback
        traceback.print_exc()
        return [], [], []


# ===============================
# CHA VIEW CUSTOMER PULLS
# ===============================

@bp.route("/cha/customer-pulls/<int:shipment_id>", methods=["GET"])
@login_required
def view_customer_pulls(shipment_id):
    """CHA views customer pulls for specific shipment"""
    try:
        shipment = ShipDocumentEntryMaster.query.get_or_404(shipment_id)
        
        # Get all pulled items
        pulled_items = ShipmentItem.query.filter_by(
            shipment_id=shipment_id,
            pulled_by_customer=True
        ).order_by(ShipmentItem.customer_pull_date.desc()).all()
        
        return render_template('cha/customer_pulls.html', 
                             shipment=shipment, 
                             pulled_items=pulled_items)
        
    except Exception as e:
        flash(f"Error loading customer pulls", "danger")
        return redirect(url_for('masters.dashboard'))


@bp.route("/cha/customer-pulls/all", methods=["GET"])
@login_required
def view_all_customer_pulls():
    """CHA views all customer pulls across shipments"""
    try:
        # Get all pulled items for this company
        pulled_items = db.session.query(
            ShipmentItem,
            ShipDocumentEntryMaster.bl_no,
            ShipDocumentEntryMaster.mbl_number
        ).join(
            ShipDocumentEntryMaster, 
            ShipmentItem.shipment_id == ShipDocumentEntryMaster.id
        ).filter(
            ShipmentItem.pulled_by_customer == True,
            ShipmentItem.company_id == current_user.company_id
        ).order_by(
            ShipmentItem.customer_pull_date.desc()
        ).all()
        
        return render_template('cha/all_customer_pulls.html', 
                             pulled_items=pulled_items)
        
    except Exception as e:
        flash(f"Error loading customer pulls", "danger")
        return redirect(url_for('masters.dashboard'))


@bp.route("/api/cha/customer-pulls", methods=["GET"])
@login_required
def get_customer_pulls_api():
    """API for CHA to get customer pulls data"""
    try:
        shipment_id = request.args.get('shipment_id')
        
        query = db.session.query(
            ShipmentItem,
            ShipDocumentEntryMaster.bl_no,
            ShipDocumentEntryMaster.mbl_number,
            ShipDocumentEntryMaster.customer_id
        ).join(
            ShipDocumentEntryMaster, 
            ShipmentItem.shipment_id == ShipDocumentEntryMaster.id
        ).filter(
            ShipmentItem.pulled_by_customer == True,
            ShipmentItem.company_id == current_user.company_id
        )
        
        if shipment_id:
            query = query.filter(ShipmentItem.shipment_id == shipment_id)
        
        results = query.order_by(
            ShipmentItem.customer_pull_date.desc()
        ).all()
        
        pulls_data = []
        for result in results:
            item = result[0]
            bl_no = result[1]
            mbl_number = result[2]
            customer_id = result[3]
            
            pulls_data.append({
                'id': item.id,
                'material_code': item.material_code,
                'material_name': item.material_name,
                'quantity': float(item.quantity) if item.quantity else 0,
                'customer_pull_date': item.customer_pull_date.isoformat() if item.customer_pull_date else None,
                'customer_notes': item.customer_notes,
                'bl_no': bl_no,
                'mbl_number': mbl_number,
                'shipment_id': item.shipment_id
            })
        
        return jsonify({
            'success': True,
            'pulls': pulls_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ===============================
# DEMURRAGE ROUTES
# ===============================

@bp.route("/api/demurrage/shipment/<int:shipment_id>", methods=["GET"])
@login_required
def get_shipment_demurrage(shipment_id):
    """Get all demurrage records for a shipment"""
    try:
        print(f"[GET] Fetching demurrage for shipment ID: {shipment_id}")
        shipment = ShipDocumentEntryMaster.query.get_or_404(shipment_id)
        
        # Updated query to include bearer information
        demurrage_records = db.session.query(
            ShipmentDemurrage,
            DemurrageReasons.reason_name,
            CurrencyMaster.CurrencyCode,
            ShipmentDemurrageBearer.name.label('bearer_name')
        ).join(
            DemurrageReasons, ShipmentDemurrage.reason_id == DemurrageReasons.id
        ).join(
            CurrencyMaster, ShipmentDemurrage.currency_id == CurrencyMaster.currencyID
        ).outerjoin(  # Use outerjoin in case bearer_id is NULL
            ShipmentDemurrageBearer, ShipmentDemurrage.bearer_id == ShipmentDemurrageBearer.id
        ).filter(
            ShipmentDemurrage.shipment_id == shipment_id
        ).all()
        
        print(f"Found {len(demurrage_records)} demurrage records")

        import_containers = ImportContainer.query.filter_by(shipment_id=shipment_id).all()
        export_containers = ExportContainer.query.filter_by(shipment_id=shipment_id).all()
        print(f"Import containers: {len(import_containers)}, Export containers: {len(export_containers)}")

        container_map = {}
        for container in import_containers:
            container_map[f"import_{container.id}"] = container.container_number
        for container in export_containers:
            container_map[f"export_{container.id}"] = container.container_number

        result = []
        total_amount = 0

        for demurrage, reason_name, currency_code, bearer_name in demurrage_records:
            container_key = f"{demurrage.container_type}_{demurrage.container_id}"
            container_number = container_map.get(container_key, "Unknown")
            
            result.append({
                "id": demurrage.id,
                "container_number": container_number,
                "container_id": demurrage.container_id,
                "container_type": demurrage.container_type,
                "demurrage_date": demurrage.demurrage_date.strftime("%Y-%m-%d"),
                "amount": demurrage.amount,
                "currency_code": currency_code,
                "currency_id": demurrage.currency_id,
                "reason_name": reason_name,
                "reason_id": demurrage.reason_id,
                "bearing_percentage": demurrage.bearing_percentage,  # NEW FIELD
                "bearer_id": demurrage.bearer_id,  # NEW FIELD
                "bearer_name": bearer_name,  # NEW FIELD
                "created_at": demurrage.created_at.strftime("%Y-%m-%d %H:%M")
            })
            total_amount += demurrage.amount
        
        return jsonify({
            "success": True,
            "data": result,
            "total_amount": total_amount
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/demurrage", methods=["POST"])
@login_required
def create_demurrage():
    """Create new demurrage record with detailed calculation tracking"""
    try:
        data = request.get_json()
        print(f"[POST] Creating demurrage with data: {data}")

        # Validate required fields
        required_fields = ['shipment_id', 'container_id', 'container_type', 'demurrage_date', 'amount', 'currency_id', 'reason_id']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"success": False, "message": f"{field} is required"}), 400

        # Get shipment and demurrage_from date
        shipment_id = data['shipment_id']
        order_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=shipment_id).first()
        
        if not order_shipment or not order_shipment.demurrage_from:
            return jsonify({"success": False, "message": "Demurrage from date not set for this shipment"}), 400

        demurrage_from = order_shipment.demurrage_from
        demurrage_date = datetime.strptime(data['demurrage_date'], '%Y-%m-%d').date()

        # Calculate detailed breakdown
        calculation_result = calculate_detailed_demurrage(
            shipment_id=shipment_id,
            container_id=data['container_id'],
            container_type=data['container_type'],
            reason_id=data['reason_id'],
            demurrage_from=demurrage_from,
            demurrage_date=demurrage_date
        )

        if not calculation_result['success']:
            return jsonify({"success": False, "message": calculation_result['message']}), 400

        # Create demurrage record
        demurrage = ShipmentDemurrage(
            shipment_id=shipment_id,
            container_id=data['container_id'],
            container_type=data['container_type'],
            demurrage_date=demurrage_date,
            demurrage_from=demurrage_from,  # NEW
            amount=calculation_result['total_amount'],
            currency_id=data['currency_id'],
            reason_id=data['reason_id'],
            rate_card_id=calculation_result.get('rate_card_id'),  # NEW
            total_days=calculation_result['total_days'],  # NEW
            chargeable_days=calculation_result['chargeable_days'],  # NEW
            excluded_days=calculation_result['excluded_days'],  # NEW
            bearing_percentage=float(data.get('bearing_percentage')) if data.get('bearing_percentage') else None,
            bearer_id=int(data.get('bearer_id')) if data.get('bearer_id') else None,
            company_id=current_user.company_id,
            created_by=current_user.id
        )

        db.session.add(demurrage)
        db.session.flush()  # Get the demurrage ID

        # Save calculation details
        for detail in calculation_result['tier_breakdown']:
            calc_detail = DemurrageCalculationDetail(
                demurrage_id=demurrage.id,
                tier_number=detail['tier_number'],
                tier_name=detail['tier_name'],
                from_day=detail['from_day'],
                to_day=detail['to_day'],
                days_in_tier=detail['days_in_tier'],
                rate_per_day=detail['rate_per_day'],
                tier_amount=detail['tier_amount'],
                day_range_display=detail['day_range_display'],
                start_date=detail['start_date'],
                end_date=detail['end_date']
            )
            db.session.add(calc_detail)

        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": "Demurrage record created successfully", 
            "id": demurrage.id,
            "calculation_details": calculation_result
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


def calculate_detailed_demurrage(shipment_id, container_id, container_type, reason_id, demurrage_from, demurrage_date):
    """Calculate detailed demurrage breakdown with date ranges"""
    
    try:
        # Get container details
        container_size_id = None
        container_type_id = None
        
        if container_type == 'import':
            container = ImportContainer.query.get(container_id)
            if container:
                container_size_id = container.container_size_id
                container_type_id = container.container_type_id
        elif container_type == 'export':
            container = ExportContainer.query.get(container_id)
            if container:
                container_size_id = getattr(container, 'container_size_id', None)
                container_type_id = getattr(container, 'container_type_id', None)

        if not container_size_id or not container_type_id:
            return {"success": False, "message": "Container size/type information not found"}

        # Find rate card
        rate_card = DemurrageRateCard.query.filter_by(
            container_size_id=container_size_id,
            container_type_id=container_type_id,
            demurrage_reason_id=reason_id,
            company_id=current_user.company_id,
            is_active=True
        ).first()

        if not rate_card:
            rate_card = DemurrageRateCard.query.filter_by(
                container_size_id=container_size_id,
                container_type_id=container_type_id,
                demurrage_reason_id=reason_id,
                company_id=None,
                is_active=True
            ).first()

        if not rate_card:
            return {"success": False, "message": "No rate card found"}

        # Calculate days
        if demurrage_date <= demurrage_from:
            return {"success": False, "message": "Demurrage date must be after demurrage from date"}
        
        total_days = (demurrage_date - demurrage_from).days
        excluded_days = 0  # Add weekend/holiday logic here if needed
        chargeable_days = max(0, total_days - excluded_days)

        # Calculate tier breakdown with detailed date information
        tier_breakdown = []
        total_amount = 0.0
        remaining_days = chargeable_days
        current_day = 1
        current_date = demurrage_from

        for tier in rate_card.tiers:
            if remaining_days <= 0:
                break
                
            # Calculate days for this tier
            tier_start_day = tier.from_day
            tier_end_day = tier.to_day
            
            # Skip if current day is past this tier's start
            if current_day > tier_start_day:
                if tier_end_day and current_day > tier_end_day:
                    continue
                tier_start_day = current_day

            # Calculate days in this tier
            if tier_end_day:
                days_in_tier = min(remaining_days, tier_end_day - tier_start_day + 1)
                if current_day > tier_start_day:
                    days_in_tier = min(remaining_days, tier_end_day - current_day + 1)
            else:
                days_in_tier = remaining_days

            if days_in_tier > 0:
                tier_amount = days_in_tier * tier.rate_amount
                
                # Calculate actual date range for this tier
                tier_start_date = current_date
                tier_end_date = current_date + timedelta(days=days_in_tier - 1) if days_in_tier > 0 else current_date
                
                tier_breakdown.append({
                    "tier_number": tier.tier_number,
                    "tier_name": f"Tier {tier.tier_number}",
                    "from_day": tier_start_day,
                    "to_day": tier_end_day,
                    "days_in_tier": days_in_tier,
                    "rate_per_day": tier.rate_amount,
                    "tier_amount": tier_amount,
                    "day_range_display": tier.day_range_display,
                    "start_date": tier_start_date,
                    "end_date": tier_end_date if tier_end_day else None
                })
                
                total_amount += tier_amount
                remaining_days -= days_in_tier
                current_day += days_in_tier
                current_date += timedelta(days=days_in_tier)

        return {
            "success": True,
            "rate_card_id": rate_card.id,
            "rate_card_name": rate_card.rate_card_name,
            "total_days": total_days,
            "chargeable_days": chargeable_days,
            "excluded_days": excluded_days,
            "total_amount": round(total_amount, 2),
            "tier_breakdown": tier_breakdown,
            "currency_code": rate_card.currency.CurrencyCode,
            "currency_id": rate_card.currency_id
        }

    except Exception as e:
        return {"success": False, "message": str(e)}


# NEW: API endpoint to get demurrage calculation details
@bp.route("/api/demurrage/<int:demurrage_id>/details", methods=["GET"])
@login_required
def get_demurrage_details(demurrage_id):
    """Get detailed demurrage calculation breakdown"""
    try:
        demurrage = ShipmentDemurrage.query.get_or_404(demurrage_id)
        
        # Get container information
        container_info = get_container_info(demurrage)
        
        # Get shipment information
        shipment = demurrage.shipment
        order_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=shipment.id).first()
        
        # Prepare basic response structure
        result = {
            "demurrage_id": demurrage.id,
            "shipment_info": {
                "import_id": order_shipment.import_id if order_shipment else shipment.docserial,
                "customer": shipment.customer.customer_name if shipment.customer else "N/A",
                "bl_no": order_shipment.bl_no if order_shipment else "N/A"
            },
            "container_info": container_info,
            "calculation_info": {
                "demurrage_from": demurrage.demurrage_from.strftime('%Y-%m-%d') if demurrage.demurrage_from else "N/A",
                "demurrage_date": demurrage.demurrage_date.strftime('%Y-%m-%d'),
                "total_days": getattr(demurrage, 'total_days', 0),
                "chargeable_days": getattr(demurrage, 'chargeable_days', 0),
                "excluded_days": getattr(demurrage, 'excluded_days', 0),
                "reason": demurrage.reason.reason_name,
                "rate_card": demurrage.rate_card.rate_card_name if demurrage.rate_card else "Manual Entry",
                "currency": demurrage.currency.CurrencyCode,
                "total_amount": demurrage.amount
            },
            "tier_breakdown": [],
            "bearer_info": {
                "bearer_name": demurrage.bearer.name if demurrage.bearer else None,
                "bearing_percentage": demurrage.bearing_percentage
            }
        }
        
        # Check if calculation details exist
        if hasattr(demurrage, 'calculation_details'):
            try:
                # Get calculation details
                calculation_details = demurrage.calculation_details.all()
                
                for detail in calculation_details:
                    result["tier_breakdown"].append({
                        "tier_number": detail.tier_number,
                        "tier_name": detail.tier_name,
                        "day_range_display": detail.day_range_display,
                        "start_date": detail.start_date.strftime('%Y-%m-%d'),
                        "end_date": detail.end_date.strftime('%Y-%m-%d') if detail.end_date else None,
                        "days_in_tier": detail.days_in_tier,
                        "rate_per_day": detail.rate_per_day,
                        "tier_amount": detail.tier_amount
                    })
            except Exception as detail_error:
                print(f"Error loading calculation details: {detail_error}")
                # If no calculation details exist, create a basic breakdown
                result["tier_breakdown"] = create_basic_tier_breakdown(demurrage)
        else:
            # If relationship doesn't exist, create a basic breakdown
            result["tier_breakdown"] = create_basic_tier_breakdown(demurrage)
        
        return jsonify({"success": True, "data": result})
        
    except Exception as e:
        print(f"Error getting demurrage details: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


def get_container_info(demurrage):
    """Get container information safely"""
    container_info = {
        "container_number": "N/A",
        "size": "N/A",
        "type": "N/A"
    }
    
    try:
        if demurrage.container_type == 'import':
            container = ImportContainer.query.get(demurrage.container_id)
            if container:
                container_info = {
                    "container_number": container.container_number,
                    "size": container.container_size.name if container.container_size else "N/A",
                    "type": container.container_type.name if container.container_type else "N/A"
                }
        elif demurrage.container_type == 'export':
            container = ExportContainer.query.get(demurrage.container_id)
            if container:
                container_info = {
                    "container_number": container.container_number,
                    "size": getattr(container.container_size, 'name', 'N/A') if hasattr(container, 'container_size') else "N/A",
                    "type": getattr(container.container_type, 'name', 'N/A') if hasattr(container, 'container_type') else "N/A"
                }
    except Exception as e:
        print(f"Error getting container info: {e}")
    
    return container_info


def create_basic_tier_breakdown(demurrage):
    """Create a basic tier breakdown for legacy records without calculation details"""
    try:
        # If we have demurrage_from, calculate basic breakdown
        if demurrage.demurrage_from:
            total_days = (demurrage.demurrage_date - demurrage.demurrage_from).days
            return [{
                "tier_number": 1,
                "tier_name": "Total Period",
                "day_range_display": f"Days 1-{total_days}",
                "start_date": demurrage.demurrage_from.strftime('%Y-%m-%d'),
                "end_date": demurrage.demurrage_date.strftime('%Y-%m-%d'),
                "days_in_tier": total_days,
                "rate_per_day": round(demurrage.amount / total_days, 2) if total_days > 0 else 0,
                "tier_amount": demurrage.amount
            }]
        else:
            # No demurrage_from date, create a single entry
            return [{
                "tier_number": 1,
                "tier_name": "Manual Entry",
                "day_range_display": "Manual Calculation",
                "start_date": demurrage.demurrage_date.strftime('%Y-%m-%d'),
                "end_date": demurrage.demurrage_date.strftime('%Y-%m-%d'),
                "days_in_tier": 1,
                "rate_per_day": demurrage.amount,
                "tier_amount": demurrage.amount
            }]
    except Exception as e:
        print(f"Error creating basic tier breakdown: {e}")
        return [{
            "tier_number": 1,
            "tier_name": "Manual Entry",
            "day_range_display": "Manual Calculation",
            "start_date": demurrage.demurrage_date.strftime('%Y-%m-%d'),
            "end_date": demurrage.demurrage_date.strftime('%Y-%m-%d'),
            "days_in_tier": 1,
            "rate_per_day": demurrage.amount,
            "tier_amount": demurrage.amount
        }]
    
# Script to populate missing data for existing records
def update_existing_demurrage_records():
    """Update existing demurrage records with missing fields"""
    try:
        demurrage_records = ShipmentDemurrage.query.all()
        
        for demurrage in demurrage_records:
            updated = False
            
            # Set demurrage_from if missing
            if not demurrage.demurrage_from:
                order_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=demurrage.shipment_id).first()
                if order_shipment and order_shipment.demurrage_from:
                    demurrage.demurrage_from = order_shipment.demurrage_from
                    updated = True
                else:
                    # Set to one day before demurrage_date as fallback
                    demurrage.demurrage_from = demurrage.demurrage_date - timedelta(days=1)
                    updated = True
            
            # Calculate and set missing fields
            if demurrage.demurrage_from and not demurrage.total_days:
                demurrage.total_days = (demurrage.demurrage_date - demurrage.demurrage_from).days
                demurrage.chargeable_days = demurrage.total_days  # Simplified for existing records
                demurrage.excluded_days = 0
                updated = True
            
            # Create basic calculation detail if missing
            if not demurrage.calculation_details.count():
                calc_detail = DemurrageCalculationDetail(
                    demurrage_id=demurrage.id,
                    tier_number=1,
                    tier_name="Legacy Entry",
                    from_day=1,
                    to_day=demurrage.total_days if demurrage.total_days else 1,
                    days_in_tier=demurrage.total_days if demurrage.total_days else 1,
                    rate_per_day=demurrage.amount / (demurrage.total_days if demurrage.total_days > 0 else 1),
                    tier_amount=demurrage.amount,
                    day_range_display=f"Days 1-{demurrage.total_days}" if demurrage.total_days else "Day 1",
                    start_date=demurrage.demurrage_from,
                    end_date=demurrage.demurrage_date
                )
                db.session.add(calc_detail)
                updated = True
            
            if updated:
                print(f"Updated demurrage record {demurrage.id}")
        
        db.session.commit()
        print("Successfully updated existing demurrage records")
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating existing records: {e}")

# Run this function once to update existing records
# update_existing_demurrage_records()    

@bp.route("/api/demurrage/<int:demurrage_id>", methods=["PUT"])
@login_required
def update_demurrage(demurrage_id):
    """Update demurrage record"""
    try:
        print(f"[PUT] Updating demurrage ID: {demurrage_id}")
        demurrage = ShipmentDemurrage.query.get_or_404(demurrage_id)

        data = request.get_json()
        print(f"Update data: {data}")

        if 'container_id' in data:
            demurrage.container_id = data['container_id']
        if 'container_type' in data:
            demurrage.container_type = data['container_type']
        if 'demurrage_date' in data:
            demurrage.demurrage_date = datetime.strptime(data['demurrage_date'], '%Y-%m-%d').date()
        if 'amount' in data:
            demurrage.amount = float(data['amount'])
        if 'currency_id' in data:
            demurrage.currency_id = data['currency_id']
        if 'reason_id' in data:
            demurrage.reason_id = data['reason_id']
        
        # NEW FIELDS UPDATE
        if 'bearing_percentage' in data:
            bearing_percentage = data['bearing_percentage']
            if bearing_percentage is not None:
                bearing_percentage = float(bearing_percentage)
                if bearing_percentage < 0 or bearing_percentage > 100:
                    return jsonify({"success": False, "message": "Bearing percentage must be between 0 and 100"}), 400
            demurrage.bearing_percentage = bearing_percentage
            
        if 'bearer_id' in data:
            demurrage.bearer_id = data['bearer_id']

        db.session.commit()
        print("Demurrage updated successfully")
        
        return jsonify({"success": True, "message": "Demurrage record updated successfully"})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    
@bp.route("/api/demurrage/<int:demurrage_id>", methods=["DELETE"])
@login_required
def delete_demurrage(demurrage_id):
    """Delete demurrage record"""
    try:
        print(f"[DELETE] Deleting demurrage ID: {demurrage_id}")
        demurrage = ShipmentDemurrage.query.get_or_404(demurrage_id)

        db.session.delete(demurrage)
        db.session.commit()
        print("Demurrage deleted successfully")
        
        return jsonify({"success": True, "message": "Demurrage record deleted successfully"})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/demurrage/reasons", methods=["GET"])
@login_required
def get_demurrage_reasons():
    """Get all active demurrage reasons"""
    try:
        print("[GET] Fetching demurrage reasons")
        if current_user.is_super_admin:
            reasons = DemurrageReasons.query.filter_by(is_active=True).all()
        else:
            reasons = DemurrageReasons.query.filter_by(is_active=True).all()
        print(f"Found {len(reasons)} reasons")
        
        result = [{
            "id": reason.id,
            "reason_name": reason.reason_name,
            "description": reason.description
        } for reason in reasons]
        
        return jsonify({"success": True, "data": result})
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

# NEW ROUTE: Get all demurrage bearers
@bp.route("/api/demurrage/bearers", methods=["GET"])
@login_required
def get_demurrage_bearers():
    """Get all active demurrage bearers"""
    try:
        bearers = ShipmentDemurrageBearer.query.filter_by(is_active=True).all()
        
        result = []
        for bearer in bearers:
            result.append({
                "id": bearer.id,
                "name": bearer.name
            })
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/demurrage/containers/<int:shipment_id>", methods=["GET"])
@login_required
def get_shipment_containers_for_demurrage(shipment_id):
    """Get all containers for a shipment"""
    try:

        containers = []
        import_containers = ImportContainer.query.filter_by(shipment_id=shipment_id).all()
        export_containers = ExportContainer.query.filter_by(shipment_id=shipment_id).all()
        print(f"Import containers: {len(import_containers)}, Export containers: {len(export_containers)}")

        # UPDATED: Handle new foreign key structure for import containers
        for container in import_containers:
            try:
                # Get size and type names from relationships with error handling
                size_name = "Unknown"
                type_name = "Unknown"
                
                if container.container_size_id and container.container_size:
                    size_name = container.container_size.name
                elif container.container_size_id:
                    # Fallback: query the size directly if relationship isn't loaded
                    size_obj = OsContainerSize.query.get(container.container_size_id)
                    size_name = size_obj.name if size_obj else "Unknown"
                
                if container.container_type_id and container.container_type:
                    type_name = container.container_type.name
                elif container.container_type_id:
                    # Fallback: query the type directly if relationship isn't loaded
                    type_obj = OsContainerType.query.get(container.container_type_id)
                    type_name = type_obj.name if type_obj else "Unknown"
                
                containers.append({
                    "id": container.id,
                    "container_number": container.container_number,
                    "container_type": "import",
                    "size_type": f"{size_name} {type_name}",
                    # Include individual components for flexibility
                    "container_size_id": container.container_size_id,
                    "container_type_id": container.container_type_id,
                    "container_size_name": size_name,
                    "container_type_name": type_name
                })
                
            except Exception as container_error:
                print(f"Error processing container {container.id}: {container_error}")
                # Add container with basic info even if size/type lookup fails
                containers.append({
                    "id": container.id,
                    "container_number": container.container_number,
                    "container_type": "import",
                    "size_type": "Unknown Size/Type",
                    "container_size_id": container.container_size_id,
                    "container_type_id": container.container_type_id,
                    "container_size_name": "Unknown",
                    "container_type_name": "Unknown"
                })

        # UPDATED: Handle export containers (assuming they still use old structure)
        # If export containers also use foreign keys, update this section similarly
        for container in export_containers:
            # Check if export containers have been updated to foreign keys
            if hasattr(container, 'container_size_id') and hasattr(container, 'container_type_id'):
                # New foreign key structure
                size_name = container.container_size.name if container.container_size else "Unknown"
                type_name = container.container_type.name if container.container_type else "Unknown"
                size_type = f"{size_name} {type_name}"
            else:
                # Old string structure (fallback)
                size_type = f"{container.container_size}' {container.container_type}" if hasattr(container, 'container_size') else "Unknown"
            
            containers.append({
                "id": container.id,
                "container_number": container.container_number,
                "container_type": "export",
                "size_type": size_type
            })

        print(f"Returning {len(containers)} containers for demurrage")
        return jsonify({"success": True, "data": containers})
        
    except Exception as e:
        print(f"Error in get_shipment_containers_for_demurrage: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/api/demurrage/calculate-rate", methods=["POST"])
@login_required
def calculate_demurrage_rate():
    """Calculate demurrage rate based on rate card and days"""
    try:
        data = request.get_json()
        print(f"[POST] Calculate demurrage rate with data: {data}")

        # Validate required fields
        required_fields = ['shipment_id', 'container_id', 'container_type', 'reason_id', 'demurrage_date']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"success": False, "message": f"{field} is required"}), 400

        shipment_id = data['shipment_id']
        container_id = data['container_id']
        container_type = data['container_type']
        reason_id = data['reason_id']
        demurrage_date_str = data['demurrage_date']

        # Parse demurrage date
        try:
            demurrage_date = datetime.strptime(demurrage_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"success": False, "message": "Invalid demurrage date format"}), 400

        # Get shipment details
        shipment_entry = ShipDocumentEntryMaster.query.get_or_404(shipment_id)
        order_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=shipment_id).first()
        
        if not order_shipment:
            return jsonify({"success": False, "message": "Order shipment not found"}), 404

        if not order_shipment.demurrage_from:
            return jsonify({"success": False, "message": "Demurrage from date not set for this shipment"}), 400

        # Get container details to extract size and type
        container_size_id = None
        container_type_id = None
        
        if container_type == 'import':
            container = ImportContainer.query.get(container_id)
            if container:
                container_size_id = container.container_size_id
                container_type_id = container.container_type_id
        elif container_type == 'export':
            container = ExportContainer.query.get(container_id)
            if container:
                # Assuming export containers also have size_id and type_id
                container_size_id = getattr(container, 'container_size_id', None)
                container_type_id = getattr(container, 'container_type_id', None)

        if not container_size_id or not container_type_id:
            return jsonify({"success": False, "message": "Container size/type information not found"}), 400

        # Find matching rate card
        rate_card = DemurrageRateCard.query.filter_by(
            container_size_id=container_size_id,
            container_type_id=container_type_id,
            demurrage_reason_id=reason_id,
            company_id=current_user.company_id,
            is_active=True
        ).first()

        # If company-specific rate card not found, try general rate card
        if not rate_card:
            rate_card = DemurrageRateCard.query.filter_by(
                container_size_id=container_size_id,
                container_type_id=container_type_id,
                demurrage_reason_id=reason_id,
                company_id=None,  # General rate card
                is_active=True
            ).first()

        if not rate_card:
            return jsonify({
                "success": False, 
                "message": "No rate card found for the selected container and reason combination"
            }), 404

        # Get company demurrage configuration
        company_config = CompanyDemurrageConfig.query.filter_by(
            country_id=shipment_entry.country_id if hasattr(shipment_entry, 'country_id') else 1,
            is_active=True
        ).first()

        # Calculate chargeable days
        calculation_result = calculate_chargeable_days(
            order_shipment.demurrage_from,
            demurrage_date,
            company_config
        )

        # Calculate tiered amounts
        tier_breakdown, total_amount = calculate_tiered_amount(
            calculation_result['chargeable_days'],
            rate_card
        )

        # Prepare response
        result = {
            "calculated_amount": total_amount,
            "currency_code": rate_card.currency.CurrencyCode,
            "currency_id": rate_card.currency_id,
            "calculation_details": {
                "demurrage_from": order_shipment.demurrage_from.strftime('%Y-%m-%d'),
                "demurrage_date": demurrage_date.strftime('%Y-%m-%d'),
                "total_days": calculation_result['total_days'],
                "chargeable_days": calculation_result['chargeable_days'],
                "excluded_days": calculation_result['excluded_days'],
                "rate_card_id": rate_card.id,
                "rate_card_name": rate_card.rate_card_name,
                "tier_breakdown": tier_breakdown
            }
        }

        return jsonify({"success": True, "data": result})

    except Exception as e:
        print(f"Error calculating demurrage rate: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


def calculate_chargeable_days(demurrage_from, demurrage_date, company_config):
    """Calculate chargeable days excluding weekends/holidays based on config"""
    
    if demurrage_date <= demurrage_from:
        return {
            'total_days': 0,
            'chargeable_days': 0,
            'excluded_days': 0
        }
    
    total_days = (demurrage_date - demurrage_from).days
    excluded_days = 0
    
    # Count excluded days if configuration exists
    if company_config:
        current_date = demurrage_from
        while current_date < demurrage_date:
            current_date += timedelta(days=1)
            
            # Exclude weekends if configured
            if company_config.exclude_weekends and current_date.weekday() >= 5:  # Saturday=5, Sunday=6
                excluded_days += 1
            
            # TODO: Add holiday exclusion logic here if needed
            # if company_config.exclude_holidays and is_holiday(current_date):
            #     excluded_days += 1
    
    chargeable_days = max(0, total_days - excluded_days)
    
    return {
        'total_days': total_days,
        'chargeable_days': chargeable_days,
        'excluded_days': excluded_days
    }


def calculate_tiered_amount(chargeable_days, rate_card):
    """Calculate amount based on flexible tiered rate structure"""
    
    if chargeable_days <= 0:
        return [], 0.0
    
    # Get tiers ordered by tier_number
    tiers = DemurrageRateCardTier.query.filter_by(
        rate_card_id=rate_card.id
    ).order_by(DemurrageRateCardTier.tier_number).all()
    
    if not tiers:
        return [], 0.0
    
    tier_breakdown = []
    total_amount = 0.0
    remaining_days = chargeable_days
    current_day = 1
    
    for tier in tiers:
        if remaining_days <= 0:
            break
            
        # Calculate days for this tier
        tier_start = tier.from_day
        tier_end = tier.to_day
        
        # Skip if current day is past this tier's start
        if current_day > tier_start:
            if tier_end and current_day > tier_end:
                continue  # Skip this tier entirely
            tier_start = current_day
        
        if tier_end:
            # Finite tier
            days_in_tier = min(remaining_days, tier_end - tier_start + 1)
            if current_day > tier_start:
                days_in_tier = min(remaining_days, tier_end - current_day + 1)
        else:
            # Unlimited tier (last tier)
            days_in_tier = remaining_days
        
        if days_in_tier > 0:
            tier_amount = days_in_tier * tier.rate_amount
            
            tier_breakdown.append({
                "tier": tier.tier_number,
                "days": days_in_tier,
                "rate": tier.rate_amount,
                "amount": tier_amount,
                "day_range": tier.day_range_display
            })
            
            total_amount += tier_amount
            remaining_days -= days_in_tier
            current_day += days_in_tier
    
    return tier_breakdown, round(total_amount, 2)

@bp.route("/api/demurrage/shipment/<int:shipment_id>/demurrage-from", methods=["GET"])
@login_required
def get_shipment_demurrage_from(shipment_id):
    """Get demurrage from date for a shipment"""
    try:
        order_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=shipment_id).first()
        
        if not order_shipment:
            return jsonify({"success": False, "message": "Order shipment not found"}), 404
        
        result = {
            "demurrage_from": order_shipment.demurrage_from.strftime('%Y-%m-%d') if order_shipment.demurrage_from else None
        }
        
        return jsonify({"success": True, "data": result})
        
    except Exception as e:
        print(f"Error getting demurrage from date: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


from fpdf import FPDF
from flask import make_response

@bp.route("/api/demurrage/<int:demurrage_id>/download-pdf", methods=["POST"])
@login_required
def download_demurrage_pdf(demurrage_id):
    try:
        # Get demurrage details
        response = get_demurrage_details(demurrage_id)
        data = response.get_json()
        
        if not data['success']:
            flash('Error generating PDF: ' + data['message'], 'error')
            return redirect(request.referrer)
        
        demurrage_data = data['data']
        
        # Generate actual PDF using FPDF
        pdf_content = create_demurrage_pdf(demurrage_data)
        
        # Return PDF as download
        response = make_response(pdf_content)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=demurrage_calculation_{demurrage_id}.pdf'
        
        return response
        
    except Exception as e:
        print(f"Error generating PDF: {e}")
        flash('Error generating PDF', 'error')
        return redirect(request.referrer)


def create_demurrage_pdf(demurrage_data):
    """Generate PDF using FPDF"""
    
    class DemurragePDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 16)
            self.cell(0, 15, 'DEMURRAGE CALCULATION STATEMENT', 0, 1, 'C')
            self.set_font('Arial', '', 10)
            self.cell(0, 8, 'Detailed Breakdown of Charges', 0, 1, 'C')
            self.ln(10)
        
        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.cell(0, 10, f'Generated on {current_date} | Demurrage ID: {demurrage_data["demurrage_id"]}', 0, 0, 'C')
    
    pdf = DemurragePDF()
    pdf.add_page()
    
    # Shipment Information Section
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Shipment Information', 0, 1)
    pdf.set_font('Arial', '', 11)
    
    # Create two-column layout for shipment info
    col_width = pdf.w / 2 - 15
    x_start = pdf.get_x()
    y_start = pdf.get_y()
    
    # Left column - Shipment details
    pdf.cell(col_width, 8, f"Import ID: {demurrage_data['shipment_info']['import_id']}", 0, 1)
    pdf.cell(col_width, 8, f"Customer: {demurrage_data['shipment_info']['customer']}", 0, 1)
    pdf.cell(col_width, 8, f"BL Number: {demurrage_data['shipment_info']['bl_no']}", 0, 1)
    
    # Right column - Container details
    pdf.set_xy(x_start + col_width + 10, y_start)
    pdf.cell(col_width, 8, f"Container #: {demurrage_data['container_info']['container_number']}", 0, 1)
    pdf.set_x(x_start + col_width + 10)
    pdf.cell(col_width, 8, f"Size: {demurrage_data['container_info']['size']}", 0, 1)
    pdf.set_x(x_start + col_width + 10)
    pdf.cell(col_width, 8, f"Type: {demurrage_data['container_info']['type']}", 0, 1)
    
    pdf.ln(15)
    
    # Calculation Summary
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Calculation Summary', 0, 1)
    pdf.set_font('Arial', '', 11)
    
    # Summary boxes
    pdf.set_fill_color(240, 240, 240)
    box_width = (pdf.w - 40) / 3
    x_pos = 10
    
    # Total Days box
    pdf.set_xy(x_pos, pdf.get_y())
    pdf.cell(box_width, 25, '', 1, 0, 'C', True)
    pdf.set_xy(x_pos, pdf.get_y())
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(box_width, 10, str(demurrage_data['calculation_info']['total_days']), 0, 1, 'C')
    pdf.set_xy(x_pos, pdf.get_y())
    pdf.set_font('Arial', '', 10)
    pdf.cell(box_width, 8, 'Total Days', 0, 1, 'C')
    pdf.set_xy(x_pos, pdf.get_y())
    pdf.cell(box_width, 7, f"{demurrage_data['calculation_info']['demurrage_from']} to", 0, 1, 'C')
    pdf.set_xy(x_pos, pdf.get_y())
    pdf.cell(box_width, 0, f"{demurrage_data['calculation_info']['demurrage_date']}", 0, 0, 'C')
    
    # Chargeable Days box
    x_pos += box_width
    pdf.set_xy(x_pos, pdf.get_y() - 25)
    pdf.cell(box_width, 25, '', 1, 0, 'C', True)
    pdf.set_xy(x_pos, pdf.get_y())
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(box_width, 10, str(demurrage_data['calculation_info']['chargeable_days']), 0, 1, 'C')
    pdf.set_xy(x_pos, pdf.get_y())
    pdf.set_font('Arial', '', 10)
    pdf.cell(box_width, 8, 'Chargeable Days', 0, 1, 'C')
    pdf.set_xy(x_pos, pdf.get_y())
    pdf.cell(box_width, 7, f"Excluding {demurrage_data['calculation_info']['excluded_days']} days", 0, 0, 'C')
    
    # Total Amount box
    x_pos += box_width
    pdf.set_xy(x_pos, pdf.get_y() - 25)
    pdf.cell(box_width, 25, '', 1, 0, 'C', True)
    pdf.set_xy(x_pos, pdf.get_y())
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(box_width, 10, f"{demurrage_data['calculation_info']['currency']} {demurrage_data['calculation_info']['total_amount']:,.2f}", 0, 1, 'C')
    pdf.set_xy(x_pos, pdf.get_y())
    pdf.set_font('Arial', '', 10)
    pdf.cell(box_width, 8, 'Total Amount', 0, 1, 'C')
    pdf.set_xy(x_pos, pdf.get_y())
    pdf.cell(box_width, 7, f"{demurrage_data['calculation_info']['rate_card']}", 0, 0, 'C')
    
    pdf.ln(20)
    
    # Additional Info
    pdf.set_font('Arial', '', 11)
    pdf.cell(0, 8, f"Reason: {demurrage_data['calculation_info']['reason']}", 0, 1)
    if demurrage_data['bearer_info']['bearer_name']:
        pdf.cell(0, 8, f"Bearer: {demurrage_data['bearer_info']['bearer_name']} ({demurrage_data['bearer_info']['bearing_percentage']}%)", 0, 1)
    
    pdf.ln(10)
    
    # Tier Breakdown Table
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, 'Detailed Tier Breakdown', 0, 1)
    
    # Table headers
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(25, 10, 'Tier', 1, 0, 'C', True)
    pdf.cell(35, 10, 'Day Range', 1, 0, 'C', True)
    pdf.cell(50, 10, 'Date Range', 1, 0, 'C', True)
    pdf.cell(20, 10, 'Days', 1, 0, 'C', True)
    pdf.cell(35, 10, 'Rate/Day', 1, 0, 'C', True)
    pdf.cell(35, 10, 'Amount', 1, 1, 'C', True)
    
    # Table data
    pdf.set_font('Arial', '', 9)
    pdf.set_fill_color(248, 249, 250)
    
    for i, tier in enumerate(demurrage_data['tier_breakdown']):
        fill = i % 2 == 0  # Alternate row colors
        
        pdf.cell(25, 8, tier['tier_name'], 1, 0, 'C', fill)
        pdf.cell(35, 8, tier['day_range_display'], 1, 0, 'C', fill)
        
        # Date range with better formatting
        date_range = f"{tier['start_date']}"
        if tier.get('end_date'):
            date_range += f" to {tier['end_date']}"
        else:
            date_range += "+"
        pdf.cell(50, 8, date_range, 1, 0, 'L', fill)
        
        pdf.cell(20, 8, str(tier['days_in_tier']), 1, 0, 'C', fill)
        pdf.cell(35, 8, f"{demurrage_data['calculation_info']['currency']} {tier['rate_per_day']:,.2f}", 1, 0, 'R', fill)
        pdf.cell(35, 8, f"{demurrage_data['calculation_info']['currency']} {tier['tier_amount']:,.2f}", 1, 1, 'R', fill)
    
    # Total row
    pdf.set_font('Arial', 'B', 11)
    pdf.set_fill_color(52, 58, 64)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(165, 12, 'TOTAL DEMURRAGE AMOUNT:', 1, 0, 'R', True)
    pdf.cell(35, 12, f"{demurrage_data['calculation_info']['currency']} {demurrage_data['calculation_info']['total_amount']:,.2f}", 1, 1, 'R', True)
    
    # Reset text color
    pdf.set_text_color(0, 0, 0)
    
    return pdf.output(dest='S')




def generate_pdf_html_content(demurrage_data):
    """Generate HTML content for PDF"""
    
    current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Demurrage Calculation - {demurrage_data['demurrage_id']}</title>
        <style>
            body {{ 
                font-family: Arial, sans-serif; 
                margin: 20px; 
                color: #333;
            }}
            .header {{ 
                text-align: center; 
                border-bottom: 2px solid #0d6efd; 
                padding-bottom: 20px; 
                margin-bottom: 30px;
            }}
            .header h1 {{ 
                color: #0d6efd; 
                margin-bottom: 5px;
            }}
            .info-section {{ 
                margin-bottom: 30px;
            }}
            .info-grid {{ 
                display: grid; 
                grid-template-columns: 1fr 1fr; 
                gap: 20px; 
                margin-bottom: 20px;
            }}
            .info-card {{ 
                border: 1px solid #ddd; 
                padding: 15px; 
                background-color: #f8f9fa;
            }}
            .info-card h3 {{ 
                color: #0d6efd; 
                margin-top: 0; 
                margin-bottom: 15px;
            }}
            .summary-grid {{ 
                display: grid; 
                grid-template-columns: 1fr 1fr 1fr; 
                gap: 15px; 
                margin-bottom: 20px;
            }}
            .summary-card {{ 
                text-align: center; 
                padding: 20px; 
                border: 1px solid #ddd; 
                background-color: #f8f9fa;
            }}
            .summary-card h2 {{ 
                margin: 0 0 5px 0; 
                color: #0d6efd;
            }}
            table {{ 
                width: 100%; 
                border-collapse: collapse; 
                margin-bottom: 20px;
            }}
            th, td {{ 
                border: 1px solid #ddd; 
                padding: 12px; 
                text-align: left;
            }}
            th {{ 
                background-color: #f8f9fa; 
                font-weight: bold;
            }}
            .text-center {{ text-align: center; }}
            .text-end {{ text-align: right; }}
            .badge {{ 
                display: inline-block; 
                padding: 4px 8px; 
                background-color: #0d6efd; 
                color: white; 
                border-radius: 4px; 
                font-size: 12px;
            }}
            .total-row {{ 
                background-color: #343a40; 
                color: white; 
                font-weight: bold;
            }}
            .footer {{ 
                text-align: center; 
                margin-top: 40px; 
                padding-top: 20px; 
                border-top: 1px solid #ddd; 
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>DEMURRAGE CALCULATION STATEMENT</h1>
            <p>Detailed Breakdown of Charges</p>
        </div>
        
        <div class="info-section">
            <div class="info-grid">
                <div class="info-card">
                    <h3>Shipment Information</h3>
                    <p><strong>Import ID:</strong> {demurrage_data['shipment_info']['import_id']}</p>
                    <p><strong>Customer:</strong> {demurrage_data['shipment_info']['customer']}</p>
                    <p><strong>BL Number:</strong> {demurrage_data['shipment_info']['bl_no']}</p>
                </div>
                <div class="info-card">
                    <h3>Container Information</h3>
                    <p><strong>Container #:</strong> {demurrage_data['container_info']['container_number']}</p>
                    <p><strong>Size:</strong> {demurrage_data['container_info']['size']}</p>
                    <p><strong>Type:</strong> {demurrage_data['container_info']['type']}</p>
                </div>
            </div>
        </div>
        
        <div class="info-section">
            <div class="summary-grid">
                <div class="summary-card">
                    <h2>{demurrage_data['calculation_info']['total_days']}</h2>
                    <p>Total Days</p>
                    <small>{demurrage_data['calculation_info']['demurrage_from']} to {demurrage_data['calculation_info']['demurrage_date']}</small>
                </div>
                <div class="summary-card">
                    <h2>{demurrage_data['calculation_info']['chargeable_days']}</h2>
                    <p>Chargeable Days</p>
                    <small>Excluding {demurrage_data['calculation_info']['excluded_days']} days</small>
                </div>
                <div class="summary-card">
                    <h2>{demurrage_data['calculation_info']['currency']} {demurrage_data['calculation_info']['total_amount']:,.2f}</h2>
                    <p>Total Amount</p>
                    <small>{demurrage_data['calculation_info']['rate_card']}</small>
                </div>
            </div>
            
            <div class="info-grid">
                <div>
                    <p><strong>Reason:</strong> {demurrage_data['calculation_info']['reason']}</p>
                    <p><strong>Currency:</strong> {demurrage_data['calculation_info']['currency']}</p>
                </div>
                <div>
                    {f"<p><strong>Bearer:</strong> {demurrage_data['bearer_info']['bearer_name']}</p>" if demurrage_data['bearer_info']['bearer_name'] else ""}
                    {f"<p><strong>Bearing:</strong> {demurrage_data['bearer_info']['bearing_percentage']}%</p>" if demurrage_data['bearer_info']['bearing_percentage'] else ""}
                </div>
            </div>
        </div>
        
        <div class="info-section">
            <h3>Detailed Tier Breakdown</h3>
            <table>
                <thead>
                    <tr>
                        <th class="text-center">Tier</th>
                        <th>Day Range</th>
                        <th>Date Range</th>
                        <th class="text-center">Days</th>
                        <th class="text-end">Rate/Day</th>
                        <th class="text-end">Amount</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    # Add tier breakdown rows
    for tier in demurrage_data['tier_breakdown']:
        html_content += f"""
                    <tr>
                        <td class="text-center">
                            <span class="badge">{tier['tier_name']}</span>
                        </td>
                        <td><strong>{tier['day_range_display']}</strong></td>
                        <td>{tier['start_date']}{' to ' + tier['end_date'] if tier['end_date'] else '+'}</td>
                        <td class="text-center">{tier['days_in_tier']}</td>
                        <td class="text-end">{demurrage_data['calculation_info']['currency']} {tier['rate_per_day']:,.2f}</td>
                        <td class="text-end"><strong>{demurrage_data['calculation_info']['currency']} {tier['tier_amount']:,.2f}</strong></td>
                    </tr>
        """
    
    html_content += f"""
                </tbody>
                <tfoot>
                    <tr class="total-row">
                        <td colspan="5" class="text-end"><strong>TOTAL DEMURRAGE AMOUNT:</strong></td>
                        <td class="text-end"><strong>{demurrage_data['calculation_info']['currency']} {demurrage_data['calculation_info']['total_amount']:,.2f}</strong></td>
                    </tr>
                </tfoot>
            </table>
        </div>
        
        <div class="footer">
            <p>This statement was generated on {current_date}</p>
            <p>Demurrage ID: {demurrage_data['demurrage_id']}</p>
        </div>
    </body>
    </html>
    """
    
    return html_content


# ===============================
# DEMURRAGE REASONS MASTER ROUTES
# ===============================

@bp.route("/demurrage-reasons")
@login_required
def demurrage_reasons():
    """List all demurrage reasons"""
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    per_page = int(request.args.get('per_page', 10))
    page = int(request.args.get('page', 1))
    
    # Base query
    if current_user.is_super_admin == 1:
        query = DemurrageReasons.query
    else:
        query = DemurrageReasons.query.filter_by(company_id=current_user.company_id)
    
    # Apply filters
    if search:
        query = query.filter(
            db.or_(
                DemurrageReasons.reason_name.ilike(f'%{search}%'),
                DemurrageReasons.description.ilike(f'%{search}%')
            )
        )
    
    if status == 'active':
        query = query.filter(DemurrageReasons.is_active == True)
    elif status == 'inactive':
        query = query.filter(DemurrageReasons.is_active == False)
    
    # Order by created date descending
    query = query.order_by(DemurrageReasons.created_at.desc())
    
    # Paginate
    reasons = query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template(
        "masters/demurrage_reasons.html",
        title="Demurrage Reasons",
        reasons=reasons
    )


@bp.route("/demurrage-reason/new", methods=["GET", "POST"])
@login_required
def new_demurrage_reason():
    """Create a new demurrage reason"""
    if request.method == "POST":
        try:
            reason_name = request.form.get("reason_name", "").strip()
            description = request.form.get("description", "").strip()
            is_active = bool(request.form.get("is_active"))
            
            # Validate required fields
            if not reason_name:
                flash("Reason name is required!", "danger")
                return render_template("masters/demurrage_reason_form.html", title="New Demurrage Reason")
            
            # Check for duplicate reason name within company
            company_id = current_user.company_id
            existing = DemurrageReasons.query.filter_by(
                reason_name=reason_name,
                company_id=company_id
            ).first()
            
            if existing:
                flash("Reason name already exists!", "danger")
                return render_template("masters/demurrage_reason_form.html", title="New Demurrage Reason")
            
            # Create new reason
            reason = DemurrageReasons(
                reason_name=reason_name,
                description=description if description else None,
                is_active=is_active,
                company_id=company_id
            )
            
            db.session.add(reason)
            db.session.commit()
            
            flash("Demurrage reason created successfully!", "success")
            return redirect(url_for("masters.demurrage_reasons"))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating demurrage reason", "danger")
            return render_template("masters/demurrage_reason_form.html", title="New Demurrage Reason")
    
    return render_template("masters/demurrage_reason_form.html", title="New Demurrage Reason")


@bp.route("/demurrage-reason/<int:reason_id>/edit", methods=["GET", "POST"])
@login_required
def edit_demurrage_reason(reason_id):
    """Edit demurrage reason"""
    reason = DemurrageReasons.query.get_or_404(reason_id)
    
    # Check permissions
    if not current_user.is_super_admin and reason.company_id != current_user.company_id:
        flash("You don't have permission to edit this reason.", "danger")
        return redirect(url_for("masters.demurrage_reasons"))
    
    if request.method == "POST":
        try:
            reason_name = request.form.get("reason_name", "").strip()
            description = request.form.get("description", "").strip()
            is_active = bool(request.form.get("is_active"))
            
            # Validate required fields
            if not reason_name:
                flash("Reason name is required!", "danger")
                return render_template("masters/demurrage_reason_form.html", title="Edit Demurrage Reason", reason=reason)
            
            # Check for duplicate reason name within company (excluding current record)
            company_id = current_user.company_id
            existing = DemurrageReasons.query.filter(
                DemurrageReasons.reason_name == reason_name,
                DemurrageReasons.company_id == company_id,
                DemurrageReasons.id != reason_id
            ).first()
            
            if existing:
                flash("Reason name already exists!", "danger")
                return render_template("masters/demurrage_reason_form.html", title="Edit Demurrage Reason", reason=reason)
            
            # Update reason
            reason.reason_name = reason_name
            reason.description = description if description else None
            reason.is_active = is_active
            
            db.session.commit()
            
            flash("Demurrage reason updated successfully!", "success")
            return redirect(url_for("masters.demurrage_reasons"))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating demurrage reason", "danger")
            return render_template("masters/demurrage_reason_form.html", title="Edit Demurrage Reason", reason=reason)
    
    return render_template("masters/demurrage_reason_form.html", title="Edit Demurrage Reason", reason=reason)


@bp.route("/demurrage-reason/<int:reason_id>/delete", methods=["POST"])
@login_required
def delete_demurrage_reason(reason_id):
    """Delete demurrage reason"""
    reason = DemurrageReasons.query.get_or_404(reason_id)
    
    # Check permissions
    if not current_user.is_super_admin and reason.company_id != current_user.company_id:
        flash("You don't have permission to delete this reason.", "danger")
        return redirect(url_for("masters.demurrage_reasons"))
    
    # Check if reason is being used in any demurrage records
    demurrage_count = ShipmentDemurrage.query.filter_by(reason_id=reason_id).count()
    if demurrage_count > 0:
        flash(f"Cannot delete reason as it is being used in {demurrage_count} demurrage record(s).", "danger")
        return redirect(url_for("masters.demurrage_reasons"))
    
    try:
        db.session.delete(reason)
        db.session.commit()
        flash("Demurrage reason deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting demurrage reason", "danger")
    
    return redirect(url_for("masters.demurrage_reasons"))


# List attachments for a demurrage
@bp.route("/api/demurrage/<int:demurrage_id>/attachments", methods=["GET"])
@login_required
def list_demurrage_attachments(demurrage_id):
    attachments = ShipmentDemurrageAttachment.query.filter_by(shipment_demurrage_id=demurrage_id).all()
    data = [{
        "id": att.id,
        "file_name": att.file_name,
        "attachment_path": att.attachment_path,
        "date": att.date.strftime("%Y-%m-%d"),
        "comment": att.comment
    } for att in attachments]
    return jsonify({"success": True, "data": data})

# Upload new attachment
@bp.route("/demurrage/<int:demurrage_id>/upload-attachment", methods=["POST"])
@login_required
def upload_demurrage_attachment(demurrage_id):
    """Upload an attachment for a demurrage record"""
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "No file selected"}), 400

        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"

        # Get the demurrage record to ensure it exists
        demurrage = ShipmentDemurrage.query.get_or_404(demurrage_id)

        # Create S3 key following your pattern
        s3_key = f"demurrage_attachments/{demurrage.shipment.docserial}/{demurrage_id}/{unique_filename}"

        # Upload to S3 using your existing function
        try:
            upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
        except Exception as e:
            return (
                jsonify({"success": False, "error": f"Error uploading file: {str(e)}"}),
                500,
            )

        # Create demurrage attachment record
        attachment = ShipmentDemurrageAttachment(
            shipment_demurrage_id=demurrage_id,
            attachment_path=s3_key,
            date=request.form.get("date"),
            comment=request.form.get("comment"),
            file_name=filename,  # Store original filename
            uploaded_by=current_user.id,
            created_at=get_sri_lanka_time()
        )

        db.session.add(attachment)
        db.session.commit()

        return jsonify({
            "success": True, 
            "message": "Attachment uploaded successfully",
            "attachment_id": attachment.id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error uploading demurrage attachment: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Edit attachment (re-upload or update date/comment)
@bp.route("/demurrage/<int:demurrage_id>/update-attachment/<int:attachment_id>", methods=["POST"])
@login_required
def update_demurrage_attachment(demurrage_id, attachment_id):
    """Update a demurrage attachment"""
    try:
        
        # Get and verify the attachment belongs to the demurrage record
        attachment = ShipmentDemurrageAttachment.query.get_or_404(attachment_id)
        if attachment.shipment_demurrage_id != demurrage_id:
            return jsonify({"success": False, "error": "Attachment not found"}), 404
        
        # Get the demurrage record for S3 path construction
        demurrage = ShipmentDemurrage.query.get_or_404(demurrage_id)
        
        # Update date if provided
        date = request.form.get('date')
        if date:
            attachment.date = datetime.strptime(date, "%Y-%m-%d").date()
        
        # Update comment
        comment = request.form.get('comment', '')
        if comment is not None:
            attachment.comment = comment
        
        # Handle file update if new file is provided
        file = request.files.get('file')
        if file and file.filename != '':
            # Delete old file from S3 if it exists
            if attachment.attachment_path:
                try:
                    delete_file_from_s3(
                        current_app.config["S3_BUCKET_NAME"],
                        attachment.attachment_path
                    )
                except Exception as e:
                    current_app.logger.error(f"Error deleting old demurrage file: {str(e)}")
            
            # Generate new filename and S3 key
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            
            # Follow your S3 key pattern
            s3_key = f"demurrage_attachments/{demurrage.shipment.docserial}/{demurrage_id}/{unique_filename}"
            
            try:
                upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key)
                attachment.attachment_path = s3_key
                attachment.file_name = filename
            except Exception as s3_error:
                current_app.logger.error(f"S3 upload error for demurrage: {str(s3_error)}")
                return jsonify({"success": False, "error": "Failed to upload new file to S3"}), 500
        
        # Update timestamp
        attachment.updated_at = get_sri_lanka_time()
        db.session.commit()
        
        return jsonify({"success": True, "message": "Attachment updated successfully"})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating demurrage attachment: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Delete attachment
@bp.route("/demurrage/<int:demurrage_id>/delete-attachment/<int:attachment_id>", methods=["POST"])
@login_required
def delete_demurrage_attachment(demurrage_id, attachment_id):
    """Delete a demurrage attachment"""
    try:
        attachment = ShipmentDemurrageAttachment.query.get_or_404(attachment_id)
        
        # Verify attachment belongs to the demurrage record
        if attachment.shipment_demurrage_id != demurrage_id:
            return jsonify({"success": False, "error": "Attachment not found"}), 404

        # Delete from S3 using your existing function
        try:
            delete_file_from_s3(
                current_app.config["S3_BUCKET_NAME"], 
                attachment.attachment_path
            )
        except Exception as e:
            print(f"Error deleting demurrage file from S3: {str(e)}")

        # Delete from database
        db.session.delete(attachment)
        db.session.commit()

        return jsonify({"success": True, "message": "Attachment deleted successfully"})
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting demurrage attachment: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500
    


# View attachment (generate S3 presigned URL)
@bp.route("/view-demurrage-document/<int:attachment_id>")
@login_required
def view_demurrage_document(attachment_id):
    """SECURE: Serve demurrage attachment through app proxy instead of presigned URLs"""
    try:
        
        # Get the attachment record
        attachment = ShipmentDemurrageAttachment.query.get_or_404(attachment_id)
        
        print(f"Attempting to view demurrage document: {attachment.attachment_path}")

        # Optional: Add additional permission checks here if needed
        # For example, verify user has access to this demurrage record:
        # if not user_can_access_demurrage(current_user, attachment):
        #     return jsonify({
        #         "success": False,
        #         "message": "Access denied"
        #     }), 403

        # Normalize the S3 key path
        s3_key = attachment.attachment_path.replace("\\", "/")  # Normalize path separators
        
        print(f"Serving demurrage document securely: {s3_key}")
        
        # REMOVED: Presigned URL generation and redirect
        # url = get_s3_url(current_app.config["S3_BUCKET_NAME"], attachment.attachment_path, expires_in=3600)
        # return redirect(url)
        
        # ADDED: Direct secure serving through app proxy
        return serve_s3_file(s3_key)

    except ClientError as e:
        # Handle S3-specific errors
        print(f"S3 error accessing demurrage document: {str(e)}")
        if e.response['Error']['Code'] == 'NoSuchKey':
            return jsonify({
                "success": False,
                "message": "File not found",
                "details": f"Demurrage document does not exist: {attachment.attachment_path}"
            }), 404
        else:
            return jsonify({
                "success": False,
                "message": "Error accessing file from storage",
                "details": str(e)
            }), 500
            
    except Exception as e:
        print(f"Error serving demurrage document: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False, 
            "message": "Error accessing file", 
            "details": str(e)
        }), 500


# ===============================
# ALERT SYSTEM
# ===============================

# Add these routes to your main blueprint file (e.g., where your other shipment routes are defined)

@bp.route('/api/material-document-alerts/<int:material_id>/<int:shipment_id>')
@login_required
def get_material_document_alerts(material_id, shipment_id):
    """Get document expiry alerts for a specific material in a shipment (CHA side)"""
    try:
        print(f"Fetching shipment with ID: {shipment_id}")
        entry = ShipDocumentEntryMaster.query.filter_by(id=shipment_id).first()
        
        if not entry:
            print("Shipment not found.")
            return jsonify({'success': False, 'message': 'Shipment not found'}), 404
        
        print("Shipment found, checking for OrderShipment...")
        order_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=shipment_id).first()
        
        comparison_date = None
        date_source = None

        if order_shipment and order_shipment.eta:
            comparison_date = order_shipment.eta.date()
            date_source = 'eta'
            print(f"Using ETA as comparison date: {comparison_date}")
        elif entry.dealineDate:
            comparison_date = entry.dealineDate
            date_source = 'deadline'
            print(f"Using deadlineDate as comparison date: {comparison_date}")
        
        if not comparison_date:
            print("No comparison date found. Returning with no alerts.")
            return jsonify({
                'success': True,
                'has_alerts': False,
                'expiring_documents': []
            })

        print(f"Fetching documents for material ID: {material_id}")
        material_docs = db.session.query(
            MaterialHSDocuments,
            HSCodeDocument,
            HSCodeIssueBody,
            HSDocumentCategory
        ).join(
            HSCodeDocument, MaterialHSDocuments.document_id == HSCodeDocument.id
        ).join(
            HSCodeIssueBody, HSCodeDocument.issuing_body_id == HSCodeIssueBody.id
        ).join(
            HSDocumentCategory, HSCodeDocument.document_category_id == HSDocumentCategory.id
        ).filter(
            MaterialHSDocuments.material_id == material_id,
            MaterialHSDocuments.expiry_date.isnot(None)
        ).all()
        
        print(f"Found {len(material_docs)} documents with expiry dates.")

        expiring_documents = []
        has_alerts = False
        
        for material_doc, hs_doc, issuing_body, doc_category in material_docs:
            expiry_date = material_doc.expiry_date
            is_expiring = expiry_date < comparison_date
            days_difference = (comparison_date - expiry_date).days if is_expiring else (expiry_date - comparison_date).days

            print(f"Document ID {material_doc.id} - Expiry Date: {expiry_date}, Is Expiring: {is_expiring}, Days Difference: {days_difference}")

            if is_expiring:
                has_alerts = True

            expiring_documents.append({
                'document_id': material_doc.id,
                'file_name': material_doc.file_name,
                'expiry_date': expiry_date.isoformat(),
                'issuing_body': issuing_body.name,
                'document_category': doc_category.name,
                'is_expiring': is_expiring,
                'days_difference': days_difference
            })
        
        print(f"Returning {len(expiring_documents)} documents. Alerts Present: {has_alerts}")

        return jsonify({
            'success': True,
            'has_alerts': has_alerts,
            'expiring_documents': expiring_documents,
            'comparison_date': comparison_date.isoformat(),
            'date_source': date_source
        })

    except Exception as e:
        current_app.logger.error(f"Error getting material document alerts: {str(e)}")
        print(f"Exception occurred: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/api/all-orders-alert-status')
@login_required
def get_all_orders_alert_status():
    """Get alert status for all orders to highlight rows in orders page (CHA side)"""
    try:
        # Get all entries (orders) for CHA users - you may need to adjust the filter based on your system
        # This assumes CHA users can see all entries, but you might want to filter by assigned CHA
        entries = ShipDocumentEntryMaster.query.all()
        
        print(f"Found {len(entries)} entries for CHA alert check")
        
        alert_status = {}
        
        for entry in entries:
            print(f"\nProcessing Entry ID: {entry.id}, DocSerial: {entry.docserial}")
            
            # Get the related OrderShipment to check for ETA
            order_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=entry.id).first()
            if order_shipment:
                print(f"  Found OrderShipment with ETA: {order_shipment.eta}")
            else:
                print("  No OrderShipment found")

            # Determine the comparison date
            comparison_date = None
            if order_shipment and order_shipment.eta:
                comparison_date = order_shipment.eta.date()
            elif entry.dealineDate:
                comparison_date = entry.dealineDate
            
            print(f"  Comparison date set to: {comparison_date}")
            
            has_alerts = False
            
            if comparison_date:
                # Get all shipment items for this entry
                shipment_items = db.session.query(ShipmentItem).filter_by(
                    shipment_id=entry.id
                ).all()
                print(f"  Found {len(shipment_items)} shipment items")
                
                for item in shipment_items:
                    print(f"    Processing ShipmentItem ID: {item.id}")
                    if item.po_detail_id:
                        po_detail = PODetail.query.get(item.po_detail_id)
                        if po_detail and po_detail.material_id:
                            print(f"      Found PODetail with Material ID: {po_detail.material_id}")
                            
                            # Check if any documents expire before the comparison date
                            expiring_docs = MaterialHSDocuments.query.filter(
                                MaterialHSDocuments.material_id == po_detail.material_id,
                                MaterialHSDocuments.expiry_date.isnot(None),
                                MaterialHSDocuments.expiry_date < comparison_date
                            ).first()
                            
                            if expiring_docs:
                                print(f"      ALERT: Expiring document found with expiry date {expiring_docs.expiry_date}")
                                has_alerts = True
                                break
                            else:
                                print("      No expiring document found")
                    
                    if has_alerts:
                        break
            
            alert_status[entry.id] = {
                'has_alerts': has_alerts,
                'entry_id': entry.id,
                'docserial': entry.docserial
            }
            print(f"  Final alert status for entry: {has_alerts}")
        
        print("\n--- Final Alert Status Result ---")
        for eid, status in alert_status.items():
            print(f"Entry ID: {eid}, Has Alerts: {status['has_alerts']}")

        return jsonify({
            'success': True,
            'alert_status': alert_status
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting all orders alert status: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@bp.route('/api/test-alert-status/<int:entry_id>')
@login_required
def test_alert_status(entry_id):
    """Test endpoint to debug alert status for a specific entry"""
    try:
        print(f"=== TESTING ALERT STATUS FOR ENTRY {entry_id} ===")
        
        # Get the shipment entry
        entry = ShipDocumentEntryMaster.query.filter_by(id=entry_id).first()
        if not entry:
            return jsonify({'error': 'Entry not found'}), 404
        
        print(f"Entry: {entry.docserial}")
        
        # Get the related OrderShipment to check for ETA
        order_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=entry_id).first()
        
        # Determine the comparison date
        comparison_date = None
        date_source = None
        
        if order_shipment and order_shipment.eta:
            comparison_date = order_shipment.eta.date()
            date_source = 'eta'
        elif entry.dealineDate:
            comparison_date = entry.dealineDate
            date_source = 'deadline'
        
        print(f"Comparison date: {comparison_date} (source: {date_source})")
        
        if not comparison_date:
            return jsonify({
                'entry_id': entry_id,
                'docserial': entry.docserial,
                'comparison_date': None,
                'date_source': None,
                'has_alerts': False,
                'reason': 'No comparison date available'
            })
        
        # Get all shipment items for this entry
        shipment_items = ShipmentItem.query.filter_by(shipment_id=entry_id).all()
        print(f"Shipment items: {len(shipment_items)}")
        
        all_materials = []
        expiring_docs = []
        all_documents_details = []
        
        for item in shipment_items:
            print(f"  ShipmentItem ID: {item.id}, PO Detail ID: {item.po_detail_id}")
            
            if item.po_detail_id:
                po_detail = PODetail.query.get(item.po_detail_id)
                if po_detail and po_detail.material_id:
                    print(f"    Material ID: {po_detail.material_id}")
                    all_materials.append(po_detail.material_id)
                    
                    # Get all documents for this material
                    material_docs = MaterialHSDocuments.query.filter(
                        MaterialHSDocuments.material_id == po_detail.material_id
                    ).all()
                    
                    print(f"    Total documents: {len(material_docs)}")
                    
                    for doc in material_docs:
                        print(f"      Document ID {doc.id}: expiry_date={doc.expiry_date}, file={doc.file_name}")
                        
                        # Calculate days difference
                        days_diff = None
                        is_expiring = False
                        if doc.expiry_date:
                            days_diff = (comparison_date - doc.expiry_date).days
                            is_expiring = doc.expiry_date < comparison_date
                        
                        doc_detail = {
                            'document_id': doc.id,
                            'material_id': po_detail.material_id,
                            'file_name': doc.file_name,
                            'expiry_date': doc.expiry_date.isoformat() if doc.expiry_date else None,
                            'expiry_date_raw': str(doc.expiry_date),
                            'comparison_date': comparison_date.isoformat(),
                            'days_difference': days_diff,
                            'is_expiring': is_expiring,
                            'uploaded_at': doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                            'comment': doc.comment
                        }
                        
                        all_documents_details.append(doc_detail)
                        
                        if is_expiring:
                            expiring_docs.append(doc_detail)
                            print(f"      *** EXPIRING DOCUMENT ***")
                        else:
                            print(f"      Not expiring (days diff: {days_diff})")
                else:
                    print(f"    No material_id found for PO detail {item.po_detail_id}")
            else:
                print(f"    No po_detail_id for shipment item {item.id}")
        
        has_alerts = len(expiring_docs) > 0
        
        result = {
            'entry_id': entry_id,
            'docserial': entry.docserial,
            'comparison_date': comparison_date.isoformat(),
            'date_source': date_source,
            'shipment_items_count': len(shipment_items),
            'materials_checked': all_materials,
            'all_documents': all_documents_details,  # NEW: All documents with full details
            'expiring_documents': expiring_docs,
            'has_alerts': has_alerts,
            'alert_count': len(expiring_docs),
            'debug_info': {
                'comparison_date_type': str(type(comparison_date)),
                'today_date': datetime.now().date().isoformat(),
                'total_documents_found': len(all_documents_details)
            }
        }
        
        print(f"Result: {result}")
        return jsonify(result)
        
    except Exception as e:
        print(f"Error in test_alert_status: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500




@bp.route('/api/order-document-alerts/<int:entry_id>')
@login_required
def get_order_document_alerts(entry_id):
    """Get document expiry alerts for a specific order/entry (CHA side)"""
    try:
        print(f"--- get_order_document_alerts called with entry_id={entry_id} ---")
        
        # Get the shipment entry
        entry = ShipDocumentEntryMaster.query.filter_by(id=entry_id).first()
        print(f"Entry found: {entry is not None}")
        
        if not entry:
            print("No entry found, returning 404")
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        # Get the related OrderShipment to check for ETA
        order_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=entry_id).first()
        print(f"OrderShipment found: {order_shipment is not None}")
        
        # Determine the comparison date
        comparison_date = None
        date_source = None
        
        if order_shipment and order_shipment.eta:
            comparison_date = order_shipment.eta.date()
            date_source = 'eta'
        elif entry.dealineDate:
            comparison_date = entry.dealineDate
            date_source = 'deadline'
        
        print(f"Comparison date: {comparison_date}, Date source: {date_source}")
        
        if not comparison_date:
            print("No comparison date found, returning no alerts")
            return jsonify({
                'success': True,
                'has_alerts': False,
                'alert_count': 0,
                'expiring_documents': []
            })
        
        # Get all shipment items for this order
        shipment_items = ShipmentItem.query.filter_by(shipment_id=entry_id).all()
        print(f"Shipment items count: {len(shipment_items)}")
        
        all_expiring_docs = []
        material_alerts = {}
        
        for item in shipment_items:
            print(f"Processing shipment item ID: {item.id}, PO detail ID: {item.po_detail_id}")
            if item.po_detail_id:
                po_detail = PODetail.query.get(item.po_detail_id)
                print(f"PO detail found: {po_detail is not None}")
                if po_detail and po_detail.material_id:
                    print(f"Fetching documents for material_id={po_detail.material_id}")
                    
                    material_docs = db.session.query(
                        MaterialHSDocuments,
                        HSCodeDocument,
                        HSCodeIssueBody,
                        HSDocumentCategory
                    ).join(
                        HSCodeDocument, MaterialHSDocuments.document_id == HSCodeDocument.id
                    ).join(
                        HSCodeIssueBody, HSCodeDocument.issuing_body_id == HSCodeIssueBody.id
                    ).join(
                        HSDocumentCategory, HSCodeDocument.document_category_id == HSDocumentCategory.id
                    ).filter(
                        MaterialHSDocuments.material_id == po_detail.material_id,
                        MaterialHSDocuments.expiry_date.isnot(None),
                        MaterialHSDocuments.expiry_date < comparison_date
                    ).all()
                    
                    print(f"Found {len(material_docs)} expiring docs for material_id={po_detail.material_id}")
                    
                    if material_docs:
                        material_alerts[po_detail.material_id] = len(material_docs)
                        for material_doc, hs_doc, issuing_body, doc_category in material_docs:
                            all_expiring_docs.append({
                                'material_id': po_detail.material_id,
                                'material_code': po_detail.material_code,
                                'document_id': material_doc.id,
                                'file_name': material_doc.file_name,
                                'expiry_date': material_doc.expiry_date.isoformat(),
                                'issuing_body': issuing_body.name,
                                'document_category': doc_category.name,
                                'days_overdue': (comparison_date - material_doc.expiry_date).days
                            })
        
        has_alerts = len(all_expiring_docs) > 0
        print(f"Total expiring documents: {len(all_expiring_docs)}, Has alerts: {has_alerts}")
        
        return jsonify({
            'success': True,
            'has_alerts': has_alerts,
            'alert_count': len(all_expiring_docs),
            'expiring_documents': all_expiring_docs,
            'material_alerts': material_alerts,
            'comparison_date': comparison_date.isoformat(),
            'date_source': date_source
        })
    
    except Exception as e:
        print(f"Error in get_order_document_alerts: {str(e)}")
        current_app.logger.error(f"Error getting order document alerts: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500



# Add this test route to check notifications
@bp.route("/test-notifications")
@login_required
def test_notifications():
    """Test route to check notification functionality"""
    from app.utils_roles import get_all_notifications
    
    print(f"\n=== TEST NOTIFICATIONS ===")
    print(f"Testing for user: {current_user.id} ({current_user.username})")
    
    notifications = get_all_notifications(current_user.id)
    
    print(f"Test results:")
    print(f"  Total count: {notifications['total_count']}")
    print(f"  Chat notifications: {len(notifications['chat_notifications'])}")
    
    for i, notif in enumerate(notifications['chat_notifications']):
        print(f"  Notification {i+1}: {notif['sender_name']} -> {notif['message'][:50]}...")
    
    print("=== END TEST NOTIFICATIONS ===\n")
    
    return jsonify({
        'success': True,
        'notifications': notifications,
        'user_id': current_user.id,
        'username': current_user.username
    })

# Add this route to handle material document viewing from CHA side
# You may need to add this to the same blueprint or create a new one depending on your structure

@bp.route('/api/get-material-documents')
@login_required
def get_material_documents_cha():
    """Get material documents for viewing from CHA side"""
    try:
        material_id = request.args.get('material_id', type=int)
        
        if not material_id:
            return jsonify({'error': 'Material ID is required'}), 400
        
        # Get material information
        material = POMaterial.query.get(material_id)
        if not material:
            return jsonify({'error': 'Material not found'}), 404
        
        # Get HS code information
        hs_code = None
        if material.hs_code_id:
            hs_code = HSCode.query.get(material.hs_code_id)
        
        # Get required documents for this HS code
        required_documents = []
        if hs_code:
            required_docs_query = db.session.query(
                HSCodeDocument,
                HSCodeIssueBody,
                HSDocumentCategory
            ).join(
                HSCodeIssueBody, HSCodeDocument.issuing_body_id == HSCodeIssueBody.id
            ).join(
                HSDocumentCategory, HSCodeDocument.document_category_id == HSDocumentCategory.id
            ).filter(
                HSCodeDocument.hscode_id == hs_code.id
            ).all()
            
            for doc, issuing_body, category in required_docs_query:
                required_documents.append({
                    'id': doc.id,
                    'document_name': doc.document_name,
                    'is_mandatory': doc.is_mandatory,
                    'issuing_body': issuing_body.name,
                    'category_name': category.name
                })
        
        # Get uploaded documents for this material
        uploaded_documents = []
        if hs_code:
            uploaded_docs_query = db.session.query(
                MaterialHSDocuments,
                HSCodeDocument,
                HSCodeIssueBody,
                HSDocumentCategory
            ).join(
                HSCodeDocument, MaterialHSDocuments.document_id == HSCodeDocument.id
            ).join(
                HSCodeIssueBody, HSCodeDocument.issuing_body_id == HSCodeIssueBody.id
            ).join(
                HSDocumentCategory, HSCodeDocument.document_category_id == HSDocumentCategory.id
            ).filter(
                MaterialHSDocuments.material_id == material_id,
                MaterialHSDocuments.hs_code_id == hs_code.id
            ).all()
            
            for material_doc, hs_doc, issuing_body, category in uploaded_docs_query:
                # Check if document is expiring (you can adjust this logic based on your needs)
                is_expiring = False
                if material_doc.expiry_date:
                    from datetime import date, timedelta
                    warning_days = 30  # Consider documents expiring within 30 days as "expiring"
                    warning_date = date.today() + timedelta(days=warning_days)
                    is_expiring = material_doc.expiry_date <= warning_date
                
                uploaded_documents.append({
                    'id': material_doc.id,
                    'document_id': hs_doc.id,
                    'file_name': material_doc.file_name,
                    'expiry_date': material_doc.expiry_date.isoformat() if material_doc.expiry_date else None,
                    'issuing_body': issuing_body.name,
                    'category_name': category.name,
                    'is_expiring': is_expiring,
                    'uploaded_at': material_doc.created_at.isoformat() if material_doc.created_at else None
                })
        
        # Prepare response data
        response_data = {
            'material_id': material.id,
            'material_code': material.material_code,
            'material_name': material.material_name,
            'hs_code': {
                'id': hs_code.id,
                'code': hs_code.code,
                'description': hs_code.description
            } if hs_code else None,
            'required_documents': required_documents,
            'uploaded_documents': uploaded_documents
        }
        
        return jsonify(response_data)
    
    except Exception as e:
        current_app.logger.error(f"Error getting material documents for CHA: {str(e)}")
        return jsonify({'error': str(e)}), 500


# Alternative route if you want to mirror the customer portal structure
# @bp.route('/get-material-documents')
# @login_required  
# def get_material_documents_cha_alt():
#     """Alternative route that mirrors customer portal structure"""
#     return get_material_documents_cha()


