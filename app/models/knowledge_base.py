from datetime import datetime
from app.extensions import db

# Supporting Models that don't exist in this app yet
class DBType(db.Model):
    __tablename__ = 'db_types'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    credentials = db.relationship('Credential', backref='db_type', lazy=True)
    
    def __repr__(self):
        return f'<DBType {self.name}>'


class Credential(db.Model):
    __tablename__ = 'credentials'
    
    id = db.Column(db.Integer, primary_key=True)
    connection_name = db.Column(db.String(255), unique=True, nullable=False)
    host = db.Column(db.String(255), nullable=False)
    user = db.Column(db.String(255), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    db_type_id = db.Column(db.Integer, db.ForeignKey('db_types.id'), nullable=False)
    company = db.Column(db.Integer, db.ForeignKey('company_info.id'))
    base_api_endpoint = db.Column(db.String(255))
    
    def __repr__(self):
        return f'<Credential {self.connection_name}>'


class Database(db.Model):
    __tablename__ = 'databases'
    
    id = db.Column(db.Integer, primary_key=True)
    credential_id = db.Column(db.Integer, db.ForeignKey('credentials.id'), nullable=False)
    database_name = db.Column(db.String(255), nullable=False)
    
    def __repr__(self):
        return f'<Database {self.database_name}>'


class UserConnectionMap(db.Model):
    __tablename__ = 'user_connection_map'
    
    id = db.Column(db.Integer, primary_key=True)
    connection_id = db.Column(db.Integer, db.ForeignKey('credentials.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Fixed: user table is singular
    
    def __repr__(self):
        return f'<UserConnectionMap user_id={self.user_id} conn_id={self.connection_id}>'


# Knowledge Base Models
class KnowledgeBaseCategory(db.Model):
    __tablename__ = 'knowledge_base_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    company_key = db.Column(db.String(50))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # Fixed: user table is singular
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    activeYN = db.Column(db.Boolean, default=True)
    
    # Relationships
    creator = db.relationship('User', backref='created_categories')
    knowledge_bases = db.relationship('KnowledgeBaseMaster', back_populates='category_info', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<KnowledgeBaseCategory {self.category}>'


class KnowledgeBaseMaster(db.Model):
    __tablename__ = 'knowledge_base_master'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    kb_description = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey('knowledge_base_categories.id', ondelete='CASCADE'), nullable=False)
    source_connection_id = db.Column(db.Integer, db.ForeignKey('credentials.id'))
    source_database_id = db.Column(db.Integer, db.ForeignKey('databases.id'))
    source_table = db.Column(db.String(255))
    description = db.Column(db.Text)
    company_key = db.Column(db.String(50))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # Fixed: user table is singular
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    activeYN = db.Column(db.Boolean, default=True)
    
    # Relationships
    category_info = db.relationship('KnowledgeBaseCategory', back_populates='knowledge_bases')
    source_connection = db.relationship('Credential', foreign_keys=[source_connection_id])
    source_database = db.relationship('Database', foreign_keys=[source_database_id])
    creator = db.relationship('User', backref='created_knowledge_bases')
    table_maps = db.relationship('KnowledgeBaseTableMap', cascade='all, delete-orphan', passive_deletes=True, back_populates='knowledge_base')
    
    def __repr__(self):
        return f'<KnowledgeBaseMaster id={self.id}>'


class KnowledgeBaseTableMap(db.Model):
    __tablename__ = 'knowledge_base_table_maps'
    
    id = db.Column(db.Integer, primary_key=True)
    knowledge_base_id = db.Column(
        db.Integer, 
        db.ForeignKey('knowledge_base_master.id', ondelete='CASCADE'),
        nullable=False
    )
    table_name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    table_order = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    knowledge_base = db.relationship(
        'KnowledgeBaseMaster',
        back_populates='table_maps'
    )
    fields = db.relationship(
        'KnowledgeBaseField', 
        cascade='all, delete-orphan', 
        passive_deletes=True, 
        back_populates='table_map',
        foreign_keys='[KnowledgeBaseField.table_map_id]'
    )
    
    def __repr__(self):
        return f'<KnowledgeBaseTableMap {self.table_name}>'


class KnowledgeBaseField(db.Model):
    __tablename__ = 'knowledge_base_fields'
    
    id = db.Column(db.Integer, primary_key=True)
    table_map_id = db.Column(db.Integer, db.ForeignKey('knowledge_base_table_maps.id', ondelete='CASCADE'), nullable=False)
    source_field_name = db.Column(db.String(255), nullable=False)
    field_description = db.Column(db.Text)
    field_order = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_unique = db.Column(db.Boolean, default=False)
    is_foreign_key = db.Column(db.Boolean, default=False)
    referenced_table_map_id = db.Column(db.Integer, db.ForeignKey('knowledge_base_table_maps.id'))
    referenced_field_id = db.Column(db.Integer, db.ForeignKey('knowledge_base_fields.id'))
    is_default_value = db.Column(db.Boolean, default=False)
    default_value = db.Column(db.Text)
    
    # Relationships
    table_map = db.relationship('KnowledgeBaseTableMap', foreign_keys=[table_map_id], back_populates='fields')
    referenced_table = db.relationship(
        'KnowledgeBaseTableMap', 
        foreign_keys=[referenced_table_map_id]
    )
    referenced_field = db.relationship('KnowledgeBaseField', remote_side=[id], foreign_keys=[referenced_field_id])
    
    def __repr__(self):
        return f'<KnowledgeBaseField {self.source_field_name}>'


class KnowledgeBaseAccess(db.Model):
    __tablename__ = 'knowledge_base_access'
    
    id = db.Column(db.Integer, primary_key=True)
    knowledge_base_id = db.Column(db.Integer, db.ForeignKey('knowledge_base_master.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Fixed: user table is singular
    granted_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Fixed: user table is singular
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    activeYN = db.Column(db.Boolean, default=True)
    
    # Relationships
    knowledge_base = db.relationship('KnowledgeBaseMaster', backref='access_permissions')
    user = db.relationship('User', foreign_keys=[user_id], backref='kb_permissions')
    grantor = db.relationship('User', foreign_keys=[granted_by], backref='granted_kb_permissions')
