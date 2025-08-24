from flask import Blueprint, render_template, redirect, url_for, make_response, request, flash, jsonify, Flask, send_file, Response, current_app, session
from . import kb_bp
from flask_login import login_required,current_user
from flask import render_template
from ..models import (
    KnowledgeBaseMaster, KnowledgeBaseField, KnowledgeBaseTableMap, User, Credential, Database, KnowledgeBaseCategory, UserConnectionMap, KnowledgeBaseAccess
)
from ..models.company import CompanyInfo
from .. import db
import plotly.express as px
from sqlalchemy import func, case
from datetime import datetime
import base64
import io
from werkzeug.security import generate_password_hash
import boto3
from ..utils_roles import check_route_permission
from sqlalchemy import desc
from .utils import get_tables, get_table_columns, check_access
from flask_wtf.csrf import generate_csrf
from .forms import KnowledgeBaseToggleForm
from sqlalchemy.exc import SQLAlchemyError
from .deepseek_chat import generate_sql, generate_chart
from ..crypto_utils import encrypt_message, decrypt_message
import mysql.connector

def safe_company_key_compare(company_key, user_company_id):
    """Safely compare company_key with user company_id, handling type conversions"""
    try:
        if company_key is None or user_company_id is None:
            return False
        # Convert both to int for comparison
        return int(company_key) == int(user_company_id)
    except (ValueError, TypeError):
        return False

#List category    
@kb_bp.route('/knowledge-base/categories', methods=['GET'])
@login_required
def list_categories():
    """Display summary of all knowledge base categories with role-based filtering"""
    try:
        if current_user.role_id == 1:  # Admin
            categories = KnowledgeBaseCategory.query.order_by(desc(KnowledgeBaseCategory.created_at)).all()
        else:  # Company Admin and other users - show categories from their company
            categories = KnowledgeBaseCategory.query.filter(
                KnowledgeBaseCategory.company_key == current_user.company_id
            ).order_by(desc(KnowledgeBaseCategory.created_at)).all()
        
        return render_template('knowledge_base/categories.html', categories=categories)
    except Exception as e:
        flash(f'Error listing categories: {str(e)}', 'error')
        return render_template('knowledge_base/categories.html', categories=[])

#create new category
@kb_bp.route('/knowledge-base/category/new', methods=['GET'])
@login_required
def create_category():
    """Display form to create a new knowledge base category"""
    # Debug logging
    current_app.logger.info(f"CREATE CATEGORY DEBUG: Current user role_id = {current_user.role_id}")
    current_app.logger.info(f"CREATE CATEGORY DEBUG: Current user company_id = {current_user.company_id}")
    
    # Test database connection
    try:
        total_companies = CompanyInfo.query.count()
        current_app.logger.info(f"CREATE CATEGORY DEBUG: Total companies in database = {total_companies}")
    except Exception as e:
        current_app.logger.error(f"CREATE CATEGORY DEBUG: Error counting companies: {str(e)}")
    
    # Get companies based on user role
    if current_user.role_id == 1:  # Special role that can choose any company
        current_app.logger.info("CREATE CATEGORY DEBUG: Getting all companies for role_id == 1")
        companies = CompanyInfo.query.all()
    else:  # Other roles can only see their own company
        current_app.logger.info(f"CREATE CATEGORY DEBUG: Getting companies for company_id = {current_user.company_id}")
        companies = CompanyInfo.query.filter_by(id=current_user.company_id).all()
    
    current_app.logger.info(f"CREATE CATEGORY DEBUG: Found {len(companies)} companies")
    for company in companies:
        current_app.logger.info(f"CREATE CATEGORY DEBUG: Company ID={company.id}, Name={company.company_name}")
    
    # Fallback: If no companies found, create a list with current user's company info
    if not companies and current_user.company_id:
        current_app.logger.info("CREATE CATEGORY DEBUG: No companies found, trying direct query")
        # Try to get company info directly
        try:
            user_company = CompanyInfo.query.get(current_user.company_id)
            if user_company:
                companies = [user_company]
                current_app.logger.info(f"CREATE CATEGORY DEBUG: Found user company: {user_company.company_name}")
            else:
                current_app.logger.warning(f"CREATE CATEGORY DEBUG: User's company_id {current_user.company_id} not found in company_info table")
        except Exception as e:
            current_app.logger.error(f"CREATE CATEGORY DEBUG: Error getting user company: {str(e)}")
    
    if not companies:
        current_app.logger.error("CREATE CATEGORY DEBUG: Still no companies found - this needs investigation")
    
    return render_template('knowledge_base/create_category.html', companies=companies)

@kb_bp.route('/knowledge-base/category', methods=['POST'])
@login_required
def save_category():
    """Save a new knowledge base category"""
    try:
        # Get JSON data from request
        data = request.json
        
        # Debug logging
        current_app.logger.info(f"SAVE CATEGORY DEBUG: Received data: {data}")
        current_app.logger.info(f"SAVE CATEGORY DEBUG: User role_id: {current_user.role_id}")
        current_app.logger.info(f"SAVE CATEGORY DEBUG: User company_id: {current_user.company_id}")
        
        # Validate required fields
        if not data or not data.get('category'):
            return jsonify({'status': 'error', 'message': 'Category name is required'}), 400
        
        # Get company_id from form data or use current user's company
        company_id = data.get('company_id')
        current_app.logger.info(f"SAVE CATEGORY DEBUG: company_id from form: {company_id}")
        
        if not company_id:
            company_id = current_user.company_id
            current_app.logger.info(f"SAVE CATEGORY DEBUG: No company_id provided, using user's company: {company_id}")
        else:
            current_app.logger.info(f"SAVE CATEGORY DEBUG: Using selected company_id: {company_id}")
            # Validate that user has permission to create categories for this company
            if current_user.role_id != 1 and int(company_id) != current_user.company_id:
                current_app.logger.warning(f"SAVE CATEGORY DEBUG: Permission denied - user role {current_user.role_id} cannot create category for company {company_id}")
                return jsonify({'status': 'error', 'message': 'You do not have permission to create categories for this company'}), 403
        
        current_app.logger.info(f"SAVE CATEGORY DEBUG: Final company_key will be: {company_id}")
        
        # Create the category record
        category = KnowledgeBaseCategory(
            category=data.get('category'),
            description=data.get('description', ''),  # Use empty string as fallback
            company_key=company_id,  # Use selected company_id instead of current_user.company_id
            created_by=current_user.id,
            activeYN=data.get('active', True)
        )
        
        # Add and commit with error handling
        try:
            db.session.add(category)
            db.session.commit()
            current_app.logger.info(f"SAVE CATEGORY DEBUG: Category created with ID: {category.id}, company_key: {category.company_key}")
            return jsonify({'status': 'success', 'category_id': category.id})
        except SQLAlchemyError as db_error:
            db.session.rollback()
            current_app.logger.error(f"SAVE CATEGORY DEBUG: Database error: {str(db_error)}")
            return jsonify({'status': 'error', 'message': f'Database error: {str(db_error)}'}), 500
            
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"SAVE CATEGORY DEBUG: Exception occurred: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

