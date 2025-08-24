from app import db
from datetime import datetime

class NonWorkingDay(db.Model):
    __tablename__ = 'non_working_days'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Date, nullable=False)
    type = db.Column(db.Enum('WEEKEND', 'PUBLIC_HOLIDAY'), nullable=False)
    country_id = db.Column(db.Integer, db.ForeignKey('countrymaster.countryID'), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, nullable=True)  # If you want company-specific holidays
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    country = db.relationship('CountryMaster', backref='non_working_days')

    __table_args__ = (db.UniqueConstraint('date', 'country_id', name='unique_date_country'),)

    def __repr__(self):
        return f"<NonWorkingDay {self.date} - {self.type}>"
    

class CompanyDemurrageConfig(db.Model):
    __tablename__ = 'company_demurrage_config'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    demurrage_days_threshold = db.Column(db.Integer, nullable=False)
    country_id = db.Column(db.Integer, db.ForeignKey('countrymaster.countryID'), nullable=False)
    exclude_weekends = db.Column(db.Boolean, default=True)
    exclude_holidays = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    country = db.relationship('CountryMaster', backref='demurrage_configs')

    def __repr__(self):
        return f"<CompanyDemurrageConfig {self.company_id} - {self.demurrage_days_threshold} days>"    



class DemurrageRateCard(db.Model):
    __tablename__ = "demurrage_rate_card"
    
    id = db.Column(db.Integer, primary_key=True)
    country_id = db.Column(db.Integer, db.ForeignKey("countrymaster.countryID"), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=True)
    rate_card_name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    
    # Rate Structure
    container_size_id = db.Column(db.Integer, db.ForeignKey("os_container_size.id"), nullable=False)
    container_type_id = db.Column(db.Integer, db.ForeignKey("os_container_type.id"), nullable=False)
    
    # Demurrage Reason Reference
    demurrage_reason_id = db.Column(db.Integer, db.ForeignKey("demurrage_reasons.id"), nullable=False)
    currency_id = db.Column(db.Integer, db.ForeignKey("currencymaster.currencyID"), nullable=False)
        
    
    port_code = db.Column(db.String(10), nullable=True)  # 'LKCMB' for Colombo, etc.
    is_active = db.Column(db.Boolean, default=True)
        
    # Authority and Approval
    set_by_authority = db.Column(db.String(100), nullable=False)  # 'SLPA', 'SHIPPING_LINE', 'TERMINAL', etc.
    approved_by = db.Column(db.String(255), nullable=True)
    approval_reference = db.Column(db.String(100), nullable=True)
    
    # Business Relationships
    
    # Audit Trail
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    
    # Relationships
    demurrage_reason = db.relationship("DemurrageReasons", backref="rate_cards")
    company = db.relationship("CompanyInfo", backref="demurrage_rate_cards")
    country = db.relationship("CountryMaster", backref="demurrage_rate_cards")
    currency = db.relationship("CurrencyMaster", backref="demurrage_rate_cards")
    container_size = db.relationship("OsContainerSize", backref="demurrage_rate_cards")
    container_type = db.relationship("OsContainerType", backref="demurrage_rate_cards")
    tiers = db.relationship("DemurrageRateCardTier", backref="rate_card", cascade="all, delete-orphan", order_by="DemurrageRateCardTier.tier_number")


class DemurrageRateCardTier(db.Model):
    __tablename__ = "demurrage_rate_card_tier"
    
    id = db.Column(db.Integer, primary_key=True)
    rate_card_id = db.Column(db.Integer, db.ForeignKey("demurrage_rate_card.id"), nullable=False)
    tier_number = db.Column(db.Integer, nullable=False)  # 1, 2, 3, etc.
    from_day = db.Column(db.Integer, nullable=False)     # Starting day (1, 4, 6, etc.)
    to_day = db.Column(db.Integer, nullable=True)        # Ending day (3, 5, 6, NULL for unlimited)
    rate_amount = db.Column(db.Float, nullable=False)    # Amount per day
    
    # Audit Trail
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<DemurrageRateCardTier {self.tier_number}: Days {self.from_day}-{self.to_day or '∞'} @ {self.rate_amount}>"
    
    @property
    def day_range_display(self):
        """Display day range in a user-friendly format"""
        if self.to_day:
            if self.from_day == self.to_day:
                return f"Day {self.from_day}"
            else:
                return f"Days {self.from_day}-{self.to_day}"
        else:
            return f"Days {self.from_day}+"


