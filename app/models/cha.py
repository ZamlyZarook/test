from app.extensions import db, bcrypt
from flask_login import UserMixin
from datetime import datetime
import json


# Masters Models
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.String(20), nullable=False, unique=True)
    customer_name = db.Column(db.String(100), nullable=False)
    short_name = db.Column(db.String(10), nullable=False)
    address = db.Column(db.Text, nullable=False)
    email = db.Column(db.String(120), nullable=False)
    telephone = db.Column(db.String(20), nullable=False)

    # Customer type: 1 = Company, 2 = Clearing Agent
    customer_type = db.Column(db.Integer, nullable=False, default=1)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))  # New column for role relationship

    # Additional fields
    credit_facility = db.Column(db.String(10), nullable=True)  # LKR, USD, etc.
    credit_period = db.Column(db.String(50), nullable=True)  # Days
    dsr_format = db.Column(db.String(50), nullable=True)
    icl_report_format = db.Column(db.String(50), nullable=True)
    new_storage_report_format = db.Column(db.String(50), nullable=True)
    sales_person = db.Column(db.String(100), nullable=True)
    cs_executive = db.Column(db.String(100), nullable=True)
    status = db.Column(db.Boolean, default=True)

    # Billing Party
    billing_party_same = db.Column(db.Boolean, default=True)
    billing_party_name = db.Column(db.String(100), nullable=True)
    billing_party_address = db.Column(db.Text, nullable=True)
    billing_party_email = db.Column(db.String(120), nullable=True)
    billing_party_contact_person = db.Column(db.String(100), nullable=True)
    billing_party_telephone = db.Column(db.String(20), nullable=True)

    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(
        db.DateTime, default=datetime.now, onupdate=datetime.now
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    role = db.relationship("Role", foreign_keys=[role_id], backref="users_role")

    @property
    def customer_type_display(self):
        """Return human-readable customer type"""
        return "Company" if self.customer_type == 1 else "Clearing Agent"
    
    def __repr__(self):
        return f"Customer('{self.customer_name}')"


class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    department_code = db.Column(db.String(20), nullable=False)
    department_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class ShipmentType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shipment_code = db.Column(db.String(20), nullable=False)
    shipment_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    docCode = db.Column(db.String(50), nullable=True)
    lastDocNumber = db.Column(db.Integer, default=0)
    base_type_id = db.Column(db.Integer, db.ForeignKey('shipment_type_base.id'), nullable=False)
    base_type = db.relationship('ShipmentTypeBase', backref='shipment_types')


    def __repr__(self):
        return f"<ShipmentType {self.shipment_name}>"
    
class ShipmentTypeBase(db.Model):
    __tablename__ = 'shipment_type_base'

    id = db.Column(db.Integer, primary_key=True)
    base_code = db.Column(db.String(50), unique=True, nullable=False)  # e.g., AIR_IMPORT

    def __repr__(self):
        return f"<ShipmentTypeBase {self.base_name}>"



class BLStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bl_code = db.Column(db.String(20), nullable=False)
    bl_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class FreightTerm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    freight_code = db.Column(db.String(20), nullable=False)
    freight_name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class RequestType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class DocumentType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class ShippingLine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shipping_line_id = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text, nullable=False)
    contact_no = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class Terminal(db.Model):
    __tablename__ = "terminal"

    id = db.Column(db.Integer, primary_key=True)
    terminal_id = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text, nullable=False)
    contact_no = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f"Terminal('{self.name}')"


class Branch(db.Model):
    __tablename__ = "branch"

    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text, nullable=False)
    contact_no = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f"Branch('{self.name}')"


