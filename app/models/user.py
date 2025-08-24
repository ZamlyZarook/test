from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import hmac
import hashlib
from app.models.task_management import Task, Issue
import base64


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(255))  # New field
    gender = db.Column(db.String(10))  # New field
    address = db.Column(db.Text)      # New field
    contact_number = db.Column(db.String(20))
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))  # New column for role relationship
    is_active = db.Column(db.Boolean, default=True)
    is_super_admin = db.Column(db.Integer, default=0)  # 0: Normal user, 1: Super Admin, 2: Runner, 3: Customer
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    company_id = db.Column(db.Integer, db.ForeignKey("company_info.id"))
    profile_picture = db.Column(db.LargeBinary)

    assigned_role = db.relationship("Role", foreign_keys=[role_id], backref="assigned_users")
    customer = db.relationship("Customer", backref="user", uselist=False)


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        try:
            # Try the original implementation first
            return check_password_hash(self.password_hash, password)
        except TypeError as e:
            # If we hit the digestmod error in Python 3.12
            if 'digestmod' in str(e):
                if self.password_hash.count('$') < 2:
                    return False
                    
                method, salt, hashval = self.password_hash.split('$', 2)
                
                # Handle the most common hash methods
                if method.startswith('pbkdf2:'):
                    # For pbkdf2 hashes, we need special handling
                    parts = method.split(':')
                    if len(parts) != 3:
                        return False
                    
                    _, algo, iterations = parts
                    iterations = int(iterations)
                    
                    # Get the hash algorithm
                    h_algo = getattr(hashlib, algo, None)
                    if not h_algo:
                        return False
                    
                    # Convert to bytes
                    password_bytes = password.encode('utf-8')
                    salt_bytes = salt.encode('utf-8')
                    
                    # Calculate pbkdf2 hash
                    dk = hashlib.pbkdf2_hmac(
                        algo, 
                        password_bytes, 
                        salt_bytes, 
                        iterations
                    )
                    
                    calculated_hash = dk.hex()
                    return hmac.compare_digest(calculated_hash, hashval)
                else:
                    # For simple hash methods like sha1, md5, etc.
                    h_algo = getattr(hashlib, method, None)
                    if not h_algo:
                        return False
                        
                    # Convert to bytes
                    password_bytes = password.encode('utf-8')
                    salt_bytes = salt.encode('utf-8')
                    
                    # Create hmac with proper digestmod
                    calculated_hash = hmac.new(salt_bytes, password_bytes, digestmod=h_algo).hexdigest()
                    return hmac.compare_digest(calculated_hash, hashval)
            else:
                # Re-raise if it's a different TypeError
                raise
            
    def __repr__(self):
        return f"<User {self.username}>"
    @property
    def profile_picture_base64(self):
        if self.profile_picture:
            return base64.b64encode(self.profile_picture).decode('utf-8')
        return None
    
    @property
    def is_admin(self):
        return self.role == "admin"

    def get_assigned_tasks_for_project(self, project_id):
        return Task.query.filter_by(project_id=project_id, assigned_to=self.id).all()
    
    def get_assigned_issues_for_project(self, project_id):
        return Issue.query.filter_by(project_id=project_id, assignee_id=self.id).all()

    


class Role(db.Model):
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(255), unique=True, nullable=False)

    menu_permissions = db.relationship('RoleMenuPermission', backref='role', lazy=True)
    

    def get_accessible_menus(self):
        return Menu.query.join(RoleMenuPermission).filter(
            RoleMenuPermission.role_id == self.id,
            RoleMenuPermission.can_access == True,
            Menu.is_active == True
        ).order_by(Menu.order_index).all()
    
    def has_menu_permission(self, menu_id):
        """Check if role has permission for a specific menu"""
        if self.role_name == 'super_admin':  # Admin has access to everything
            return True
        
        permission = RoleMenuPermission.query.filter_by(
            role_id=self.id,
            menu_id=menu_id,
            can_access=True
        ).first()
        
        return permission is not None

class Menu(db.Model):
    __tablename__ = 'menus'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.String(255))
    parent_id = db.Column(db.Integer, db.ForeignKey('menus.id'))
    route = db.Column(db.String(255))
    order_index = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    
    children = db.relationship('Menu', backref=db.backref('parent', remote_side=[id]))
    roles = db.relationship('Role', secondary='role_menu_permissions')