# Demurrage Reasons Master Table
class DemurrageReasons(db.Model):
    __tablename__ = "demurrage_reasons"
    
    id = db.Column(db.Integer, primary_key=True)
    reason_name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

# Shipment Demurrage Main Table  
class ShipmentDemurrage(db.Model):
    __tablename__ = "shipment_demurrage"
    
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("ship_document_entry_master.id"), nullable=False)
    container_id = db.Column(db.Integer, nullable=False)  # Will reference ImportContainer or ExportContainer
    container_type = db.Column(db.String(10), nullable=False)  # 'import' or 'export'
    demurrage_date = db.Column(db.Date, nullable=False)
    demurrage_from = db.Column(db.Date, nullable=False)  # NEW FIELD
    amount = db.Column(db.Float, nullable=False)
    currency_id = db.Column(db.Integer, db.ForeignKey("currencymaster.currencyID"), nullable=False)
    reason_id = db.Column(db.Integer, db.ForeignKey("demurrage_reasons.id"), nullable=False)
    rate_card_id = db.Column(db.Integer, db.ForeignKey("demurrage_rate_card.id"), nullable=True)  # NEW FIELD
    total_days = db.Column(db.Integer, nullable=False)  # NEW FIELD
    chargeable_days = db.Column(db.Integer, nullable=False)  # NEW FIELD
    excluded_days = db.Column(db.Integer, default=0)  # NEW FIELD
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    bearing_percentage = db.Column(db.Float, nullable=True)  # Percentage of demurrage bearing
    bearer_id = db.Column(db.Integer, db.ForeignKey("shipment_demurrage_bearer.id"), nullable=True)
    
    # Relationships
    shipment = db.relationship("ShipDocumentEntryMaster", backref="demurrage_records")
    currency = db.relationship("CurrencyMaster")
    reason = db.relationship("DemurrageReasons")
    creator = db.relationship("User")
    bearer = db.relationship("ShipmentDemurrageBearer")  # NEW RELATIONSHIP
    rate_card = db.relationship("DemurrageRateCard")  # NEW RELATIONSHIP
    calculation_details = db.relationship("DemurrageCalculationDetail", backref="demurrage_record", cascade="all, delete-orphan", lazy='dynamic')

class DemurrageCalculationDetail(db.Model):
    __tablename__ = "demurrage_calculation_detail"
    
    id = db.Column(db.Integer, primary_key=True)
    demurrage_id = db.Column(db.Integer, db.ForeignKey("shipment_demurrage.id"), nullable=False)
    tier_number = db.Column(db.Integer, nullable=False)
    tier_name = db.Column(db.String(100), nullable=True)  # e.g., "Tier 1", "Days 1-3"
    from_day = db.Column(db.Integer, nullable=False)
    to_day = db.Column(db.Integer, nullable=True)  # NULL for unlimited
    days_in_tier = db.Column(db.Integer, nullable=False)
    rate_per_day = db.Column(db.Float, nullable=False)
    tier_amount = db.Column(db.Float, nullable=False)
    day_range_display = db.Column(db.String(50), nullable=True)  # "Days 1-3", "Day 4", "Days 5+"
    
    # Date breakdown for this tier
    start_date = db.Column(db.Date, nullable=False)  # Actual date when this tier starts
    end_date = db.Column(db.Date, nullable=True)     # Actual date when this tier ends
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<DemurrageCalculationDetail Tier {self.tier_number}: {self.days_in_tier} days @ {self.rate_per_day}>"
    

# Add this new model to your models file
class ShipmentDemurrageBearer(db.Model):
    __tablename__ = "shipment_demurrage_bearer"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<ShipmentDemurrageBearer {self.name}>"
    

class ShipmentDemurrageAttachment(db.Model):
    __tablename__ = "shipment_demurrage_attachments"
    
    id = db.Column(db.Integer, primary_key=True)
    shipment_demurrage_id = db.Column(db.Integer, db.ForeignKey("shipment_demurrage.id"), nullable=False)
    attachment_path = db.Column(db.String(1000), nullable=False)
    date = db.Column(db.Date, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    file_name = db.Column(db.String(255), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    demurrage = db.relationship("ShipmentDemurrage", backref="attachments")
    uploader = db.relationship("User", backref="demurrage_attachments")
    
    def __repr__(self):
        return f'<ShipmentDemurrageAttachment {self.id}: {self.file_name}>'

