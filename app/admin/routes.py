from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
    send_file,
    current_app,
    session,
    Response
)
from flask_login import login_required, current_user
from app import db
from app.admin import bp
from app.models import User
from app.models.user import CountryMaster, CurrencyMaster, User, UserActionPermission, Role, Menu, RoleMenuPermission, Route, RoutePermission, ProductPackage
from app.models.company import CompanyInfo
from app.admin.forms import (
    CreateUserForm,
    EditUserForm
)
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_

from app.utils import admin_required, generate_merchant_code
import qrcode
import os
from datetime import datetime, timedelta, date
import json
import io
import base64
import random
import string
import csv
from io import BytesIO
from io import StringIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.colors import Color
from reportlab.lib.colors import toColor
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
from io import BytesIO
import hashlib
import secrets
from PIL import Image
import logging
import traceback
from sqlalchemy import func
from app.email import send_email, send_async_email, send_transaction_confirmation
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
from app.utils_cha.s3_utils import serve_s3_file

# Add this list of countries
COUNTRIES = [
    "United States",
    "United Kingdom",
    "Canada",
    "Australia",
    "India",
    "Germany",
    "France",
    "Italy",
    "Spain",
    "Japan",
    "China",
    # Add more countries as needed
]


@bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("admin/dashboard.html")


@bp.route("/secure_document/<path:s3_key>")
@login_required  # Add your authentication requirements
def serve_secure_document(s3_key):
    """
    Serve documents securely through the application proxy.
    This route replaces direct S3 presigned URLs.
    """
    try:
        # Optional: Add additional authorization checks here
        # For example, check if user has permission to access this specific document
        # document = ShipDocumentEntryAttachment.query.filter_by(attachement_path=s3_key).first()
        # if document and document.user_id != current_user.id:
        #     return Response("Unauthorized", status=403)
        
        # Serve the file through S3 proxy
        return serve_s3_file(s3_key)
        
    except Exception as e:
        print(f"Error serving secure document: {str(e)}")
        return Response("Error serving document", status=500)


# @bp.route("/customers")
# @login_required
# def customer_list():
#     # Get search parameters
#     search_name = request.args.get("search_name", "").strip()
#     search_email = request.args.get("search_email", "").strip()
#     search_mobile = request.args.get("search_mobile", "").strip()

#     # Build query
#     query = Customer.query.filter(Customer.is_deleted == False)

#     # Apply company-level filtering if user is not admin
#     if current_user.role_id != 1:
#         query = query.filter(Customer.company_id == current_user.company_id)

#     # Apply search filters
#     if search_name:
#         query = query.filter(Customer.name.ilike(f"%{search_name}%"))
#     if search_email:
#         query = query.filter(Customer.email.ilike(f"%{search_email}%"))
#     if search_mobile:
#         query = query.filter(Customer.mobile.ilike(f"%{search_mobile}%"))

#     customers = query.order_by(Customer.created_at.desc()).all()
    
#     # Check if each customer has coupons issued
#     # We'll create a dictionary to store this information
#     customer_has_coupons = {}
#     for customer in customers:
#         # Check if there are any coupons issued to this customer
#         has_coupons = db.session.query(Coupon).filter(Coupon.issued_to_id == customer.id).first() is not None
#         customer_has_coupons[customer.id] = has_coupons

#     return render_template(
#         "admin/customer_list_admin.html",
#         customers=customers,
#         customer_has_coupons=customer_has_coupons,
#         search_name=search_name,
#         search_email=search_email,
#         search_mobile=search_mobile,
#     )


# @bp.route("/customer/add", methods=["GET", "POST"])
# @login_required
# def add_customer():
#     print("Entering add_customer function")
#     form = CustomerForm()
#     try:
#         print(f"Request method: {request.method}")
#         if form.validate_on_submit():
#             print("Form validated successfully")
#             selected_type = form.type.data
#             gender_value = form.gender.data if selected_type == "individual" else "N/A"
            
#             print(f"Form data received:")
#             print(f"  - Name: {form.name.data}")
#             print(f"  - Type: {selected_type}")
#             print(f"  - Gender: {gender_value}")
#             print(f"  - Email: {form.email.data}")
#             print(f"  - Mobile: {form.mobile.data}")
#             print(f"  - WhatsApp: {form.whatsapp.data}")
#             print(f"  - Address: {form.address.data}")
#             print(f"  - City: {form.city.data}")
#             print(f"  - Country ID: {form.country_id.data}")
#             print(f"  - Company ID: {current_user.company_id}")
            