#view category
@kb_bp.route('/knowledge-base/category/<int:category_id>', methods=['GET'])
@login_required
def view_category(category_id):
    """View a specific category and its knowledge bases"""
    category = KnowledgeBaseCategory.query.get_or_404(category_id)
    
    # Check permissions based on role
    if current_user.role_id != 1 and not safe_company_key_compare(category.company_key, current_user.company_id):
        flash('You do not have permission to view this category', 'error')
        return redirect(url_for('knowledge_base.list_categories'))
    
    # Get knowledge bases under this category with appropriate filtering
    if current_user.role_id == 1:  # Admin
        knowledge_bases = KnowledgeBaseMaster.query.filter_by(
            category_id=category_id
        ).order_by(desc(KnowledgeBaseMaster.created_at)).all()
    elif current_user.role_id == 5:  # Company Admin
        knowledge_bases = KnowledgeBaseMaster.query.filter_by(
            category_id=category_id,
            company_key=current_user.company_id
        ).order_by(desc(KnowledgeBaseMaster.created_at)).all()
    else:  # Developer
        knowledge_bases = KnowledgeBaseMaster.query.filter_by(
            category_id=category_id
        ).join(
            Credential, KnowledgeBaseMaster.source_connection_id == Credential.id
        ).join(
            UserConnectionMap, Credential.id == UserConnectionMap.connection_id
        ).filter(
            UserConnectionMap.user_id == current_user.id
        ).order_by(desc(KnowledgeBaseMaster.created_at)).all()
    
    return render_template('knowledge_base/view_category.html', 
                           category=category, 
                           knowledge_bases=knowledge_bases,
                           Company=CompanyInfo)

#edit category

@kb_bp.route('/knowledge-base/category/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_category(category_id):
    """Display and process the edit form for a knowledge base category"""
    # Get the category by ID - Remove company filter for role_id == 2
    if current_user.role_id == 1:  # Special role can edit any company's categories
        category = KnowledgeBaseCategory.query.get_or_404(category_id)
    else:  # Other roles can only edit their company's categories
        category = KnowledgeBaseCategory.query.filter_by(
            id=category_id, 
            company_key=current_user.company_id
        ).first_or_404()
    
    # For GET requests, render the edit template
    if request.method == 'GET':
        # Debug prints
        current_app.logger.info(f"Debug EDIT: Current user role_id = {current_user.role_id}")
        current_app.logger.info(f"Debug EDIT: Current user company_id = {current_user.company_id}")
        
        # Get companies based on user role
        if current_user.role_id == 1:  # Special role that can choose any company
            current_app.logger.info("Debug EDIT: Getting all companies for role_id == 1")
            companies = CompanyInfo.query.all()
        else:  # Other roles can only see their own company
            current_app.logger.info(f"Debug EDIT: Getting companies for company_id = {current_user.company_id}")
            companies = CompanyInfo.query.filter_by(id=current_user.company_id).all()
        
        current_app.logger.info(f"Debug EDIT: Found {len(companies)} companies")
        for company in companies:
            current_app.logger.info(f"Debug EDIT: Company ID={company.id}, Name={company.company_name}")
        
        # Fallback: If no companies found, create a list with current user's company info
        if not companies and current_user.company_id:
            current_app.logger.info("Debug EDIT: No companies found, trying direct query")
            # Try to get company info directly
            try:
                user_company = CompanyInfo.query.get(current_user.company_id)
                if user_company:
                    companies = [user_company]
                    current_app.logger.info(f"Debug EDIT: Found user company: {user_company.company_name}")
                else:
                    current_app.logger.warning(f"Debug EDIT: User's company_id {current_user.company_id} not found in company_info table")
            except Exception as e:
                current_app.logger.error(f"Debug EDIT: Error getting user company: {str(e)}")
        
        if not companies:
            current_app.logger.error("Debug EDIT: Still no companies found - this needs investigation")
            
        return render_template(
            'knowledge_base/edit_category.html', 
            category=category,
            companies=companies
        )
    
    # For POST requests, update the category
    try:
        # Get JSON data from request
        data = request.json
        
        # Debug logging
        current_app.logger.info(f"EDIT CATEGORY DEBUG: Received data: {data}")
        current_app.logger.info(f"EDIT CATEGORY DEBUG: User role_id: {current_user.role_id}")
        current_app.logger.info(f"EDIT CATEGORY DEBUG: User company_id: {current_user.company_id}")
        current_app.logger.info(f"EDIT CATEGORY DEBUG: Current category company_key: {category.company_key}")
        
        # Validate required fields
        if not data or not data.get('category'):
            return jsonify({'status': 'error', 'message': 'Category name is required'}), 400
        
        # Get company_id from form data or keep existing
        company_id = data.get('company_id')
        current_app.logger.info(f"EDIT CATEGORY DEBUG: company_id from form: {company_id}")
        
        if company_id:
            # Validate that user has permission to assign categories to this company
            if current_user.role_id != 1 and int(company_id) != current_user.company_id:
                current_app.logger.warning(f"EDIT CATEGORY DEBUG: Permission denied - user role {current_user.role_id} cannot assign category to company {company_id}")
                return jsonify({'status': 'error', 'message': 'You do not have permission to assign categories to this company'}), 403
            category.company_key = company_id
            current_app.logger.info(f"EDIT CATEGORY DEBUG: Updated company_key to: {company_id}")
        else:
            current_app.logger.info(f"EDIT CATEGORY DEBUG: No company_id provided, keeping existing company_key: {category.company_key}")
        
        # Update the category
        category.category = data.get('category')
        category.description = data.get('description', '')
        category.activeYN = data.get('active', True)
        category.updated_by = current_user.id
        category.updated_at = datetime.utcnow()
        
        # Save changes
        try:
            db.session.commit()
            current_app.logger.info(f"EDIT CATEGORY DEBUG: Category updated: {category.id}, final company_key: {category.company_key}")
            return jsonify({'status': 'success', 'category_id': category.id})
        except SQLAlchemyError as db_error:
            db.session.rollback()
            current_app.logger.error(f"EDIT CATEGORY DEBUG: Database error: {str(db_error)}")
            return jsonify({'status': 'error', 'message': f'Database error: {str(db_error)}'}), 500
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Exception occurred: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

#Delete category
@kb_bp.route('/knowledge-base/category/<int:category_id>/delete', methods=['POST'])
@login_required
def delete_category(category_id):
    """Delete a knowledge base category"""
    try:
        # Find the category
        category = KnowledgeBaseCategory.query.filter_by(
            id=category_id,
            company_key=current_user.company_id
        ).first_or_404()
        
        # Store category name for logging
        category_name = category.category
        
        # Check if the category has knowledge bases
        kb_count = len(category.knowledge_bases)
        
        # Delete the category regardless of knowledge bases (orphans them)
        db.session.delete(category)
        
        # Commit changes
        db.session.commit()
        
        # Log the deletion
        current_app.logger.info(f"Category '{category_name}' (ID: {category_id}) deleted by user {current_user.username} (ID: {current_user.id})")
        
        # Return success response
        return jsonify({
            'status': 'success',
            'message': 'Category deleted successfully'
        })
    
    except SQLAlchemyError as db_error:
        # Roll back transaction on error
        db.session.rollback()
        current_app.logger.error(f"Database error deleting category {category_id}: {str(db_error)}")
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(db_error)}'
        }), 500
    
    except Exception as e:
        # Handle any other exceptions
        db.session.rollback()
        current_app.logger.error(f"Exception occurred deleting category {category_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# Knowledge Base routes
@kb_bp.route('/knowledge-base/new/<int:category_id>', methods=['GET'])
@login_required
def create_knowledge_base(category_id):
    """Display form to create a new knowledge base under a specific category"""
    category = KnowledgeBaseCategory.query.get_or_404(category_id)
    
    # Check permissions
    if current_user.role_id != 1 and not safe_company_key_compare(category.company_key, current_user.company_id):
        if current_user.role_id != 5:
            flash('You do not have permission to create a knowledge base in this category', 'error')
            return redirect(url_for('knowledge_base.list_categories'))
    
    return render_template('knowledge_base/create.html', category=category)

@kb_bp.route('/knowledge-base/<int:kb_id>', methods=['GET'])
@login_required
def view_knowledge_base(kb_id):
    """View a specific knowledge base"""
    # Query the knowledge base with all necessary relationships joined
    kb = KnowledgeBaseMaster.query.options(
        db.joinedload(KnowledgeBaseMaster.category_info),
        db.joinedload(KnowledgeBaseMaster.source_connection),
        db.joinedload(KnowledgeBaseMaster.source_database),
        db.joinedload(KnowledgeBaseMaster.creator)
    ).get_or_404(kb_id)
    
    # Check access permissions
    if not check_access(kb.source_connection):
        flash('You do not have permission to view this knowledge base', 'error')
        return redirect(url_for('knowledge_base.list_categories'))
    
    # Get tables with their fields
    tables = KnowledgeBaseTableMap.query.filter_by(
    knowledge_base_id=kb_id
).options(
    db.joinedload(KnowledgeBaseTableMap.fields).joinedload(KnowledgeBaseField.referenced_table),
    db.joinedload(KnowledgeBaseTableMap.fields).joinedload(KnowledgeBaseField.referenced_field)
).order_by(KnowledgeBaseTableMap.table_order).all()
    
    # Create toggle form
    toggle_form = KnowledgeBaseToggleForm()
    toggle_form.kb_id.data = kb_id
    
    return render_template('knowledge_base/view.html', kb=kb, tables=tables, form=toggle_form, Company=CompanyInfo)

@kb_bp.route('/knowledge-base', methods=['POST'])
@login_required
def save_knowledge_base():
    """Save a new knowledge base"""
    try:
        data = request.json
        # Validate access to connection
        connection_id = data.get('connection_id')
        connection = Credential.query.get(connection_id)
        if not connection or not check_access(connection):
            return jsonify({'status': 'error', 'message': 'Access denied to this connection'})

        # Validate category access
        category_id = data.get('category_id')
        category = KnowledgeBaseCategory.query.get(category_id)
        if not category:
            return jsonify({'status': 'error', 'message': 'Category not found'})
        
        # Debug logging
        current_app.logger.info(f"SAVE KB DEBUG: User company_id: {current_user.company_id}")
        current_app.logger.info(f"SAVE KB DEBUG: Category company_key: {category.company_key}")
        current_app.logger.info(f"SAVE KB DEBUG: Will use category company_key for knowledge base")
        
        if current_user.role_id != 1 and not safe_company_key_compare(category.company_key, current_user.company_id):
            if current_user.role_id != 5:
                return jsonify({'status': 'error', 'message': 'Access denied to this category'})

        # Create the knowledge base master record
        kb = KnowledgeBaseMaster(
            name=data.get('name'),
            kb_description=data.get('kb_description'),
            category_id=category_id,
            source_connection_id=connection_id,
            source_database_id=data.get('database_id'),
            source_table=data.get('source_table', data.get('tables', [{}])[0].get('table_name', '')), 
            description=data.get('description', ''),
            company_key=category.company_key,  # Use category's company_key instead of current_user.company_id
            created_by=current_user.id,
            activeYN=data.get('active', True)
        )
        db.session.add(kb)
        db.session.flush()  # Get ID without committing
        
        # Dictionary to store table mappings for easier lookup by table name
        table_map_dict = {}
        # Dictionary to store field objects for easier lookup
        field_dict = {}
        # Dictionary to store foreign key references to be set later
        fk_references = []
        
        # Process table mappings
        tables = data.get('tables', [])
        for idx, table_data in enumerate(tables):
            table_name = table_data.get('table_name')
            table_map = KnowledgeBaseTableMap(
                knowledge_base_id=kb.id,
                table_name=table_name,
                description=table_data.get('description', ''),
                table_order=idx + 1
            )
            db.session.add(table_map)
            db.session.flush()  # Get ID without committing
            
            # Store the table mapping for later lookup
            table_map_dict[table_name] = table_map
            
            # Process fields for this table
            fields = table_data.get('fields', [])
            for field_idx, field_data in enumerate(fields):
                field_name = field_data.get('source_field')
                field = KnowledgeBaseField(
                    table_map_id=table_map.id,
                    source_field_name=field_name,
                    field_description=field_data.get('description'),
                    field_order=field_idx + 1,
                    is_unique=field_data.get('is_unique', False),
                    is_foreign_key=field_data.get('is_foreign_key', False)
                )
                db.session.add(field)
                db.session.flush()  # Get ID to use for foreign key references
                
                # Store the field for later lookup
                field_key = f"{table_name}.{field_name}"
                field_dict[field_key] = field
                
                # Store foreign key details for later processing
                if field_data.get('is_foreign_key', False):
                    ref_table_name = field_data.get('referenced_table')
                    ref_field_name = field_data.get('referenced_field')
                    
                    if ref_table_name and ref_field_name:
                        fk_references.append({
                            'field': field,
                            'ref_table_name': ref_table_name,
                            'ref_field_name': ref_field_name
                        })
        
        # First commit to ensure all tables and fields are saved
        db.session.commit()
        
        # Process foreign key relationships
        for fk_ref in fk_references:
            field = fk_ref['field']
            ref_table_name = fk_ref['ref_table_name']
            ref_field_name = fk_ref['ref_field_name']
            
            # Get the referenced table map
            ref_table_map = table_map_dict.get(ref_table_name)
            
            if not ref_table_map:
                # If the referenced table isn't included in our mapping yet, create it
                ref_table_map = KnowledgeBaseTableMap(
                    knowledge_base_id=kb.id,
                    table_name=ref_table_name,
                    table_order=len(table_map_dict) + 1
                )
                db.session.add(ref_table_map)
                db.session.flush()
                table_map_dict[ref_table_name] = ref_table_map
            
            # Look up the referenced field
            ref_field_key = f"{ref_table_name}.{ref_field_name}"
            ref_field = field_dict.get(ref_field_key)
            
            if not ref_field:
                # If the referenced field isn't included in our mapping yet, create it
                ref_field = KnowledgeBaseField(
                    table_map_id=ref_table_map.id,
                    source_field_name=ref_field_name,
                    field_description=f"Referenced by {field.source_field_name}",
                    field_order=0,  # Will need to be updated if more fields are added
                    is_unique=True,  # Assume referenced fields are unique
                    is_foreign_key=False
                )
                db.session.add(ref_field)
                db.session.flush()
                field_dict[ref_field_key] = ref_field
            
            # Update the field with foreign key references
            field.referenced_table_map_id = ref_table_map.id
            field.referenced_field_id = ref_field.id
        
        # Final commit to save foreign key relationships
        db.session.commit()
        current_app.logger.info(f"SAVE KB DEBUG: Knowledge base created with ID: {kb.id}, company_key: {kb.company_key} (inherited from category)")
        return jsonify({'status': 'success', 'kb_id': kb.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)})