class Runner(db.Model):
    __tablename__ = "runner"

    id = db.Column(db.Integer, primary_key=True)
    runner_id = db.Column(db.String(20), nullable=False)
    profile_image = db.Column(db.String(255))
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    nic_no = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    mobile = db.Column(db.String(20), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    driving_license_no = db.Column(db.String(20), nullable=False)
    driving_license_expiry = db.Column(db.Date, nullable=False)
    assigned_area = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    user = db.relationship("User", backref="runner", uselist=False)

    # Vehicle Details
    registration_no = db.Column(db.String(20))
    vehicle_type = db.Column(db.String(50))
    vehicle_model = db.Column(db.String(50))
    vehicle_color = db.Column(db.String(50))
    engine_no = db.Column(db.String(50))
    chassis_no = db.Column(db.String(50))
    insurance_no = db.Column(db.String(50))
    insurance_company = db.Column(db.String(100))
    insurance_expiry = db.Column(db.Date)

    # Medical Profile
    blood_group = db.Column(db.String(5))
    allergies = db.Column(db.Text)
    medical_insurance = db.Column(db.Boolean, default=False)
    medical_insurance_company = db.Column(db.String(100))
    medical_insurance_no = db.Column(db.String(50))
    medical_insurance_expiry = db.Column(db.Date)

    # Emergency Contact
    emergency_contact_name = db.Column(db.String(100))
    emergency_contact_relationship = db.Column(db.String(50))
    emergency_contact_telephone = db.Column(db.String(20))
    emergency_contact_mobile = db.Column(db.String(20))

    def __repr__(self):
        return f"Runner('{self.first_name} {self.last_name}')"


class WharfProfile(db.Model):
    __tablename__ = "wharf_profiles"

    id = db.Column(db.Integer, primary_key=True)
    wharf_id = db.Column(db.String(20), unique=True, nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    nic_no = db.Column(db.String(20), nullable=False)
    contact_number = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    address = db.Column(db.Text, nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    driving_license_number = db.Column(db.String(50), nullable=False)
    driving_license_expiry = db.Column(db.Date, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    user = db.relationship("User", backref="wharf_profile", uselist=False)

    # Vehicle Details
    registration_no = db.Column(db.String(20), nullable=False)
    vehicle_type = db.Column(db.String(50), nullable=False)
    vehicle_model = db.Column(db.String(50), nullable=False)
    vehicle_color = db.Column(db.String(30), nullable=False)
    engine_no = db.Column(db.String(50), nullable=False)
    chassis_no = db.Column(db.String(50), nullable=False)

    # Insurance Details
    insurance_number = db.Column(db.String(50), nullable=False)
    insurance_company = db.Column(db.String(100), nullable=False)
    insurance_expiry = db.Column(db.Date, nullable=False)

    # Medical Insurance Details
    medical_insurance_number = db.Column(db.String(50), nullable=False)
    medical_insurance_expiry = db.Column(db.Date, nullable=False)

    # Documents
    nic_document = db.Column(db.String(150), nullable=True)
    insurance_document = db.Column(db.String(150), nullable=True)
    profile_image = db.Column(db.String(150), nullable=True, default="default.jpg")

    status = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(
        db.DateTime, default=datetime.now, onupdate=datetime.now
    )
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)

    def __repr__(self):
        return f"<WharfProfile {self.first_name} {self.last_name}>"


class DocumentStatus(db.Model):
    """Model for document status."""

    __tablename__ = "document_status"

    docStatusID = db.Column(db.Integer, primary_key=True)
    docType = db.Column(db.String(50), nullable=False)
    docStatusName = db.Column(db.String(50), nullable=False)
    docLevel = db.Column(db.Integer, nullable=False)  # New field for document level
    isActive = db.Column(db.Integer, default=1)  # 1 for active, 0 for inactive
    doctypeid = db.Column(db.Integer, db.ForeignKey("shipment_type.id"), nullable=True)
    shipment_type = db.relationship("ShipmentType", backref="document_statuses")

    def __repr__(self):
        return f"<DocumentStatus {self.docStatusName}>"


class ShipCategory(db.Model):
    """Model for ship category."""

    __tablename__ = "ship_category"

    id = db.Column(db.Integer, primary_key=True)
    catCode = db.Column(db.String(20), nullable=False)
    catname = db.Column(db.String(100), nullable=False)
    isActive = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.now)
    shipmentType = db.Column(
        db.Integer, db.ForeignKey("shipment_type.id"), nullable=False
    )
    shipment_type = db.relationship("ShipmentType", backref="ship_categories")

    def __repr__(self):
        return f"<ShipCategory {self.catname}>"


class ShipCatDocument(db.Model):
    __tablename__ = "ship_cat_document"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    shipCatid = db.Column(db.Integer, db.ForeignKey("ship_category.id"), nullable=False)
    shipmentTypeid = db.Column(
        db.Integer, db.ForeignKey("shipment_type.id"), nullable=False
    )  # Changed from shipmentType
    description = db.Column(db.String(255), nullable=True)
    isMandatory = db.Column(db.Integer, default=0)
    sample_file_path = db.Column(db.String(512), nullable=True)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())
    key_fields = db.Column(db.Text, nullable=True)
    confidence_level = db.Column(db.Float, default=0.0, nullable=False)  # New field
    content_similarity = db.Column(db.Float, default=0.0, nullable=False)  # New field (0-100)
    ai_validate = db.Column(db.Integer, default=0, nullable=False)         # New switch field (0/1)
    multiple_document = db.Column(db.Integer, default=0, nullable=False)
    
    # Relationships
    ship_category = db.relationship("ShipCategory", backref="documents")
    shipment_type = db.relationship("ShipmentType", backref="category_documents")

    def __repr__(self):
        return f"<ShipCatDocument {self.description}>"


class ShipDocumentEntryMaster(db.Model):
    """Model for ship document entry master."""

    __tablename__ = "ship_document_entry_master"

    id = db.Column(db.Integer, primary_key=True)
    shipTypeid = db.Column(
        db.Integer, db.ForeignKey("shipment_type.id"), nullable=False
    )
    docCode = db.Column(db.String(50), nullable=True)  # From shipment_type.docCode
    docnum = db.Column(db.Integer, nullable=False)  # lastDocNumber + 1
    docserial = db.Column(db.String(100), nullable=False)  # Combined docCode & docnum
    dateCreated = db.Column(db.DateTime, default=datetime.now)
    dealineDate = db.Column(db.Date, nullable=True)
    docStatusID = db.Column(
        db.Integer, db.ForeignKey("document_status.docStatusID"), nullable=False
    )
    custComment = db.Column(db.String(255), nullable=True)
    cusOriginalReady = db.Column(db.String(10), nullable=True)  # Yes/No dropdown
    shipCategory = db.Column(
        db.Integer, db.ForeignKey("ship_category.id"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=True)
    docLevel = db.Column(db.Integer, nullable=False, default=0)  # Document level field
    dateSubmitted = db.Column(db.DateTime)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"))
    selected_workflow_id = db.Column(db.Integer, db.ForeignKey('container_deposit_workflows.id'), nullable=True)
    assigned_clearing_company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=True)

    # Relationships
    shipment_type = db.relationship("ShipmentType", backref="document_entries")
    document_status = db.relationship("DocumentStatus", backref="document_entries")
    ship_category_rel = db.relationship("ShipCategory", backref="document_entries")
    user = db.relationship("User", foreign_keys=[user_id], backref="document_entries")
    customer = db.relationship("Customer", backref="document_entries")
    company = db.relationship("CompanyInfo", foreign_keys=[company_id], backref="document_entry")
    selected_workflow = db.relationship('ContainerDepositWorkflow', backref='entries')
    assigned_clearing_company = db.relationship('CompanyInfo', foreign_keys=[assigned_clearing_company_id], backref='assigned_clearing_entries')


    def __repr__(self):
        return f"<ShipDocumentEntryMaster {self.docserial}>"
    
    def get_resubmission_stats(self):
        """
        Get statistics about rejected and resubmitted documents
        Returns a dictionary with resubmission information
        """
        from sqlalchemy import and_, func
        
        # Get all attachments for this entry
        attachments = ShipDocumentEntryAttachment.query.filter_by(
            shipDocEntryMasterID=self.id
        ).all()
        
        # Count rejected documents (those that have been explicitly rejected)
        rejected_docs = [doc for doc in attachments if doc.docAccepted == 'rejected']
        rejected_count = len(rejected_docs)
        
        if rejected_count == 0:
            return {
                'has_resubmissions': False,
                'rejected_count': 0,
                'resubmitted_count': 0,
                'pending_resubmissions': 0
            }
        
        # Get rejected document IDs for history lookup
        rejected_doc_ids = [doc.id for doc in rejected_docs]
        
        # Count how many of the rejected documents have been resubmitted
        # A document is considered resubmitted if there's a history entry with action='resubmitted'
        # OR if the document was rejected but now has docAccepted=None (pending review after resubmission)
        resubmitted_count = 0
        
        for doc in rejected_docs:
            # Check if this document has a resubmission history
            has_resubmission_history = ShipDocumentHistory.query.filter_by(
                attachment_id=doc.id,
                action='resubmitted'
            ).first() is not None
            
            # OR check if the document was rejected but is now pending (likely resubmitted)
            is_pending_after_rejection = (
                doc.docAccepted is None and 
                doc.docAccepteDate is not None  # Had been processed before
            )
            
            if has_resubmission_history or is_pending_after_rejection:
                resubmitted_count += 1
        
        return {
            'has_resubmissions': resubmitted_count > 0,
            'rejected_count': rejected_count,
            'resubmitted_count': resubmitted_count,
            'pending_resubmissions': rejected_count - resubmitted_count
        }




class ShipDocumentEntryAttachment(db.Model):
    __tablename__ = "ship_document_entry_attachement"

    id = db.Column(db.Integer, primary_key=True)
    shipDocEntryMasterID = db.Column(
        db.Integer, db.ForeignKey("ship_document_entry_master.id"), nullable=False
    )
    description = db.Column(db.String(255), nullable=False)
    isMandatory = db.Column(db.Integer, nullable=False)
    attachement_path = db.Column(db.String(255), nullable=False)
    note = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    docAccepted = db.Column(db.String(10))
    docAccepteDate = db.Column(db.Date)
    docAccepteComments = db.Column(db.String(255))
    docAccepteUserID = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)
    expiry_date = db.Column(db.Date)
    ai_validated = db.Column(db.Integer)
    validation_results = db.Column(db.Text)  # Store full JSON results
    extracted_content = db.Column(db.Text) 
    validation_percentage = db.Column(db.Float, default=0)  # Store validation score
    document_similarity_percentage = db.Column(db.Float, default=0)  # New column for document similarity percentage
    similarity_message = db.Column(db.String(500)) 
    ship_category_id = db.Column(db.Integer, db.ForeignKey("ship_category.id"))
    ship_cat_document_id = db.Column(db.Integer, db.ForeignKey("ship_cat_document.id"))


    # Relationships
    master_entry = db.relationship("ShipDocumentEntryMaster", backref="attachments")
    user = db.relationship(
        "User", foreign_keys=[user_id], backref="document_attachments"
    )
    customer = db.relationship("Customer", backref="document_attachments")
    accepte_user = db.relationship(
        "User", foreign_keys=[docAccepteUserID], backref="accepted_documents"
    )

    ship_category = db.relationship("ShipCategory", backref="document_attachments")
    ship_cat_document = db.relationship("ShipCatDocument", backref="document_attachments")


    def __repr__(self):
        return f"<ShipDocumentEntryAttachment {self.id}>"


