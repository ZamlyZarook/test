from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.blueprints.admin import bp
from app import db
from app.models.user import User
from app.utils import admin_required

# @bp.route("/dashboard")
# @login_required
# @admin_required
# def dashboard():
#     if current_user.role_id not in [1, 2]:
#         flash("Access denied.", "danger")
#         return redirect(url_for("main.index"))

#     # Get statistics based on role
#     if current_user.role_id == 1:  # Super Admin - show all counts
#         total_cards = Coupon.query.count()
#         total_merchants = Customer.query.count()
#         total_schemes = Scheme.query.count()
#     else:  # Regular Admin (role_id=2) - filter by company_id
#         total_cards = Coupon.query.filter_by(company_id=current_user.company_id).count()
#         total_merchants = Customer.query.filter_by(company_id=current_user.company_id).count()
#         total_schemes = Scheme.query.filter_by(company_id=current_user.company_id).count()

#     return render_template(
#         "admin/dashboard.html",
#         total_cards=total_cards,
#         total_merchants=total_merchants,
#         total_schemes=total_schemes,
#     )

# Add other routes as needed...