# API endpoints for relationship visualization
@kb_bp.route('/api/relationships/<int:kb_id>', methods=['GET'])
@login_required
def get_relationships(kb_id):
    """Get table relationships for visualization"""
    try:
        kb = KnowledgeBaseMaster.query.get_or_404(kb_id)
        if not check_access(kb.source_connection):
            return jsonify({'status': 'error', 'message': 'Access denied'})
        
        tables = KnowledgeBaseTableMap.query.filter_by(knowledge_base_id=kb_id).all()
        
        # Build relationship data
        nodes = []
        links = []
        
        # Create nodes for tables
        for table in tables:
            nodes.append({
                'id': f'table_{table.id}',
                'name': table.table_name,
                'type': 'table'
            })
        
        # Create links for relationships
        for table in tables:
            fields = KnowledgeBaseField.query.filter_by(
                table_map_id=table.id,
                is_foreign_key=True
            ).all()
            
            for field in fields:
                if field.referenced_table_map_id:
                    links.append({
                        'source': f'table_{table.id}',
                        'target': f'table_{field.referenced_table_map_id}',
                        'field': field.source_field_name,
                        'referenced_field': field.referenced_field.source_field_name if field.referenced_field else 'Unknown'
                    })
        
        return jsonify({
            'status': 'success',
            'nodes': nodes,
            'links': links
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

def check_access(connection):
    if current_user.role_id == 1:  # Admin
        return True
    elif current_user.role_id == 5:  # Company Admin
        return connection.company == current_user.company_id
    elif current_user.role_id == 2:  # Developer
        # Check user connection map
        has_access = UserConnectionMap.query.filter_by(
            user_id=current_user.id,
            connection_id=connection.id
        ).first()
        return has_access is not None
    return False
        
@kb_bp.route('/api/connections', methods=['GET'])
@login_required
def get_connections():
    """Get available connections based on user role"""
    try:
        if current_user.role_id == 1:  # Admin
            connections = Credential.query.all()
        elif current_user.role_id == 5:  # Company Admin
            connections = Credential.query.filter(
                Credential.company == current_user.company_id
            ).all()
        else:  # Developer
            connections = Credential.query.join(
                UserConnectionMap
            ).filter(
                UserConnectionMap.user_id == current_user.id
            ).all()
        
        connection_data = [{
            'id': conn.id,
            'name': conn.connection_name
        } for conn in connections]
        
        return jsonify({
            'status': 'success',
            'connections': connection_data
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@kb_bp.route('/api/databases', methods=['GET'])
@login_required
def get_databases():
    """Get databases for a connection"""
    try:
        connection_id = request.args.get('connection_id')
        if not connection_id:
            return jsonify({'status': 'error', 'message': 'Connection ID is required'})
        
        # Verify access
        connection = Credential.query.get(connection_id)
        if not connection or not check_access(connection):
            return jsonify({'status': 'error', 'message': 'Access denied to this connection'})
        
        # Get databases
        databases = Database.query.filter_by(credential_id=connection_id).all()
        
        database_data = [{
            'id': db.id,
            'name': db.database_name
        } for db in databases]
        
        return jsonify({
            'status': 'success',
            'databases': database_data
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@kb_bp.route('/api/tables', methods=['GET'])
@login_required
def get_database_tables():
    """Get tables for a database"""
    try:
        connection_id = request.args.get('connection_id')
        database_id = request.args.get('database_id')
        
        if not connection_id or not database_id:
            return jsonify({
                'status': 'error', 
                'message': 'Connection ID and database ID are required'
            })
        
        # Verify access
        connection = Credential.query.get(connection_id)
        if not connection or not check_access(connection):
            return jsonify({'status': 'error', 'message': 'Access denied to this connection'})
        
        # Get database
        database = Database.query.get(database_id)
        if not database:
            return jsonify({'status': 'error', 'message': 'Database not found'})
        
        # Get tables
        tables = get_tables(connection.connection_name, database.database_name)
        
        return jsonify({
            'status': 'success',
            'tables': tables
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@kb_bp.route('/api/columns', methods=['GET'])
@login_required
def get_table_columns_api():
    """Get columns for a table"""
    try:
        connection_id = request.args.get('connection_id')
        database_id = request.args.get('database_id')
        table = request.args.get('table')
        
        if not all([connection_id, database_id, table]):
            return jsonify({
                'status': 'error', 
                'message': 'Connection ID, database ID, and table are required'
            })
        
        # Verify access
        connection = Credential.query.get(connection_id)
        if not connection or not check_access(connection):
            return jsonify({'status': 'error', 'message': 'Access denied to this connection'})
        
        # Get database
        database = Database.query.get(database_id)
        if not database:
            return jsonify({'status': 'error', 'message': 'Database not found'})
        
        # Get columns
        columns = get_table_columns(connection.connection_name, database.database_name, table)
        
        return jsonify({
            'status': 'success',
            'columns': columns
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@kb_bp.route('/knowledge-base/<int:kb_id>/toggle-status', methods=['POST'])
@login_required
def toggle_knowledge_base_status(kb_id):
    """Toggle the active status of a knowledge base"""
    form = KnowledgeBaseToggleForm()
    
    if form.validate_on_submit():
        kb = KnowledgeBaseMaster.query.get_or_404(kb_id)
        
        # Check access permissions
        if not check_access(kb.source_connection):
            flash('You do not have permission to modify this knowledge base', 'error')
            return redirect(url_for('knowledge_base.view_knowledge_base', kb_id=kb_id))
        
        try:
            # Toggle the active status
            kb.activeYN = not kb.activeYN
            db.session.commit()
            
            status = "activated" if kb.activeYN else "deactivated"
            flash(f'Knowledge base successfully {status}', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating knowledge base status: {str(e)}', 'error')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'Error in {field}: {error}', 'error')
    
    # Redirect back to the knowledge base view
    return redirect(url_for('knowledge_base.view_knowledge_base', kb_id=kb_id))

    
    return render_template('knowledge_base/edit_knowledgebase.html', kb=kb)

@kb_bp.route('/delete_kb/<int:kb_id>/<int:category_id>', methods=['GET', 'POST'])
@login_required
def delete_knowledge_base(kb_id, category_id):
    kb = KnowledgeBaseMaster.query.get_or_404(kb_id)
    
    # Check if user has permission to delete
    if current_user.id != kb.created_by and not current_user.is_admin:
        flash('You do not have permission to delete this knowledge base.', 'danger')
        return redirect(url_for('knowledge_base.view_category', category_id=category_id))
    
    if request.method == 'POST':
        try:
            db.session.delete(kb)
            db.session.commit()
            flash('Knowledge base deleted successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error deleting knowledge base: {str(e)}', 'danger')
        
        return redirect(url_for('knowledge_base.view_category', category_id=category_id))
    
    return render_template('knowledge_base/delete_confirm.html', kb=kb, category_id=category_id)

#Update knowledge base

@kb_bp.route('/api/update-knowledge-base/<int:kb_id>', methods=['PUT'])
@login_required
def update_knowledge_base(kb_id):
    """Update an existing knowledge base"""
    try:
        data = request.json
        
        # Get the existing knowledge base
        kb = KnowledgeBaseMaster.query.get_or_404(kb_id)
        
        # Check if user has access to the knowledge base
        if not check_access(kb.source_connection):
            return jsonify({'status': 'error', 'message': 'Access denied to this knowledge base'})
        
        # Check category access if category is being changed
        if 'category_id' in data:
            category_id = data.get('category_id')
            category = KnowledgeBaseCategory.query.get(category_id)
            if not category:
                return jsonify({'status': 'error', 'message': 'Category not found'})
            
            if current_user.role_id != 1 and not safe_company_key_compare(category.company_key, current_user.company_id):
                if current_user.role_id != 5:
                    return jsonify({'status': 'error', 'message': 'Access denied to this category'})
            
            kb.category_id = category_id
            # Update company_key to match the new category's company_key
            kb.company_key = category.company_key
            current_app.logger.info(f"UPDATE KB DEBUG: Updated category and company_key to {category.company_key} for KB {kb_id}")
        
        # Update connection if provided
        if 'connection_id' in data:
            connection_id = data.get('connection_id')
            connection = Credential.query.get(connection_id)
            if not connection or not check_access(connection):
                return jsonify({'status': 'error', 'message': 'Access denied to this connection'})
            
            kb.source_connection_id = connection_id
        
        # Update other basic fields
        if 'database_id' in data:
            kb.source_database_id = data.get('database_id')
        
        if 'source_table' in data:
            kb.source_table = data.get('source_table')
        elif 'tables' in data and data.get('tables') and data.get('tables')[0].get('table_name'):
            kb.source_table = data.get('tables')[0].get('table_name')
        
        if 'active' in data:
            kb.activeYN = data.get('active')
        
        kb.updated_by = current_user.id
        kb.updated_at = datetime.utcnow()
        
        # Handle table and field updates if provided
        if 'tables' in data:
            # Option 1: Delete and recreate approach
            # First get all existing table maps to potentially delete
            existing_tables = KnowledgeBaseTableMap.query.filter_by(knowledge_base_id=kb.id).all()
            existing_table_ids = [table.id for table in existing_tables]
            
            # Dictionary to store table mappings for easier lookup by table name
            table_map_dict = {}
            # Dictionary to store field objects for easier lookup
            field_dict = {}
            # Dictionary to store foreign key references to be set later
            fk_references = []
            # Track which tables we're keeping
            processed_table_ids = []
            
            # Process table mappings
            tables = data.get('tables', [])
            for idx, table_data in enumerate(tables):
                table_name = table_data.get('table_name')
                table_id = table_data.get('id')
                
                # Check if we're updating an existing table
                if table_id:
                    table_map = KnowledgeBaseTableMap.query.get(table_id)
                    if table_map and table_map.knowledge_base_id == kb.id:
                        # Update existing table
                        table_map.table_name = table_name
                        table_map.table_order = idx + 1
                        processed_table_ids.append(table_map.id)
                    else:
                        # If ID is invalid, create new table
                        table_map = KnowledgeBaseTableMap(
                            knowledge_base_id=kb.id,
                            table_name=table_name,
                            table_order=idx + 1
                        )
                        db.session.add(table_map)
                        db.session.flush()
                else:
                    # Create new table
                    table_map = KnowledgeBaseTableMap(
                        knowledge_base_id=kb.id,
                        table_name=table_name,
                        table_order=idx + 1
                    )
                    db.session.add(table_map)
                    db.session.flush()
                
                # Store the table mapping for later lookup
                table_map_dict[table_name] = table_map
                
                # Handle fields for this table
                if 'fields' in table_data:
                    # Get existing fields for this table to potentially delete
                    existing_fields = KnowledgeBaseField.query.filter_by(table_map_id=table_map.id).all()
                    existing_field_ids = [field.id for field in existing_fields]
                    processed_field_ids = []
                    
                    # Process fields for this table
                    fields = table_data.get('fields', [])
                    for field_idx, field_data in enumerate(fields):
                        field_name = field_data.get('source_field')
                        field_id = field_data.get('id')
                        
                        # Check if we're updating an existing field
                        if field_id:
                            field = KnowledgeBaseField.query.get(field_id)
                            if field and field.table_map_id == table_map.id:
                                # Update existing field
                                field.source_field_name = field_name
                                field.field_description = field_data.get('description')
                                field.field_order = field_idx + 1
                                field.is_unique = field_data.get('is_unique', False)
                                field.is_foreign_key = field_data.get('is_foreign_key', False)
                                processed_field_ids.append(field.id)
                            else:
                                # If ID is invalid, create new field
                                field = KnowledgeBaseField(
                                    table_map_id=table_map.id,
                                    source_field_name=field_name,
                                    field_description=field_data.get('description'),
                                    field_order=field_idx + 1,
                                    is_unique=field_data.get('is_unique', False),
                                    is_foreign_key=field_data.get('is_foreign_key', False)
                                )
                                db.session.add(field)
                                db.session.flush()
                        else:
                            # Create new field
                            field = KnowledgeBaseField(
                                table_map_id=table_map.id,
                                source_field_name=field_name,
                                field_description=field_data.get('description'),
                                field_order=field_idx + 1,
                                is_unique=field_data.get('is_unique', False),
                                is_foreign_key=field_data.get('is_foreign_key', False)
                            )
                            db.session.add(field)
                            db.session.flush()
                        
                        # Store the field for later lookup
                        field_key = f"{table_name}.{field_name}"
                        field_dict[field_key] = field
                        
                        # Store foreign key details for later processing
                        if field_data.get('is_foreign_key', False):
                            ref_table_name = field_data.get('referenced_table')
                            ref_field_name = field_data.get('referenced_field')
                            
                            if ref_table_name and ref_field_name:
                                fk_references.append({
                                    'field': field,
                                    'ref_table_name': ref_table_name,
                                    'ref_field_name': ref_field_name
                                })
                    
                    # Delete fields that weren't processed (removed fields)
                    for field_id in existing_field_ids:
                        if field_id not in processed_field_ids:
                            field_to_delete = KnowledgeBaseField.query.get(field_id)
                            if field_to_delete:
                                db.session.delete(field_to_delete)
            
            # Delete tables that weren't processed (removed tables)
            for table_id in existing_table_ids:
                if table_id not in processed_table_ids:
                    table_to_delete = KnowledgeBaseTableMap.query.get(table_id)
                    if table_to_delete:
                        # Also delete all fields associated with this table
                        fields_to_delete = KnowledgeBaseField.query.filter_by(table_map_id=table_id).all()
                        for field in fields_to_delete:
                            db.session.delete(field)
                        db.session.delete(table_to_delete)
            
            # Process foreign key relationships
            for fk_ref in fk_references:
                field = fk_ref['field']
                ref_table_name = fk_ref['ref_table_name']
                ref_field_name = fk_ref['ref_field_name']
                
                # Get the referenced table map
                ref_table_map = table_map_dict.get(ref_table_name)
                
                if not ref_table_map:
                    # If the referenced table isn't included in our mapping yet, create it
                    ref_table_map = KnowledgeBaseTableMap(
                        knowledge_base_id=kb.id,
                        table_name=ref_table_name,
                        table_order=len(table_map_dict) + 1
                    )
                    db.session.add(ref_table_map)
                    db.session.flush()
                    table_map_dict[ref_table_name] = ref_table_map
                
                # Look up the referenced field
                ref_field_key = f"{ref_table_name}.{ref_field_name}"
                ref_field = field_dict.get(ref_field_key)
                
                if not ref_field:
                    # If the referenced field isn't included in our mapping yet, create it
                    ref_field = KnowledgeBaseField(
                        table_map_id=ref_table_map.id,
                        source_field_name=ref_field_name,
                        field_description=f"Referenced by {field.source_field_name}",
                        field_order=0,  # Will need to be updated if more fields are added
                        is_unique=True,  # Assume referenced fields are unique
                        is_foreign_key=False
                    )
                    db.session.add(ref_field)
                    db.session.flush()
                    field_dict[ref_field_key] = ref_field
                
                # Update the field with foreign key references
                field.referenced_table_map_id = ref_table_map.id
                field.referenced_field_id = ref_field.id
        
        # Commit all changes
        db.session.commit()
        return jsonify({'status': 'success', 'kb_id': kb.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)})

@kb_bp.route('/edit/<int:kb_id>', methods=['GET'])
@login_required
def edit_knowledge_base(kb_id):
    """Render the edit knowledge base page"""
    try:
        # Get the knowledge base
        kb = KnowledgeBaseMaster.query.get_or_404(kb_id)
        
        # Check access permission
        if not check_access(kb.source_connection):
            return render_template('errors/403.html', 
                message="You don't have permission to edit this knowledge base")
        
        # Get all available categories based on user role
        if current_user.role_id == 1:  # Admin
            categories = KnowledgeBaseCategory.query.all()
        elif current_user.role_id == 5:  # Company Admin
            categories = KnowledgeBaseCategory.query.filter_by(
                company_key=current_user.company_id
            ).all()
        else:  # Developer
            categories = KnowledgeBaseCategory.query.filter_by(
                company_key=current_user.company_id, 
                active=True
            ).all()
        
        # Get all available connections based on user role
        if current_user.role_id == 1:  # Admin
            connections = Credential.query.all()
        elif current_user.role_id == 5:  # Company Admin
            connections = Credential.query.filter(
                Credential.company == current_user.company_id
            ).all()
        else:  # Developer
            connections = Credential.query.join(
                UserConnectionMap
            ).filter(
                UserConnectionMap.user_id == current_user.id
            ).all()
        
        # Get databases for the current connection if available
        databases = []
        if kb.source_connection_id:
            databases = Database.query.filter_by(
                credential_id=kb.source_connection_id
            ).all()
        
        return render_template('knowledge_base/edit.html', 
            kb=kb,
            categories=categories,
            connections=connections,
            databases=databases
        )
    except Exception as e:
        # Log the error
        current_app.logger.error(f"Error editing knowledge base: {str(e)}")
        return render_template('errors/500.html', error=str(e))

@kb_bp.route('/api/knowledge-base/<int:kb_id>', methods=['GET'])
@login_required
def get_knowledge_base(kb_id):
    """Get knowledge base details for editing"""
    try:
        # Get the knowledge base
        kb = KnowledgeBaseMaster.query.get_or_404(kb_id)
        
        # Check access permission
        if not check_access(kb.source_connection):
            return jsonify({'status': 'error', 'message': 'Access denied to this knowledge base'})
        
        # Get table mappings
        tables = KnowledgeBaseTableMap.query.filter_by(knowledge_base_id=kb.id).all()
        
        table_data = []
        for table in tables:
            # Get fields for this table
            fields = KnowledgeBaseField.query.filter_by(table_map_id=table.id).all()
            
            field_data = []
            for field in fields:
                # Get referenced table and field if this is a foreign key
                referenced_table_map = None
                referenced_field = None
                
                if field.is_foreign_key and field.referenced_table_map_id and field.referenced_field_id:
                    referenced_table_map = KnowledgeBaseTableMap.query.get(field.referenced_table_map_id)
                    referenced_field = KnowledgeBaseField.query.get(field.referenced_field_id)
                
                field_data.append({
                    'id': field.id,
                    'source_field_name': field.source_field_name,
                    'field_description': field.field_description,
                    'is_unique': field.is_unique,
                    'is_foreign_key': field.is_foreign_key,
                    'referenced_table_map': {
                        'id': referenced_table_map.id,
                        'table_name': referenced_table_map.table_name
                    } if referenced_table_map else None,
                    'referenced_field': {
                        'id': referenced_field.id,
                        'source_field_name': referenced_field.source_field_name
                    } if referenced_field else None
                })
            
            table_data.append({
                'id': table.id,
                'table_name': table.table_name,
                'table_order': table.table_order,
                'description': table.description,
                'fields': field_data
            })
        
        kb_data = {
            'id': kb.id,
            'category_id': kb.category_id,
            'source_connection_id': kb.source_connection_id,
            'source_database_id': kb.source_database_id,
            'source_table': kb.source_table,
            'description': kb.description,
            'activeYN': kb.activeYN
        }
        
        return jsonify({
            'status': 'success',
            'kb': kb_data,
            'tables': table_data
        })
    except Exception as e:
        # Log the error
        current_app.logger.error(f"Error getting knowledge base: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})

@kb_bp.route('/api/update-knowledge-base', methods=['POST'])
@login_required
def update_knowledge_base_api():
    """Update an existing knowledge base from the edit page"""
    try:
        data = request.json
        kb_id = data.get('kb_id')
        
        if not kb_id:
            return jsonify({'status': 'error', 'message': 'Knowledge base ID is required'})
        
        # Get the knowledge base
        kb = KnowledgeBaseMaster.query.get_or_404(kb_id)
        
        # Check access permission
        if not check_access(kb.source_connection):
            return jsonify({'status': 'error', 'message': 'Access denied to this knowledge base'})
        
        # Update KB master details
        if 'category_id' in data and data.get('category_id') != kb.category_id:
            new_category_id = data.get('category_id')
            new_category = KnowledgeBaseCategory.query.get(new_category_id)
            if not new_category:
                return jsonify({'status': 'error', 'message': 'Category not found'})
            
            # Check permission for new category
            if current_user.role_id != 1 and not safe_company_key_compare(new_category.company_key, current_user.company_id):
                if current_user.role_id != 5:
                    return jsonify({'status': 'error', 'message': 'Access denied to this category'})
            
            kb.category_id = new_category_id
            # Update company_key to match the new category's company_key
            kb.company_key = new_category.company_key
            current_app.logger.info(f"UPDATE KB API DEBUG: Updated category and company_key to {new_category.company_key} for KB {kb_id}")
        else:
            kb.category_id = data.get('category_id', kb.category_id)
            
        kb.source_connection_id = data.get('connection_id', kb.source_connection_id)
        kb.source_database_id = data.get('database_id', kb.source_database_id)
        kb.description = data.get('description', kb.description)
        kb.activeYN = data.get('active', kb.activeYN)
        
        # Update or create table mappings
        table_data = data.get('tables', [])
        existing_table_ids = []
        
        for table_info in table_data:
            table_id = table_info.get('id')
            table_name = table_info.get('table_name')
            
            if table_id:  # Update existing table
                table = KnowledgeBaseTableMap.query.get(table_id)
                if table:
                    table.table_name = table_name
                    table.description = table_info.get('description', table.description)
                    existing_table_ids.append(table_id)
                else:
                    # Create new table if ID doesn't exist
                    table = KnowledgeBaseTableMap(
                        knowledge_base_id=kb_id,
                        table_name=table_name,
                        table_order=len(existing_table_ids) + 1
                    )
                    db.session.add(table)
                    db.session.flush()  # Get the ID for the new table
                    existing_table_ids.append(table.id)
            else:  # Create new table
                table = KnowledgeBaseTableMap(
                    knowledge_base_id=kb_id,
                    table_name=table_name,
                    description=table_info.get('description', ''),
                    table_order=len(existing_table_ids) + 1
                )
                db.session.add(table)
                db.session.flush()  # Get the ID for the new table
                existing_table_ids.append(table.id)
            
            # Process field mappings for this table
            field_data = table_info.get('fields', [])
            existing_field_ids = []
            
            for field_info in field_data:
                field_id = field_info.get('id')
                source_field = field_info.get('source_field')
                description = field_info.get('description', '')
                is_unique = field_info.get('is_unique', False)
                is_foreign_key = field_info.get('is_foreign_key', False)
                
                if field_id:  # Update existing field
                    field = KnowledgeBaseField.query.get(field_id)
                    if field:
                        field.source_field_name = source_field
                        field.field_description = description
                        field.is_unique = is_unique
                        field.is_foreign_key = is_foreign_key
                        existing_field_ids.append(field_id)
                    else:
                        # Create new field if ID doesn't exist
                        field = KnowledgeBaseField(
                            table_map_id=table.id,
                            source_field_name=source_field,
                            field_description=description,
                            is_unique=is_unique,
                            is_foreign_key=is_foreign_key
                        )
                        db.session.add(field)
                        db.session.flush()  # Get the ID for the new field
                        existing_field_ids.append(field.id)
                else:  # Create new field
                    field = KnowledgeBaseField(
                        table_map_id=table.id,
                        source_field_name=source_field,
                        field_description=description,
                        is_unique=is_unique,
                        is_foreign_key=is_foreign_key
                    )
                    db.session.add(field)
                    db.session.flush()  # Get the ID for the new field
                    existing_field_ids.append(field.id)
                
                # Handle foreign key references if applicable
                if is_foreign_key:
                    referenced_table_name = field_info.get('referenced_table')
                    referenced_field_name = field_info.get('referenced_field')
                    
                    if referenced_table_name and referenced_field_name:
                        # Find or create the referenced table
                        ref_table = KnowledgeBaseTableMap.query.filter_by(
                            knowledge_base_id=kb_id,
                            table_name=referenced_table_name
                        ).first()
                        
                        if not ref_table:
                            # Create the referenced table if it doesn't exist
                            ref_table = KnowledgeBaseTableMap(
                                knowledge_base_id=kb_id,
                                table_name=referenced_table_name,
                                table_order=len(existing_table_ids) + 1
                            )
                            db.session.add(ref_table)
                            db.session.flush()
                            existing_table_ids.append(ref_table.id)
                        
                        # Find or create the referenced field
                        ref_field = KnowledgeBaseField.query.filter_by(
                            table_map_id=ref_table.id,
                            source_field_name=referenced_field_name
                        ).first()
                        
                        if not ref_field:
                            # Create the referenced field if it doesn't exist
                            ref_field = KnowledgeBaseField(
                                table_map_id=ref_table.id,
                                source_field_name=referenced_field_name,
                                field_description='',
                                is_unique=False,
                                is_foreign_key=False
                            )
                            db.session.add(ref_field)
                            db.session.flush()
                        
                        # Update the foreign key reference
                        field.referenced_table_map_id = ref_table.id
                        field.referenced_field_id = ref_field.id
                    else:
                        # Clear foreign key references if not provided
                        field.referenced_table_map_id = None
                        field.referenced_field_id = None
                else:
                    # Clear foreign key references if not a foreign key
                    field.referenced_table_map_id = None
                    field.referenced_field_id = None
            
            # Delete fields that were removed from the UI
            KnowledgeBaseField.query.filter(
                KnowledgeBaseField.table_map_id == table.id,
                ~KnowledgeBaseField.id.in_(existing_field_ids)
            ).delete(synchronize_session=False)
        
        # Delete tables that were removed from the UI
        KnowledgeBaseTableMap.query.filter(
            KnowledgeBaseTableMap.knowledge_base_id == kb_id,
            ~KnowledgeBaseTableMap.id.in_(existing_table_ids)
        ).delete(synchronize_session=False)
        
        # Commit the changes
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Knowledge base updated successfully',
            'kb_id': kb_id
        })
    except Exception as e:
        db.session.rollback()
        # Log the error
        current_app.logger.error(f"Error updating knowledge base: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})

@kb_bp.route('/knowledge-base/<int:kb_id>/update-description', methods=['POST'])
@login_required
def update_kb_description(kb_id):
    """Update the technical description of a knowledge base"""
    try:
        # Get the knowledge base
        kb = KnowledgeBaseMaster.query.get_or_404(kb_id)
        
        # Check access permission
        if not check_access(kb.source_connection):
            return jsonify({
                'status': 'error',
                'message': "You don't have permission to edit this knowledge base"
            }), 403
        
        # Get the new description from the request
        data = request.json
        description = data.get('description')
        
        # Update the description
        kb.description = description
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Description updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

def execute_query_with_connection(kb):
    """Execute query using the knowledge base's connection details"""
    from ..models import Credential, Database
    from ..crypto_utils import decrypt_message
    import mysql.connector
    
    try:
        # Get connection details
        connection = Credential.query.get(kb.source_connection_id)
        database = Database.query.get(kb.source_database_id)
        
        if not connection or not database:
            return None, None

        # Decrypt credentials - using correct attribute names from the model
        db_user = decrypt_message(connection.user)  # Changed to user
        db_password = decrypt_message(connection.password)  # Changed to password
        db_host = decrypt_message(connection.host)  # Changed to host
        db_port = '3306'  # Default MySQL port since it's not in the model
        db_name = database.database_name

        # Create database connection
        conn = mysql.connector.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            port=int(db_port),
            database=db_name
        )
        
        cursor = conn.cursor()
        
        return conn, cursor
    except Exception as e:
        current_app.logger.error(f"Database connection error: {str(e)}")
        return None, None

@kb_bp.route("/kb-chat/", defaults={'kb_id': None}, methods=["GET", "POST"])
@kb_bp.route("/kb-chat/<int:kb_id>", methods=["GET", "POST"])
@login_required
def kb_chat(kb_id):
    """Knowledge base chat interface with DeepSeek integration"""
    
    # If no kb_id is provided, show the selection page
    if kb_id is None:
        if current_user.role_id == 1:  # Admin
            knowledge_bases = KnowledgeBaseMaster.query.all()
        elif current_user.role_id == 5:  # Company Admin
            knowledge_bases = KnowledgeBaseMaster.query.filter_by(
                company_key=current_user.company_id
            ).all()
        else:  # Other roles - show only permitted KBs
            knowledge_bases = KnowledgeBaseMaster.query.join(
                KnowledgeBaseAccess,
                KnowledgeBaseMaster.id == KnowledgeBaseAccess.knowledge_base_id
            ).filter(
                KnowledgeBaseAccess.user_id == current_user.id,
                KnowledgeBaseAccess.activeYN == True
            ).all()
        
        return render_template("knowledge_base/select_chat.html", 
                             knowledge_bases=knowledge_bases)

    # If kb_id is provided, proceed with chat interface
    kb = KnowledgeBaseMaster.query.get_or_404(kb_id)
    
    # Check access permission
    if current_user.role_id not in [1, 5]:  # Not admin or company admin
        access = KnowledgeBaseAccess.query.filter_by(
            knowledge_base_id=kb_id,
            user_id=current_user.id,
            activeYN=True
        ).first()
        
        if not access:
            return render_template('errors/403.html', 
                message="You don't have permission to access this knowledge base")

    # Initialize chat history in session if not exists
    session_key = f'chat_history_{kb_id}'
    if session_key not in session:
        session[session_key] = []

    if request.method == "GET":
        return render_template("knowledge_base/kb_chat.html", 
                             kb=kb, 
                             chat_history=session[session_key])

    if request.method == "POST":
        user_prompt = request.form["prompt"]
        output_type = request.form.get("output_type", "text")
        chart_type = request.form.get("chart_type", None)

        # Add user message to history
        session[session_key].append({
            'role': 'user',
            'content': user_prompt
        })

        # Generate SQL query with chat history context
        sql_query = generate_sql(user_prompt, kb_id, session[session_key])
        current_app.logger.info(f"Generated SQL: {sql_query}")

        if sql_query.startswith("Error"):
            error_message = sql_query
            # Add AI error response to history
            session[session_key].append({
                'role': 'assistant',
                'content': error_message
            })
            session.modified = True
            return jsonify({
                'status': 'error',
                'message': error_message
            })

        # Execute the query using the knowledge base's connection
        try:
            conn, cursor = execute_query_with_connection(kb)
            if not conn or not cursor:
                raise Exception("Failed to establish database connection")

            try:
                cursor.execute(sql_query)
                columns = [desc[0] for desc in cursor.description]
                results = cursor.fetchall()
                results = [list(row) for row in results]

                # Prepare AI response message
                if not results:
                    ai_message = 'No data found for your query'
                elif output_type == "text":
                    if len(results) == 1:
                        ai_message = f"The result is: {results[0][0]}"
                    else:
                        items = [str(row[0]) for row in results]
                        ai_message = f"Here are the results: {', '.join(items[:-1])} and {items[-1]}"
                else:
                    ai_message = 'Here are the results of your query:'

                # Add AI response to history
                session[session_key].append({
                    'role': 'assistant',
                    'content': ai_message
                })
                session.modified = True

                # Return appropriate response based on output type
                if output_type == "text":
                    return jsonify({
                        'status': 'success',
                        'message': ai_message,
                        'type': 'text'
                    })
                elif output_type == "table":
                    return jsonify({
                        'status': 'success',
                        'type': 'table',
                        'columns': columns,
                        'results': results
                    })
                else:  # visualization
                    chart_url = None
                    if chart_type and len(columns) >= 2:
                        try:
                            chart_url = generate_chart(columns, results, chart_type, f"kb_{kb_id}_chart")
                        except Exception as e:
                            current_app.logger.error(f"Chart generation error: {str(e)}")

                    return jsonify({
                        'status': 'success',
                        'type': 'table',
                        'columns': columns,
                        'results': results,
                        'chart_url': chart_url
                    })

            except Exception as query_error:
                current_app.logger.error(f"Query execution error: {str(query_error)}")
                return jsonify({
                    'status': 'error',
                    'message': f"Error executing query: {str(query_error)}"
                })

            finally:
                cursor.close()
                conn.close()

        except Exception as conn_error:
            current_app.logger.error(f"Connection error: {str(conn_error)}")
            return jsonify({
                'status': 'error',
                'message': f"Database connection error: {str(conn_error)}"
            })

def build_schema_info(kb):
    """Build schema information string from knowledge base tables and fields"""
    schema_parts = []
    
    # Get all tables for this knowledge base
    tables = KnowledgeBaseTableMap.query.filter_by(knowledge_base_id=kb.id).all()
    
    for table in tables:
        # Start table definition
        table_def = [f"{table.table_name}:"]
        
        # Get fields for this table
        fields = KnowledgeBaseField.query.filter_by(table_map_id=table.id).all()
        
        for field in fields:
            field_def = f"- {field.source_field_name}"
            if field.field_description:
                field_def += f" AS '{field.field_description}'"
            if field.is_foreign_key and field.referenced_table_map_id and field.referenced_field_id:
                ref_table = KnowledgeBaseTableMap.query.get(field.referenced_table_map_id)
                ref_field = KnowledgeBaseField.query.get(field.referenced_field_id)
                field_def += f" # Foreign key to {ref_table.table_name}.{ref_field.source_field_name}"
            table_def.append(field_def)
        
        schema_parts.append("\n".join(table_def))
    
    # Add relationships section
    relationships = []
    for table in tables:
        fields = KnowledgeBaseField.query.filter_by(
            table_map_id=table.id,
            is_foreign_key=True
        ).all()
        
        for field in fields:
            if field.referenced_table_map_id and field.referenced_field_id:
                ref_table = KnowledgeBaseTableMap.query.get(field.referenced_table_map_id)
                ref_field = KnowledgeBaseField.query.get(field.referenced_field_id)
                relationships.append(
                    f"- {table.table_name}.{field.source_field_name} = "
                    f"{ref_table.table_name}.{ref_field.source_field_name}"
                )
    
    if relationships:
        schema_parts.append("\nTable Relationships:\n" + "\n".join(relationships))
    
    return "\n\n".join(schema_parts)

@kb_bp.route('/manage_access/<int:kb_id>', methods=['GET', 'POST'])
@login_required
def get_kb_access(kb_id):
    if request.method == 'GET':
        try:
            current_app.logger.info(f"Starting manage_access for KB ID: {kb_id}")
            
            kb = KnowledgeBaseMaster.query.get_or_404(kb_id)
            current_app.logger.info(f"Found knowledge base: {kb.name}")
            current_app.logger.info(f"Knowledge base company_key: {kb.company_key}")
            
            # Get regular users from the same company - Fixed role filtering
            current_app.logger.info("Querying users...")
            try:
                users = User.query.filter(
                    User.company_id == kb.company_key,
                    ~User.role_id.in_([1, 5])  # Fixed: Exclude admin (1) and company admin (5)
                ).all()
                current_app.logger.info(f"Found {len(users)} users")
            except Exception as query_error:
                current_app.logger.error(f"Error during user query: {str(query_error)}")
                import traceback
                traceback.print_exc()
                raise
            
            # Get existing access permissions
            current_app.logger.info("Getting access permissions...")
            try:
                access_map = {
                    access.user_id: access.activeYN 
                    for access in KnowledgeBaseAccess.query.filter_by(
                        knowledge_base_id=kb_id
                    ).all()
                }
                current_app.logger.info(f"Found {len(access_map)} access permissions")
            except Exception as access_error:
                current_app.logger.error(f"Error getting access permissions: {str(access_error)}")
                import traceback
                traceback.print_exc()
                raise
            
            current_app.logger.info("Processing users...")
            users_data = []
            for user in users:
                try:
                    # Debug what we're working with
                    current_app.logger.info(f"Processing user: {user.username}")
                    current_app.logger.info(f"User role (string): {user.role}")
                    current_app.logger.info(f"User role_id: {user.role_id}")
                    current_app.logger.info(f"User assigned_role object: {user.assigned_role}")
                    
                    # Safely get role name
                    if user.assigned_role and hasattr(user.assigned_role, 'role_name'):
                        role_name = user.assigned_role.role_name
                    elif user.role:
                        role_name = str(user.role)
                    else:
                        role_name = 'No Role'
                    
                    current_app.logger.info(f"Final role_name: {role_name}")
                    
                    user_data = {
                        'id': user.id,
                        'name': user.username,
                        'role': role_name,
                        'has_access': access_map.get(user.id, False)
                    }
                    users_data.append(user_data)
                    
                except Exception as user_error:
                    current_app.logger.error(f"Error processing user {user.username}: {str(user_error)}")
                    import traceback
                    traceback.print_exc()
                    # Add user with minimal info if there's an error
                    users_data.append({
                        'id': user.id,
                        'name': user.username,
                        'role': 'Error loading role',
                        'has_access': access_map.get(user.id, False)
                    })
            
            current_app.logger.info(f"Returning users data: {users_data}")  # Debug log
            return jsonify({'users': users_data})
            
        except Exception as e:
            current_app.logger.error(f"Error in GET manage_access: {str(e)}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
            
    else:  # POST request
        try:
            data = request.get_json()
            updates = data.get('updates', [])
            current_app.logger.info(f"Received updates: {updates}")

            # Process each update
            for update in updates:
                user_id = update['user_id']
                has_access = update['has_access']
                
                # Find existing access record
                access = KnowledgeBaseAccess.query.filter_by(
                    knowledge_base_id=kb_id,
                    user_id=user_id
                ).first()
                
                if has_access:
                    if not access:
                        # Create new access record
                        access = KnowledgeBaseAccess(
                            knowledge_base_id=kb_id,
                            user_id=user_id,
                            granted_by=current_user.id,
                            activeYN=True
                        )
                        db.session.add(access)
                    else:
                        # Update existing record
                        access.activeYN = True
                else:
                    if access:
                        # Deactivate access
                        access.activeYN = False
            
            db.session.commit()
            
            # After updating, fetch the current state
            users = User.query.filter(
                User.company_id == KnowledgeBaseMaster.query.get(kb_id).company_key,
                ~User.role_id.in_([1, 5])
            ).all()
            
            access_map = {
                access.user_id: access.activeYN 
                for access in KnowledgeBaseAccess.query.filter_by(
                    knowledge_base_id=kb_id
                ).all()
            }
            
            users_data = []
            for user in users:
                try:
                    # Debug what we're working with
                    current_app.logger.info(f"Processing user: {user.username}")
                    current_app.logger.info(f"User role (string): {user.role}")
                    current_app.logger.info(f"User role_id: {user.role_id}")
                    current_app.logger.info(f"User assigned_role object: {user.assigned_role}")
                    
                    # Safely get role name
                    if user.assigned_role and hasattr(user.assigned_role, 'role_name'):
                        role_name = user.assigned_role.role_name
                    elif user.role:
                        role_name = str(user.role)
                    else:
                        role_name = 'No Role'
                    
                    current_app.logger.info(f"Final role_name: {role_name}")
                    
                    user_data = {
                        'id': user.id,
                        'name': user.username,
                        'role': role_name,
                        'has_access': access_map.get(user.id, False)
                    }
                    users_data.append(user_data)
                    
                except Exception as user_error:
                    current_app.logger.error(f"Error processing user {user.username}: {str(user_error)}")
                    # Add user with minimal info if there's an error
                    users_data.append({
                        'id': user.id,
                        'name': user.username,
                        'role': 'Error loading role',
                        'has_access': access_map.get(user.id, False)
                    })
            
            return jsonify({
                'status': 'success',
                'message': 'Access permissions updated successfully',
                'users': users_data  # Return updated users data
            })
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating access: {str(e)}")
            return jsonify({
                'status': 'error',
                'error': str(e)
            }), 500

@kb_bp.route('/knowledge-base/chat-select', methods=['GET'])
@login_required
def select_kb_chat():
    """Show knowledge base selection for chat"""
    if current_user.role_id == 1:  # Admin
        knowledge_bases = KnowledgeBaseMaster.query.all()
    elif current_user.role_id == 5:  # Company Admin
        knowledge_bases = KnowledgeBaseMaster.query.filter_by(
            company_key=current_user.company_id
        ).all()
    else:  # Other roles
        knowledge_bases = KnowledgeBaseMaster.query.join(
            KnowledgeBaseAccess,
            KnowledgeBaseMaster.id == KnowledgeBaseAccess.knowledge_base_id
        ).filter(
            KnowledgeBaseAccess.user_id == current_user.id,
            KnowledgeBaseAccess.activeYN == True
        ).all()
    
    return render_template('knowledge_base/select_chat.html', knowledge_bases=knowledge_bases)