class ChatMessage(db.Model):
    """Model for chat messages"""

    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey("chat_threads.id"), nullable=False)
    reference_id = db.Column(db.Integer, nullable=False)
    module_name = db.Column(db.String(50), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    message = db.Column(db.Text)
    message_type = db.Column(db.String(20), default="text")  # text, voice, document
    parent_message_id = db.Column(
        db.Integer, db.ForeignKey("chat_messages.id"), nullable=True
    )
    created_at = db.Column(db.DateTime, default=datetime.now)
    is_read = db.Column(db.Boolean, default=False)
    sender_role = db.Column(db.String(50), nullable=True)  # 'user', 'customer'
    recipient_role = db.Column(db.String(50), nullable=True)  # 'user', 'customer'
    # Relationships
    sender = db.relationship("User", foreign_keys=[sender_id])
    thread = db.relationship("ChatThread", back_populates="messages")
    attachments = db.relationship(
        "ChatAttachment", back_populates="message", cascade="all, delete-orphan"
    )
    parent_message = db.relationship("ChatMessage", remote_side=[id], backref="replies")


class ChatThread(db.Model):
    """Model for chat threads"""

    __tablename__ = "chat_threads"

    id = db.Column(db.Integer, primary_key=True)
    module_name = db.Column(db.String(50), nullable=False)  # e.g., 'sea_import'
    reference_id = db.Column(db.Integer, nullable=False)  # e.g., entry_id
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(
        db.DateTime, default=datetime.now, onupdate=datetime.now
    )
    sender_role = db.Column(db.String(50))  # 'company', 'customer'
    recipient_role = db.Column(db.String(50))  # 'company', 'customer'
    company_roles = db.Column(db.String(255))  # Store as JSON: ['user', 'base_user']
    customer_role = db.Column(db.String(50))   # Always 'customer'

    # Relationships
    messages = db.relationship(
        "ChatMessage", back_populates="thread", cascade="all, delete-orphan"
    )
    participants = db.relationship(
        "ChatParticipant", back_populates="thread", cascade="all, delete-orphan"
    )


class ChatParticipant(db.Model):
    """Model for chat thread participants"""

    __tablename__ = "chat_participants"

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey("chat_threads.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.now)
    last_read_at = db.Column(db.DateTime, default=datetime.now)

    # Relationships
    thread = db.relationship("ChatThread", back_populates="participants")
    user = db.relationship("User")


class ChatAttachment(db.Model):
    """Model for chat message attachments"""

    __tablename__ = "chat_attachments"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(
        db.Integer, db.ForeignKey("chat_messages.id"), nullable=False
    )
    file_type = db.Column(db.String(20), nullable=False)  # document, voice, image
    file_path = db.Column(db.String(255), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Relationships
    message = db.relationship("ChatMessage", back_populates="attachments")


class Order(db.Model):
    __tablename__ = "order"
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    order_date = db.Column(db.DateTime, nullable=False, default=datetime.now)
    status = db.Column(db.String(50), nullable=False, default="Pending")
    total_amount = db.Column(db.Float, nullable=False, default=0.0)
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    # Relationships
    customer = db.relationship("Customer", backref="orders")
    creator = db.relationship("User", backref="created_orders")
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")
    documents = db.relationship(
        "OrderDocument", backref="order", cascade="all, delete-orphan"
    )


class OrderItem(db.Model):
    __tablename__ = "order_item"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)


class OrderDocument(db.Model):
    __tablename__ = "order_document"
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    document_name = db.Column(db.String(100), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    # Relationships
    uploader = db.relationship("User", backref="uploaded_order_documents")


class ShipDocumentHistory(db.Model):
    __tablename__ = "ship_document_history"

    id = db.Column(db.Integer, primary_key=True)
    attachment_id = db.Column(
        db.Integer, db.ForeignKey("ship_document_entry_attachement.id"), nullable=False
    )
    shipDocEntryMasterID = db.Column(
        db.Integer, db.ForeignKey("ship_document_entry_master.id"), nullable=False
    )
    description = db.Column(db.String(255), nullable=False)
    document_path = db.Column(db.String(255), nullable=False)  # S3 path to the document
    action = db.Column(db.String(20), nullable=False)  # 'accepted', 'rejected', 'uploaded'
    note = db.Column(db.String(255))
    action_comments = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)


class OrderShipment(db.Model):
    __tablename__ = "order_shipment"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ship_doc_entry_id = db.Column(db.Integer, db.ForeignKey("ship_document_entry_master.id"), nullable=False)
    branch_id = db.Column(db.Integer)
    import_type = db.Column(db.String(50))
    import_id = db.Column(db.String(50))
    shipment_deadline = db.Column(db.Date)
    bl_no = db.Column(db.String(100))
    license_number = db.Column(db.String(100))
    primary_job_yn = db.Column(db.String(5))
    primary_job = db.Column(db.String(100))
    shipment_type_id = db.Column(db.Integer)
    sub_type_id = db.Column(db.Integer)
    customer_category_id = db.Column(db.Integer)
    business_type_id = db.Column(db.Integer)
    customer_id = db.Column(db.Integer)
    billing_party_id = db.Column(db.Integer)
    clearing_agent = db.Column(db.String(200))
    contact_person = db.Column(db.String(200))
    sales_person_id = db.Column(db.Integer)
    cs_executive_id = db.Column(db.Integer)
    wharf_clerk_id = db.Column(db.Integer)
    po_no = db.Column(db.String(100))
    invoice_no = db.Column(db.String(100))
    customer_ref_no = db.Column(db.String(100))
    customs_dti_no = db.Column(db.String(100))
    mbl_number = db.Column(db.String(100))
    vessel = db.Column(db.String(200))
    voyage = db.Column(db.String(100))
    eta = db.Column(db.DateTime)
    shipper = db.Column(db.String(200))
    port_of_loading = db.Column(db.String(200))
    port_of_discharge = db.Column(db.String(200))
    job_type = db.Column(db.Integer, db.ForeignKey('os_job_type.id'), nullable=True)  # Now an integer FK
    fcl_gate_out_date = db.Column(db.Date)
    pod_datetime = db.Column(db.DateTime)
    no_of_packages = db.Column(db.Integer)
    package_type = db.Column(db.String(100))
    cbm = db.Column(db.Float)
    gross_weight = db.Column(db.Float)
    cargo_description = db.Column(db.Text)
    liner = db.Column(db.String(200))
    entrepot = db.Column(db.String(200))
    job_currency = db.Column(db.String(5))
    ex_rating_buying = db.Column(db.Float)
    ex_rating_selling = db.Column(db.Float)
    remarks = db.Column(db.Text)
    onhold_yn = db.Column(db.String(5))
    onhold_reason = db.Column(db.Text)
    cleared_date = db.Column(db.Date)
    estimated_job_closing_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime)
    created_by = db.Column(db.Integer)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    is_demurrage = db.Column(db.Boolean, default=False)
    demurrage_from = db.Column(db.Date, nullable=True)

    job_type_rel = db.relationship('OsJobType', backref='shipments')



class ShipCatDocumentAICheck(db.Model):
    """Model for AI Check Fields for Ship Category Documents"""

    __tablename__ = "ship_cat_document_ai_check"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    shipment_type_id = db.Column(db.Integer, db.ForeignKey("shipment_type.id"), nullable=False)
    ship_category_id = db.Column(db.Integer, db.ForeignKey("ship_category.id"), nullable=False)
    ship_cat_document_id = db.Column(db.Integer, db.ForeignKey("ship_cat_document.id"), nullable=False)
    document_description = db.Column(db.String(255), nullable=False)
    field_name = db.Column(db.String(255), nullable=False)
    condition = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(
        db.DateTime, default=datetime.now, onupdate=datetime.now
    )

    # Relationships
    company = db.relationship("CompanyInfo")
    shipment_type = db.relationship("ShipmentType")
    ship_category = db.relationship("ShipCategory")
    ship_cat_document = db.relationship("ShipCatDocument")

    def __repr__(self):
        return f"<ShipCatDocumentAICheck {self.field_name} - {self.condition}>"


class ImportContainer(db.Model):
    """Model for import containers associated with shipments."""
    
    __tablename__ = "import_container"

    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("ship_document_entry_master.id"), nullable=False)
    container_number = db.Column(db.String(50), nullable=False)
    container_size_id = db.Column(db.Integer, db.ForeignKey("os_container_size.id"), nullable=True)
    container_type_id = db.Column(db.Integer, db.ForeignKey("os_container_type.id"), nullable=True)
    remarks = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationship
    shipment = db.relationship("ShipDocumentEntryMaster", backref=db.backref("import_containers", cascade="all, delete-orphan"))
    container_size = db.relationship("OsContainerSize", backref="import_containers")
    container_type = db.relationship("OsContainerType", backref="import_containers")

    @property
    def size_name(self):
        return self.container_size.name if self.container_size else ""
    
    @property
    def type_name(self):
        return self.container_type.name if self.container_type else ""
    
    # Combined property for display (e.g., "20ft GP")
    @property
    def size_type(self):
        size = self.container_size.name if self.container_size else ""
        type_name = self.container_type.name if self.container_type else ""
        return f"{size} {type_name}".strip()

    def __repr__(self):
        return f"<ImportContainer {self.container_number}>"


