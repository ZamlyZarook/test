from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, send_file, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models.hs import HSCodeCategory, HSCodeIssueBody, HSCode, HSCodeDocument, HSCodeDocumentAttachment, HSDocumentCategory
from app.models.user import RoleMenuPermission, Menu
from app.hs import bp
import os
import uuid
from werkzeug.utils import secure_filename
from datetime import datetime
import json
from app.utils_cha.s3_utils import upload_file_to_s3, get_s3_url, serve_s3_file
from botocore.exceptions import ClientError

def check_hs_permission(action='access'):
    """
    Check if current user has permission for HS module
    action can be: 'access', 'create', 'edit', 'delete', 'print'
    """
    # Super admin (user ID 1) has all permissions
    if current_user.id == 1:
        return True
    
    # Find the HS module menu entry
    hs_menu = Menu.query.filter_by(route='hs.index').first()
    if not hs_menu:
        # If menu doesn't exist, allow access (fallback)
        return True
    
    # Check role-based permission
    if current_user.role_id:
        permission = RoleMenuPermission.query.filter_by(
            role_id=current_user.role_id,
            menu_id=hs_menu.id
        ).first()
        
        if permission and permission.can_access:
            if action == 'access':
                return True
            elif action == 'create' and permission.can_create:
                return True
            elif action == 'edit' and permission.can_edit:
                return True
            elif action == 'delete' and permission.can_delete:
                return True
            elif action == 'print' and permission.can_print:
                return True
    
    return False


@bp.route('/')
@login_required
def index():
    if not check_hs_permission('access'):
        abort(403)
    
    if current_user.id == 1:
        categories = HSCodeCategory.query.all()
        codes = HSCode.query.all()
    else:
        categories = HSCodeCategory.query.filter_by(company_id=current_user.company_id).all()
        codes = HSCode.query.filter_by(company_id=current_user.company_id).all()
    return render_template('hs/index.html', categories=categories, codes=codes)

@bp.route('/categories', strict_slashes=False)
@login_required
def list_categories():
    if not check_hs_permission('access'):
        abort(403)
    
    if current_user.id == 1:
        categories = HSCodeCategory.query.all()
    else:
        categories = HSCodeCategory.query.filter_by(company_id=current_user.company_id).all()
    return render_template('hs/categories.html', categories=categories)

