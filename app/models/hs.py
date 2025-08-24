from app import db
from datetime import datetime

class HSCodeCategory(db.Model):
    __tablename__ = 'hs_code_category'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(1000))

class HSCodeIssueBody(db.Model):
    __tablename__ = 'hs_code_issue_body'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    address = db.Column(db.String(256))
    contact_number = db.Column(db.String(64))
    email = db.Column(db.String(128))
    website = db.Column(db.String(128))


class HSDocumentCategory(db.Model):
    __tablename__ = 'hs_document_category'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(1000))
    issuing_body_id = db.Column(db.Integer, db.ForeignKey('hs_code_issue_body.id'), nullable=False)  # Add this line
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    issuing_body = db.relationship('HSCodeIssueBody', backref='document_categories')


class HSCode(db.Model):
    __tablename__ = 'hs_code'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('hs_code_category.id'))
    code = db.Column(db.String(64), nullable=False)
    description = db.Column(db.String(1000))
    category = db.relationship('HSCodeCategory', backref='hscodes')

class HSCodeDocument(db.Model):
    __tablename__ = 'hs_code_document'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    hscode_id = db.Column(db.Integer, db.ForeignKey('hs_code.id'))
    issuing_body_id = db.Column(db.Integer, db.ForeignKey('hs_code_issue_body.id'))
    document_category_id = db.Column(db.Integer, db.ForeignKey('hs_document_category.id'))
    description = db.Column(db.String(256))
    is_mandatory = db.Column(db.Boolean, default=False)
    sample_doc = db.Column(db.String(256))
    hscode = db.relationship('HSCode', backref=db.backref('documents', cascade="all, delete-orphan"))
    issuing_body = db.relationship('HSCodeIssueBody')
    document_category = db.relationship('HSDocumentCategory')

class HSCodeDocumentAttachment(db.Model):
    __tablename__ = 'hs_code_document_attachments'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    hs_code_document_id = db.Column(db.Integer, db.ForeignKey('hs_code_document.id'), nullable=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)
    file_type = db.Column(db.String(100))
    description = db.Column(db.Text)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    deleted_at = db.Column(db.DateTime)
    
    # Cloud storage fields
    cloud_provider = db.Column(db.String(50), nullable=True)
    cloud_file_id = db.Column(db.String(255), nullable=True)
    cloud_path = db.Column(db.String(255), nullable=True)
    
    # Relationships
    hs_code_document = db.relationship('HSCodeDocument', backref=db.backref('attachments', cascade="all, delete-orphan"))
    uploader = db.relationship('User', foreign_keys=[uploaded_by], backref='uploaded_hs_document_attachments')
    deleter = db.relationship('User', foreign_keys=[deleted_by], backref='deleted_hs_document_attachments')