#             generated_id = Customer.generate_customer_id()
#             print(f"Generated customer ID: {generated_id}")

#             customer = Customer(
#                 customer_id=generated_id,
#                 name=form.name.data,
#                 type=selected_type,
#                 gender=gender_value,
#                 email=form.email.data,
#                 mobile=form.mobile.data,
#                 whatsapp=form.whatsapp.data,
#                 address=form.address.data,
#                 city=form.city.data,
#                 country_id=form.country_id.data,  # storing countryID now
#                 company_id=current_user.company_id
#             )
            
#             print("Customer object created, about to add to database")
#             db.session.add(customer)
            
#             print("Committing to database...")
#             db.session.commit()
#             print("Database commit successful")
            
#             print("Redirecting to customer list")
#             return redirect(url_for("admin_panel.customer_list"))

#         print("Form not validated or GET request")
#         print(f"Form errors (if any): {form.errors}")
#         return render_template("admin/customer_form_admin.html", form=form, title="Add Customer")

#     except Exception as e:
#         print(f"Exception occurred: {str(e)}")
#         print(f"Exception type: {type(e).__name__}")
#         print(f"Traceback: {traceback.format_exc()}")
#         db.session.rollback()
#         return redirect(url_for("admin_panel.customer_list"))
    
# @bp.route("/customer/<int:customer_id>/deactivate", methods=["POST"])
# @login_required
# def deactivate_customer(customer_id):
#     """Toggle the deactivation status of a customer"""
#     try:
#         customer = Customer.query.get_or_404(customer_id)
        
#         # Check if user has permission to modify this customer
#         if current_user.role_id != 1 and customer.company_id != current_user.company_id:
#             return jsonify({"success": False, "message": "You don't have permission to modify this customer."}), 403
        
#         # Toggle the deactivation status
#         customer.is_deactivated = not customer.is_deactivated
        
#         db.session.commit()
        
#         action = "deactivated" if customer.is_deactivated else "activated"
#         return jsonify({
#             "success": True, 
#             "message": f"Customer {action} successfully.", 
#             "is_deactivated": customer.is_deactivated
#         })
    
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500


# @bp.route("/customer/<int:customer_id>/delete", methods=["POST"])
# @login_required
# def delete_customer(customer_id):
#     """Mark a customer as deleted"""
#     try:
#         customer = Customer.query.get_or_404(customer_id)
        
#         # Check if user has permission to modify this customer
#         if current_user.role_id != 1 and customer.company_id != current_user.company_id:
#             return jsonify({"success": False, "message": "You don't have permission to delete this customer."}), 403
        
#         # Check if the customer has any coupons issued
#         has_coupons = db.session.query(Coupon).filter(Coupon.issued_to_id == customer.id).first() is not None
        
#         if has_coupons:
#             return jsonify({
#                 "success": False, 
#                 "message": "This customer has issued coupons and cannot be deleted. Please deactivate instead."
#             }), 400
        
#         # Mark as deleted
#         customer.is_deleted = True
#         db.session.commit()
        
#         return jsonify({
#             "success": True, 
#             "message": "Customer deleted successfully."
#         })
    
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500

# @bp.route("/customer/edit/<int:id>", methods=["GET", "POST"])
# @login_required
# def edit_customer(id):
#     print(f"Entering edit_customer function for ID: {id}")
#     customer = Customer.query.get_or_404(id)
#     print(f"Customer found: {customer.name} (ID: {customer.customer_id})")
    
#     form = CustomerForm(obj=customer)
#     print(f"Request method: {request.method}")
    
#     if form.validate_on_submit():
#         print("Form validated successfully")
#         selected_type = form.type.data
#         gender_value = form.gender.data if selected_type == "individual" else "N/A"
        
#         print(f"Form data received for update:")
#         print(f"  - Name: {form.name.data}")
#         print(f"  - Type: {selected_type}")
#         print(f"  - Gender: {gender_value}")
#         print(f"  - Email: {form.email.data}")
#         print(f"  - Mobile: {form.mobile.data}")
#         print(f"  - WhatsApp: {form.whatsapp.data}")
#         print(f"  - Address: {form.address.data}")
#         print(f"  - City: {form.city.data}")
#         print(f"  - Country ID: {form.country_id.data}")
        
