from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField,
    TextAreaField,
    BooleanField,
    SubmitField,
    EmailField,
    DateField,
    SelectField,
    IntegerField,
    FloatField,
    FieldList,
    FormField,
)
from wtforms.validators import (
    DataRequired,
    Length,
    ValidationError,
    Email,
    Optional,
    NumberRange,
)
from app.models.cha import (
    Customer,
    Department,
    ShipmentType,
    BLStatus,
    FreightTerm,
    RequestType,
    DocumentType,
    ShippingLine,
    Terminal,
)
from app.models.user import User, CountryMaster, CurrencyMaster


class BaseMasterForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(min=2, max=100)])
    is_active = BooleanField("Active")
    submit = SubmitField("Save")


class CustomerForm(FlaskForm):
    customer_id = StringField(
        "Customer ID", validators=[DataRequired(), Length(max=20)], render_kw={'readonly': True} 
    )
    customer_name = StringField(
        "Customer Name", validators=[DataRequired(), Length(max=100)]
    )
    short_name = StringField(
        "Short Name", validators=[DataRequired(), Length(max=10)]
    )
    customer_type = SelectField(
        "Customer Type",
        choices=[
            (1, "Customer"),
            (2, "Freight Forwarder"),
            (3, "Custom House Agent")
        ],
        coerce=int,
        validators=[DataRequired()],
        default=1
    )
    address = TextAreaField("Address", validators=[DataRequired()])
    email = EmailField("Email", validators=[DataRequired(), Email()])
    telephone = StringField("Telephone No", validators=[DataRequired(), Length(max=20)])

    # Additional fields
    credit_facility = SelectField(
        "Credit Facility",
        choices=[("", "Select Currency"), ("LKR", "LKR"), ("USD", "USD")],
        validators=[DataRequired()],
    )
    credit_period = StringField("Credit Period (Days)", validators=[Length(max=50)])
    dsr_format = SelectField(
        "DSR Format",
        choices=[
            ("", "Select DSR Format"),
            ("format1", "Format 1"),
            ("format2", "Format 2"),
        ],
        validators=[Optional()],
    )
    icl_report_format = SelectField(
        "ICL Report Format",
        choices=[
            ("", "Select Report Format"),
            ("format1", "Format 1"),
            ("format2", "Format 2"),
        ],
        validators=[Optional()],
    )
    new_storage_report_format = SelectField(
        "New Storage Report Format",
        choices=[
            ("", "Select Report Format"),
            ("format1", "Format 1"),
            ("format2", "Format 2"),
        ],
        validators=[Optional()],
    )
    sales_person = SelectField(
        "Sales Person", choices=[("", "Select Sales Person")], validators=[Optional()]
    )
    cs_executive = SelectField(
        "CS Executive", choices=[("", "Select CS Executive")], validators=[Optional()]
    )
    status = BooleanField("Active", default=True)

    # Billing Party
    billing_party_same = BooleanField("Same as Customer", default=True)
    billing_party_name = StringField(
        "Billing Party Name", validators=[Optional(), Length(max=100)]
    )
    billing_party_address = TextAreaField("Billing Address", validators=[Optional()])
    billing_party_email = EmailField("Billing Email", validators=[Optional(), Email()])
    billing_party_contact_person = StringField(
        "Contact Person", validators=[Optional(), Length(max=100)]
    )
    billing_party_telephone = StringField(
        "Billing Telephone", validators=[Optional(), Length(max=20)]
    )

    submit = SubmitField("Save")


class CurrencyForm(BaseMasterForm):
    code = StringField("Code", validators=[DataRequired(), Length(min=2, max=3)])

    def validate_code(self, code):
        currency = CurrencyMaster.query.filter_by(CUrrencyCode=code.data).first()
        if currency:
            raise ValidationError(
                "Currency code already exists. Please choose another one."
            )


class DepartmentForm(FlaskForm):
    department_code = StringField(
        "Department Code", validators=[DataRequired(), Length(min=2, max=20)]
    )
    department_name = StringField(
        "Department Name", validators=[DataRequired(), Length(min=2, max=100)]
    )
    is_active = BooleanField("Active")
    submit = SubmitField("Submit")


class ShipmentTypeForm(FlaskForm):
    shipment_code = StringField(
        "Shipment Type Code", validators=[DataRequired(), Length(min=2, max=20)]
    )
    base_type_id = SelectField(
        'Base Shipment Type',
        choices=[],  # This will be populated in the route
        coerce=int,
        validators=[
            DataRequired(message="Please select a base shipment type"),
            NumberRange(min=1, message="Please select a valid base shipment type")
        ]
    )
    docCode = StringField("Document Code", validators=[Optional(), Length(max=50)])
    is_active = BooleanField("Active")
    submit = SubmitField("Submit")


class BLStatusForm(FlaskForm):
    bl_code = StringField(
        "BL Status Code", validators=[DataRequired(), Length(min=2, max=20)]
    )
    bl_name = StringField(
        "BL Status Name", validators=[DataRequired(), Length(min=2, max=100)]
    )
    is_active = BooleanField("Active")
    submit = SubmitField("Submit")