@bp.route('/category/new', methods=['GET', 'POST'])
@login_required
def new_category():
    if not check_hs_permission('create'):
        abort(403)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            description = request.form.get('description')
            
            if not name:
                flash("Name is required!", "danger")
                return jsonify({"success": False, "message": "Name is required!"}), 400
            
            category = HSCodeCategory(
                name=name, 
                description=description,
                company_id=current_user.company_id
            )
            db.session.add(category)
            db.session.commit()
            flash("Category added successfully!", "success")
            return jsonify({
                "success": True, 
                "message": "Category added successfully!",
                "category": {
                    "id": category.id,
                    "name": category.name,
                    "description": category.description
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding category: {str(e)}")
            flash("Error adding category: " + str(e), "danger")
            return jsonify({"success": False, "message": str(e)}), 500
    
    return render_template('hs/category_form.html')

@bp.route('/category/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_category(id):
    if not check_hs_permission('edit'):
        abort(403)
    
    category = HSCodeCategory.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            description = request.form.get('description')
            
            if not name:
                flash("Name is required!", "danger")
                return jsonify({"success": False, "message": "Name is required!"}), 400
            
            category.name = name
            category.description = description
            db.session.commit()
            flash("Category updated successfully!", "success")
            return jsonify({
                "success": True, 
                "message": "Category updated successfully!",
                "category": {
                    "id": category.id,
                    "name": category.name,
                    "description": category.description
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating category: {str(e)}")
            flash("Error updating category: " + str(e), "danger")
            return jsonify({"success": False, "message": str(e)}), 500
    
    return render_template('hs/category_form.html', category=category)

@bp.route('/category/<int:id>/delete', methods=['POST'])
@login_required
def delete_category(id):
    if not check_hs_permission('delete'):
        abort(403)
    
    try:
        category = HSCodeCategory.query.get_or_404(id)
        
        # Check if category is being used by any HS codes
        used_codes = HSCode.query.filter_by(category_id=id).first()
        if used_codes:
            flash("Cannot delete category. It is being used by HS codes.", "danger")
            return jsonify({
                "success": False, 
                "message": "Cannot delete category. It is being used by HS codes."
            }), 400
        
        db.session.delete(category)
        db.session.commit()
        flash("Category deleted successfully!", "success")
        return jsonify({"success": True, "message": "Category deleted successfully!"})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting category: {str(e)}")
        flash("Error deleting category: " + str(e), "danger")
        return jsonify({"success": False, "message": str(e)}), 500

@bp.route('/issue-bodies', strict_slashes=False)
@login_required
def list_issue_bodies():
    if not check_hs_permission('access'):
        abort(403)
    
    if current_user.id == 1:
        issue_bodies = HSCodeIssueBody.query.all()
    else:
        issue_bodies = HSCodeIssueBody.query.filter_by(company_id=current_user.company_id).all()
    return render_template('hs/issue_bodies.html', issue_bodies=issue_bodies)

@bp.route('/issue-body/new', methods=['GET', 'POST'])
@login_required
def new_issue_body():
    if not check_hs_permission('create'):
        abort(403)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            address = request.form.get('address')
            contact_number = request.form.get('contact_number')
            email = request.form.get('email')
            website = request.form.get('website')
            
            if not name:
                flash("Name is required!", "danger")
                return jsonify({"success": False, "message": "Name is required!"}), 400
            
            body = HSCodeIssueBody(
                name=name,
                address=address,
                contact_number=contact_number,
                email=email,
                website=website,
                company_id=current_user.company_id
            )
            db.session.add(body)
            db.session.commit()
            flash("Issue Body added successfully!", "success")
            return jsonify({
                "success": True, 
                "message": "Issue Body added successfully!",
                "body": {
                    "id": body.id,
                    "name": body.name,
                    "address": body.address,
                    "contact_number": body.contact_number,
                    "email": body.email,
                    "website": body.website
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding issue body: {str(e)}")
            flash("Error adding issue body: " + str(e), "danger")
            return jsonify({"success": False, "message": str(e)}), 500
    
    return render_template('hs/issue_body_form.html')

@bp.route('/issue-body/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_issue_body(id):
    if not check_hs_permission('edit'):
        abort(403)
    
    body = HSCodeIssueBody.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            address = request.form.get('address')
            contact_number = request.form.get('contact_number')
            email = request.form.get('email')
            website = request.form.get('website')
            
            if not name:
                flash("Name is required!", "danger")
                return jsonify({"success": False, "message": "Name is required!"}), 400
            
            body.name = name
            body.address = address
            body.contact_number = contact_number
            body.email = email
            body.website = website
            db.session.commit()
            flash("Issue Body updated successfully!", "success")
            return jsonify({
                "success": True, 
                "message": "Issue Body updated successfully!",
                "body": {
                    "id": body.id,
                    "name": body.name,
                    "address": body.address,
                    "contact_number": body.contact_number,
                    "email": body.email,
                    "website": body.website
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating issue body: {str(e)}")
            flash("Error updating issue body: " + str(e), "danger")
            return jsonify({"success": False, "message": str(e)}), 500
    
    return render_template('hs/issue_body_form.html', body=body)

@bp.route('/issue-body/<int:id>/delete', methods=['POST'])
@login_required
def delete_issue_body(id):
    if not check_hs_permission('delete'):
        abort(403)
    
    try:
        body = HSCodeIssueBody.query.get_or_404(id)
        
        # Check if issue body is being used by any HS code documents
        used_documents = HSCodeDocument.query.filter_by(issuing_body_id=id).first()
        if used_documents:
            flash("Cannot delete issue body. It is being used by HS code documents.", "danger")
            return jsonify({
                "success": False, 
                "message": "Cannot delete issue body. It is being used by HS code documents."
            }), 400
        
        db.session.delete(body)
        db.session.commit()
        flash("Issue Body deleted successfully!", "success")
        return jsonify({"success": True, "message": "Issue Body deleted successfully!"})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting issue body: {str(e)}")
        flash("Error deleting issue body: " + str(e), "danger")
        return jsonify({"success": False, "message": str(e)}), 500

@bp.route('/codes')
@login_required
def list_codes():
    if not check_hs_permission('access'):
        abort(403)
    
    company_id = current_user.company_id
    if current_user.id == 1:
        codes = HSCode.query.order_by(HSCode.id.desc()).all()
        categories = HSCodeCategory.query.order_by(HSCodeCategory.name).all()
        issue_bodies = HSCodeIssueBody.query.order_by(HSCodeIssueBody.name).all()
        document_categories = HSDocumentCategory.query.join(HSCodeIssueBody).order_by(HSDocumentCategory.name).all()
    else:
        codes = HSCode.query.filter_by(company_id=company_id).order_by(HSCode.id.desc()).all()
        categories = HSCodeCategory.query.filter_by(company_id=company_id).order_by(HSCodeCategory.name).all()
        issue_bodies = HSCodeIssueBody.query.filter_by(company_id=company_id).order_by(HSCodeIssueBody.name).all()
        document_categories = HSDocumentCategory.query.join(HSCodeIssueBody).filter(
            HSCodeIssueBody.company_id == company_id
        ).order_by(HSDocumentCategory.name).all()
    
    # Convert documents to dictionaries for JSON serialization
    for code in codes:
        code.documents_dict = []
        for document in code.documents:
            if current_user.id == 1:
                attachments = HSCodeDocumentAttachment.query.filter_by(
                    hs_code_document_id=document.id,
                    is_deleted=False
                ).all()
            else:
                # For non-admin users, also check company_id
                attachments = HSCodeDocumentAttachment.query.join(
                    HSCodeDocument
                ).filter(
                    HSCodeDocumentAttachment.hs_code_document_id == document.id,
                    HSCodeDocumentAttachment.is_deleted == False,
                    HSCodeDocument.company_id == current_user.company_id
                ).all()
            
            # Convert attachments to dictionaries
            attachments_dict = []
            for att in attachments:
                attachments_dict.append({
                    'id': att.id,
                    'file_name': att.file_name,
                    'file_path': att.file_path,
                    'file_size': att.file_size,
                    'file_type': att.file_type,
                    'description': att.description,
                    'uploaded_at': att.uploaded_at.isoformat() if att.uploaded_at else None,
                    'is_deleted': att.is_deleted
                })
            
            # Add this line to set sampleDocName from the first attachment, if any
            sample_doc_name = attachments_dict[0]['file_name'] if attachments_dict else ''

            # Convert document to dictionary (removed description field from HS code document)
            document_dict = {
                'id': document.id,
                'issuing_body_id': document.issuing_body_id,
                'document_category_id': document.document_category_id,
                'is_mandatory': document.is_mandatory,
                'sampleDocName': sample_doc_name,
                'issuing_body': {
                    'id': document.issuing_body.id,
                    'name': document.issuing_body.name
                } if document.issuing_body else None,
                'document_category': {
                    'id': document.document_category.id,
                    'name': document.document_category.name
                } if document.document_category else None,
                'attachments': attachments_dict
            }
            code.documents_dict.append(document_dict)
    
    return render_template(
        'hs/codes.html',
        codes=codes,
        categories=categories,
        issue_bodies=issue_bodies,
        document_categories=document_categories
    )

@bp.route('/code/new', methods=['POST'])
@login_required
def new_code():
    if not check_hs_permission('create'):
        abort(403)
    
    try:
        category_id = request.form.get('category_id')
        code_val = request.form.get('code')
        description = request.form.get('description')
        
        if not code_val or not category_id:
            flash("Category and Code are required!", "danger")
            return jsonify({"success": False, "message": "Category and Code are required!"}), 400
        
        # Create HS Code
        code_obj = HSCode(
            category_id=category_id,
            code=code_val,
            description=description,
            company_id=current_user.company_id
        )
        db.session.add(code_obj)
        db.session.flush()

        # Handle documents from JSON (updated structure without description)
        documents_json = request.form.get('documents_json')
        if documents_json:
            documents = json.loads(documents_json)
            for doc in documents:
                new_doc = HSCodeDocument(
                    hscode_id=code_obj.id,
                    company_id=code_obj.company_id,
                    issuing_body_id=doc['issuingBodyId'],
                    document_category_id=doc.get('documentCategoryId'),
                    description=None,  # Remove description field
                    is_mandatory=(doc['isMandatory'] == 'Yes')
                )
                db.session.add(new_doc)
                db.session.flush()  # Get new_doc.id

                # Link all attachments
                attachments = doc.get('attachments', [])
                for att in attachments:
                    attachment_id = att.get('attachment_id')
                    if attachment_id:
                        attachment = HSCodeDocumentAttachment.query.get(attachment_id)
                        if attachment:
                            attachment.hs_code_document_id = new_doc.id
                            db.session.add(attachment)
        
        db.session.commit()
        flash("HS Code added successfully!", "success")
        return jsonify({
            "success": True,
            "message": "HS Code added successfully!",
            "code": {
                "id": code_obj.id,
                "code": code_obj.code,
                "description": code_obj.description,
                "category_id": code_obj.category_id
            }
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding HS code: {str(e)}")
        flash("Error adding HS code: " + str(e), "danger")
        return jsonify({"success": False, "message": str(e)}), 500

@bp.route('/code/<int:id>/edit', methods=['POST'])
@login_required
def edit_code(id):
    if not check_hs_permission('edit'):
        abort(403)
    
    try:
        code_obj = HSCode.query.get_or_404(id)
        
        # Update HSCode master details
        code_obj.category_id = request.form.get('category_id')
        code_obj.code = request.form.get('code')
        code_obj.description = request.form.get('description')
        
        # Handle documents from JSON - updated structure without description
        documents_json = request.form.get('documents_json')
        if documents_json:
            form_documents = json.loads(documents_json)
            
            # Get existing documents
            existing_documents = {doc.id: doc for doc in code_obj.documents}
            form_document_ids = {doc.get('documentId') for doc in form_documents if doc.get('documentId')}
            
            # Delete documents that are not in the form anymore
            for doc_id, doc in existing_documents.items():
                if doc_id not in form_document_ids:
                    db.session.delete(doc)
            
            # Process form documents
            for form_doc in form_documents:
                doc_id = form_doc.get('documentId')
                
                if doc_id and doc_id in existing_documents:
                    # Update existing document
                    doc_to_update = existing_documents[doc_id]
                    doc_to_update.issuing_body_id = form_doc['issuingBodyId']
                    doc_to_update.document_category_id = form_doc.get('documentCategoryId')
                    doc_to_update.description = None  # Remove description field
                    doc_to_update.is_mandatory = (form_doc['isMandatory'] == 'Yes')
                else:
                    # Create new document
                    new_doc = HSCodeDocument(
                        hscode_id=code_obj.id,
                        company_id=code_obj.company_id,
                        issuing_body_id=form_doc['issuingBodyId'],
                        document_category_id=form_doc.get('documentCategoryId'),
                        description=None,  # Remove description field
                        is_mandatory=(form_doc['isMandatory'] == 'Yes')
                    )
                    db.session.add(new_doc)
                    db.session.flush()  # Get ID for new document
                    doc_to_update = new_doc
                
                # Link attachments
                for att_data in form_doc.get('attachments', []):
                    attachment_id = att_data.get('attachment_id')
                    if attachment_id:
                        attachment = HSCodeDocumentAttachment.query.get(attachment_id)
                        if attachment and attachment.hs_code_document_id != doc_to_update.id:
                            attachment.hs_code_document_id = doc_to_update.id
                            db.session.add(attachment)

        db.session.commit()
        flash("HS Code updated successfully!", "success")
        return jsonify({
            "success": True,
            "message": "HS Code updated successfully!",
            "code": {
                "id": code_obj.id,
                "code": code_obj.code,
                "description": code_obj.description,
                "category_id": code_obj.category_id
            }
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating HS code {id}: {str(e)}")
        flash(f"Error updating HS code {id}: " + str(e), "danger")
        return jsonify({"success": False, "message": str(e)}), 500
    


@bp.route('/document/<int:id>/delete', methods=['POST'])
@login_required
def delete_document(id):
    if not check_hs_permission('delete'):
        return jsonify({"success": False, "message": "Permission denied."}), 403
    
    try:
        document = HSCodeDocument.query.get_or_404(id)
        
        # Security check: ensure the document belongs to the user's company (if not admin)
        if current_user.id != 1 and document.company_id != current_user.company_id:
            return jsonify({"success": False, "message": "Forbidden."}), 403
            
        db.session.delete(document)
        db.session.commit()
        flash("Document deleted successfully!", "success")
        return jsonify({"success": True, "message": "Document deleted successfully!"})
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting HS code document {id}: {str(e)}")
        flash(f"Error deleting HS code document {id}: " + str(e), "danger")
        return jsonify({"success": False, "message": str(e)}), 500

@bp.route('/code/<int:id>/delete', methods=['POST'])
@login_required
def delete_code(id):
    if not check_hs_permission('delete'):
        abort(403)
    
    try:
        code_obj = HSCode.query.get_or_404(id)
        db.session.delete(code_obj)
        db.session.commit()
        flash("HS Code deleted successfully!", "success")
        return jsonify({"success": True, "message": "HS Code deleted successfully!"})
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting HS code: {str(e)}")
        flash("Error deleting HS code: " + str(e), "danger")
        return jsonify({"success": False, "message": str(e)}), 500

# File handling routes for attachments
@bp.route('/attachment/<int:id>/download')
@login_required
def download_attachment(id):
    if not check_hs_permission('access'):
        abort(403)
    
    try:
        attachment = HSCodeDocumentAttachment.query.get_or_404(id)
        
        # Check if file exists
        if not os.path.exists(attachment.file_path):
            return jsonify({"success": False, "message": "File not found!"}), 404
        
        return send_file(
            attachment.file_path,
            as_attachment=True,
            download_name=attachment.file_name
        )
    except Exception as e:
        current_app.logger.error(f"Error downloading attachment: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@bp.route('/attachment/<int:id>/view')
@login_required
def view_attachment(id):
    """SECURE: View attachment through app proxy (supports both S3 and local files)"""
    if not check_hs_permission('access'):
        abort(403)
    
    try:
        
        attachment = HSCodeDocumentAttachment.query.get_or_404(id)
        
        # Handle S3-stored files
        if attachment.cloud_provider == 's3' and attachment.cloud_path:
            try:
                # Normalize the S3 key path
                s3_key = attachment.cloud_path.replace("\\", "/")
                
                print(f"Serving S3 attachment securely: {s3_key}")
                
                # REMOVED: Presigned URL generation and redirect
                # s3_bucket = current_app.config['S3_BUCKET_NAME']
                # url = get_s3_url(s3_bucket, attachment.cloud_path)
                # return redirect(url)
                
                # ADDED: Direct secure serving through app proxy
                return serve_s3_file(s3_key)
                
            except ClientError as e:
                current_app.logger.error(f"S3 error viewing attachment {id}: {str(e)}")
                print(f"S3 error viewing attachment: {str(e)}")
                
                if e.response['Error']['Code'] == 'NoSuchKey':
                    return jsonify({
                        "success": False, 
                        "message": "File not found in cloud storage"
                    }), 404
                else:
                    return jsonify({
                        "success": False, 
                        "message": "Error accessing file from cloud storage"
                    }), 500
        
        # Handle local files (legacy support)
        elif attachment.file_path:
            print(f"Serving local attachment: {attachment.file_path}")
            
            if not os.path.exists(attachment.file_path):
                return jsonify({
                    "success": False, 
                    "message": "Local file not found"
                }), 404
            
            # Serve local file directly (already secure)
            return send_file(attachment.file_path)
        
        # No valid file path found
        else:
            return jsonify({
                "success": False, 
                "message": "No valid file path found for this attachment"
            }), 404
    
    except Exception as e:
        current_app.logger.error(f"Error viewing attachment {id}: {str(e)}")
        print(f"Error viewing attachment: {str(e)}")
        return jsonify({
            "success": False, 
            "message": "An error occurred while accessing the file"
        }), 500


@bp.route('/attachment/<int:id>/delete', methods=['POST'])
@login_required
def delete_attachment(id):
    if not check_hs_permission('delete'):
        abort(403)
    
    try:
        attachment = HSCodeDocumentAttachment.query.get_or_404(id)
        
        # Soft delete
        attachment.is_deleted = True
        attachment.deleted_by = current_user.id
        attachment.deleted_at = datetime.utcnow()
        
        db.session.commit()
        flash("Attachment deleted successfully!", "success")
        return jsonify({"success": True, "message": "Attachment deleted successfully"})
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting attachment: {str(e)}")
        flash("Error deleting attachment: " + str(e), "danger")
        return jsonify({"success": False, "message": str(e)}), 500

@bp.route('/upload-attachment', methods=['POST'])
@login_required
def upload_attachment():
    if not check_hs_permission('create'):
        abort(403)
    
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "message": "No file provided"}), 400
        
        file = request.files['file']
        document_id = request.form.get('document_id')
        description = request.form.get('description', '')
        
        if file.filename == '':
            return jsonify({"success": False, "message": "No file selected"}), 400
        
        # Allow document_id to be optional for initial upload
        if not document_id or document_id == '':
            document_id = None
        
        # S3 bucket and key
        s3_bucket = current_app.config['S3_BUCKET_NAME']  # Set this in your config
        s3_key = f"hs_documents/{uuid.uuid4()}_{secure_filename(file.filename)}"

        # Upload to S3
        file.seek(0)
        upload_success = upload_file_to_s3(file, s3_bucket, s3_key)
        if not upload_success:
            return jsonify({"success": False, "message": "Failed to upload to S3"}), 500

        # Store S3 info in DB
        attachment = HSCodeDocumentAttachment(
            hs_code_document_id=document_id,
            file_name=file.filename,
            file_path=s3_key,  # Store S3 key, not local path
            file_size=file.content_length or 0,
            file_type=file.content_type,
            description=description,
            uploaded_by=current_user.id,
            cloud_provider='s3',
            cloud_file_id=None,
            cloud_path=s3_key
        )
        db.session.add(attachment)
        db.session.commit()

        # Generate presigned URL for viewing
        file_url = get_s3_url(s3_bucket, s3_key)

        return jsonify({
            "success": True,
            "message": "File uploaded successfully",
            "attachment": {
                "id": attachment.id,
                "file_name": file.filename,
                "file_size": attachment.file_size,
                "file_url": file_url
            }
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error uploading attachment: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


# Document Categories CRUD Routes - Updated with Issuing Body relationship
@bp.route('/document-categories', strict_slashes=False)
@login_required
def list_document_categories():
    if not check_hs_permission('access'):
        abort(403)
    
    if current_user.id == 1:
        document_categories = HSDocumentCategory.query.join(HSCodeIssueBody).all()
        issue_bodies = HSCodeIssueBody.query.all()
    else:
        document_categories = HSDocumentCategory.query.join(HSCodeIssueBody).filter(
            HSCodeIssueBody.company_id == current_user.company_id
        ).all()
        issue_bodies = HSCodeIssueBody.query.filter_by(company_id=current_user.company_id).all()
    
    return render_template('hs/document_categories.html', 
                         document_categories=document_categories, 
                         issue_bodies=issue_bodies)

@bp.route('/document-category/new', methods=['GET', 'POST'])
@login_required
def new_document_category():
    if not check_hs_permission('create'):
        abort(403)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            description = request.form.get('description')
            issuing_body_id = request.form.get('issuing_body_id')
            
            if not name:
                flash("Name is required!", "danger")
                return jsonify({"success": False, "message": "Name is required!"}), 400
            
            if not issuing_body_id:
                flash("Issuing Body is required!", "danger")
                return jsonify({"success": False, "message": "Issuing Body is required!"}), 400
            
            # Verify issuing body belongs to user's company (if not admin)
            if current_user.id != 1:
                issuing_body = HSCodeIssueBody.query.filter_by(
                    id=issuing_body_id, 
                    company_id=current_user.company_id
                ).first()
                if not issuing_body:
                    flash("Invalid Issuing Body!", "danger")
                    return jsonify({"success": False, "message": "Invalid Issuing Body!"}), 400
            
            document_category = HSDocumentCategory(
                name=name, 
                description=description,
                issuing_body_id=issuing_body_id
            )
            db.session.add(document_category)
            db.session.commit()
            flash("Document Category added successfully!", "success")
            return jsonify({
                "success": True, 
                "message": "Document Category added successfully!",
                "document_category": {
                    "id": document_category.id,
                    "name": document_category.name,
                    "description": document_category.description,
                    "issuing_body_id": document_category.issuing_body_id
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding document category: {str(e)}")
            flash("Error adding document category: " + str(e), "danger")
            return jsonify({"success": False, "message": str(e)}), 500
    
    # For GET request
    if current_user.id == 1:
        issue_bodies = HSCodeIssueBody.query.all()
    else:
        issue_bodies = HSCodeIssueBody.query.filter_by(company_id=current_user.company_id).all()
    
    return render_template('hs/document_category_form.html', issue_bodies=issue_bodies)

@bp.route('/document-category/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_document_category(id):
    if not check_hs_permission('edit'):
        abort(403)
    
    document_category = HSDocumentCategory.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            description = request.form.get('description')
            issuing_body_id = request.form.get('issuing_body_id')
            
            if not name:
                flash("Name is required!", "danger")
                return jsonify({"success": False, "message": "Name is required!"}), 400
            
            if not issuing_body_id:
                flash("Issuing Body is required!", "danger")
                return jsonify({"success": False, "message": "Issuing Body is required!"}), 400
            
            # Verify issuing body belongs to user's company (if not admin)
            if current_user.id != 1:
                issuing_body = HSCodeIssueBody.query.filter_by(
                    id=issuing_body_id, 
                    company_id=current_user.company_id
                ).first()
                if not issuing_body:
                    flash("Invalid Issuing Body!", "danger")
                    return jsonify({"success": False, "message": "Invalid Issuing Body!"}), 400
            
            document_category.name = name
            document_category.description = description
            document_category.issuing_body_id = issuing_body_id
            db.session.commit()
            flash("Document Category updated successfully!", "success")
            return jsonify({
                "success": True, 
                "message": "Document Category updated successfully!",
                "document_category": {
                    "id": document_category.id,
                    "name": document_category.name,
                    "description": document_category.description,
                    "issuing_body_id": document_category.issuing_body_id
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating document category: {str(e)}")
            flash("Error updating document category: " + str(e), "danger")
            return jsonify({"success": False, "message": str(e)}), 500
    
    # For GET request
    if current_user.id == 1:
        issue_bodies = HSCodeIssueBody.query.all()
    else:
        issue_bodies = HSCodeIssueBody.query.filter_by(company_id=current_user.company_id).all()
    
    return render_template('hs/document_category_form.html', 
                         document_category=document_category, 
                         issue_bodies=issue_bodies)

# Add new route to get document categories by issuing body (AJAX endpoint)
@bp.route('/api/document-categories/<int:issuing_body_id>')
@login_required
def get_document_categories_by_issuing_body(issuing_body_id):
    if not check_hs_permission('access'):
        abort(403)
    
    try:
        if current_user.id == 1:
            categories = HSDocumentCategory.query.filter_by(issuing_body_id=issuing_body_id).all()
        else:
            # Ensure the issuing body belongs to the user's company
            issuing_body = HSCodeIssueBody.query.filter_by(
                id=issuing_body_id, 
                company_id=current_user.company_id
            ).first()
            if not issuing_body:
                return jsonify({"success": False, "message": "Invalid Issuing Body"}), 403
            
            categories = HSDocumentCategory.query.filter_by(issuing_body_id=issuing_body_id).all()
        
        categories_list = []
        for cat in categories:
            categories_list.append({
                "id": cat.id,
                "name": cat.name,
                "description": cat.description
            })
        
        return jsonify({
            "success": True,
            "categories": categories_list
        })
    except Exception as e:
        current_app.logger.error(f"Error fetching document categories: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route('/document-category/<int:id>/delete', methods=['POST'])
@login_required
def delete_document_category(id):
    if not check_hs_permission('delete'):
        abort(403)
    
    try:
        document_category = HSDocumentCategory.query.get_or_404(id)
        
        # Check if document category is being used by any HS code documents
        used_documents = HSCodeDocument.query.filter_by(document_category_id=id).first()
        if used_documents:
            flash("Cannot delete document category. It is being used by HS code documents.", "danger")
            return jsonify({
                "success": False, 
                "message": "Cannot delete document category. It is being used by HS code documents."
            }), 400
        
        db.session.delete(document_category)
        db.session.commit()
        flash("Document Category deleted successfully!", "success")
        return jsonify({"success": True, "message": "Document Category deleted successfully!"})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting document category: {str(e)}")
        flash("Error deleting document category: " + str(e), "danger")
        return jsonify({"success": False, "message": str(e)}), 500
    