#         print("Previous customer data:")
#         print(f"  - Name: {customer.name}")
#         print(f"  - Type: {customer.type}")
#         print(f"  - Gender: {customer.gender}")
#         print(f"  - Email: {customer.email}")
        
#         customer.name = form.name.data
#         customer.type = selected_type
#         customer.gender = gender_value
#         customer.email = form.email.data
#         customer.address = form.address.data
#         customer.city = form.city.data
#         customer.country_id = form.country_id.data  # store country ID correctly
#         customer.mobile = form.mobile.data
#         customer.whatsapp = form.whatsapp.data
        
#         print("Customer object updated, about to commit changes")
        
#         try:
#             db.session.commit()
#             print("Database commit successful")
#             flash("Customer updated successfully", "success")
#             print("Redirecting to customer list")
#             return redirect(url_for("admin_panel.customer_list"))
#         except Exception as e:
#             print(f"Exception during commit: {str(e)}")
#             print(f"Exception type: {type(e).__name__}")
#             print(f"Traceback: {traceback.format_exc()}")
#             db.session.rollback()
#             flash(f"Error updating customer: {str(e)}", "danger")
#             return redirect(url_for("admin_panel.customer_list"))
#     else:
#         print(f"Form not validated or GET request")
#         print(f"Form errors (if any): {form.errors}")

#     return render_template(
#         "admin/customer_form_admin.html", form=form, customer=customer, title="Edit Customer"
#     )


# @bp.route("/customer/<int:id>/details")
# @login_required
# def customer_details(id):
#     customer = Customer.query.get_or_404(id)

#     # Get coupon statistics
#     total_coupons = Coupon.query.filter_by(issued_to_id=id).count()
#     redeemed_coupons = Coupon.query.filter_by(issued_to_id=id, status="redeemed").count()
#     balance_coupons = total_coupons - redeemed_coupons

#     stats = {
#         "total_coupons": total_coupons,
#         "redeemed_coupons": redeemed_coupons,
#         "balance_coupons": balance_coupons
#     }

#     return render_template(
#         "admin/customer_details_admin.html", customer=customer, stats=stats
#     )






@bp.route("/user_configuration")
@login_required
def user_configuration():
    # Get search and filter parameters
    search_query = request.args.get('search', '').strip()
    company_id = request.args.get('company', type=int)
    role_id = request.args.get('role', type=int)
    
    # Start with base query
    query = User.query

    if current_user.role == 'user':
        query = query.filter(User.company_id == current_user.company_id)
    
    # Apply search if it exists
    if search_query:
        search_filter = (
            User.username.ilike(f'%{search_query}%') |
            User.email.ilike(f'%{search_query}%')
        )
        query = query.filter(search_filter)
    
    if current_user.role == 'user':
        if company_id:
            query = query.filter(User.company_id == company_id)
    if role_id:
        query = query.filter(User.role_id == role_id)
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 10
    total_users = query.count()
    user_pagination = query.paginate(page=page, per_page=per_page)
    total_pages = (total_users + per_page - 1) // per_page
    
    companies = CompanyInfo.query.all() if current_user.role == 'super_admin' else \
               CompanyInfo.query.filter_by(id=current_user.company_id).all()
    
    roles = Role.query.all()

    return render_template(
        'administration/user_configuration.html',
        users=user_pagination.items,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        user_pagination=user_pagination,
        companies=companies,
        roles=roles,
        selected_company=company_id,
        selected_role=role_id,
        search_query=search_query
    )

@bp.route("/add_user_page")
@login_required
def add_user_page():
    form = CreateUserForm()  # Use CreateUserForm for new users
    
    # For company admin, show only their company
    if current_user.role == 'user':
        form.company_id.choices = [(current_user.company_id, current_user.company.company_name)]
        # Show only non-admin roles for company admins
        form.role_id.choices = [(r.id, r.role_name) for r in Role.query.filter(
            Role.role_name.notin_([ 'super_admin', 'admin', 'customer'])
        ).all()]
    else:
        # For admin, show all companies and roles
        form.company_id.choices = [(c.id, c.company_name) for c in CompanyInfo.query.all()]
        form.role_id.choices = [(r.id, r.role_name) for r in Role.query.all()]
        
    return render_template(
        "administration/add_user.html",
        form=form
    )

