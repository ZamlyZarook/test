from flask import (
    render_template,
    redirect,
    url_for,
    flash,
    request,
    current_app,
    jsonify,
    session
)
from flask_login import login_user, logout_user, current_user, login_required
from app import db
from app.auth import bp
from app.auth.forms import LoginForm, RegistrationForm, ForgotPasswordForm
from app.models import User
from app.models.cha import Customer
from app.masters.routes import generate_customer_id
from sqlalchemy.exc import IntegrityError
import traceback
from app.utils import generate_merchant_code
from app.models.company import CompanyInfo
from app.models.user import CountryMaster, ProductPackage
from app.email import send_email, send_async_email

import sys
import os

# Add navitrax root to the system path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from changepassword import reset_all_passwords  # ✅ Now you can import it

@bp.route("/landing", methods=["GET", "POST"])
def landing():
    if current_user.is_authenticated:
        # if current_user.role_id in [1, 2]:
        return redirect(url_for("customer_portal.index"))
        # else:
        #     pass

    return render_template("auth/landing.html")




@bp.route("/login", methods=["GET", "POST"])
def login():
    print("\n=== Login Route Accessed ===")
    print(f"Method: {request.method}")
    print(f"Form Data: {request.form}")

    if current_user.is_authenticated:
        return redirect(url_for("customer_portal.index"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        remember_me = request.form.get("remember_me") == "on"

        print(f"\nLogin attempt:")
        print(f"Email: {email}")
        print(f"Password provided: {bool(password)}")
        print(f"Remember me: {remember_me}")

        user = User.query.filter_by(email=email).first()
        print(f"User found: {user is not None}")

        if user:
            if not user.is_active:
                print("Login failed - account not activated")
                flash("Your account is being verified. You will be notified via e-mail once the verification is completed.", "warning")
            elif user.check_password(password):
                login_user(user, remember=remember_me)
                print(f"Login successful for {email}")
                return redirect(url_for("customer_portal.index"))
            else:
                print("Login failed - invalid credentials")
                flash("Invalid email or password", "danger")
        else:
            print("Login failed - user does not exist")
            flash("Invalid email or password", "danger")

    return render_template("auth/login.html", form=LoginForm())



@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("customer_portal.index"))

    # Get all countries for the dropdown
    countries = CountryMaster.query.order_by(CountryMaster.countryName).all()
    
    if request.method == "POST":
        try:
            # Get form data
            user_type = request.form.get('user_type')  # New field
            company_name = request.form.get('company_name')
            address = request.form.get('address')
            country_id = request.form.get('country')
            website = request.form.get('website')
            contact_number = request.form.get('contact_number')

            name = request.form.get('name')
            gender = request.form.get('gender')
            contact = request.form.get('contact')
            user_address = request.form.get('user_address')

            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            
            # Validate required fields
            if not all([user_type, company_name, country_id, contact_number, name, gender, contact, username, email, password, confirm_password]):
                flash("Please fill all required fields", "danger")
                return render_template("auth/register.html", countries=countries)
            
            # Validate user_type
            if user_type not in ['cha', 'company']:
                flash("Invalid user type selection", "danger")
                return render_template("auth/register.html", countries=countries)
            
            # Validate passwords match
            if password != confirm_password:
                flash("Passwords do not match", "danger")
                return render_template("auth/register.html", countries=countries)
            
            # Check if username exists
            if User.query.filter_by(username=username).first():
                flash("Username already exists. Please choose a different one.", "danger")
                return render_template("auth/register.html", countries=countries)
            
            # Check if email exists
            if User.query.filter_by(email=email).first():
                flash("Email already registered. Please use a different one.", "danger")
                return render_template("auth/register.html", countries=countries)
            
            # Get the country object
            country = CountryMaster.query.get(country_id)
            if not country:
                flash("Invalid country selection", "danger")
                return render_template("auth/register.html", countries=countries)
            
            # Set role based on user type
            if user_type == 'cha':
                role = "user"
                role_id = 3
                is_super_admin = 0
                is_cha = True
                customer_type = 2  # Clearing Agent
            else:  # company
                role = "customer"
                role_id = 4
                is_super_admin = 3
                is_cha = False
                customer_type = 1  # Company
            
            # Check if company already exists
            company = CompanyInfo.query.filter_by(company_name=company_name).first()
            
            if not company:
                # Create a new company
                company = CompanyInfo(
                    company_name=company_name,
                    legal_name=company_name,  # Assuming legal name is same as company name
                    address=address,
                    country=country_id,
                    email=email,
                    website=website,
                    contact_num=contact_number,
                    is_cha=is_cha,  # Set the CHA flag
                )
                db.session.add(company)
                db.session.flush()  # Get company ID before commit

            # Create the user and assign the company
            user = User(
                username=username,
                name=name,
                gender=gender,
                contact_number=contact,
                address=user_address,
                email=email,
                role=role,
                role_id=role_id,
                is_active=0,  # Account starts as inactive, needs admin activation
                is_super_admin=is_super_admin,
                company_id=company.id,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()  # Get user ID before creating customer

            # Only create customer record for company type (not for CHA)
            if user_type == 'company':
                # Generate customer ID and create customer record
                customer_id = generate_customer_id()
                
                # Create short_name from first 10 characters of company_name
                short_name = company_name[:10] if len(company_name) >= 10 else company_name
                
                # Create customer record
                customer = Customer(
                    customer_id=customer_id,
                    customer_name=company_name,
                    short_name=short_name,
                    address=address,
                    email=email,
                    telephone=contact_number,
                    customer_type=customer_type,
                    role_id=role_id,
                    company_id=company.id,
                    user_id=user.id,  # Link the user to this customer
                    status=True  # Assuming default status is active
                )
                db.session.add(customer)

            # Fetch all base product packages (only for companies)
            if user_type == 'company':
                base_packages = ProductPackage.query.filter_by(is_base=1).all()

                # Clone each base product for the new company
                for base in base_packages:
                    new_package = ProductPackage(
                        product=base.product,
                        value=base.value,
                        companyID=company.id,
                        is_base=0  # Mark as non-base
                    )
                    db.session.add(new_package)

            db.session.commit()
            
            # Send registration confirmation email
            try:
                from datetime import datetime
                current_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
                current_year = datetime.now().year
                
                email_data = {
                    'customer_name': name,
                    'company_name': company_name,
                    'email': email,
                    'username': username,
                    'account_type': user_type,  # 'company' or 'cha'
                    'registration_date': current_date,
                    'current_year': current_year
                }
                
                send_email(
                    subject=f"Registration Successful - Welcome to Navitrax",
                    recipient=email,
                    template="email/registration_confirmation.html",
                    **email_data
                )
                print(f"Registration confirmation email sent to: {email}")
                
            except Exception as email_error:
                print(f"Failed to send registration confirmation email: {str(email_error)}")
                # Don't fail the registration if email fails
            
            flash("Registration successful! Account verification is in progress. You will receive an email when your account is verified and activated.", "success")
            return redirect(url_for("auth.login"))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error during registration", "danger")
            print(f"Error during registration: {str(e)}")
    
    return render_template("auth/register.html", countries=countries)



@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.landing"))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            flash("Password reset instructions have been sent to your email.", "info")
            return redirect(url_for("auth.login"))
        flash("Email address not found.", "error")
    return render_template("auth/forgot_password.html", form=form)


@bp.route("/test_login")
def test_login():
    try:
        email = "test@test.com"
        user = User.query.filter_by(email=email).first()

        if not user:
            base_username = "test"
            counter = 1
            username = base_username

            while User.query.filter_by(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1

            user = User(username=username, email=email)
            user.set_password("test123")
            db.session.add(user)
            db.session.commit()

        login_user(user)

        return jsonify(
            {
                "success": current_user.is_authenticated,
                "user": {
                    "email": user.email,
                    "username": user.username,
                    "is_authenticated": current_user.is_authenticated,
                },
            }
        )

    except Exception as e:
        db.session.rollback()
        return (
            jsonify(
                {"success": False, "error": str(e), "traceback": traceback.format_exc()}
            ),
            500,
        )


@bp.route("/reset-all-passwords", methods=["GET", "POST"])
@login_required
def reset_all_passwords_route():
    print("Calling reset_all_passwords() from changepassword.py...")
    success = reset_all_passwords()

    if success:
        return jsonify({"success": True, "message": "All passwords reset to welcome1"})
    else:
        return jsonify({"success": False, "message": "Password reset failed"}), 500



@bp.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not current_user.check_password(current_password):
        flash("Current password is incorrect.", "danger")
        return redirect(request.referrer or url_for('user.edit_profile'))

    if not new_password or not confirm_password:
        flash("Please fill out all password fields.", "warning")
        return redirect(request.referrer or url_for('user.edit_profile'))

    if new_password != confirm_password:
        flash("New passwords do not match.", "warning")
        return redirect(request.referrer or url_for('user.edit_profile'))

    if len(new_password) < 8:
        flash("New password must be at least 8 characters long.", "warning")
        return redirect(request.referrer or url_for('user.edit_profile'))

    current_user.set_password(new_password)
    db.session.commit()
    flash("Password changed successfully.", "success")
    return redirect(url_for('user.edit_profile'))

