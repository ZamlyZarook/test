# administration/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Email, Optional
from urllib.parse import urlparse
from wtforms import StringField, PasswordField, SelectField, BooleanField, TextAreaField
from wtforms.validators import DataRequired, Email, Optional, Length, EqualTo
from app.models.user import User, Role, Menu, RoleMenuPermission
from app.models.company import CompanyInfo

def validate_url(form, field):
    if field.data:
        # Allow empty values since URL is optional
        if not field.data.startswith(('http://', 'https://')):
            field.data = 'http://' + field.data  # Add http:// if missing

class CreateCompanyForm(FlaskForm):
    company_name = StringField('Company Name', validators=[DataRequired()])
    company_code = StringField('Company Code', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    website = StringField('Website', validators=[DataRequired(), validate_url])
    contact_number = StringField('Contact Number', validators=[DataRequired()])
    address = TextAreaField('Address', validators=[DataRequired()])

class EditCompanyForm(FlaskForm):
    company_name = StringField('Company Name', validators=[DataRequired()])
    company_code = StringField('Company Code', validators=[Optional()])
    email = StringField('Email', validators=[Optional(), Email()])
    website = StringField('Website', validators=[Optional(), validate_url])
    contact_number = StringField('Contact Number', validators=[Optional()])
    address = TextAreaField('Address', validators=[Optional()])