@bp.route("/add_user", methods=['POST'])
@login_required
def add_user():

    form = CreateUserForm()  # Use CreateUserForm for validation
    
    # Set choices based on role
    if current_user.role == 'company_admin':
        form.company_id.choices = [(current_user.company_id, current_user.company.company_name)]
        form.role_id.choices = [(r.id, r.role_name) for r in Role.query.filter(
            Role.role_name.notin_(['admin', 'company_admin'])
        ).all()]
    else:
        form.company_id.choices = [(c.id, c.company_name) for c in CompanyInfo.query.all()]
        form.role_id.choices = [(r.id, r.role_name) for r in Role.query.all()]
    
    if form.validate_on_submit():
        try:
            # Check if username already exists
            if User.query.filter_by(username=form.username.data).first():
                flash('Username already exists!', 'error')
                return redirect(url_for('admin_panel.add_user_page'))
            
            # Check if email already exists
            if User.query.filter_by(email=form.email.data).first():
                flash('Email already exists!', 'error')
                return redirect(url_for('admin_panel.add_user_page'))
            
            profile_picture_data = None
            if form.profile_picture.data:
                profile_picture_data = form.profile_picture.data.read()

            password=form.password.data
            role_id = form.role_id.data  # Get role_id from form
            role = Role.query.filter_by(id=role_id).first()  # Fetch role instance

            if role:  
                role_name = role.role_name  # Access role_name
            else:
                role_name = None  # Handle case where role_id is invalid

            # Create new user
            user = User(
                username=form.username.data,
                name=form.name.data,
                gender=form.gender.data,
                address=form.address.data,
                contact_number=form.contact.data,
                email=form.email.data,
                role_id=form.role_id.data,
                role=role_name,
                company_id=form.company_id.data,
                is_active=True,
                is_super_admin=0,

            )
            user.is_active = form.status.data
            user.set_password(password)
            db.session.add(user)
            db.session.flush()  # Get the user ID before committing
            
            # Fetch all menus to assign permissions
            menus = Menu.query.all()

            # Process permissions for each menu
            for menu in menus:
                # Get permissions for the current menu from the form
                create = request.form.get(f"permissions[{menu.id}][create]") == "on"
                edit = request.form.get(f"permissions[{menu.id}][edit]") == "on"
                delete = request.form.get(f"permissions[{menu.id}][delete]") == "on"
                print_perm = request.form.get(f"permissions[{menu.id}][print]") == "on"

                # Create a new permission entry for this user and menu
                permission = UserActionPermission(
                    role_id=form.role_id.data,
                    menu_id=menu.id,
                    user_id=user.id,
                    access=True,  # Always True by default
                    create=create,
                    edit=edit,
                    delete=delete,
                    print=print_perm,
                )
                db.session.add(permission)

            db.session.commit()
            flash('User and permissions added successfully!', 'success')
            return redirect(url_for('admin_panel.user_configuration'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding user: {str(e)}', 'error')
            print("Error:", str(e))  # This will help us debug
            
    else:
        print("Form Errors:", form.errors)  # This will help us debug
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'error')
    
    return redirect(url_for('admin_panel.add_user_page'))

@bp.route("/edit_user/<int:user_id>")
@login_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)

    current_permissions = {
        (permission.menu_id, permission.user_id): permission
        for permission in UserActionPermission.query.filter_by(user_id=user.id).all()
    }
    
    # If company admin, ensure they can only edit users from their company
    if current_user.role == 'admin' and user.company_id != current_user.company_id:
        flash('You do not have permission to edit users from other companies', 'error')
        return redirect(url_for('admin_panel.user_configuration'))
        
    form = EditUserForm(obj=user)
    
    # For company admin, show only their company
    if current_user.role == 'admin':
        form.company_id.choices = [(current_user.company_id, current_user.company.company_name)]
        # Show only non-admin roles for company admins
        form.role_id.choices = [(r.id, r.role_name) for r in Role.query.filter(
            Role.role_name.notin_(['super_admin'])
        ).all()]
    else:
        # For admin, show all companies and roles
        form.company_id.choices = [(company.id, company.company_name) for company in CompanyInfo.query.all()]
        form.role_id.choices = [(role.id, role.role_name) for role in Role.query.all()]
        
    form.password.data = ''  # Clear password field
    form.confirm_password.data = ''  # Clear confirm password field
    
    return render_template("administration/edit_user.html", form=form, user=user, current_permissions=current_permissions)


