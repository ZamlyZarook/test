from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    TextAreaField,
    DecimalField,
    SelectField,
    SubmitField,
    SelectMultipleField,
    PasswordField,
    BooleanField,
    IntegerField,
    DateTimeField,
    FileField,
)
from flask_wtf.file import FileField, FileAllowed
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    EqualTo,
    Optional,
    NumberRange,
)
from datetime import datetime, timedelta
from app.utils import get_sri_lanka_time


class MerchantForm(FlaskForm):
    # Basic Details
    name = StringField("Company Name", validators=[DataRequired(), Length(max=100)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    phone = StringField("Contact Number", validators=[DataRequired(), Length(max=20)])
    address = TextAreaField("Address", validators=[DataRequired()])
    country = SelectField("Country", validators=[DataRequired()])
    status = SelectField(
        "Status", choices=[("active", "Active"), ("inactive", "Inactive")]
    )

    # Login Details Checkbox
    create_login = BooleanField("Create Login Credentials")

    # Login Details
    username = StringField("Username", validators=[Optional(), Length(min=4, max=64)])
    password = PasswordField("Password", validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[Optional(), EqualTo("password", message="Passwords must match")],
    )

    submit = SubmitField("Submit")

    def __init__(self, *args, **kwargs):
        super(MerchantForm, self).__init__(*args, **kwargs)
        self.country.choices = [
            ("United Arab Emirates", "United Arab Emirates"),
            ("United States", "United States"),
            ("United Kingdom", "United Kingdom"),
            ("Canada", "Canada"),
            ("Australia", "Australia"),
            ("India", "India"),
            ("Germany", "Germany"),
            ("France", "France"),
            ("Italy", "Italy"),
            ("Spain", "Spain"),
            ("Japan", "Japan"),
            ("China", "China"),
        ]


class SchemeForm(FlaskForm):
    name = StringField(
        "Scheme Name", validators=[DataRequired(), Length(min=2, max=100)]
    )
    description = TextAreaField("Description", validators=[DataRequired()])
    value = DecimalField("Value", validators=[DataRequired()])
    price = DecimalField("Price", validators=[DataRequired()])
    status = SelectField(
        "Status",
        choices=[("active", "Active"), ("inactive", "Inactive")],
        validators=[DataRequired()],
    )
    submit = SubmitField("Submit")


class IssueCouponsForm(FlaskForm):
    merchant_id = SelectField(
        "Select Customer", coerce=int, validators=[DataRequired()]
    )
    scheme_id = SelectField("Select Scheme", coerce=int, validators=[DataRequired()])
    coupons = SelectMultipleField(
        "Select Coupons", coerce=int, validators=[DataRequired()]
    )
    note = StringField("Note")
    submit = SubmitField("Issue Coupons")

    def __init__(self, *args, **kwargs):
        super(IssueCouponsForm, self).__init__(*args, **kwargs)
        # Initialize with placeholder options
        self.merchant_id.choices = [(-1, "-- Select Customer --")]
        self.scheme_id.choices = [(-1, "-- Select Scheme --")]
        self.coupons.choices = []



class BulkGenerateCouponsForm(FlaskForm):
    scheme_id = SelectField("Scheme", coerce=int, validators=[DataRequired()])
    num_coupons = IntegerField(
        "Number of Coupons",
        validators=[DataRequired(), NumberRange(min=1, max=1000)],
        default=1,
    )
    validity_date = DateTimeField(
        "Validity Date",
        format="%Y-%m-%d %H:%M:%S",
        validators=[DataRequired()],
        default=lambda: get_sri_lanka_time() + timedelta(days=365),
    )
    submit = SubmitField("Generate Coupons")

    def __init__(self, *args, **kwargs):
        super(BulkGenerateCouponsForm, self).__init__(*args, **kwargs)
        from app.models import Scheme

        self.scheme_id.choices = [(s.id, s.name) for s in Scheme.query.all()]


class CreateUserForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=3, max=255, message="Username must be between 3 and 255 characters")
    ])
    name = StringField('Full Name', validators=[
        DataRequired(),
        Length(max=255, message="Name must be less than 255 characters")
    ])
    gender = SelectField('Gender', choices=[('Male', 'Male'), ('Female', 'Female')], validators=[DataRequired()])
    address = TextAreaField('Address', validators=[Optional()])
    contact = StringField('Contact Number', validators=[
        Optional(),
        Length(max=20, message="Contact number must be less than 20 characters")
    ])
    email = StringField('Email', validators=[
        DataRequired(),
        Email(message="Please enter a valid email address")
    ])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=6, message='Password must be at least 6 characters')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    role_id = SelectField('Role', coerce=int, validators=[DataRequired()])
    company_id = SelectField('Company', coerce=int, validators=[DataRequired()])
    status  = BooleanField('Active', default=True)
    deactivation_reason = TextAreaField('Deactivation Reason', validators=[Optional()])
    profile_picture = FileField('Profile Picture', validators=[
        FileAllowed(['jpg', 'jpeg', 'png'], 'Only JPG, JPEG, and PNG files are allowed!'),
        Optional()
    ])


class EditUserForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=3, max=255, message="Username must be between 3 and 255 characters")
    ])
    name = StringField('Full Name', validators=[
        DataRequired(),
        Length(max=255, message="Name must be less than 255 characters")
    ])
    gender = SelectField('Gender', choices=[('Male', 'Male'), ('Female', 'Female')], validators=[DataRequired()])
    address = TextAreaField('Address', validators=[Optional()])
    contact = StringField('Contact Number', validators=[
        Optional(),
        Length(max=20, message="Contact number must be less than 20 characters")
    ])
    email = StringField('Email', validators=[
        DataRequired(),
        Email(message="Please enter a valid email address")
    ])
    password = PasswordField('Password', validators=[
        Optional(),  # Optional for editing
        Length(min=6, message='Password must be at least 6 characters')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        Optional(),  # Optional for editing
        EqualTo('password', message='Passwords must match')
    ])
    role_id = SelectField('Role', coerce=int, validators=[DataRequired()])
    company_id = SelectField('Company', coerce=int, validators=[DataRequired()])
    status = BooleanField('Active', default=True)
    deactivation_reason = TextAreaField('Deactivation Reason', validators=[Optional()])
    profile_picture = FileField('Profile Picture', validators=[
        FileAllowed(['jpg', 'jpeg', 'png'], 'Only JPG, JPEG, and PNG files are allowed!'),
        Optional()
    ])