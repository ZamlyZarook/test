from app.extensions import db
from datetime import datetime
import base64


class CompanyInfo(db.Model):
    __tablename__ = "company_info"
    __table_args__ = {"extend_existing": True}
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), nullable=False)
    legal_name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text)
    country = db.Column(db.Integer, db.ForeignKey("countrymaster.countryID"), nullable=False)
    email = db.Column(db.String(120), unique=True)
    website = db.Column(db.String(200))
    contact_num = db.Column(db.String(20))
    vat_identification_number = db.Column(db.String(50))
    company_logo = db.Column(db.LargeBinary)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(
        db.DateTime, default=datetime.now, onupdate=datetime.now
    )
    is_active = db.Column(db.Boolean, default=True)
    is_cha = db.Column(db.Boolean, default=False, nullable=False)  # New column: 1 for CHA, 0 for Company


    # Relationship with User model
    users = db.relationship("User", backref="company", lazy=True)
    country_info = db.relationship("CountryMaster", backref="company_info", lazy=True)

    @property
    def logo_base64(self):
        """Decode BLOB to base64 string for HTML display"""
        if self.company_logo:
            return base64.b64encode(self.company_logo).decode('utf-8')
        return None
    
    @property
    def logo_data_url(self):
        """Get data URL for direct HTML img src usage"""
        if self.company_logo:
            # Detect image type (you might want to store this separately)
            # For now, assuming PNG - you can enhance this
            return f"data:image/png;base64,{self.logo_base64}"
        return None
    
    