@bp.route("/delete_user/<int:user_id>", methods=['POST'])
@login_required
def delete_user(user_id):
    try:
        # Get the user to delete
        user = User.query.get_or_404(user_id)
        
        # Check permissions - only super_admin or company_admin can delete users
        if current_user.role != 'super_admin':
            if current_user.role != 'user':
                flash('You do not have permission to delete this user', 'error')
                return redirect(url_for('admin_panel.user_configuration'))
        
        # Delete related permissions first
        UserActionPermission.query.filter_by(user_id=user_id).delete()
        
        # Store the username for the success message
        username = user.username
        
        # Delete the user
        db.session.delete(user)
        db.session.commit()
        
        flash(f'User {username} has been deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'error')
        
    return redirect(url_for('admin_panel.user_configuration'))

#new routes
@bp.route("/get_role_menus/<int:role_id>/<int:user_id>", methods=["GET"])
@login_required
def get_role_menus(role_id, user_id):
    try:
        # Fetch role menu permissions
        role_menu_permissions = RoleMenuPermission.query.filter(
            RoleMenuPermission.role_id == role_id,
            RoleMenuPermission.can_access == True
        ).all()

        if not role_menu_permissions:
            return jsonify({"success": False, "menus": []})

        # Get permitted menu IDs
        permitted_menu_ids = {permission.menu_id for permission in role_menu_permissions}

        # Create role permissions map
        role_permissions_map = {
            perm.menu_id: {
                "create": perm.can_create,
                "edit": perm.can_edit,
                "delete": perm.can_delete,
                "print": perm.can_print
            } for perm in role_menu_permissions
        }

        # Fetch existing user permissions
        user_permissions = UserActionPermission.query.filter_by(
            user_id=user_id
        ).all()

        # Create user permissions map
        user_permissions_map = {
            perm.menu_id: {
                "create": perm.create,
                "edit": perm.edit,
                "delete": perm.delete,
                "print": perm.print
            } for perm in user_permissions
        }

        # Fetch all active menus
        all_menus = Menu.query.filter(
            Menu.is_active == True,
            Menu.id.in_(permitted_menu_ids)
        ).all()

        # Create menu dictionary with permissions
        menus_by_id = {}
        for menu in all_menus:
            # Get role permissions for this menu
            role_perms = role_permissions_map.get(menu.id, {
                "create": False,
                "edit": False,
                "delete": False,
                "print": False
            })
            
            # Get user permissions and validate against role permissions
            user_perms = user_permissions_map.get(menu.id, {
                "create": False,
                "edit": False,
                "delete": False,
                "print": False
            })

            # Ensure user permissions don't exceed role permissions
            validated_permissions = {
                action: user_perms[action] and role_perms[action]
                for action in ["create", "edit", "delete", "print"]
            }

            menus_by_id[menu.id] = {
                "id": menu.id,
                "name": menu.name,
                "parent_id": menu.parent_id,
                "submenus": [],
                "permissions": validated_permissions,
                "role_permissions": role_perms
            }

        # Build menu hierarchy
        top_level_menus = []
        for menu in menus_by_id.values():
            if menu["parent_id"] is None:
                top_level_menus.append(menu)
            elif menu["parent_id"] in menus_by_id:
                menus_by_id[menu["parent_id"]]["submenus"].append(menu)

        return jsonify({"success": True, "menus": top_level_menus})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})
  
