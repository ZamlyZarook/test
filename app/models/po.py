# models.py - Add these models to your existing models file
from app.extensions import db, bcrypt
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy.sql import func
from app.utils import get_sri_lanka_time
from decimal import Decimal



class POSupplier(db.Model):
    __tablename__ = 'po_suppliers'
    
    id = db.Column(db.Integer, primary_key=True)
    supplier_code = db.Column(db.String(50), nullable=False, index=True)
    supplier_name = db.Column(db.String(200), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    company = db.relationship('CompanyInfo', backref='po_suppliers')
    
    # Unique constraint for supplier_code per company
    __table_args__ = (db.UniqueConstraint('supplier_code', 'company_id', name='unique_supplier_per_company'),)

class POMaterial(db.Model):
    __tablename__ = 'po_materials'
    
    id = db.Column(db.Integer, primary_key=True)
    material_code = db.Column(db.String(50), nullable=False, index=True)
    material_name = db.Column(db.String(200), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    hs_code_id = db.Column(db.Integer, db.ForeignKey('hs_code.id'), nullable=True)

    # Relationships
    company = db.relationship('CompanyInfo', backref='po_materials')
    hs_code = db.relationship('HSCode', backref='materials')
    
    # Unique constraint for material_code per company
    __table_args__ = (db.UniqueConstraint('material_code', 'company_id', name='unique_material_per_company'),)

class POOrderUnit(db.Model):
    __tablename__ = 'po_order_units'
    
    id = db.Column(db.Integer, primary_key=True)
    order_unit = db.Column(db.String(10), nullable=False, unique=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class POHeader(db.Model):
    __tablename__ = 'po_headers'
    
    id = db.Column(db.Integer, primary_key=True)
    sysdocnum = db.Column(db.String(20), nullable=False, unique=True, index=True)
    po_number = db.Column(db.String(50), nullable=False, index=True)
    po_date = db.Column(db.Date, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('po_suppliers.id'), nullable=False)
    currency = db.Column(db.String(10), default='LKR')
    total_value = db.Column(db.Numeric(15, 2), default=0.00)
    inco_term = db.Column(db.String(50), nullable=True)
    payment_term = db.Column(db.String(1000), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    remarks = db.Column(db.Text, nullable=True)  # New field for remarks
    is_completed = db.Column(db.Boolean, default=False, nullable=False, index=True)  # NEW FIELD

    # Relationships
    supplier = db.relationship('POSupplier', backref='po_headers')
    company = db.relationship('CompanyInfo', backref='po_headers')
    creator = db.relationship('User', backref='created_po_headers')
    po_details = db.relationship('PODetail', backref='po_header', cascade='all, delete-orphan')
    
    # Unique constraint for po_number per company
    __table_args__ = (db.UniqueConstraint('po_number', 'company_id', name='unique_po_per_company'),)
    
    @staticmethod
    def generate_sysdocnum():
        """Generate next system document number"""
        last_po = POHeader.query.order_by(POHeader.sysdocnum.desc()).first()
        if last_po and last_po.sysdocnum.startswith('CHA'):
            try:
                last_num = int(last_po.sysdocnum[3:])
                return f"CHA{last_num + 1:04d}"
            except ValueError:
                pass
        return "CHA0001"
    
    def calculate_total_value(self):
        """Calculate and update the total value of the PO"""
        total = db.session.query(func.sum(PODetail.order_quantity * PODetail.net_price)).filter(
            PODetail.po_header_id == self.id
        ).scalar() or 0
        self.total_value = total
        return total
    
    def check_completion_status(self):
        """Check and update completion status based on PO details"""
        incomplete_items = PODetail.query.filter_by(
            po_header_id=self.id,
            is_completed=False
        ).count()
        
        if incomplete_items == 0:
            self.is_completed = True
            self.updated_at = datetime.utcnow()
        else:
            self.is_completed = False
        
        return self.is_completed
    
    def get_completion_summary(self):
        """Get completion summary for this PO"""
        total_items = PODetail.query.filter_by(po_header_id=self.id).count()
        completed_items = PODetail.query.filter_by(
            po_header_id=self.id,
            is_completed=True
        ).count()
        
        return {
            'total_items': total_items,
            'completed_items': completed_items,
            'pending_items': total_items - completed_items,
            'completion_percentage': (completed_items / total_items * 100) if total_items > 0 else 0
        }

class PODetail(db.Model):
    __tablename__ = 'po_details'
    
    id = db.Column(db.Integer, primary_key=True)
    po_header_id = db.Column(db.Integer, db.ForeignKey('po_headers.id'), nullable=False)
    po_number = db.Column(db.String(50), nullable=False, index=True)  # For reference
    sysdocnum = db.Column(db.String(20), nullable=False, index=True)  # For reference
    item_number = db.Column(db.Integer, nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('po_materials.id'), nullable=False)
    material_code = db.Column(db.String(50), nullable=False)  # For reference
    material_name = db.Column(db.String(200), nullable=False)  # For reference
    order_unit_id = db.Column(db.Integer, db.ForeignKey('po_order_units.id'), nullable=False)
    order_unit = db.Column(db.String(10), nullable=False)  # For reference
    order_quantity = db.Column(db.Numeric(15, 3), nullable=False)
    quantity_received = db.Column(db.Numeric(15, 3), default=0.000)
    quantity_pending = db.Column(db.Numeric(15, 3), nullable=False)
    delivery_date = db.Column(db.Date, nullable=True)
    net_price = db.Column(db.Numeric(15, 2), nullable=False)
    line_total = db.Column(db.Numeric(15, 2), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('po_suppliers.id'), nullable=False)
    supplier_code = db.Column(db.String(50), nullable=False)  # For reference
    supplier_name = db.Column(db.String(200), nullable=False)  # For reference
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # NEW FIELD
    is_completed = db.Column(db.Boolean, default=False, nullable=False, index=True)  # NEW FIELD
    date_delivered = db.Column(db.Date, nullable=True)  # NEW FIELD

    # Relationships
    material = db.relationship('POMaterial', backref='po_details')
    order_unit_rel = db.relationship('POOrderUnit', backref='po_details')
    supplier = db.relationship('POSupplier', backref='po_detail_suppliers')
    company = db.relationship('CompanyInfo', backref='po_details')
    
    def __init__(self, **kwargs):
        super(PODetail, self).__init__(**kwargs)
        # Calculate line total when creating
        if self.order_quantity and self.net_price:
            from decimal import Decimal
            self.line_total = Decimal(str(self.order_quantity)) * Decimal(str(self.net_price))

    def update_quantities(self, quantity_received=None, quantity_pending=None):
        """Update quantities and check completion status"""
        if quantity_received is not None:
            self.quantity_received = quantity_received
        
        if quantity_pending is not None:
            self.quantity_pending = quantity_pending
        
        # Auto-check completion based on quantities
        if self.quantity_received >= self.order_quantity:
            self.is_completed = True
        elif self.quantity_pending <= 0:
            self.is_completed = True
        else:
            self.is_completed = False
        
        self.updated_at = datetime.utcnow()
        return self.is_completed
    
    def get_status(self):
        """Get current status of this item"""
        if self.is_completed:
            return 'completed'
        elif not self.quantity_received or self.quantity_received == 0:
            return 'pending'
        elif self.quantity_received > 0 and self.quantity_received < self.order_quantity:
            return 'partial'
        else:
            return 'unknown'
    
    def get_completion_percentage(self):
        """Get completion percentage for this item"""
        if self.order_quantity == 0:
            return 0
        return (float(self.quantity_received) / float(self.order_quantity)) * 100
    
    @classmethod
    def get_items_by_po_and_status(cls, po_number, company_id, is_completed=None):
        """Get items by PO number and completion status"""
        query = cls.query.filter_by(
            po_number=po_number,
            company_id=company_id
        )
        
        if is_completed is not None:
            query = query.filter_by(is_completed=is_completed)
        
        return query.all()
    
    @classmethod
    def get_incomplete_items_by_company(cls, company_id):
        """Get all incomplete items for a company"""
        return cls.query.filter_by(
            company_id=company_id,
            is_completed=False
        ).all()
    
    @classmethod
    def mark_items_completed_by_po(cls, po_number, company_id, exclude_materials=None):
        """Mark items as completed for a specific PO, optionally excluding certain materials"""
        query = cls.query.filter_by(
            po_number=po_number,
            company_id=company_id,
            is_completed=False
        )
        
        if exclude_materials:
            query = query.filter(~cls.material_code.in_(exclude_materials))
        
        items = query.all()
        for item in items:
            item.is_completed = True
            item.updated_at = datetime.utcnow()
        
        return len(items)


class ShipmentItem(db.Model):
    __tablename__ = 'shipment_items'
    
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('ship_document_entry_master.id'), nullable=False)
    
    # Source tracking
    source_type = db.Column(db.String(20), nullable=False)  # 'manual' or 'po'
    po_detail_id = db.Column(db.Integer, db.ForeignKey('po_details.id'), nullable=True)
    po_header_id = db.Column(db.Integer, db.ForeignKey('po_headers.id'), nullable=True)
    po_number = db.Column(db.String(50), nullable=True)
    
    # Item details (either from PO or manual entry)
    material_code = db.Column(db.String(50), nullable=False)
    material_name = db.Column(db.String(200), nullable=False)
    order_unit = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Numeric(15, 3), nullable=False)
    net_price = db.Column(db.Numeric(15, 2), nullable=True)
    line_total = db.Column(db.Numeric(15, 2), nullable=True)
    
    # Additional fields for manual entry
    supplier_name = db.Column(db.String(200), nullable=True)
    delivery_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    
    # Metadata
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=get_sri_lanka_time)
    updated_at = db.Column(db.DateTime, default=get_sri_lanka_time, onupdate=get_sri_lanka_time)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    shipment = db.relationship('ShipDocumentEntryMaster', backref='shipment_items')
    po_detail = db.relationship('PODetail', backref='shipment_items')
    company = db.relationship('CompanyInfo', backref='shipment_items')
    creator = db.relationship('User', backref='created_shipment_items')
    po_header = db.relationship('POHeader', backref='shipment_items')

    def __init__(self, **kwargs):
        super(ShipmentItem, self).__init__(**kwargs)
        # Calculate line total when creating if both quantity and net_price are provided
        if self.quantity and self.net_price:
            self.line_total = Decimal(str(self.quantity)) * Decimal(str(self.net_price))
    
    def calculate_line_total(self):
        """Calculate and update line total"""
        if self.quantity and self.net_price:
            self.line_total = Decimal(str(self.quantity)) * Decimal(str(self.net_price))
        else:
            self.line_total = None
        return self.line_total
    
    def __repr__(self):
        return f'<ShipmentItem {self.material_code}: {self.quantity} {self.order_unit}>'

class MaterialHSDocuments(db.Model):
    __tablename__ = 'material_hs_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('po_materials.id'), nullable=False)
    hs_code_id = db.Column(db.Integer, db.ForeignKey('hs_code.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('hs_code_document.id'), nullable=False)
    file_path = db.Column(db.String(1000), nullable=False)
    file_name = db.Column(db.String(1000), nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)
    comment = db.Column(db.Text, nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    company_id = db.Column(db.Integer, db.ForeignKey('company_info.id'), nullable=False)
    
    # Relationships
    material = db.relationship('POMaterial', backref='hs_documents')
    hs_code = db.relationship('HSCode', backref='material_documents')
    document = db.relationship('HSCodeDocument', backref='material_uploads')
    uploader = db.relationship('User', backref='uploaded_material_docs')
    company = db.relationship('CompanyInfo', backref='material_hs_documents')