class ExportContainer(db.Model):
    """Model for export containers associated with shipments."""
    
    __tablename__ = "export_container"

    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("ship_document_entry_master.id"), nullable=False)
    container_number = db.Column(db.String(50), nullable=False)
    container_size = db.Column(db.String(10), nullable=False)  # '20', '40'
    container_type = db.Column(db.String(10), nullable=False)  # 'GP', 'HC', 'RF', 'OT'
    gross_weight = db.Column(db.Float, nullable=True)
    is_dangerous_goods = db.Column(db.String(1), default='N')  # 'Y' or 'N'
    remarks = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationship
    shipment = db.relationship("ShipDocumentEntryMaster", backref=db.backref("export_containers", cascade="all, delete-orphan"))
    
    def __repr__(self):
        return f"<ExportContainer {self.container_number}>"



class ShipDocumentEntryDocument(db.Model):
    """Documents attached to ShipDocumentEntryMaster records."""
    
    __tablename__ = "ship_document_entry_documents"

    id = db.Column(db.Integer, primary_key=True)
    ship_doc_entry_id = db.Column(db.Integer, db.ForeignKey("ship_document_entry_master.id"), nullable=False)
    document_name = db.Column(db.String(255), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)  # invoice, bill-of-lading, packing-list, customs, certificate, other
    description = db.Column(db.Text, nullable=True)
    is_confidential = db.Column(db.Boolean, default=False)
    file_path = db.Column(db.String(512), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    ship_doc_entry = db.relationship("ShipDocumentEntryMaster", backref=db.backref("documents", cascade="all, delete-orphan"))
    uploaded_by_user = db.relationship("User", foreign_keys=[uploaded_by])
    
    def __repr__(self):
        return f"<ShipDocumentEntryDocument {self.document_name}>"


class IncomeExpense(db.Model):
    """Income or Expense classification for accounting purposes."""
    
    __tablename__ = "income_expense"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)  # income or expense
    description = db.Column(db.String(255), nullable=False)
    gl_code = db.Column(db.String(50), nullable=False)
    status = db.Column(db.Boolean, default=True)  # True for Active, False for Inactive
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_date = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    company = db.relationship("CompanyInfo", backref=db.backref("income_expenses", lazy=True))
    
    def __repr__(self):
        return f"<IncomeExpense {self.type}: {self.description}>"


