from flask_wtf import FlaskForm
from wtforms import SelectField, IntegerField, SubmitField
from wtforms.validators import DataRequired, NumberRange


class IssueCouponsForm(FlaskForm):
    merchant_id = SelectField(
        "Select Merchant", coerce=int, validators=[DataRequired()]
    )
    scheme_id = SelectField("Select Scheme", coerce=int, validators=[DataRequired()])
    number_of_coupons = IntegerField(
        "Number of Coupons",
        validators=[
            DataRequired(),
            NumberRange(min=1, max=1000, message="Number must be between 1 and 1000"),
        ],
    )
    submit = SubmitField("Issue Coupons")