@bp.route("/update_permission", methods=["POST"])
@login_required
def update_permission():
    try:
        print("Entering update_permission route")
        
        # Parse incoming JSON data
        data = request.json
        print(f"Received data: {data}")
        
        user_id = data.get("userId")
        menu_id = data.get("menuId")
        role_id = data.get("roleId")
        permissions = data.get("permissions")  # Object for bulk update
        action = data.get("action")
        value = data.get("value")
        
        print(f"user_id: {user_id}, menu_id: {menu_id}, role_id: {role_id}")
        print(f"permissions: {permissions}, action: {action}, value: {value}")
        
        try:
            # Start a nested transaction
            db.session.begin_nested()
            
            if permissions:  # Bulk update case
                print("Bulk permissions update detected")
                
                # Force-retrieve or create permission record
                permission = UserActionPermission.query.filter_by(
                    user_id=user_id, 
                    menu_id=menu_id
                ).with_for_update().first()  # Add lock for concurrent updates
                
                if not permission:
                    print(f"Creating new permission record for user_id: {user_id}, menu_id: {menu_id}")
                    permission = UserActionPermission(
                        user_id=user_id,
                        role_id=role_id,
                        menu_id=menu_id,
                        access=True,
                        create=False,
                        edit=False,
                        delete=False,
                        print=False
                    )
                    db.session.add(permission)
                    # Flush to ensure the record is created
                    db.session.flush()
                
                # Update the specified permissions
                for action_name, action_value in permissions.items():
                    if hasattr(permission, action_name):
                        print(f"Updating '{action_name}' to: {action_value}")
                        setattr(permission, action_name, action_value)
                
                # Verify the updates before commit
                db.session.flush()
                
                # Verify the permission state
                updated_permission = UserActionPermission.query.filter_by(
                    user_id=user_id,
                    menu_id=menu_id
                ).first()
                
                print(f"Permission state after update for menu {menu_id}:")
                for action_name in ['create', 'edit', 'delete', 'print']:
                    print(f"- {action_name}: {getattr(updated_permission, action_name, None)}")

            else:  # Single action update case
                print("Single action update detected")
                
                # Force-retrieve or create permission record
                permission = UserActionPermission.query.filter_by(
                    user_id=user_id, 
                    menu_id=menu_id
                ).with_for_update().first()
                
                if not permission:
                    print(f"Creating new permission record for user_id: {user_id}, menu_id: {menu_id}")
                    permission = UserActionPermission(
                        user_id=user_id,
                        role_id=role_id,
                        menu_id=menu_id,
                        access=True,
                        create=False,
                        edit=False,
                        delete=False,
                        print=False
                    )
                    db.session.add(permission)
                    db.session.flush()

                # Update the specific action
                if action in ['create', 'edit', 'delete', 'print']:
                    print(f"Updating '{action}' to: {value}")
                    setattr(permission, action, value)
                    
                # Verify the update
                db.session.flush()
                
                # Verify the permission state
                updated_permission = UserActionPermission.query.filter_by(
                    user_id=user_id,
                    menu_id=menu_id
                ).first()
                print(f"Permission state after update for menu {menu_id}:")
                print(f"- {action}: {getattr(updated_permission, action, None)}")

            # Commit the transaction
            db.session.commit()
            print(f"Permissions updated successfully for menu {menu_id}")
            
            # Double-check the final state
            final_permission = UserActionPermission.query.filter_by(
                user_id=user_id,
                menu_id=menu_id
            ).first()
            
            print(f"Final permission state for menu {menu_id}:")
            for action_name in ['create', 'edit', 'delete', 'print']:
                print(f"- {action_name}: {getattr(final_permission, action_name, None)}")
            
            return jsonify({"success": True})

        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"Database error: {str(e)}")
            return jsonify({"success": False, "error": str(e)})

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        return jsonify({"success": False, "error": str(e)})


@bp.route("/get_menus_by_role/<int:role_id>", methods=["GET"])
@login_required
def get_menus_by_role(role_id):
    print(f"Fetching menus for role_id: {role_id}")

    # Fetch role menu permissions based on the role
    role_menu_permissions = RoleMenuPermission.query.filter(
        RoleMenuPermission.role_id == role_id, RoleMenuPermission.can_access == True
    ).all()

    if not role_menu_permissions:
        return jsonify({"success": False, "menus": [], "permissions": {}})

    # Create permissions dictionary
    permissions = {}
    for perm in role_menu_permissions:
        permissions[perm.menu_id] = {
            "create": perm.can_create,
            "edit": perm.can_edit,
            "delete": perm.can_delete,
            "print": perm.can_print
        }

    # Extract the permitted menu IDs
    permitted_menu_ids = {permission.menu_id for permission in role_menu_permissions}
    print(f"Permitted menu IDs: {permitted_menu_ids}")

    # Fetch all active menus and filter by permission
    all_menus = Menu.query.filter(Menu.is_active == True).all()
    menus_by_id = {
        menu.id: {
            "id": menu.id,
            "name": menu.name,
            "parent_id": menu.parent_id,
            "submenus": []
        }
        for menu in all_menus if menu.id in permitted_menu_ids
    }

    # Link submenus to their respective parents
    for menu in menus_by_id.values():
        if menu["parent_id"] is not None and menu["parent_id"] in menus_by_id:
            parent_menu = menus_by_id[menu["parent_id"]]
            parent_menu["submenus"].append(menu)

    # Collect only top-level menus (parent_id is None and permitted)
    top_level_menus = [
        menu for menu in menus_by_id.values()
        if menu["parent_id"] is None
    ]

    print(f"Returning filtered top-level menus: {top_level_menus}")
    return jsonify({"success": True, "menus": top_level_menus, "permissions": permissions})