class ShipmentExpense(db.Model):
    """Model for storing shipment-related expenses."""
    
    __tablename__ = "shipment_expenses"

    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("ship_document_entry_master.id"), nullable=False)
    expense_type_id = db.Column(db.Integer, db.ForeignKey("income_expense.id"), nullable=False)
    narration = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    margin = db.Column(db.Float, nullable=True, default=0)
    chargeable_amount = db.Column(db.Float, nullable=True) 
    payment_status = db.Column(db.Integer, default=0)
    currency_id = db.Column(db.Integer, db.ForeignKey("currencymaster.currencyID"), nullable=False)
    reference = db.Column(db.String(100), nullable=True)
    doc_date = db.Column(db.Date, nullable=True)
    document_number = db.Column(db.String(100), nullable=True)
    supplier_name = db.Column(db.String(255), nullable=True)
    value_amount = db.Column(db.Float, nullable=True)
    vat_amount = db.Column(db.Float, nullable=True)
    margin_amount = db.Column(db.Float, nullable=True)
    attachment_path = db.Column(db.String(255), nullable=True)
    visible_to_customer = db.Column(db.Boolean, default=False)
    attachment_visible_to_customer = db.Column(db.Boolean, default=False)  # New field for attachment visibility
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    charged_amount = db.Column(db.Float, nullable=False, default=0)
    balance_amount = db.Column(db.Float, nullable=True)

    # Relationships
    shipment = db.relationship("ShipDocumentEntryMaster", backref="expenses")
    expense_type = db.relationship("IncomeExpense", backref="shipment_expenses")
    currency = db.relationship("CurrencyMaster", backref="shipment_expenses")
    creator = db.relationship("User", backref="created_shipment_expenses")
    
    def __repr__(self):
        return f"<ShipmentExpense {self.id}: {self.amount} for shipment {self.shipment_id}>"
    
    @property
    def formatted_amount(self):
        """Return formatted amount with currency symbol."""
        if self.currency:
            return f"{self.currency.CurrencyCode} {self.amount:,.2f}"
        return f"{self.amount:,.2f}"
    
    @property
    def formatted_vat_amount(self):
        """Return formatted VAT amount with currency symbol, safely handling None."""
        if self.vat_amount is not None:
            if self.currency:
                return f"{self.currency.CurrencyCode} {self.vat_amount:,.2f}"
            return f"{self.vat_amount:,.2f}"
        return "-"
    
    @property
    def formatted_margin_amount(self):
        """Return formatted VAT amount with currency symbol, safely handling None."""
        if self.margin_amount is not None:
            if self.currency:
                return f"{self.currency.CurrencyCode} {self.margin_amount:,.2f}"
            return f"{self.margin_amount:,.2f}"
        return "-"
    

    
    @property
    def formatted_value_amount(self):
        """Return formatted value amount with currency symbol, safely handling None."""
        if self.currency and self.value_amount is not None:
            return f"{self.currency.CurrencyCode} {self.value_amount:,.2f}"
        elif self.value_amount is not None:
            return f"{self.value_amount:,.2f}"
        return "-"

    @property
    def is_fully_settled(self):
        """Check if the expense is fully settled."""
        if self.balance_amount is None:
            return False
        return self.balance_amount <= 0
    
    @property
    def expense_description(self):
        """Return expense type description."""
        if self.expense_type:
            return self.expense_type.description
        return "Unknown"
    
    @property
    def formatted_chargeable_amount(self):
        """Return formatted chargeable amount with currency symbol."""
        if self.currency and self.chargeable_amount:
            return f"{self.currency.CurrencyCode} {self.chargeable_amount:,.2f}"
        return f"{self.chargeable_amount:,.2f}" if self.chargeable_amount else "-"

    @property
    def formatted_charged_amount(self):
        """Return formatted chargeable amount with currency symbol."""
        if self.currency and self.charged_amount:
            return f"{self.currency.CurrencyCode} {self.charged_amount:,.2f}"
        return f"{self.charged_amount:,.2f}" if self.charged_amount else "-"


    @property
    def formatted_balance_amount(self):
        """Return formatted chargeable amount with currency symbol."""
        if self.currency and self.balance_amount:
            return f"{self.currency.CurrencyCode} {self.balance_amount:,.2f}"
        return f"{self.balance_amount:,.2f}" if self.balance_amount else "-"




