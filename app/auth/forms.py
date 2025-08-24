from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    BooleanField,
    SubmitField,
    SelectField,
    TextAreaField,
    EmailField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, ValidationError
from app.models import User
from app.models.user import CountryMaster


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField("Sign In")


from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, SelectField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

class RegistrationForm(FlaskForm):
    # User fields
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=4, max=64)]
    )
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])

    # Company fields
    company_name = StringField(
        "Company Name", validators=[DataRequired(), Length(max=100)]
    )
    address = TextAreaField("Address")
    country = SelectField(
        "Country",
        validators=[DataRequired()],
        coerce=int
    )
    website = StringField("Website", validators=[Length(max=200)])
    contact_number = StringField("Contact Number", validators=[DataRequired(), Length(max=20)])

    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match"),
        ],
    )
    
    # Navigation buttons
    next_button = SubmitField("Next")
    previous_button = SubmitField("Previous")
    submit = SubmitField("Register")

    def __init__(self, *args, **kwargs):
        super(RegistrationForm, self).__init__(*args, **kwargs)
        # Populate country choices from database
        self.country.choices = [(country.countryID, country.countryName) 
                               for country in CountryMaster.query.order_by(CountryMaster.countryName).all()]

    def validate_username(self, field):
        user = User.query.filter_by(username=field.data).first()
        if user:
            raise ValidationError(
                "Username already exists. Please choose a different one."
            )

    def validate_email(self, field):
        user = User.query.filter_by(email=field.data).first()
        if user:
            raise ValidationError(
                "Email already registered. Please use a different one."
            )


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Reset Password")


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

    # Login Details
    username = StringField("Username", validators=[Optional(), Length(min=4, max=64)])
    password = PasswordField("Password", validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[Optional(), EqualTo("password", message="Passwords must match")],
    )

    submit = SubmitField("Submit")

   