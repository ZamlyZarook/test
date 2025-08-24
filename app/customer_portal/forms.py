from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, DateField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Optional


class ShipDocumentEntryForm(FlaskForm):
    shipTypeid = SelectField("Shipment Type", coerce=int, validators=[DataRequired()])
    dealineDate = DateField("Deadline Date", validators=[Optional()])
    docStatusID = SelectField(
        "Document Status", coerce=int, validators=[DataRequired()]
    )
    custComment = TextAreaField("Customer Comment", validators=[Optional()])
    cusOriginalReady = SelectField(
        "Original Ready",
        choices=[("Yes", "Yes"), ("No", "No")],
        validators=[DataRequired()],
    )
    shipCategory = SelectField("Ship Category", coerce=int, validators=[DataRequired()])
    assigned_clearing_company = SelectField(
        "Clearing Company", 
        coerce=lambda x: int(x) if x else None,  # Convert to int if not empty, else None
        validators=[Optional()],
        choices=[]
    )