class InvoiceHeader(db.Model):
    """Model for invoice headers."""
    
    __tablename__ = "invoice_headers"

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(20), nullable=False)
    invoice_date = db.Column(db.Date, nullable=False, default=datetime.now().date)
    narration = db.Column(db.Text, nullable=True)
    ship_doc_entry_id = db.Column(db.Integer, db.ForeignKey("ship_document_entry_master.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    payment_status = db.Column(db.Integer, default=0)
    total = db.Column(db.Float, nullable=False, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    submitted = db.Column(db.Boolean, default=False, nullable=False)

    # Relationships
    ship_doc_entry = db.relationship("ShipDocumentEntryMaster", backref="invoices")
    customer = db.relationship("Customer", backref="invoices")
    creator = db.relationship("User", backref="created_invoices")
    details = db.relationship("InvoiceDetail", backref="invoice_header", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<InvoiceHeader {self.invoice_number}: {self.total}>"
    
    @classmethod
    def generate_invoice_number(cls, company_id):
        """Generate a new unique invoice number for a company."""
        # Get the highest invoice number for this company
        last_invoice = cls.query.filter_by(company_id=company_id).order_by(cls.id.desc()).first()
        
        if not last_invoice:
            # First invoice for this company
            return "INV001"
        
        # Extract the numeric part from last invoice number
        last_num = int(last_invoice.invoice_number.replace("INV", ""))
        new_num = last_num + 1
        
        # Format the number with leading zeros
        return f"INV{new_num:03d}"


class InvoiceDetail(db.Model):
    """Model for invoice details linking to expenses or rate cards."""
    
    __tablename__ = "invoice_details"

    id = db.Column(db.Integer, primary_key=True)
    invoice_header_id = db.Column(db.Integer, db.ForeignKey("invoice_headers.id"), nullable=False)
    expense_id = db.Column(db.Integer, db.ForeignKey("shipment_expenses.id"), nullable=True)  # Make nullable
    rate_card_id = db.Column(db.Integer, db.ForeignKey("rate_card.id"), nullable=True)  # Add rate_card_id
    description = db.Column(db.Text, nullable=True)
    original_amount = db.Column(db.Float, nullable=False)
    margin = db.Column(db.Float, nullable=True, default=0)
    original_chargeable_amount = db.Column(db.Float, nullable=True)
    final_amount = db.Column(db.Float, nullable=False)
    item_type = db.Column(db.String(20), nullable=False, default='expense')  # Add item type ('expense' or 'rate_card')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    settlement_id = db.Column(db.Integer, db.ForeignKey("expense_settlements.id"), nullable=True)
    charged_amount_before_vat = db.Column(db.Float, nullable=True)  # Amount before VAT
    vat_percentage = db.Column(db.Float, nullable=True, default=0)  # VAT percentage (e.g., 18.00 for 18%)
    vat_amount = db.Column(db.Float, nullable=True, default=0) # Calculated VAT amount
    # Relationships
    expense = db.relationship("ShipmentExpense", backref="invoice_details")
    rate_card = db.relationship("RateCard", backref="invoice_details")  # Add relationship to RateCard
    settlement = db.relationship("ExpenseSettlement", backref="invoice_detail", uselist=False)
    
    def __repr__(self):
        return f"<InvoiceDetail {self.id}: {self.final_amount}>"

    @property
    def formatted_vat_amount(self):
        """Return formatted VAT amount."""
        if self.vat_amount:
            # You can access currency through expense or rate_card relationships
            return f"{self.vat_amount:,.2f}"
        return "0.00"
    
    @property
    def formatted_charged_before_vat(self):
        """Return formatted charged amount before VAT."""
        if self.charged_amount_before_vat:
            return f"{self.charged_amount_before_vat:,.2f}"
        return "0.00"

class ExpenseSettlement(db.Model):
    """Track partial settlements of expenses in invoices."""
    
    __tablename__ = "expense_settlements"

    id = db.Column(db.Integer, primary_key=True)
    expense_id = db.Column(db.Integer, db.ForeignKey("shipment_expenses.id"), nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice_headers.id"), nullable=False)
    shipment_id = db.Column(db.Integer, db.ForeignKey("ship_document_entry_master.id"), nullable=False)
    amount_charged = db.Column(db.Float, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    expense = db.relationship("ShipmentExpense", backref="settlements")
    invoice = db.relationship("InvoiceHeader", backref="expense_settlements")
    creator = db.relationship("User", backref="created_settlements")
    shipment = db.relationship("ShipDocumentEntryMaster", backref="expense_settlements")
    
    def __repr__(self):
        return f"<ExpenseSettlement {self.id}: {self.amount_charged} from expense {self.expense_id} in invoice {self.invoice_id}>"



class RateCard(db.Model):
    __tablename__ = "rate_card"
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    income_id = db.Column(db.Integer, db.ForeignKey("income_expense.id"), nullable=False)
    currency_id = db.Column(db.Integer, db.ForeignKey("currencymaster.currencyID"), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    customer = db.relationship("Customer", backref=db.backref("rate_cards", lazy=True))
    company = db.relationship("CompanyInfo")
    income = db.relationship("IncomeExpense")
    currency = db.relationship("CurrencyMaster")
    
    def __repr__(self):
        return f"<RateCard {self.customer.customer_name}: {self.income.description} - {self.amount} {self.currency.code}>"


class EntryAssignmentHistory(db.Model):
    __tablename__ = "entry_assignment_history"

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey("ship_document_entry_master.id"), nullable=False)
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    company_id = db.Column(db.Integer, nullable=False)
    assigned_date = db.Column(db.DateTime, default=datetime.utcnow)
    till_date = db.Column(db.DateTime, nullable=True)
    currently_assigned = db.Column(db.Boolean, default=True)

    assigned_to = db.relationship("User", foreign_keys=[assigned_to_user_id])



class ContainerDocument(db.Model):
    __tablename__ = 'container_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    document_code = db.Column(db.String(50), nullable=False)
    document_name = db.Column(db.String(200), nullable=False)
    sample_file_path = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    company_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('document_code', 'company_id', name='unique_document_code_per_company'),)
    
    def __repr__(self):
        return f'<ContainerDocument {self.document_name}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'document_code': self.document_code,
            'document_name': self.document_name,
            'sample_file_path': self.sample_file_path,
            'is_active': self.is_active,
            'company_id': self.company_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ContainerDepositWorkflow(db.Model):
    __tablename__ = 'container_deposit_workflows'
    
    id = db.Column(db.Integer, primary_key=True)
    workflow_code = db.Column(db.String(50), nullable=False)
    workflow_name = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    company_id = db.Column(db.Integer, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships - Updated to use steps instead of direct documents
    workflow_steps = db.relationship('ContainerDepositWorkflowStep', 
                                   backref='workflow', 
                                   cascade='all, delete-orphan',
                                   lazy='dynamic',
                                   order_by='ContainerDepositWorkflowStep.step_number')
    
    # Keep the old relationship for backward compatibility during migration
    workflow_documents = db.relationship('ContainerDepositWorkflowDocument', 
                                       backref='workflow', 
                                       cascade='all, delete-orphan',
                                       lazy='dynamic')
    
    __table_args__ = (db.UniqueConstraint('workflow_code', 'company_id', name='unique_workflow_code_per_company'),)
    
    def __repr__(self):
        return f'<ContainerDepositWorkflow {self.workflow_name}>'
    
    def get_documents(self):
        """Get all documents associated with this workflow across all steps"""
        documents = []
        for step in self.workflow_steps:
            for step_doc in step.step_documents:
                documents.append((step_doc, step_doc.document, step))
        return documents
    
    def get_steps_with_documents(self):
        """Get organized step and document data"""
        steps_data = []
        for step in self.workflow_steps.order_by(ContainerDepositWorkflowStep.step_number):
            step_data = {
                'step': step,
                'documents': []
            }
            for step_doc in step.step_documents:
                step_data['documents'].append({
                    'step_document': step_doc,
                    'document': step_doc.document
                })
            steps_data.append(step_data)
        return steps_data
    
    def get_total_documents_count(self):
        """Get total count of documents across all steps"""
        total = 0
        for step in self.workflow_steps:
            total += step.step_documents.count()
        return total

    def to_dict(self):
        return {
            'id': self.id,
            'workflow_code': self.workflow_code,
            'workflow_name': self.workflow_name,
            'is_active': self.is_active,
            'company_id': self.company_id,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'steps_count': self.workflow_steps.count()
        }


# NEW MODEL: Workflow Steps
class ContainerDepositWorkflowStep(db.Model):
    __tablename__ = 'container_deposit_workflow_steps'
    
    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer, db.ForeignKey('container_deposit_workflows.id'), nullable=False)
    step_number = db.Column(db.Integer, nullable=False)
    step_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    step_documents = db.relationship('ContainerDepositWorkflowStepDocument', 
                                   backref='step', 
                                   cascade='all, delete-orphan',
                                   lazy='dynamic')
    
    __table_args__ = (
        db.UniqueConstraint('workflow_id', 'step_number', name='unique_workflow_step_number'),
    )
    
    def __repr__(self):
        return f'<WorkflowStep {self.step_number}: {self.step_name}>'
    
    def get_mandatory_documents(self):
        """Get all mandatory documents for this step"""
        return self.step_documents.filter_by(is_mandatory=True).all()
    
    def get_optional_documents(self):
        """Get all optional documents for this step"""
        return self.step_documents.filter_by(is_mandatory=False).all()
    
    def to_dict(self):
        return {
            'id': self.id,
            'workflow_id': self.workflow_id,
            'step_number': self.step_number,
            'step_name': self.step_name,
            'description': self.description,
            'is_active': self.is_active,
            'documents_count': self.step_documents.count(),
            'mandatory_count': self.step_documents.filter_by(is_mandatory=True).count(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# NEW MODEL: Step Documents (replaces the old workflow documents)
class ContainerDepositWorkflowStepDocument(db.Model):
    __tablename__ = 'container_deposit_workflow_step_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    step_id = db.Column(db.Integer, db.ForeignKey('container_deposit_workflow_steps.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('container_documents.id'), nullable=False)
    is_mandatory = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    document = db.relationship('ContainerDocument', backref='step_mappings')
    
    __table_args__ = (
        db.UniqueConstraint('step_id', 'document_id', name='unique_step_document'),
    )
    
    def __repr__(self):
        return f'<StepDocument S:{self.step_id} D:{self.document_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'step_id': self.step_id,
            'document_id': self.document_id,
            'is_mandatory': self.is_mandatory,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# KEEP OLD MODEL for backward compatibility during migration
class ContainerDepositWorkflowDocument(db.Model):
    __tablename__ = 'container_deposit_workflow_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer, db.ForeignKey('container_deposit_workflows.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('container_documents.id'), nullable=False)
    is_mandatory = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    document = db.relationship('ContainerDocument', backref='workflow_mappings_old')
    
    __table_args__ = (db.UniqueConstraint('workflow_id', 'document_id', name='unique_workflow_document'),)
    
    def __repr__(self):
        return f'<WorkflowDocument W:{self.workflow_id} D:{self.document_id}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'workflow_id': self.workflow_id,
            'document_id': self.document_id,
            'is_mandatory': self.is_mandatory,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# UPDATED MODEL: Container Workflow Documents with step support
class ContainerWorkflowDocument(db.Model):
    """Model for storing documents uploaded against container workflow steps."""
    
    __tablename__ = 'container_workflow_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, nullable=False)
    entry_id = db.Column(db.Integer, db.ForeignKey('ship_document_entry_master.id'), nullable=False)
    container_id = db.Column(db.Integer, db.ForeignKey('import_container.id'), nullable=False)
    workflow_id = db.Column(db.Integer, db.ForeignKey('container_deposit_workflows.id'), nullable=False)
    step_id = db.Column(db.Integer, db.ForeignKey('container_deposit_workflow_steps.id'), nullable=True)  # NEW FIELD
    container_document_id = db.Column(db.Integer, db.ForeignKey('container_documents.id'), nullable=False)
    uploaded_by_id = db.Column(db.Integer, nullable=False)
    uploaded_file_path = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    narration = db.Column(db.Text, nullable=True)
    uploaded_time = db.Column(db.DateTime, default=datetime.utcnow)
    updated_time = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    entry = db.relationship('ShipDocumentEntryMaster', backref='container_workflow_documents')
    container = db.relationship('ImportContainer', backref='workflow_documents')
    workflow = db.relationship('ContainerDepositWorkflow', backref='uploaded_documents')
    step = db.relationship('ContainerDepositWorkflowStep', backref='uploaded_documents')  # NEW RELATIONSHIP
    container_document = db.relationship('ContainerDocument', backref='uploaded_files')
    
    def __repr__(self):
        return f'<ContainerWorkflowDocument {self.original_filename}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'company_id': self.company_id,
            'entry_id': self.entry_id,
            'container_id': self.container_id,
            'workflow_id': self.workflow_id,
            'step_id': self.step_id,  # NEW FIELD
            'container_document_id': self.container_document_id,
            'uploaded_by_id': self.uploaded_by_id,
            'uploaded_file_path': self.uploaded_file_path,
            'original_filename': self.original_filename,
            'narration': self.narration,
            'uploaded_time': self.uploaded_time.isoformat() if self.uploaded_time else None,
            'updated_time': self.updated_time.isoformat() if self.updated_time else None
        }

class ContainerStepCompletion(db.Model):
    """Track manual completion of container workflow steps"""
    __tablename__ = 'container_step_completions'
    
    id = db.Column(db.Integer, primary_key=True)
    container_id = db.Column(db.Integer, db.ForeignKey('import_container.id'), nullable=False)
    step_id = db.Column(db.Integer, db.ForeignKey('container_deposit_workflow_steps.id'), nullable=False)
    completed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    completion_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    container = db.relationship('ImportContainer', backref='step_completions')
    step = db.relationship('ContainerDepositWorkflowStep', backref='completions')
    completed_by = db.relationship('User', backref='completed_steps')
    
    def __repr__(self):
        return f'<ContainerStepCompletion {self.container_id}-{self.step_id}>'


class EntryClearingAgentHistory(db.Model):
    __tablename__ = 'entry_clearing_agent_history'
    
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('ship_document_entry_master.id'), nullable=False)
    assigned_to_clearing_agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    assigned_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    till_date = db.Column(db.DateTime, nullable=True)
    currently_assigned = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relationships
    entry = db.relationship('ShipDocumentEntryMaster', backref='clearing_agent_assignments')
    clearing_agent = db.relationship('User', foreign_keys=[assigned_to_clearing_agent_id])
    company = db.relationship('CompanyInfo')
    
    def __repr__(self):
        return f'<EntryClearingAgentHistory {self.id}: Entry {self.entry_id} -> Agent {self.assigned_to_clearing_agent_id}>'

class EntryClearingCompanyHistory(db.Model):
    __tablename__ = 'entry_clearing_company_history'
    
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('ship_document_entry_master.id'), nullable=False)
    assigned_to_clearing_company_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    assigned_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    till_date = db.Column(db.DateTime, nullable=True)
    currently_assigned = db.Column(db.Boolean, default=True, nullable=False)
    
    # Relationships
    entry = db.relationship('ShipDocumentEntryMaster', backref='clearing_company_assignments')
    clearing_company_user = db.relationship('User', foreign_keys=[assigned_to_clearing_company_id])
    company = db.relationship('CompanyInfo')
    
    def __repr__(self):
        return f'<EntryClearingCompanyHistory {self.id}: Entry {self.entry_id} -> User {self.assigned_to_clearing_company_id}>'


class AgentAssignment(db.Model):
    __tablename__ = 'agent_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_agent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    assignment_date = db.Column(db.DateTime, default=datetime.now)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_user_id], backref='agent_assignments_made')
    assigned_agent = db.relationship('User', foreign_keys=[assigned_agent_id], backref='agent_assignments_received')
    company = db.relationship('CompanyInfo', backref='agent_assignments')
    
    def __repr__(self):
        return f"<AgentAssignment {self.id}: Agent {self.assigned_agent_id} assigned by {self.assigned_by_user_id}>"


# models.py - Add this model to your existing models file

class CompanyAssignment(db.Model):
    __tablename__ = 'company_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    assignment_date = db.Column(db.DateTime, default=datetime.now)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    assigned_by = db.relationship('User', foreign_keys=[assigned_by_user_id], backref='company_assignments_made')
    assigned_company = db.relationship('CompanyInfo', foreign_keys=[assigned_company_id], backref='company_assignments_received')
    company = db.relationship('CompanyInfo', foreign_keys=[company_id], backref='company_assignments')
    
    def __repr__(self):
        return f"<CompanyAssignment {self.id}: Company {self.assigned_company_id} assigned by {self.assigned_by_user_id}>"


class AttachmentType(db.Model):
    __tablename__ = 'attachment_types'
    
    id = db.Column(db.Integer, primary_key=True)
    attachment_code = db.Column(db.String(50), nullable=False)
    attachment_name = db.Column(db.String(100), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False, unique=True)  # One attachment type per role
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    role = db.relationship('Role', backref='attachment_type', uselist=False)
    documents = db.relationship('AttachmentDocument', backref='attachment_type', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<AttachmentType {self.attachment_name}>'


class AttachmentDocument(db.Model):
    __tablename__ = 'attachment_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    attachment_type_id = db.Column(db.Integer, db.ForeignKey('attachment_types.id'), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    is_mandatory = db.Column(db.Boolean, default=False)
    allow_multiple = db.Column(db.Boolean, default=False)
    sample_file_path = db.Column(db.String(500))  # S3 path for sample document
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f'<AttachmentDocument {self.description}>'


# models/customer_attachment.py

class CustomerAttachment(db.Model):
    __tablename__ = 'customer_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # From customer table
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Current user
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    
    # Document details
    file_path = db.Column(db.String(500), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    description = db.Column(db.Text, nullable=True)
    
    # Timestamps
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    customer = db.relationship('Customer', backref='attachments')
    uploader = db.relationship('User', foreign_keys=[uploaded_by], backref='uploaded_attachments_uploader')
    user = db.relationship('User', foreign_keys=[user_id], backref='customer_attachments')


class OsShipmentType(db.Model):
    __tablename__ = 'os_shipment_type'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

class OsSubType(db.Model):
    __tablename__ = 'os_sub_type'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

class OsCustomerCategory(db.Model):
    __tablename__ = 'os_customer_category'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

class OsBusinessType(db.Model):
    __tablename__ = 'os_business_type'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

class OsContainerSize(db.Model):
    __tablename__ = 'os_container_size'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

class OsContainerType(db.Model):
    __tablename__ = 'os_container_type'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

class OsJobType(db.Model):
    __tablename__ = 'os_job_type'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    

