from app.user import bp
from flask import render_template, redirect, url_for, jsonify, request, flash
from flask_login import login_required, current_user
from app import db
from werkzeug.utils import secure_filename

from app.models.user import User  # Ensure this is present

# --- Cleaned up user profile routes ---

@bp.route('/profile')
@login_required
def profile():
    return render_template("user/profile.html")

@bp.route('/edit_profile')
@login_required
def edit_profile():
    user = current_user
    return render_template('user/edit_profile.html', user=user)

@bp.route('/update_user_details', methods=["POST"])
@login_required
def update_user_details():
    user = current_user

    # Get the form data
    full_name = request.form.get('full_name')
    username = request.form.get('username')
    email = request.form.get('email')
    gender = request.form.get('gender')
    address = request.form.get('address')
    contact_number = request.form.get('contact_number')

    # Validation
    if not full_name or not username or not email:
        flash("Full name, username, and email are required.", "warning")
        return redirect(url_for('user.edit_profile'))

    # Update user details
    user.name = full_name
    user.username = username
    user.email = email
    user.gender = gender
    user.address = address
    user.contact_number = contact_number
    db.session.commit()

    flash("Profile updated successfully.", "success")
    return redirect(url_for('user.edit_profile'))

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    if 'profile_picture' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('user.edit_profile'))

    file = request.files['profile_picture']
    if file and allowed_file(file.filename):
        file_data = file.read()
        current_user.profile_picture = file_data
        db.session.commit()
        flash("Profile picture updated successfully.", "success")
    else:
        flash("Invalid file type. Only jpg, jpeg, png allowed.", "danger")

    return redirect(url_for('user.edit_profile'))