class RoleMenuPermission(db.Model):
    __tablename__ = 'role_menu_permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    menu_id = db.Column(db.Integer, db.ForeignKey('menus.id'), nullable=False)
    can_access = db.Column(db.Boolean, default=True)
    can_create = db.Column(db.Boolean, default=False)
    can_edit = db.Column(db.Boolean, default=False)
    can_delete = db.Column(db.Boolean, default=False)
    can_print = db.Column(db.Boolean, default=False)
    
    __table_args__ = (db.UniqueConstraint('role_id', 'menu_id', name='unique_role_menu'),)

class Route(db.Model):
    __tablename__ = 'routes'
    
    id = db.Column(db.Integer, primary_key=True)
    route_name = db.Column(db.String(255), nullable=False)  # e.g., 'administration.company_configuration'
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    menu_id = db.Column(db.Integer, db.ForeignKey('menus.id'), nullable=False)

    
    # Relationship with permissions
    menu = db.relationship('Menu', backref=db.backref('routes', uselist=False))
    permissions = db.relationship('RoutePermission', backref='route', lazy=True)


class RoutePermission(db.Model):
    __tablename__ = 'route_permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    route_id = db.Column(db.Integer, db.ForeignKey('routes.id'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    can_access = db.Column(db.Boolean, default=True)
    
    # Add unique constraint to prevent duplicate permissions
    __table_args__ = (
        db.UniqueConstraint('route_id', 'role_id', name='unique_route_role'),
    )

class UserActionPermission(db.Model):
    __tablename__ = 'user_action_permissions'

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=True)
    menu_id = db.Column(db.Integer, db.ForeignKey('menus.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    access = db.Column(db.Boolean, default=False)
    create = db.Column(db.Boolean, default=False)
    edit = db.Column(db.Boolean, default=False)
    delete = db.Column(db.Boolean, default=False)
    print = db.Column(db.Boolean, default=False)

    # Relationships
    role = db.relationship('Role', backref=db.backref('user_action_permissions', lazy=True))
    menu = db.relationship('Menu', backref=db.backref('user_action_permissions', lazy=True))
    user = db.relationship('User', backref=db.backref('user_action_permissions', lazy=True))


class CountryMaster(db.Model):
    __tablename__ = 'countrymaster'

    countryID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    companySystemID = db.Column(db.Integer, nullable=True)
    countryCode = db.Column(db.String(20), nullable=False)
    alpha2Code = db.Column(db.String(255), nullable=True)
    countryName = db.Column(db.String(100), nullable=True)
    nationality = db.Column(db.String(100), nullable=True)
    regionID = db.Column(db.Integer, nullable=True)
    isLocal = db.Column(db.Integer, default=0)
    countryFlag = db.Column(db.String(255), nullable=True)
    currency_code = db.Column(db.String(10), nullable=True)
    currency_name = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<Country {self.countryName}>"

class CurrencyMaster(db.Model):
    __tablename__ = 'currencymaster'

    currencyID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    CurrencyName = db.Column(db.String(255), nullable=True)
    CurrencyCode = db.Column(db.String(255), nullable=True, unique=True)
    DecimalPlaces = db.Column(db.Integer, nullable=True)
    ExchangeRate = db.Column(db.Float, default=0)
    isLocal = db.Column(db.Integer, nullable=True)
    DateModified = db.Column(db.DateTime, nullable=True)
    ModifiedBy = db.Column(db.String(255), nullable=True)
    createdUserGroup = db.Column(db.String(255), nullable=True)
    createdPcID = db.Column(db.String(255), nullable=True)
    createdUserID = db.Column(db.String(255), nullable=True)
    modifiedPc = db.Column(db.String(255), nullable=True)
    modifiedUser = db.Column(db.String(255), nullable=True)
    createdDateTime = db.Column(db.DateTime, nullable=True)
    timeStamp = db.Column(db.TIMESTAMP, nullable=True)

    def __repr__(self):
        return f"<Currency {self.CurrencyCode}>"


class ProductPackage(db.Model):
    __tablename__ = 'productpackages'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    product = db.Column(db.String(255), nullable=True)
    value = db.Column(db.Float, nullable=True)
    companyID = db.Column(db.Integer, nullable=True)
    is_base = db.Column(db.Integer, nullable=True) 