class FreightTermForm(FlaskForm):
    freight_code = StringField(
        "Freight Term Code", validators=[DataRequired(), Length(min=2, max=20)]
    )
    freight_name = StringField(
        "Freight Term Name", validators=[DataRequired(), Length(min=2, max=100)]
    )
    is_active = BooleanField("Active")
    submit = SubmitField("Submit")


class RequestTypeForm(BaseMasterForm):
    pass


class DocumentTypeForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=100)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save")


class ShippingLineForm(FlaskForm):
    shipping_line_id = StringField(
        "Shipping Line ID", validators=[DataRequired(), Length(max=20)]
    )
    name = StringField("Name", validators=[DataRequired(), Length(max=100)])
    address = TextAreaField("Address", validators=[DataRequired()])
    contact_no = StringField("Contact No", validators=[DataRequired(), Length(max=20)])
    email = StringField("Email", validators=[DataRequired(), Length(max=120)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save")


class CountryForm(FlaskForm):
    countryCode = StringField(
        "Country Code", validators=[DataRequired(), Length(max=20)]
    )
    alpha2Code = StringField("Alpha-2 Code", validators=[Length(max=255)])
    countryName = StringField("Country Name", validators=[Length(max=100)])
    nationality = StringField("Nationality", validators=[Length(max=100)])
    regionID = StringField("Region ID")
    isLocal = BooleanField("Is Local")
    countryFlag = StringField("Country Flag", validators=[Length(max=255)])
    currency_code = StringField("Currency Code", validators=[Length(max=10)])
    currency_name = StringField("Currency Name", validators=[Length(max=255)])
    submit = SubmitField("Save")


class TerminalForm(FlaskForm):
    terminal_id = StringField(
        "Terminal ID", validators=[DataRequired(), Length(max=20)]
    )
    name = StringField("Name", validators=[DataRequired(), Length(max=100)])
    address = TextAreaField("Address", validators=[DataRequired()])
    contact_no = StringField("Contact No", validators=[DataRequired(), Length(max=20)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Create")


class BranchForm(FlaskForm):
    branch_id = StringField("Branch ID", validators=[DataRequired(), Length(max=20)])
    name = StringField("Name", validators=[DataRequired(), Length(max=100)])
    address = TextAreaField("Address", validators=[DataRequired()])
    contact_no = StringField("Contact No", validators=[DataRequired(), Length(max=20)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Create")


class RunnerForm(FlaskForm):
    # Runner Profile
    runner_id = StringField("Runner ID", validators=[DataRequired(), Length(max=20)])
    profile_image = FileField(
        "Profile Image",
        validators=[FileAllowed(["jpg", "png", "jpeg"], "Images only!")],
    )
    first_name = StringField("First Name", validators=[DataRequired(), Length(max=100)])
    last_name = StringField("Last Name", validators=[DataRequired(), Length(max=100)])
    nic_no = StringField("NIC No", validators=[DataRequired(), Length(max=20)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    mobile = StringField("Mobile", validators=[DataRequired(), Length(max=20)])
    date_of_birth = StringField("Date of Birth", validators=[DataRequired()])
    driving_license_no = StringField(
        "Driving License No", validators=[DataRequired(), Length(max=20)]
    )
    driving_license_expiry = StringField(
        "Driving License Expiry Date", validators=[DataRequired()]
    )
    assigned_area = StringField(
        "Assigned Area", validators=[DataRequired(), Length(max=100)]
    )
    is_active = BooleanField("Active", default=True)

    # Vehicle Details
    registration_no = StringField("Registration No", validators=[Length(max=20)])
    vehicle_type = StringField("Vehicle Type", validators=[Length(max=50)])
    vehicle_model = StringField("Vehicle Model", validators=[Length(max=50)])
    vehicle_color = StringField("Vehicle Color", validators=[Length(max=50)])
    engine_no = StringField("Engine No", validators=[Length(max=50)])
    chassis_no = StringField("Chassis No", validators=[Length(max=50)])
    insurance_no = StringField("Insurance No", validators=[Length(max=50)])
    insurance_company = StringField("Insurance Company", validators=[Length(max=100)])
    insurance_expiry = StringField("Insurance Expiry Date")

    # Medical Profile
    blood_group = StringField("Blood Group", validators=[Length(max=5)])
    allergies = TextAreaField("Allergies/Sicknesses")
    medical_insurance = BooleanField("Medical Insurance")
    medical_insurance_company = StringField(
        "Insurance Company Name", validators=[Length(max=100)]
    )
    medical_insurance_no = StringField("Insurance No", validators=[Length(max=50)])
    medical_insurance_expiry = StringField("Insurance Expiry Date")

    # Emergency Contact
    emergency_contact_name = StringField("Name", validators=[Length(max=100)])
    emergency_contact_relationship = StringField(
        "Relationship", validators=[Length(max=50)]
    )
    emergency_contact_telephone = StringField("Telephone", validators=[Length(max=20)])
    emergency_contact_mobile = StringField("Mobile", validators=[Length(max=20)])

    submit = SubmitField("Save")


class WharfProfileForm(FlaskForm):
    wharf_id = StringField("Wharf ID", validators=[DataRequired(), Length(max=20)])
    first_name = StringField(
        "First Name", validators=[DataRequired(), Length(min=2, max=50)]
    )
    last_name = StringField(
        "Last Name", validators=[DataRequired(), Length(min=2, max=50)]
    )
    nic_no = StringField("NIC No", validators=[DataRequired(), Length(max=20)])
    contact_number = StringField(
        "Contact Number", validators=[DataRequired(), Length(min=8, max=20)]
    )
    email = EmailField("Email", validators=[DataRequired(), Email()])
    address = TextAreaField("Address", validators=[DataRequired()])
    date_of_birth = StringField("Date of Birth", validators=[DataRequired()])

    # Driving License
    driving_license_number = StringField(
        "Driving License Number", validators=[DataRequired(), Length(max=50)]
    )
    driving_license_expiry = StringField(
        "Driving License Expiry", validators=[DataRequired()]
    )

    # Vehicle Details
    registration_no = StringField(
        "Registration No", validators=[DataRequired(), Length(max=20)]
    )
    vehicle_type = StringField(
        "Vehicle Type", validators=[DataRequired(), Length(max=50)]
    )
    vehicle_model = StringField(
        "Vehicle Model", validators=[DataRequired(), Length(max=50)]
    )
    vehicle_color = StringField(
        "Vehicle Color", validators=[DataRequired(), Length(max=30)]
    )
    engine_no = StringField("Engine No", validators=[DataRequired(), Length(max=50)])
    chassis_no = StringField("Chassis No", validators=[DataRequired(), Length(max=50)])

    # Insurance Details
    insurance_number = StringField(
        "Insurance Number", validators=[DataRequired(), Length(max=50)]
    )
    insurance_company = StringField(
        "Insurance Company", validators=[DataRequired(), Length(max=100)]
    )
    insurance_expiry = StringField("Insurance Expiry", validators=[DataRequired()])

    # Medical Insurance
    medical_insurance_number = StringField(
        "Medical Insurance Number", validators=[DataRequired(), Length(max=50)]
    )
    medical_insurance_expiry = StringField(
        "Medical Insurance Expiry", validators=[DataRequired()]
    )

    # Documents
    profile_image = FileField(
        "Profile Image",
        validators=[
            FileAllowed(
                ["jpg", "png", "jpeg"], "Only jpg, png, and jpeg images are allowed!"
            )
        ],
    )
    nic_document = FileField(
        "NIC Document",
        validators=[FileAllowed(["pdf"], "Only PDF files are allowed!")],
    )
    insurance_document = FileField(
        "Insurance Document",
        validators=[FileAllowed(["doc", "docx", "pdf"], "Only Word documents are allowed!")],
    )

    status = BooleanField("Active")
    submit = SubmitField("Submit")


class OrderItemForm(FlaskForm):
    item_name = StringField("Item Name", validators=[DataRequired()])
    quantity = IntegerField("Quantity", validators=[DataRequired(), NumberRange(min=1)])
    unit_price = FloatField(
        "Unit Price", validators=[DataRequired(), NumberRange(min=0)]
    )
    description = TextAreaField("Description")


class OrderForm(FlaskForm):
    customer_id = SelectField("Customer", coerce=int, validators=[DataRequired()])
    order_date = DateField("Order Date", validators=[DataRequired()])
    status = SelectField(
        "Status",
        choices=[
            ("Pending", "Pending"),
            ("Processing", "Processing"),
            ("Completed", "Completed"),
            ("Cancelled", "Cancelled"),
        ],
        validators=[DataRequired()],
    )
    description = TextAreaField("Description")
    items = FieldList(FormField(OrderItemForm), min_entries=1)
    submit = SubmitField("Save Order")


class ShipDocumentEntryForm(FlaskForm):
    shipTypeid = SelectField("Shipment Type", coerce=int, validators=[DataRequired()])
    shipCategory = SelectField("Ship Category", coerce=int, validators=[DataRequired()])
    customer_id = SelectField("Customer", coerce=int, validators=[DataRequired()])
    dealineDate = DateField("Deadline Date", validators=[DataRequired()])
    docStatusID = SelectField(
        "Document Status", coerce=int, validators=[DataRequired()]
    )
    cusOriginalReady = SelectField(
        "Original Ready",
        choices=[("Y", "Yes"), ("N", "No")],
        validators=[DataRequired()],
    )
    custComment = TextAreaField("Comments")
    submit = SubmitField("Create Entry")

    def __init__(self, *args, **kwargs):
        super(ShipDocumentEntryForm, self).__init__(*args, **kwargs)
        # Choices will be populated dynamically in the route
        self.shipTypeid.choices = []
        self.shipCategory.choices = []
        self.docStatusID.choices = []
        self.customer_id.choices = []