@bp.route("/update_user/<int:user_id>", methods=['POST'])
@login_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    form = EditUserForm()
    
    # Set choices based on role
    if current_user.role == 'admin':
        if user.company_id != current_user.company_id:
            flash('You cannot edit users from other companies', 'error')
            return redirect(url_for('administration.user_configuration'))
            
        form.company_id.choices = [(current_user.company_id, current_user.company.company_name)]
        form.role_id.choices = [(r.id, r.role_name) for r in Role.query.filter(
            Role.role_name.notin_(['admin', 'super_admin'])
        ).all()]
    else:
        form.company_id.choices = [(company.id, company.company_name) for company in CompanyInfo.query.all()]
        form.role_id.choices = [(role.id, role.role_name) for role in Role.query.all()]
    
    if form.validate_on_submit():
        try:
            print("✅ Debug: Form validated successfully")
            # Additional validation for company admin
            if current_user.role == 'admin':
                if int(form.company_id.data) != current_user.company_id:
                    flash('You cannot assign users to other companies', 'error')
                    return redirect(url_for('admin_panel.edit_user', user_id=user_id))
                
                selected_role = Role.query.get(form.role_id.data)
                if selected_role.role_name in ['admin', 'super_admin']:
                    flash('You cannot assign administrative roles', 'error')
                    return redirect(url_for('admin_panel.edit_user', user_id=user_id))
            
            user.username = form.username.data
            user.name = form.name.data
            user.gender = form.gender.data
            user.address = form.address.data
            user.contact_number = form.contact.data
            user.email = form.email.data
            user.is_active = form.status.data
            if form.password.data:  # Only update password if provided
                user.set_password(form.password.data)
            user.role_id = form.role_id.data
            user.company_id = form.company_id.data

            role_id = form.role_id.data  # Get role_id from form
            role = Role.query.filter_by(id=role_id).first()  # Fetch role instance

            if role:  
                role_name = role.role_name  # Access role_name
            else:
                role_name = None  # Handle case where role_id is invalid
            user.role= role_name
                
            db.session.commit()
            flash('User updated successfully!', 'success')
            return redirect(url_for('admin_panel.user_configuration'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'error')
            print("Error:", str(e))  # This will help us debug
            
    else:
        print("Form Errors:", form.errors)  # This will help us debug
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{getattr(form, field).label.text}: {error}', 'error')
    
    return redirect(url_for('admin_panel.edit_user', user_id=user_id))

@bp.route('/get_company_users/<int:company_id>')
@login_required
def get_company_users(company_id):
    print(f"Fetching users for company ID: {company_id}")  # Debug log
    users = User.query.filter_by(
        company_id=company_id,
        isactiveYN=True
    ).all()
    
    user_list = [{
        'id': user.id,
        'name': user.name
    } for user in users]
    
    print(f"Found users: {user_list}")  # Debug log
    return jsonify(user_list)

# ROLE MANAGEMENT

@bp.route('/roles')
@login_required
def manage_roles():
    roles = Role.query.all()
    return render_template('administration/manage_roles.html', 
                         roles=roles,
                         title="Role Management")

@bp.route('/role/<int:role_id>', methods=['GET'])
@login_required
def get_role(role_id):
    role = Role.query.get_or_404(role_id)
    return jsonify({
        'role_name': role.role_name,
        'description': getattr(role, 'description', '')
    })

@bp.route('/role', methods=['POST'])
@login_required
def create_role():
    try:
        data = request.get_json()
        role = Role(role_name=data['role_name'])
        db.session.add(role)
        db.session.commit()
        return jsonify({'message': 'Success'})
    except Exception as e:
        db.session.rollback()
        print(f"Error creating role: {str(e)}")
        return jsonify({'message': 'Error creating role'}), 500

@bp.route('/role/<int:role_id>', methods=['PUT'])
@login_required
def update_role(role_id):
    try:
        role = Role.query.get_or_404(role_id)
        data = request.get_json()
        
        role.role_name = data['role_name']
        if 'description' in data:
            role.description = data['description']
            
        db.session.commit()
        return jsonify({'message': 'Success'})
    except Exception as e:
        db.session.rollback()
        print(f"Error updating role: {str(e)}")
        return jsonify({'message': 'Error updating role'}), 500

@bp.route('/role/<int:role_id>/menus', methods=['POST'])
@login_required
def update_role_menus(role_id):
    try:
        role = Role.query.get_or_404(role_id)
        menu_ids = request.json.get('menu_ids', [])
        
        # Clear existing menu permissions
        RoleMenuPermission.query.filter_by(role_id=role_id).delete()
        
        # Add new menu permissions and collect routes
        route_names = set()
        for menu_id in menu_ids:
            # Add menu permission
            permission = RoleMenuPermission(role_id=role_id, menu_id=menu_id, can_access=True)
            db.session.add(permission)
            
            # Get route from menu
            menu = Menu.query.get(menu_id)
            if menu and menu.route:
                route_names.add(menu.route)
        
        # Update route permissions
        for route_name in route_names:
            route = Route.query.filter_by(route_name=route_name).first()
            if route:
                # Check if permission exists
                route_permission = RoutePermission.query.filter_by(
                    route_id=route.id,
                    role_id=role_id
                ).first()
                
                if not route_permission:
                    route_permission = RoutePermission(
                        route_id=route.id,
                        role_id=role_id,
                        can_access=True
                    )
                    db.session.add(route_permission)
        
        db.session.commit()
        return jsonify({'message': 'Success'})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating permissions: {str(e)}")
        return jsonify({'message': 'Error updating permissions'}), 500
    


@bp.route("/company_configuration")
@login_required
def company_configuration():
    # Get the current user's company
    company = current_user.company
    
    if not company:
        flash('No company associated with your account', 'error')
        return redirect(url_for('dashboard.index'))
    
    # Get all countries from the database
    countries = CountryMaster.query.order_by(CountryMaster.countryName).all()
    
    return render_template("administration/company_configuration.html", 
                         company=company,
                         countries=countries)

@bp.route("/update_company", methods=['PUT', 'POST'])
@login_required 
def update_company():

    
    # Get the current user's company
    company = current_user.company
    
    if not company:
        return jsonify({'success': False, 'message': 'No company associated with your account'}), 404
    
    try:
        # Get form data
        company.company_name = request.form.get('company_name', '').strip()
        company.address = request.form.get('address', '').strip()
        company.country = int(request.form.get('country'))  # Convert to integer since we're storing ID now
        company.email = request.form.get('email', '').strip()
        company.website = request.form.get('website', '').strip()
        company.contact_num = request.form.get('contact_num', '').strip()
        company.vat_identification_number = request.form.get('vat_identification_number', '').strip()
        
        # Handle file upload for company logo
        if 'company_logo' in request.files:
            file = request.files['company_logo']
            if file and file.filename:
                # Validate file type
                allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
                if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                    # Read file content as binary
                    company.company_logo = file.read()
                else:
                    return jsonify({'success': False, 'message': 'Invalid file type. Only PNG, JPG, JPEG, and GIF are allowed.'}), 400
        
        # Validate required fields
        if not company.company_name:
            return jsonify({'success': False, 'message': 'Company name is required'}), 400
        
        # Check for duplicate email (excluding current company)
        if company.email:
            existing_company = CompanyInfo.query.filter(
                CompanyInfo.email == company.email,
                CompanyInfo.id != company.id
            ).first()
            
            if existing_company:
                return jsonify({'success': False, 'message': 'Email already exists'}), 400
        
        # Save changes
        company.updated_at = datetime.now()
        db.session.commit()
        
        if request.method == 'POST':  # Handle form submission
            flash('Company information updated successfully', 'success')
            return redirect(url_for('admin_panel.company_configuration'))
        else:  # Handle AJAX PUT request
            return jsonify({'success': True, 'message': 'Company information updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        if request.method == 'POST':
            flash(f'Error updating company: {str(e)}', 'error')
            return redirect(url_for('admin_panel.company_configuration'))
        else:
            return jsonify({'success': False, 'message': f'Error updating company: {str(e)}'}), 500





