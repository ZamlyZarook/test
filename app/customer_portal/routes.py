from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
    current_app,
    send_file,
    json,
    abort
)
from app import db
from flask_login import login_required, current_user
from functools import wraps
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
    Runner,
    WharfProfile,
    Branch,
    ShipCategory,
    ShipCatDocument,
    Order,
    OrderItem,
    OrderDocument,
    DocumentStatus,
    ShipDocumentEntryMaster,
    ShipDocumentEntryAttachment,
    ChatThread,
    ChatMessage,
    ChatParticipant,
    ChatAttachment,
    ShipDocumentHistory,
    OrderShipment,
    ShipCatDocumentAICheck,
    ExportContainer,
    ImportContainer,
    ShipDocumentEntryDocument,
    IncomeExpense,
    ShipmentExpense,
    InvoiceHeader,
    InvoiceDetail,
    EntryAssignmentHistory,
    EntryClearingAgentHistory,
    EntryClearingCompanyHistory,
    AgentAssignment,
    CompanyAssignment,
    ShipmentTypeBase
    )
from app.models.demurrage import DemurrageRateCard, CompanyDemurrageConfig, DemurrageCalculationDetail, DemurrageReasons, ShipmentDemurrage, ShipmentDemurrageAttachment, ShipmentDemurrageBearer, DemurrageRateCardTier
from app.models.po import PODetail,POHeader, POMaterial, POOrderUnit, POSupplier, ShipmentItem, MaterialHSDocuments
from app.models.hs import HSCode, HSCodeCategory, HSCodeDocument, HSCodeDocumentAttachment, HSCodeIssueBody, HSDocumentCategory
from app.models.task_management import Project, Task, TaskVisibility, TaskPriority, ProjectTaskStatus, ProjectMember
from app.models.user import User, CountryMaster, CurrencyMaster
from app.models.company import CompanyInfo
from app.validation_service import extract_text_from_pdf, send_to_deepseek, validate_using_ai, extract_text_from_docx, extract_text_from_image, extract_text_from_file, get_semantic_similarity, get_document_type, extract_content_from_text, validate_document, extract_invoice_json
from .forms import ShipDocumentEntryForm
from datetime import datetime, timedelta
from app.email import send_email, send_async_email
from werkzeug.utils import secure_filename
import os
import boto3
import uuid
import tempfile
from app.utils_cha.s3_utils import (
    upload_file_to_s3,
    get_s3_url,
    delete_file_from_s3,
    get_s3_client,
    get_secure_document_url,
    serve_s3_file
)
from decimal import Decimal

from app.customer_portal import bp
from sqlalchemy.sql import and_, or_, cast
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from io import BytesIO
from flask import Response
import time
from botocore.exceptions import ClientError
import requests
from app.utils import get_sri_lanka_time

def customer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth.login"))
        if current_user.is_super_admin != 3:
            flash("Access denied. This page is for customers only.", "danger")
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)

    return decorated_function


def get_s3_client():
    return boto3.client(
        's3',
        aws_access_key_id=current_app.config['AWS_ACCESS_KEY'],
        aws_secret_access_key=current_app.config['AWS_SECRET_KEY'],
        region_name=current_app.config['AWS_REGION']
    )

def download_s3_file(file_key):
    """Download file from S3 to a temporary file using the technique from the upload route"""
    try:
        # Create temporary directory if it doesn't exist
        temp_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Create temporary file path
        temp_file_path = os.path.join(temp_dir, os.path.basename(file_key))
        
        # Initialize S3 client with explicit credentials
        s3_client = boto3.client(
            's3',
            aws_access_key_id=current_app.config["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=current_app.config["AWS_SECRET_ACCESS_KEY"]
        )
        
        # Download file from S3 to local temp file
        s3_client.download_file(
            current_app.config["S3_BUCKET_NAME"],
            file_key,
            temp_file_path
        )
        
        return temp_file_path
    except Exception as e:
        print(f"Error downloading file from S3: {str(e)}")
        import traceback
        traceback.print_exc()
        return None



def send_document_validation_results_email(customer_id, entry_id=None):
    """
    Send validation results email to customer for their documents.
    If entry_id is provided, only send results for documents in that specific entry.
    Otherwise, send results for all recently validated documents across entries.
    
    Fixed issues:
    1. Now sends emails for ALL validation statuses (not just accepted)
    2. Prevents duplicate emails by using a global tracking mechanism
    """
    try:
        # Get customer information
        customer = Customer.query.get(customer_id)
        if not customer or not customer.email:
            print(f"Customer not found or email missing for ID: {customer_id}")
            return False
        
        # Create a file-based tracking system to prevent duplicate emails
        tracking_dir = os.path.join(current_app.config.get("UPLOAD_FOLDER", "/tmp"), "email_tracking")
        os.makedirs(tracking_dir, exist_ok=True)
        
        # If entry_id is specified, only process that entry
        if entry_id:
            # Check if we've already sent an email for this entry recently
            tracking_file = os.path.join(tracking_dir, f"entry_{entry_id}_emailed.txt")
            if os.path.exists(tracking_file):
                # Check if the file is less than 10 minutes old
                file_time = os.path.getmtime(tracking_file)
                current_time = time.time()
                if current_time - file_time < 600:  # 10 minutes in seconds
                    print(f"Email for entry {entry_id} was already sent in the last 10 minutes. Skipping.")
                    return False
            
            # Build query for only the specified entry
            entries_to_process = [entry_id]
        else:
            # Get all entries for this customer with documents validated in the last 24 hours
            yesterday = get_sri_lanka_time() - timedelta(days=1)
            
            # Find all entries with recently validated documents
            entries_with_validated_docs = db.session.query(ShipDocumentEntryMaster.id).distinct().join(
                ShipDocumentEntryAttachment, 
                ShipDocumentEntryAttachment.shipDocEntryMasterID == ShipDocumentEntryMaster.id
            ).filter(
                ShipDocumentEntryMaster.customer_id == customer_id,
                ShipDocumentEntryAttachment.ai_validated != 0,  # Any status except pending
                or_(
                    ShipDocumentEntryAttachment.updated_at >= yesterday,
                    ShipDocumentEntryAttachment.docAccepteDate >= yesterday
                )
            ).all()
            
            entries_to_process = [entry[0] for entry in entries_with_validated_docs]
        
        if not entries_to_process:
            print(f"No entries with validated documents found for customer ID: {customer_id}")
            return False
        
        # Process each entry and send a separate email for each
        emails_sent = 0
        
        for current_entry_id in entries_to_process:
            try:
                entry = ShipDocumentEntryMaster.query.get(current_entry_id)
                if not entry:
                    print(f"Entry {current_entry_id} not found")
                    continue
                
                # Check if all documents in this entry have been validated
                total_docs_count = ShipDocumentEntryAttachment.query.filter_by(
                    shipDocEntryMasterID=current_entry_id
                ).count()
                
                validated_docs_count = ShipDocumentEntryAttachment.query.filter(
                    ShipDocumentEntryAttachment.shipDocEntryMasterID == current_entry_id,
                    ShipDocumentEntryAttachment.ai_validated != 0  # Any non-pending status
                ).count()
                
                print(f"Entry {current_entry_id}: {validated_docs_count} of {total_docs_count} documents validated")
                
                # Only send email if all documents have been validated
                if validated_docs_count == total_docs_count:
                    # Get all validated documents for this entry
                    validated_docs = ShipDocumentEntryAttachment.query.filter(
                        ShipDocumentEntryAttachment.shipDocEntryMasterID == current_entry_id,
                        ShipDocumentEntryAttachment.ai_validated != 0  # Include all validation statuses
                    ).all()
                    
                    # Set up the entries_data dict for just this entry
                    entries_data = {
                        current_entry_id: {
                            'id': entry.id,
                            'docserial': entry.docserial,
                            'shipment_type': entry.shipment_type.shipment_name if entry.shipment_type else "Unknown",
                            'ship_category': entry.ship_category_rel.catname if entry.ship_category_rel else "Unknown",
                            'documents': []
                        }
                    }
                    
                    # Process document validation results
                    for doc in validated_docs:
                        # Log document info for debugging
                        print(f"Processing document {doc.id}: {doc.description}, validation status: {doc.ai_validated}")
                        
                        validation_data = {
                            'id': doc.id,
                            'description': doc.description,
                            'is_mandatory': doc.isMandatory,
                            'status': 'Accepted' if doc.ai_validated == 1 else 'Rejected',
                            'match_percentage': doc.validation_percentage or 0,
                            'document_type_similarity': doc.document_similarity_percentage or 0,
                            'similarity_message': doc.similarity_message,
                            'validation_details': {},
                            'validation_status': doc.ai_validated  # The actual validation status code
                        }
                        
                        # Parse validation results for more details
                        if doc.validation_results:
                            try:
                                validation_results = json.loads(doc.validation_results)
                                validation_data['validation_details'] = validation_results
                            except:
                                validation_data['validation_details'] = {}
                                
                        entries_data[current_entry_id]['documents'].append(validation_data)
                    
                    # Send email for this entry
                    subject = f"Document Validation Results - {entry.docserial}"
                    send_email(
                        subject=subject,
                        recipient=customer.email,
                        template='email/document_validation_results.html',
                        customer=customer,
                        entries=entries_data,
                        current_year=get_sri_lanka_time().year
                    )
                    
                    # Create tracking file to prevent duplicate emails
                    tracking_file = os.path.join(tracking_dir, f"entry_{current_entry_id}_emailed.txt")
                    with open(tracking_file, 'w') as f:
                        f.write(f"Email sent at {get_sri_lanka_time().isoformat()}")
                    
                    emails_sent += 1
                    print(f"Validation results email sent to {customer.email} for entry {current_entry_id}")
                else:
                    print(f"Skipping email for entry {current_entry_id} - not all documents validated yet")
            except Exception as entry_error:
                print(f"Error processing entry {current_entry_id}: {str(entry_error)}")
                continue
        
        return emails_sent > 0
        
    except Exception as e:
        print(f"Error sending validation results email: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    
# AI VALIDATION STATUS
# 0 - Not validated yet
# 1 - Accepted
# 2 - Rejected
# 3 - No Sample document found
# 4 - Sample Document text extraction failed
# 5 - Submitted document text extraction failed
# 6 - Both document text extraction failed
# 7 - Other errors in validation
# 8 - Document Type Mismatch


def process_document_validation(document):
    """Process validation for a single document with dynamic thresholds"""
    # print("\n" + "="*80)
    # print(f"STARTING VALIDATION FOR DOCUMENT ID: {document.id}")
    # print("="*80)
    
    temp_files = []  # Keep track of temporary files to clean up
    
    try:
        # Get the ShipCatDocument configuration for this document
        sample_document = ShipCatDocument.query.filter_by(
            id=document.ship_cat_document_id
        ).first()
        
        if not sample_document or not sample_document.sample_file_path:
            # No sample document to compare against
            print(f"No sample document available for comparison. Setting ai_validated=3")
            document.ai_validated = 3  # No sample available
            db.session.commit()
            return {
                "success": True,
                "message": "No sample document available for comparison",
                "status": "no_sample"
            }
        
        # Get dynamic thresholds from database
        confidence_threshold = sample_document.confidence_level / 100  # Convert percentage to decimal
        content_similarity_threshold = sample_document.content_similarity  # Use as percentage
        ai_validate_enabled = sample_document.ai_validate == 1
        
        # print(f"Found sample document: {sample_document.description}")
        # print(f"Using dynamic thresholds: Confidence={confidence_threshold*100}%, Content Similarity={content_similarity_threshold}%")
        # print(f"AI Validation enabled: {ai_validate_enabled}")
        
        if not ai_validate_enabled:
            # print(f"AI validation is disabled for this document type. Skipping validation.")
            document.ai_validated = 0  # Keep as pending since AI validation is not enabled
            db.session.commit()
            return {
                "success": True,
                "message": "AI validation is disabled for this document type",
                "status": "ai_disabled"
            }
        
        # Download the submitted document from S3
        # print(f"Downloading submitted document from S3: {document.attachement_path}")
        submitted_file_path = download_s3_file(document.attachement_path)
        
        if not submitted_file_path:
            print(f"FAILED to download submitted document from S3")
            return {
                "success": False,
                "message": f"Failed to download submitted document: {document.attachement_path}"
            }
        
        temp_files.append(submitted_file_path)
        # print(f"Successfully downloaded submitted document to: {submitted_file_path}")
        
        # Download the sample document from S3
        # print(f"Downloading sample document from S3: {sample_document.sample_file_path}")
        sample_file_path = download_s3_file(sample_document.sample_file_path)
        
        if not sample_file_path:
            print(f"FAILED to download sample document from S3")
            # Clean up temporary files
            for file_path in temp_files:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
            return {
                "success": False,
                "message": f"Failed to download sample document: {sample_document.sample_file_path}"
            }
        
        temp_files.append(sample_file_path)
        # print(f"Successfully downloaded sample document to: {sample_file_path}")
        
        # Extract text from both documents
        # print(f"Extracting text from submitted document")
        submitted_text = extract_text_from_file(submitted_file_path)
        
        # print(f"Extracting text from sample document")
        sample_text = extract_text_from_file(sample_file_path)
        
        # Clean up temporary files early to free space
        for file_path in temp_files:
            if os.path.exists(file_path):
                print(f"Removing temporary file: {file_path}")
                os.remove(file_path)
        
        temp_files = []  # Reset the list
            
        if not submitted_text and not sample_text:
            print(f"Failed to extract text from BOTH documents")
            document.ai_validated = 6  # Both text extractions failed
            document.similarity_message = "Failed to extract text from both submitted and sample documents. Please check file formats."
            db.session.commit()
            return {
                "success": False,
                "message": "Failed to extract text from both documents"
            }
        elif not submitted_text:
            print(f"Failed to extract text from SUBMITTED document")
            document.ai_validated = 5  # Submitted document text extraction failed
            document.similarity_message = "Failed to extract text from your submitted document. Please check the file format and ensure it contains extractable text."
            db.session.commit()
            return {
                "success": False,
                "message": "Failed to extract text from submitted document"
            }
        elif not sample_text:
            print(f"Failed to extract text from SAMPLE document")
            document.ai_validated = 4  # Sample document text extraction failed
            document.similarity_message = "Failed to extract text from the sample document. This is a system issue. Please contact support."
            db.session.commit()
            return {
                "success": False,
                "message": "Failed to extract text from sample document"
            }
        
        print(f"Successfully extracted text: Submitted ({len(submitted_text)} chars), Sample ({len(sample_text)} chars)")
        
        # Identify document types
        print("Identifying document types...")
        submitted_doc_type = get_document_type(submitted_text)
        sample_doc_type = get_document_type(sample_text)
        
        print(f"Submitted document type: {submitted_doc_type['type']} with confidence {submitted_doc_type['confidence']:.2%}")
        print(f"Sample document type: {sample_doc_type['type']} with confidence {sample_doc_type['confidence']:.2%}")
        
        # Check document type compatibility with dynamic threshold
        document_type_message = ""
        document_type_valid = True
        document_type_similarity = 1.0  # Default to full match
        
        print(f"Using dynamic confidence threshold: {confidence_threshold:.1%}")
        
        if not submitted_doc_type["type"] or not sample_doc_type["type"]:
            document_type_valid = False
            document_type_message = "Could not determine document type with sufficient confidence."
            document_type_similarity = 0.0
            print(f"Document type validation warning: {document_type_message}")
        elif submitted_doc_type["type"] != sample_doc_type["type"]:
            document_type_valid = False
            document_type_message = (
                f"Document type mismatch. Sample document is a {sample_doc_type['type']} "
                f"(confidence: {sample_doc_type['confidence']:.2%}), but submitted document appears to be a "
                f"{submitted_doc_type['type']} (confidence: {submitted_doc_type['confidence']:.2%})."
            )
            document_type_similarity = 0.0
            print(f"Document type validation warning: {document_type_message}")
        elif submitted_doc_type["confidence"] < confidence_threshold or sample_doc_type["confidence"] < confidence_threshold:
            document_type_valid = False
            document_type_message = (
                f"Low confidence in document type detection (threshold: {confidence_threshold:.1%}). "
                f"Sample document: {sample_doc_type['confidence']:.2%}, "
                f"Submitted document: {submitted_doc_type['confidence']:.2%}."
            )
            document_type_similarity = min(submitted_doc_type["confidence"], sample_doc_type["confidence"])
            print(f"Document type validation warning: {document_type_message}")
        else:
            print(f"Document type validation passed: {submitted_doc_type['type']} with confidence {submitted_doc_type['confidence']:.2%}")
        

        # Handle document type mismatch and exit early
        if not document_type_valid:
            print(f"Document type mismatch detected. Setting ai_validated=8 and stopping validation")
            document.ai_validated = 8  # Document type mismatch
            document.document_similarity_percentage = document_type_similarity * 100  # Convert to percentage
            document.similarity_message = document_type_message
            
            # Create validation results structure with document type info only
            validation_results_dict = {
                "document_type": {
                    "expected_type": sample_doc_type["type"],
                    "detected_type": submitted_doc_type["type"],
                    "expected_confidence": sample_doc_type["confidence"],
                    "detected_confidence": submitted_doc_type["confidence"],
                    "is_valid": document_type_valid,
                    "message": document_type_message,
                    "similarity": document_type_similarity,
                    "threshold": confidence_threshold  # Include threshold in results
                }
            }
            document.validation_results = json.dumps(validation_results_dict)
            
            # Commit changes to database
            db.session.commit()
            print(f"Database updated with document type mismatch status")
            
            # print("="*80)
            # print(f"VALIDATION STOPPED DUE TO DOCUMENT TYPE MISMATCH FOR DOCUMENT ID: {document.id}")
            # print("="*80 + "\n")
            
            return {
                "success": True,
                "message": "Document validation stopped due to document type mismatch",
                "results": {
                    "document_similarity": 0,
                    "match_percentage": 0,
                    "validation_status": 8,
                    "document_type": {
                        "expected": sample_doc_type["type"],
                        "detected": submitted_doc_type["type"],
                        "expected_confidence": sample_doc_type["confidence"],
                        "detected_confidence": submitted_doc_type["confidence"],
                        "is_valid": document_type_valid,
                        "message": document_type_message,
                        "similarity": document_type_similarity,
                        "threshold": confidence_threshold
                    }
                }
            }

        # Use the existing validate_document function for content comparison with dynamic threshold
        print(f"Starting document content validation with similarity threshold: {content_similarity_threshold}%")
        validation_result = validate_document(submitted_text, sample_text, sample_document)
        
        # Extract structured data if needed
        try:
            print("Extracting structured data")
            extracted_content = send_to_deepseek(submitted_text) if 'send_to_deepseek' in globals() else {}
        except Exception as extract_error:
            print(f"Error extracting structured data: {str(extract_error)}")
            extracted_content = {}
        
        # Update the document record with validation results
        print(f"Updating database with validation results")
        
        # Get validation results or initialize empty dict
        validation_results_dict = validation_result.get("validation_results", {})
        
        # Add document type validation info to validation results
        validation_results_dict["document_type"] = {
            "expected_type": sample_doc_type["type"],
            "detected_type": submitted_doc_type["type"],
            "expected_confidence": sample_doc_type["confidence"],
            "detected_confidence": submitted_doc_type["confidence"],
            "is_valid": document_type_valid,
            "message": document_type_message,
            "similarity": document_type_similarity,
            "threshold": confidence_threshold  # Include threshold in results
        }
        
        # Store results in database
        document.validation_results = json.dumps(validation_results_dict)
        document.extracted_content = json.dumps(extracted_content)
        document.validation_percentage = validation_result.get("match_percentage", 0)
        
        document.document_similarity_percentage = document_type_similarity * 100  # Convert to percentage
        document.similarity_message = document_type_message if not document_type_valid else None
        
        # Set validation status based on dynamic content similarity threshold
        match_percentage = validation_result.get("match_percentage", 0)
        print(f"Match percentage: {match_percentage}% (Threshold: {content_similarity_threshold}%)")
        
        if validation_result.get("error", False):
            print(f"Validation error: {validation_result.get('message', 'Unknown error')}")
            document.ai_validated = 7  # Rejected due to error
        elif match_percentage >= content_similarity_threshold:  # Use dynamic threshold
            print(f"Document ACCEPTED: Match percentage >= {content_similarity_threshold}%")
            document.ai_validated = 1  # Accepted
        else:
            print(f"Document REJECTED: Match percentage ({match_percentage}%) < {content_similarity_threshold}%")
            document.ai_validated = 2  # Rejected
            
        db.session.commit()
        print(f"Database updated successfully")

        entry = ShipDocumentEntryMaster.query.get(document.shipDocEntryMasterID)
        
        # Check if this document is the last one to be validated in this entry
        if entry:
            # Get count of all documents in this entry
            total_docs = ShipDocumentEntryAttachment.query.filter_by(
                shipDocEntryMasterID=entry.id
            ).count()
            
            # Get count of documents that have been validated (ai_validated != 0)
            validated_docs = ShipDocumentEntryAttachment.query.filter(
                ShipDocumentEntryAttachment.shipDocEntryMasterID==entry.id,
                ShipDocumentEntryAttachment.ai_validated!=0
            ).count()
            
            print(f"Validation status for entry {entry.id}: {validated_docs} of {total_docs} documents validated")
            
            # If all documents have been validated, send the email
            if validated_docs == total_docs and entry.customer_id:
                print(f"All documents for entry {entry.id} have been validated. Sending email to customer {entry.customer_id}")
                send_document_validation_results_email(entry.customer_id, entry.id)

        
        # print("="*80)
        # print(f"VALIDATION COMPLETED for DOCUMENT ID: {document.id}")
        # print(f"Dynamic thresholds used - Confidence: {confidence_threshold*100}%, Content: {content_similarity_threshold}%")
        # print("="*80 + "\n")
        
        return {
            "success": True,
            "message": "Document validation completed",
            "results": {
                "document_similarity": validation_result.get("document_similarity", 0),
                "match_percentage": match_percentage,
                "validation_status": document.ai_validated,
                "thresholds": {
                    "confidence_level": confidence_threshold * 100,  # Convert back to percentage for display
                    "content_similarity": content_similarity_threshold
                },
                "document_type": {
                    "expected": sample_doc_type["type"],
                    "detected": submitted_doc_type["type"],
                    "expected_confidence": sample_doc_type["confidence"],
                    "detected_confidence": submitted_doc_type["confidence"],
                    "is_valid": document_type_valid,
                    "message": document_type_message if document_type_message else "Document type is valid",
                    "similarity": document_type_similarity,
                    "threshold": confidence_threshold
                },
                "field_validation": validation_results_dict,
                "error": validation_result.get("error", False),
                "error_message": validation_result.get("message", "")
            }
        }
        
    except Exception as e:
        # Clean up any remaining temporary files
        for file_path in temp_files:
            if os.path.exists(file_path):
                os.remove(file_path)
            
        print(f"ERROR in document validation: {str(e)}")
        import traceback
        traceback.print_exc()
        print("="*80 + "\n")
        return {"success": False, "message": str(e)}  

@bp.route("/")
@login_required
def index():
    print("==> Accessed Customer Portal Index Page")
    print(f"User ID: {current_user.id}, Username: {current_user.name}, Role: {current_user.role}")

    entries = []
    customer = None

    if current_user.role == "customer":
        customer = Customer.query.filter_by(user_id=current_user.id).first()
        if not customer:
            print("!! No customer profile found.")
            return redirect(url_for("main.index"))
        
        print(f"Customer ID: {customer.id}")
        entries = ShipDocumentEntryMaster.query.filter_by(customer_id=customer.id).all()

    elif current_user.role == "clearing_agent":
        agent_entry_ids = db.session.query(EntryClearingAgentHistory.entry_id).filter_by(
            assigned_to_clearing_agent_id=current_user.id,
            currently_assigned=True
        ).all()
        entry_ids = [entry_id for (entry_id,) in agent_entry_ids]
        
        entries = ShipDocumentEntryMaster.query.filter(
            ShipDocumentEntryMaster.id.in_(entry_ids)
        ).all()

    elif current_user.role == "clearing_company":
        # NEW: Get entries assigned to this clearing company through assigned_clearing_company_id
        clearing_company_entries = ShipDocumentEntryMaster.query.filter_by(
            assigned_clearing_company_id=current_user.id
        ).all()
        
        # EXISTING: Also get entries from the history table (for backward compatibility)
        clearing_company_entry_ids = db.session.query(EntryClearingCompanyHistory.entry_id).filter_by(
            assigned_to_clearing_company_id=current_user.id,
            currently_assigned=True
        ).all()
        entry_ids = [entry_id for (entry_id,) in clearing_company_entry_ids]

        history_entries = ShipDocumentEntryMaster.query.filter(
            ShipDocumentEntryMaster.id.in_(entry_ids)
        ).all()
        
        # Combine both sets of entries and remove duplicates
        all_entries = clearing_company_entries + history_entries
        seen_ids = set()
        entries = []
        for entry in all_entries:
            if entry.id not in seen_ids:
                entries.append(entry)
                seen_ids.add(entry.id)
        
        print(f"Found {len(clearing_company_entries)} entries via assigned_clearing_company_id")
        print(f"Found {len(history_entries)} entries via clearing company history")
        print(f"Total unique entries: {len(entries)}")

    else:
        print("!! Invalid role or access not permitted.")
        return redirect(url_for("main.index"))

    print(f"Total Shipment Entries Found: {len(entries)}")

    # --- Shared Logic with Open Shipments ---
    doc_statuses = {
        status.docStatusID: status.docStatusName
        for status in DocumentStatus.query.all()
    }

    # Initialize counters
    open_shipments = 0      # NEW: Open shipments counter
    new_shipments = 0
    ongoing_shipments = 0
    completed_shipments = 0
    
    # DYNAMIC: Get all available base types and initialize counters
    base_types = ShipmentTypeBase.query.all()
    shipment_types = {}
    base_type_map = {}
    
    # Create mapping of base_type_id to base_code and initialize counters
    for base_type in base_types:
        shipment_types[base_type.base_code] = 0
        base_type_map[base_type.id] = base_type.base_code
    
    print(f"Available base types: {list(shipment_types.keys())}")
    
    recent_activities = []

    for entry in entries:
        status_name = doc_statuses.get(entry.docStatusID, "").lower()
        
        # Categorize shipments by status
        if "open" in status_name:
            open_shipments += 1      # NEW: Count open shipments
        elif "new" in status_name or "pending" in status_name:
            new_shipments += 1
        elif "complete" in status_name or "done" in status_name:
            completed_shipments += 1
        else:
            ongoing_shipments += 1

        # DYNAMIC: Count shipments by base type instead of hardcoded names
        if entry.shipment_type and entry.shipment_type.base_type_id:
            base_code = base_type_map.get(entry.shipment_type.base_type_id)
            if base_code and base_code in shipment_types:
                shipment_types[base_code] += 1
                print(f"Entry {entry.id}: {entry.shipment_type.shipment_name} -> {base_code}")

        recent_activities.append({
            "user": entry.user.name,
            "action": "created new shipment",
            "reference": entry.docserial,
            "timestamp": entry.dateCreated,
        })

    print(f"Open: {open_shipments}, New: {new_shipments}, Ongoing: {ongoing_shipments}, Completed: {completed_shipments}")
    print(f"Dynamic shipment type breakdown: {shipment_types}")

    # Chat activity (only if customer)
    recent_chats = []
    pending_chat_list = []

    if current_user.role == "customer":
        chat_activities = (
            ChatMessage.query.join(ChatThread)
            .join(ShipDocumentEntryMaster, ShipDocumentEntryMaster.id == ChatThread.reference_id)
            .filter(
                ChatThread.module_name == "sea_import",
                ShipDocumentEntryMaster.customer_id == customer.id,
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(5)
            .all()
        )

        pending_replies = (
            ChatMessage.query.join(ChatThread)
            .join(ShipDocumentEntryMaster, ShipDocumentEntryMaster.id == ChatThread.reference_id)
            .filter(
                ChatThread.module_name == "sea_import",
                ShipDocumentEntryMaster.customer_id == customer.id,
                ChatMessage.sender_id != current_user.id,
                ChatMessage.is_read == False,
            )
            .order_by(ChatMessage.created_at.desc())
            .all()
        )

        for msg in chat_activities:
            entry = ShipDocumentEntryMaster.query.get(msg.thread.reference_id)
            if entry:
                recent_chats.append({
                    "user": msg.sender.name,
                    "message": (msg.message[:100] + "...") if len(msg.message) > 100 else msg.message,
                    "timestamp": msg.created_at,
                    "entry_id": entry.id,
                    "doc_serial": entry.docserial,
                })

        for msg in pending_replies:
            entry = ShipDocumentEntryMaster.query.get(msg.thread.reference_id)
            if entry:
                pending_chat_list.append({
                    "user": msg.sender.name,
                    "message": (msg.message[:100] + "...") if len(msg.message) > 100 else msg.message,
                    "timestamp": msg.created_at,
                    "entry_id": entry.id,
                    "doc_serial": entry.docserial,
                })

        print(f"Recent chat messages found: {len(recent_chats)}")
        print(f"Pending chat replies found: {len(pending_chat_list)}")

    # Connected Companies (for clearing agents and clearing companies)
    connected_companies = []
    
    if current_user.role == "clearing_agent":
        # Get unique customer companies from entries assigned to this agent
        customer_ids = set()
        for entry in entries:
            if entry.customer_id:
                customer_ids.add(entry.customer_id)
        
        # Get customer details and their associated users
        for customer_id in customer_ids:
            customer_obj = Customer.query.get(customer_id)
            if customer_obj and customer_obj.user:
                connected_companies.append({
                    "company_name": customer_obj.user.name or customer_obj.user.username or f"Customer {customer_id}",
                    "company_email": customer_obj.user.email,
                    "company_type": "Customer",
                    "connection_status": "Active",
                    "last_interaction": "Recently assigned",
                })
        
        print(f"Found {len(connected_companies)} connected companies for clearing agent")
        
    elif current_user.role == "clearing_company":
        # Get unique customer companies from entries assigned to this company
        customer_ids = set()
        for entry in entries:
            if entry.customer_id:
                customer_ids.add(entry.customer_id)
        
        # Get customer details and their associated users
        for customer_id in customer_ids:
            customer_obj = Customer.query.get(customer_id)
            if customer_obj and customer_obj.user:
                connected_companies.append({
                    "company_name": customer_obj.user.name or customer_obj.user.username or f"Customer {customer_id}",
                    "company_email": customer_obj.user.email,
                    "company_type": "Customer",
                    "connection_status": "Active",
                    "last_interaction": "Recently assigned",
                })
        
        print(f"Found {len(connected_companies)} connected companies for clearing company")

    # Trim recent activities to 5
    recent_activities.sort(key=lambda x: x["timestamp"], reverse=True)
    recent_activities = recent_activities[:5]

    expiring_documents_summary = []
    if current_user.role == "customer":
        # Get documents expiring within 30 days by default
        days_threshold = 30
        today = datetime.now().date()
        expiry_threshold = today + timedelta(days=days_threshold)
        
        # Query expiring documents with joins
        expiring_docs = db.session.query(
            MaterialHSDocuments,
            HSCodeDocument,
            HSCodeIssueBody,
            HSDocumentCategory
        ).join(
            HSCodeDocument, MaterialHSDocuments.document_id == HSCodeDocument.id
        ).join(
            HSCodeIssueBody, HSCodeDocument.issuing_body_id == HSCodeIssueBody.id
        ).join(
            HSDocumentCategory, HSCodeDocument.document_category_id == HSDocumentCategory.id
        ).filter(
            MaterialHSDocuments.company_id == current_user.company_id,
            MaterialHSDocuments.expiry_date.isnot(None),
            MaterialHSDocuments.expiry_date <= expiry_threshold,
            MaterialHSDocuments.expiry_date >= today
        ).all()
        
        # Group documents for summary
        grouped_docs = {}
        for material_doc, hs_doc, issuing_body, doc_category in expiring_docs:
            group_key = f"{issuing_body.id}_{doc_category.id}"
            
            if group_key not in grouped_docs:
                grouped_docs[group_key] = {
                    'issuing_body_name': issuing_body.name,
                    'document_category_name': doc_category.name,
                    'count': 0,
                    'earliest_expiry': material_doc.expiry_date
                }
            
            grouped_docs[group_key]['count'] += 1
            if material_doc.expiry_date < grouped_docs[group_key]['earliest_expiry']:
                grouped_docs[group_key]['earliest_expiry'] = material_doc.expiry_date
        
        # Convert to list and calculate days
        for group_data in grouped_docs.values():
            days_until_expiry = (group_data['earliest_expiry'] - today).days
            expiring_documents_summary.append({
                'display_name': f"{group_data['issuing_body_name']} > {group_data['document_category_name']}",
                'count': group_data['count'],
                'days_until_expiry': days_until_expiry
            })
        
        # Sort by urgency
        expiring_documents_summary.sort(key=lambda x: x['days_until_expiry'])
        expiring_documents_summary = expiring_documents_summary[:5]  # Top 5 most urgent

    statistics = {
        "total_shipments": open_shipments + new_shipments + ongoing_shipments + completed_shipments,
        "open_shipments": open_shipments,      # NEW: Add open shipments count
        "new_shipments": new_shipments,
        "ongoing_shipments": ongoing_shipments,
        "completed_shipments": completed_shipments,
        "shipment_types": shipment_types,  # Now dynamic based on base types
        "recent_activities": recent_activities,
        "recent_chats": recent_chats,
        "pending_replies": pending_chat_list,
        "connected_companies": connected_companies,
        "expiring_documents_summary": expiring_documents_summary,
    }

    print("==> Rendering Customer Portal Index with statistics")
    return render_template(
        "customer_portal/index.html",
        title="Customer Portal",
        customer=customer,
        statistics=statistics,
    )



def calculate_tier_based_cost(rate_card, total_days):
    """
    Calculate demurrage cost using tier system.
    
    Args:
        rate_card: DemurrageRateCard object with tiers
        total_days: Total number of demurrage days
    
    Returns:
        float: Total calculated cost
    """
    if total_days <= 0:
        return 0.0
    
    try:
        total_cost = 0.0
        remaining_days = total_days
        
        # Sort tiers by tier_number to ensure correct progression
        sorted_tiers = sorted(rate_card.tiers, key=lambda x: x.tier_number)
        
        print(f"    Calculating cost for {total_days} days using {len(sorted_tiers)} tiers")
        
        for i, tier in enumerate(sorted_tiers):
            if remaining_days <= 0:
                break
            
            # Determine how many days fall into this tier
            if hasattr(tier, 'max_days') and tier.max_days:
                # If tier has max_days defined
                days_in_tier = min(remaining_days, tier.max_days)
            elif hasattr(tier, 'days_range') and tier.days_range:
                # If tier has days_range defined
                days_in_tier = min(remaining_days, tier.days_range)
            elif i == len(sorted_tiers) - 1:
                # Last tier takes all remaining days
                days_in_tier = remaining_days
            else:
                # Default: assume each tier covers a reasonable range
                # You may need to adjust this based on your tier structure
                default_tier_days = 5  # Assume each tier covers 5 days
                days_in_tier = min(remaining_days, default_tier_days)
            
            # Calculate cost for this tier
            tier_cost = days_in_tier * tier.rate_amount
            total_cost += tier_cost
            remaining_days -= days_in_tier
            
            print(f"      Tier {tier.tier_number}: {days_in_tier} days × {tier.rate_amount}/day = {tier_cost}")
            
            # If this tier consumed all remaining days, stop
            if remaining_days <= 0:
                break
        
        print(f"    Total calculated cost: {total_cost}")
        return total_cost
        
    except Exception as e:
        print(f"    Error calculating tier cost: {str(e)}")
        # Fallback to simple calculation
        if rate_card.tiers:
            fallback_rate = rate_card.tiers[0].rate_amount
            fallback_cost = total_days * fallback_rate
            print(f"    Using fallback: {total_days} days × {fallback_rate}/day = {fallback_cost}")
            return fallback_cost
        return 0.0
    

def calculate_highest_projected_cost_for_container(container, days_in_demurrage):
    """Calculate highest projected cost across all demurrage reasons for a specific container."""
    if not container.container_size_id or not container.container_type_id or days_in_demurrage <= 0:
        return 0.0, "LKR"  # Default to LKR
    
    # Get all active demurrage reasons
    reasons = DemurrageReasons.query.filter_by(is_active=True).all()
    
    highest_cost = 0.0
    best_currency = "LKR"  # Default to LKR
    
    for reason in reasons:
        # Get rate card for this size/type/reason combination
        rate_card = DemurrageRateCard.query.filter(
            DemurrageRateCard.container_size_id == container.container_size_id,
            DemurrageRateCard.container_type_id == container.container_type_id,
            DemurrageRateCard.demurrage_reason_id == reason.id,
            DemurrageRateCard.is_active == True
        ).first()
        
        if rate_card and rate_card.tiers:
            # Calculate tier-based cost for this reason
            reason_cost = calculate_tier_based_cost(rate_card, days_in_demurrage)
            if reason_cost > highest_cost:
                highest_cost = reason_cost
                if rate_card.currency:
                    best_currency = rate_card.currency.CurrencyCode
    
    return highest_cost, best_currency


def calculate_projected_cost_if_cleared_today(container, shipment):
    """Calculate what the cost would be if container is cleared today."""
    from datetime import datetime
    today = datetime.now().date()
    
    if not shipment.demurrage_from or today <= shipment.demurrage_from:
        return 0.0, "LKR"  # Default to LKR
    
    days_in_demurrage = (today - shipment.demurrage_from).days
    return calculate_highest_projected_cost_for_container(container, days_in_demurrage)


def get_timeline_segments_for_container(container, shipment):
    """Generate timeline segments for interactive graph."""
    from datetime import datetime, timedelta
    today = datetime.now().date()
    
    segments = []
    
    if not shipment.eta or not shipment.demurrage_from:
        return segments

    # Free period segment
    segments.append({
        'type': 'free_period',
        'start_date': shipment.eta.date() if hasattr(shipment.eta, 'date') else shipment.eta,
        'end_date': shipment.demurrage_from,
        'color': '#28a745',  # Green
        'cost': 0,
        'description': 'Free Period',
        'days': (shipment.demurrage_from - (shipment.eta.date() if hasattr(shipment.eta, 'date') else shipment.eta)).days
    })
    
    # Only add demurrage segments if we're past demurrage_from date
    if today > shipment.demurrage_from:
        days_in_demurrage = (today - shipment.demurrage_from).days
        
        # Get the best rate card for this container
        best_rate_card = None
        highest_cost = 0
        best_currency = "LKR"  # Default to LKR
        
        reasons = DemurrageReasons.query.filter_by(is_active=True).all()
        for reason in reasons:
            rate_card = DemurrageRateCard.query.filter(
                DemurrageRateCard.container_size_id == container.container_size_id,
                DemurrageRateCard.container_type_id == container.container_type_id,
                DemurrageRateCard.demurrage_reason_id == reason.id,
                DemurrageRateCard.is_active == True
            ).first()
            
            if rate_card and rate_card.tiers:
                cost = calculate_tier_based_cost(rate_card, days_in_demurrage)
                if cost > highest_cost:
                    highest_cost = cost
                    best_rate_card = rate_card
                    # Get actual currency from rate card
                    if rate_card.currency:
                        best_currency = rate_card.currency.CurrencyCode
        
        # Generate tier segments if we have a rate card
        if best_rate_card and best_rate_card.tiers:
            colors = ['#ffc107', '#fd7e14', '#dc3545', '#6f42c1', '#e83e8c']  # Yellow to Red progression
            current_date = shipment.demurrage_from
            remaining_days = days_in_demurrage
            
            for i, tier in enumerate(sorted(best_rate_card.tiers, key=lambda x: x.tier_number)):
                if remaining_days <= 0:
                    break
                
                # Determine days in this tier
                if tier.to_day:
                    tier_days = min(remaining_days, tier.to_day - tier.from_day + 1)
                else:
                    tier_days = remaining_days
                
                if tier_days > 0:
                    end_date = current_date + timedelta(days=tier_days)
                    
                    # Calculate accumulated cost up to this point
                    accumulated_cost = calculate_tier_based_cost(best_rate_card, 
                                                               (current_date - shipment.demurrage_from).days + tier_days)
                    
                    segments.append({
                        'type': 'demurrage_tier',
                        'tier_number': tier.tier_number,
                        'start_date': current_date,
                        'end_date': end_date,
                        'color': colors[min(i, len(colors)-1)],
                        'cost': accumulated_cost,
                        'rate_per_day': tier.rate_amount,
                        'days': tier_days,
                        'description': f'Tier {tier.tier_number} ({best_currency} {tier.rate_amount}/day)',  # Changed this line
                        'day_range': tier.day_range_display,
                        'currency': best_currency  # Added currency info
                    })
                    
                    current_date = end_date
                    remaining_days -= tier_days
    
    return segments


def categorize_shipments_by_risk(customer_id):
    """Categorize shipments into high risk (demurrage) and low risk (free period)."""
    from datetime import datetime
    today = datetime.now().date()
    
    # High Risk: Shipments in demurrage period
    demurrage_shipments = OrderShipment.query.filter(
        OrderShipment.customer_id == customer_id,
        OrderShipment.is_demurrage == True,
        OrderShipment.cleared_date.is_(None)
    ).all()
    
    # Low Risk: Shipments in free period (ETA passed but not in demurrage yet)
    free_period_shipments = OrderShipment.query.filter(
        OrderShipment.customer_id == customer_id,
        OrderShipment.is_demurrage == False,
        OrderShipment.eta < today,
        OrderShipment.cleared_date.is_(None)
    ).all()
    
    return demurrage_shipments, free_period_shipments


@bp.route("/api/demurrage-snapshots")
@login_required
def demurrage_snapshots():
    """Get AI projected demurrage snapshot data for dashboard cards."""
    try:
        print(f"==> AI Demurrage Snapshots API called by user {current_user.id}")
        
        if current_user.role != "customer":
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        customer = Customer.query.filter_by(user_id=current_user.id).first()
        if not customer:
            return jsonify({"success": False, "message": "Customer not found"}), 404
        
        from datetime import datetime
        today = datetime.now().date()
        
        # Get categorized shipments
        demurrage_shipments, free_period_shipments = categorize_shipments_by_risk(customer.id)
        
        print(f"Found {len(demurrage_shipments)} demurrage shipments and {len(free_period_shipments)} free period shipments")
        
        total_projected_demurrage = 0
        demurrage_container_count = 0
        currency_codes = []
        
        # Calculate projected costs for demurrage shipments only
        for shipment in demurrage_shipments:
            if not shipment.demurrage_from:
                continue
                
            days_in_demurrage = (today - shipment.demurrage_from).days
            if days_in_demurrage <= 0:
                continue
            
            # Get containers for this shipment
            containers = ImportContainer.query.filter_by(
                shipment_id=shipment.ship_doc_entry_id
            ).all()
            
            print(f"Processing shipment {shipment.id} with {len(containers)} containers, {days_in_demurrage} days in demurrage")
            
            for container in containers:
                if container.container_size_id and container.container_type_id:
                    # Calculate highest projected cost across all reasons
                    projected_cost, currency = calculate_highest_projected_cost_for_container(
                        container, days_in_demurrage
                    )
                    
                    total_projected_demurrage += projected_cost
                    demurrage_container_count += 1
                    currency_codes.append(currency)
                    
                    print(f"  Container {container.container_number}: {currency} {projected_cost:.2f}")
        
        # Determine most common currency, default to LKR
        from collections import Counter
        most_common_currency = "LKR"  # Default to LKR
        
        if currency_codes:
            currency_counter = Counter(currency_codes)
            most_common_currency = currency_counter.most_common(1)[0][0]
        
        # Calculate average cost per demurrage container
        avg_cost_per_container = 0
        if demurrage_container_count > 0:
            avg_cost_per_container = total_projected_demurrage / demurrage_container_count
        
        # Prepare response data with currency code only
        snapshots = {
            "total_projected": f"{most_common_currency} {total_projected_demurrage:,.2f}",
            "at_risk_count": len(demurrage_shipments),  # High risk - in demurrage
            "critical_actions": len(free_period_shipments),  # Low risk - in free period  
            "avg_cost": f"{most_common_currency} {avg_cost_per_container:,.2f}",
            "avg_cost_type": "Demurrage Containers",
            "currency": most_common_currency,
            "demurrage_container_count": demurrage_container_count
        }
        
        print(f"Final AI snapshots: {snapshots}")
        return jsonify({"success": True, "data": snapshots})
        
    except Exception as e:
        print(f"❌ Error in AI demurrage snapshots: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "message": str(e)}), 500
       

@bp.route("/api/at-risk-shipments")
@login_required
def at_risk_shipments():
    """Get at-risk shipments data with proper risk categorization."""
    try:
        print(f"==> At-Risk Shipments API called by user {current_user.id}")
        
        if current_user.role != "customer":
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        customer = Customer.query.filter_by(user_id=current_user.id).first()
        if not customer:
            return jsonify({"success": False, "message": "Customer not found"}), 404
        
        from datetime import datetime
        today = datetime.now().date()
        
        # Get categorized shipments
        demurrage_shipments, free_period_shipments = categorize_shipments_by_risk(customer.id)
        
        shipments_data = []
        
        # Process High Risk shipments (in demurrage)
        for shipment in demurrage_shipments:
            days_in_demurrage = 0
            if shipment.demurrage_from:
                days_in_demurrage = (today - shipment.demurrage_from).days
            
            # Get containers
            containers = ImportContainer.query.filter_by(
                shipment_id=shipment.ship_doc_entry_id
            ).all()
            
            container_details = []
            container_count = len(containers)
            total_projected_cost = 0
            currency_code = "LKR"  # Default to LKR
            
            for container in containers:
                if container.size_type:
                    container_details.append(container.size_type)
                
                if container.container_size_id and container.container_type_id and days_in_demurrage > 0:
                    projected_cost, currency = calculate_highest_projected_cost_for_container(
                        container, days_in_demurrage
                    )
                    total_projected_cost += projected_cost
                    currency_code = currency
            
            shipments_data.append({
                "shipment_id": shipment.ship_doc_entry_id,
                "job_number": shipment.import_id,
                "bl_number": shipment.bl_no,
                "container_details": ", ".join(set(container_details)) if container_details else "Unknown",
                "container_count": container_count,
                "eta_date": shipment.eta.isoformat() if shipment.eta else None,
                "demurrage_from": shipment.demurrage_from.isoformat() if shipment.demurrage_from else None,
                "days_status_text": f"In Demurrage (Day {days_in_demurrage})" if days_in_demurrage > 0 else "Demurrage Started",
                "days_overdue": days_in_demurrage,
                "risk_level": "High",
                "is_demurrage": True,
                "projected_cost": f"{currency_code} {total_projected_cost:,.2f}" if total_projected_cost > 0 else "N/A",
                "currency": currency_code
            })
        
        # Process Low Risk shipments (in free period)
        for shipment in free_period_shipments:
            days_since_eta = (today - shipment.eta.date()).days if shipment.eta else 0
            
            # Estimate free time left (assuming 3 days free time if demurrage_from not set)
            if shipment.demurrage_from:
                days_left = (shipment.demurrage_from - today).days
                status_text = f"Free Period ({days_left} days left)" if days_left > 0 else "Free Period Ending"
            else:
                estimated_free_time = 3
                days_left = estimated_free_time - days_since_eta
                status_text = f"Free Period (~{max(0, days_left)} days left)"
            
            # Get containers
            containers = ImportContainer.query.filter_by(
                shipment_id=shipment.ship_doc_entry_id
            ).all()
            
            container_details = []
            for container in containers:
                if container.size_type:
                    container_details.append(container.size_type)
            
            shipments_data.append({
                "shipment_id": shipment.ship_doc_entry_id,
                "job_number": shipment.import_id,
                "bl_number": shipment.bl_no,
                "container_details": ", ".join(set(container_details)) if container_details else "Unknown",
                "container_count": len(containers),
                "eta_date": shipment.eta.isoformat() if shipment.eta else None,
                "demurrage_from": shipment.demurrage_from.isoformat() if shipment.demurrage_from else None,
                "days_status_text": status_text,
                "days_overdue": 0,  # Not in demurrage yet
                "risk_level": "Low",
                "is_demurrage": False,
                "projected_cost": "N/A",  # No cost in free period
                "currency": "LKR"  # Default
            })
        
        return jsonify({"success": True, "data": shipments_data})
        
    except Exception as e:
        print(f"Error in at-risk shipments: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
     

@bp.route("/api/critical-timeline-graph")
@login_required
def critical_timeline_graph():
    """Get interactive timeline graph data for demurrage containers."""
    try:
        print(f"==> Critical Timeline Graph API called by user {current_user.id}")
        
        if current_user.role != "customer":
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        customer = Customer.query.filter_by(user_id=current_user.id).first()
        if not customer:
            return jsonify({"success": False, "message": "Customer not found"}), 404
        
        from datetime import datetime
        today = datetime.now().date()
        
        # Get only demurrage shipments for timeline
        demurrage_shipments, _ = categorize_shipments_by_risk(customer.id)
        
        containers_timeline = []
        
        for shipment in demurrage_shipments:
            # Get containers for this shipment
            containers = ImportContainer.query.filter_by(
                shipment_id=shipment.ship_doc_entry_id
            ).all()
            
            for container in containers:
                # Generate timeline segments
                timeline_segments = get_timeline_segments_for_container(container, shipment)
                
                # Calculate projected cost if cleared today
                projected_cost_today, currency = calculate_projected_cost_if_cleared_today(container, shipment)
                
                container_data = {
                    "container_id": container.id,
                    "container_number": container.container_number,
                    "size_type": container.size_type or "Unknown",
                    "shipment_id": shipment.ship_doc_entry_id,
                    "job_number": shipment.import_id,
                    "bl_number": shipment.bl_no,
                    "eta_date": shipment.eta.isoformat() if shipment.eta else None,
                    "demurrage_from": shipment.demurrage_from.isoformat() if shipment.demurrage_from else None,
                    "timeline_segments": [
                        {
                            **segment,
                            "start_date": segment["start_date"].isoformat(),
                            "end_date": segment["end_date"].isoformat() if segment["end_date"] else None
                        } for segment in timeline_segments
                    ],
                    "projected_cost_today": f"{currency} {projected_cost_today:,.2f}",
                    "currency": currency
                }
                
                containers_timeline.append(container_data)
        
        return jsonify({"success": True, "data": containers_timeline})
        
    except Exception as e:
        print(f"Error in critical timeline graph: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "message": str(e)}), 500
    

@bp.route("/api/critical-timeline")
@login_required
def critical_timeline():
    """Get critical timeline data - now shows only demurrage shipments with timeline graphs."""
    try:
        print(f"==> Critical Timeline API called by user {current_user.id}")
        
        if current_user.role != "customer":
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        customer = Customer.query.filter_by(user_id=current_user.id).first()
        if not customer:
            return jsonify({"success": False, "message": "Customer not found"}), 404
        
        from datetime import datetime, timedelta
        today = datetime.now().date()
        
        # Get only demurrage shipments
        demurrage_shipments, _ = categorize_shipments_by_risk(customer.id)
        
        timeline_data = {
            "demurrage_containers": []
        }
        
        for shipment in demurrage_shipments:
            days_in_demurrage = 0
            if shipment.demurrage_from:
                days_in_demurrage = (today - shipment.demurrage_from).days
            
            # Get containers
            containers = ImportContainer.query.filter_by(
                shipment_id=shipment.ship_doc_entry_id
            ).all()
            
            for container in containers:
                # Calculate projected cost
                projected_cost, currency = calculate_projected_cost_if_cleared_today(container, shipment)
                
                container_info = {
                    "container_id": container.id,
                    "container_number": container.container_number,
                    "size_type": container.size_type or "Unknown",
                    "job_number": shipment.import_id,
                    "bl_number": shipment.bl_no,
                    "days_in_demurrage": days_in_demurrage,
                    "projected_cost": f"{currency} {projected_cost:.2f}",
                    "eta_date": shipment.eta.isoformat() if shipment.eta else None,
                    "demurrage_from": shipment.demurrage_from.isoformat() if shipment.demurrage_from else None,
                    "timeline_url": f"/customer_portal/api/critical-timeline-graph?container_id={container.id}"
                }
                
                timeline_data["demurrage_containers"].append(container_info)
        
        return jsonify({"success": True, "data": timeline_data})
        
    except Exception as e:
        print(f"Error in critical timeline: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500        

@bp.route("/api/shipment-demurrage-details/<int:shipment_id>")
@login_required
def shipment_demurrage_details(shipment_id):
    """Get detailed demurrage information for a specific shipment with single projected cost."""
    try:
        print(f"==> Shipment Demurrage Details API called for shipment {shipment_id}")
        
        if current_user.role != "customer":
            return jsonify({"success": False, "message": "Access denied"}), 403
        
        customer = Customer.query.filter_by(user_id=current_user.id).first()
        if not customer:
            return jsonify({"success": False, "message": "Customer not found"}), 404
        
        # Get shipment and verify ownership
        shipment = OrderShipment.query.filter(
            OrderShipment.ship_doc_entry_id == shipment_id,
            OrderShipment.customer_id == customer.id
        ).first()
        
        if not shipment:
            return jsonify({"success": False, "message": "Shipment not found"}), 404
        
        # Get containers
        containers = ImportContainer.query.filter_by(
            shipment_id=shipment.ship_doc_entry_id
        ).all()
        
        # Calculate risk assessment
        from datetime import datetime
        today = datetime.now().date()
        
        risk_level = "High" if shipment.is_demurrage else "Low"
        
        if shipment.is_demurrage:
            days_in_demurrage = (today - shipment.demurrage_from).days if shipment.demurrage_from else 0
            risk_explanation = f"Shipment is in demurrage period for {days_in_demurrage} days and incurring charges."
        else:
            days_since_eta = (today - shipment.eta.date()).days if shipment.eta else 0
            risk_explanation = f"Shipment is in free period ({days_since_eta} days since ETA) but approaching demurrage."
        
        # Calculate single projected cost per container type
        projected_costs = []
        container_types = {}
        
        for container in containers:
            container_type_key = container.size_type or "Unknown"
            
            if container_type_key not in container_types:
                container_types[container_type_key] = {
                    "count": 0,
                    "total_cost": 0,
                    "currency": "LKR"
                }
            
            container_types[container_type_key]["count"] += 1
            
            if shipment.is_demurrage and shipment.demurrage_from:
                days_in_demurrage = (today - shipment.demurrage_from).days
                if days_in_demurrage > 0:
                    cost, currency = calculate_highest_projected_cost_for_container(container, days_in_demurrage)
                    container_types[container_type_key]["total_cost"] += cost
                    container_types[container_type_key]["currency"] = currency
        
        # Convert to list format
        for container_type, data in container_types.items():
            projected_costs.append({
                "container_type": container_type,
                "container_count": data["count"],
                "total_cost": f"{data['currency']} {data['total_cost']:,.2f}",
                "currency": data["currency"]
            })
        
        shipment_details = {
            "job_number": shipment.import_id,
            "bl_number": shipment.bl_no,
            "eta_date": shipment.eta.isoformat() if shipment.eta else None,
            "demurrage_from": shipment.demurrage_from.isoformat() if shipment.demurrage_from else None,
            "port_of_discharge": shipment.port_of_discharge,
            "container_count": len(containers),
            "container_details": ", ".join(set(c.size_type for c in containers if c.size_type)),
            "demurrage_status": "In Demurrage" if shipment.is_demurrage else "Free Period",
            "risk_level": risk_level,
            "risk_explanation": risk_explanation,
            "projected_costs": projected_costs
        }
        
        return jsonify({"success": True, "data": shipment_details})
        
    except Exception as e:
        print(f"Error in shipment demurrage details: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    

# Add these routes to your customer_portal routes file

@bp.route('/api/expiring-documents')
@login_required
def get_expiring_documents():
    """Get documents expiring within specified days grouped by issuing body and document category"""
    
    # Only customers can access this
    if current_user.role != "customer":
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    # Get days parameter (default 30)
    days = request.args.get('days', 30, type=int)
    
    # Calculate expiry date threshold
    today = datetime.now().date()
    expiry_threshold = today + timedelta(days=days)
    
    # Query expiring documents with joins
    expiring_docs = db.session.query(
        MaterialHSDocuments,
        HSCodeDocument,
        HSCodeIssueBody,
        HSDocumentCategory,
        POMaterial
    ).join(
        HSCodeDocument, MaterialHSDocuments.document_id == HSCodeDocument.id
    ).join(
        HSCodeIssueBody, HSCodeDocument.issuing_body_id == HSCodeIssueBody.id
    ).join(
        HSDocumentCategory, HSCodeDocument.document_category_id == HSDocumentCategory.id
    ).join(
        POMaterial, MaterialHSDocuments.material_id == POMaterial.id
    ).filter(
        MaterialHSDocuments.company_id == current_user.company_id,
        MaterialHSDocuments.expiry_date.isnot(None),
        MaterialHSDocuments.expiry_date <= expiry_threshold,
        MaterialHSDocuments.expiry_date >= today  # Don't include already expired
    ).all()
    
    # Group documents by issuing body and document category
    grouped_docs = {}
    
    for material_doc, hs_doc, issuing_body, doc_category, material in expiring_docs:
        # Create unique key for grouping
        group_key = f"{issuing_body.id}_{doc_category.id}"
        
        if group_key not in grouped_docs:
            grouped_docs[group_key] = {
                'issuing_body_id': issuing_body.id,
                'issuing_body_name': issuing_body.name,
                'document_category_id': doc_category.id,
                'document_category_name': doc_category.name,
                'documents': [],
                'materials': set(),
                'earliest_expiry': material_doc.expiry_date,
                'latest_expiry': material_doc.expiry_date
            }
        
        # Add document and material to group
        grouped_docs[group_key]['documents'].append({
            'id': material_doc.id,
            'file_name': material_doc.file_name,
            'expiry_date': material_doc.expiry_date,
            'material_id': material.id,
            'material_code': material.material_code,
            'material_name': material.material_name
        })
        
        grouped_docs[group_key]['materials'].add(material.id)
        
        # Update earliest and latest expiry dates
        if material_doc.expiry_date < grouped_docs[group_key]['earliest_expiry']:
            grouped_docs[group_key]['earliest_expiry'] = material_doc.expiry_date
        if material_doc.expiry_date > grouped_docs[group_key]['latest_expiry']:
            grouped_docs[group_key]['latest_expiry'] = material_doc.expiry_date
    
    # Format response data
    result = []
    for group_key, group_data in grouped_docs.items():
        days_until_expiry = (group_data['earliest_expiry'] - today).days
        
        result.append({
            'issuing_body_id': group_data['issuing_body_id'],
            'issuing_body_name': group_data['issuing_body_name'],
            'document_category_id': group_data['document_category_id'],
            'document_category_name': group_data['document_category_name'],
            'display_name': f"{group_data['issuing_body_name']} > {group_data['document_category_name']}",
            'material_count': len(group_data['materials']),
            'document_count': len(group_data['documents']),
            'earliest_expiry': group_data['earliest_expiry'].isoformat(),
            'latest_expiry': group_data['latest_expiry'].isoformat(),
            'days_until_expiry': days_until_expiry,
            'status': 'expired' if days_until_expiry < 0 else 'expiring' if days_until_expiry <= 7 else 'warning'
        })
    
    # Sort by days until expiry (most urgent first)
    result.sort(key=lambda x: x['days_until_expiry'])
    
    return jsonify({
        'success': True,
        'data': result,
        'total_groups': len(result),
        'days_threshold': days
    })

@bp.route('/api/bulk-update-documents', methods=['POST'])
@login_required
def bulk_update_documents():
    """Bulk update all documents for a specific issuing body and document category"""
    
    # Only customers can access this
    if current_user.role != "customer":
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        # Get form data
        issuing_body_id = request.form.get('issuing_body_id', type=int)
        document_category_id = request.form.get('document_category_id', type=int)
        expiry_date = request.form.get('expiry_date')
        comment = request.form.get('comment', '')
        
        # Validate required fields
        if not issuing_body_id or not document_category_id:
            return jsonify({
                'success': False,
                'message': 'Issuing body and document category are required'
            }), 400
        
        if not expiry_date:
            return jsonify({
                'success': False,
                'message': 'Expiry date is required'
            }), 400
        
        # Validate file upload
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'message': 'File is required'
            }), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'success': False,
                'message': 'Please select a file'
            }), 400
        
        # Parse and validate expiry date
        try:
            expiry_date_obj = datetime.strptime(expiry_date, '%Y-%m-%d').date()
            if expiry_date_obj <= datetime.now().date():
                return jsonify({
                    'success': False,
                    'message': 'Expiry date must be in the future'
                }), 400
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'Invalid expiry date format'
            }), 400
        
        # Upload file to S3
        s3_bucket = current_app.config['S3_BUCKET_NAME']
        s3_base_folder = current_app.config.get('S3_BASE_FOLDER', '')
        
        if s3_base_folder:
            s3_key = f"{s3_base_folder}/bulk_material_docs/{uuid.uuid4()}_{secure_filename(file.filename)}"
        else:
            s3_key = f"bulk_material_docs/{uuid.uuid4()}_{secure_filename(file.filename)}"
        
        # Upload to S3
        file.seek(0)
        upload_result = upload_file_to_s3(file, s3_bucket, s3_key)
        if upload_result is False:
            return jsonify({
                'success': False,
                'message': 'Failed to upload file to S3'
            }), 500
        
        # Find all documents to update
        documents_to_update = db.session.query(MaterialHSDocuments).join(
            HSCodeDocument, MaterialHSDocuments.document_id == HSCodeDocument.id
        ).filter(
            MaterialHSDocuments.company_id == current_user.company_id,
            HSCodeDocument.issuing_body_id == issuing_body_id,
            HSCodeDocument.document_category_id == document_category_id
        ).all()
        
        if not documents_to_update:
            return jsonify({
                'success': False,
                'message': 'No documents found to update'
            }), 404
        
        # Update all documents
        updated_count = 0
        material_ids = set()
        
        for doc in documents_to_update:
            doc.file_path = s3_key
            doc.file_name = file.filename
            doc.expiry_date = expiry_date_obj
            doc.comment = comment
            doc.uploaded_by = current_user.id
            doc.uploaded_at = datetime.utcnow()
            material_ids.add(doc.material_id)
            updated_count += 1
        
        db.session.commit()
        
        # Get issuing body and document category names for response
        issuing_body = HSCodeIssueBody.query.get(issuing_body_id)
        document_category = HSDocumentCategory.query.get(document_category_id)
        
        return jsonify({
            'success': True,
            'message': f'Successfully updated {updated_count} documents for {len(material_ids)} materials',
            'updated_count': updated_count,
            'material_count': len(material_ids),
            'issuing_body_name': issuing_body.name if issuing_body else 'Unknown',
            'document_category_name': document_category.name if document_category else 'Unknown'
        })
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in bulk document update: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error updating documents: {str(e)}'
        }), 500

@bp.route('/api/document-expiry-details/<int:issuing_body_id>/<int:document_category_id>')
@login_required
def get_document_expiry_details(issuing_body_id, document_category_id):
    """Get detailed information about documents for a specific issuing body and category"""
    
    # Only customers can access this
    if current_user.role != "customer":
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    # Get documents with material details
    documents = db.session.query(
        MaterialHSDocuments,
        POMaterial,
        HSCode
    ).join(
        POMaterial, MaterialHSDocuments.material_id == POMaterial.id
    ).join(
        HSCode, MaterialHSDocuments.hs_code_id == HSCode.id
    ).join(
        HSCodeDocument, MaterialHSDocuments.document_id == HSCodeDocument.id
    ).filter(
        MaterialHSDocuments.company_id == current_user.company_id,
        HSCodeDocument.issuing_body_id == issuing_body_id,
        HSCodeDocument.document_category_id == document_category_id
    ).all()
    
    # Format response
    result = []
    for material_doc, material, hs_code in documents:
        days_until_expiry = None
        if material_doc.expiry_date:
            days_until_expiry = (material_doc.expiry_date - datetime.now().date()).days
        
        result.append({
            'document_id': material_doc.id,
            'material_code': material.material_code,
            'material_name': material.material_name,
            'hs_code': hs_code.code,
            'file_name': material_doc.file_name,
            'expiry_date': material_doc.expiry_date.isoformat() if material_doc.expiry_date else None,
            'days_until_expiry': days_until_expiry,
            'comment': material_doc.comment,
            'uploaded_at': material_doc.uploaded_at.isoformat()
        })
    
    # Get issuing body and document category info
    issuing_body = HSCodeIssueBody.query.get(issuing_body_id)
    document_category = HSDocumentCategory.query.get(document_category_id)
    
    return jsonify({
        'success': True,
        'issuing_body_name': issuing_body.name if issuing_body else 'Unknown',
        'document_category_name': document_category.name if document_category else 'Unknown',
        'documents': result,
        'total_documents': len(result)
    })


@bp.route("/sea-import", methods=["GET", "POST"])
@login_required
def sea_import():
    print("DEBUG: Entered sea_import route")

    # Get the customer associated with the current user
    customer = Customer.query.filter_by(user_id=current_user.id).first()
    print(f"DEBUG: Retrieved customer: {customer}")

    if not customer:
        print("DEBUG: No customer profile found")
        return redirect(url_for("main.index"))

    form = ShipDocumentEntryForm()
    print("DEBUG: Initialized ShipDocumentEntryForm")

    
    # NEW: Get status parameter from URL for auto-filtering
    status_filter = request.args.get('status', '')
    print(f"DEBUG: Status filter from URL: '{status_filter}'")

    # Get assigned shipping agents for dropdown
    assigned_companies = (
        db.session.query(CompanyInfo)
        .join(CompanyAssignment, CompanyInfo.id == CompanyAssignment.assigned_company_id)
        .filter(
            CompanyAssignment.assigned_by_user_id == current_user.id,
            CompanyAssignment.is_active == True
        )
        .all()
    )
    print(f"DEBUG: Retrieved assigned shipping agents: {[comp.company_name for comp in assigned_companies]}")

    # Initialize empty choices - will be populated dynamically
    form.shipTypeid.choices = []

    # For API requests only, avoid form processing
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({"error": "This endpoint doesn't handle AJAX requests. Use /sea-import/api/create instead."})

    # Get ship categories and document statuses based on selected shipment type
    if request.method == "POST":
        print("DEBUG: Handling POST request")
        selected_assigned_company = request.form.get("assignedClearanceCompany")
        selected_shipment_type = request.form.get("shipTypeid")
        print(f"DEBUG: Selected assigned company ID from form: {selected_assigned_company}")
        print(f"DEBUG: Selected shipment type ID from form: {selected_shipment_type}")

        # Validate assigned company belongs to current user
        if selected_assigned_company:
            assignment = CompanyAssignment.query.filter_by(
                assigned_by_user_id=current_user.id,
                assigned_company_id=selected_assigned_company,
                is_active=True
            ).first()
            
            if not assignment:
                print("DEBUG: Invalid assigned company selection")
                flash("Invalid shipping agent selection.", "danger")
                return redirect(url_for("customer_portal.sea_import"))

        # Get shipment types for the selected company
        if selected_assigned_company:
            shipment_types = ShipmentType.query.filter_by(
                company_id=selected_assigned_company, 
                is_active=True
            ).all()
            form.shipTypeid.choices = [(st.id, st.shipment_name) for st in shipment_types]
        
        if selected_shipment_type:
            ship_categories = ShipCategory.query.filter_by(
                shipmentType=selected_shipment_type
            ).all()
            doc_statuses = DocumentStatus.query.filter_by(
                doctypeid=selected_shipment_type
            ).all()
        else:
            ship_categories = []
            doc_statuses = []

        # Handle form submission for regular (non-AJAX) requests
        if form.validate_on_submit():
            try:
                print("DEBUG: Form validated on submit")

                # Verify assigned company again
                if not selected_assigned_company:
                    flash("Please select an assigned shipping agent.", "danger")
                    return redirect(url_for("customer_portal.sea_import"))

                assignment = CompanyAssignment.query.filter_by(
                    assigned_by_user_id=current_user.id,
                    assigned_company_id=selected_assigned_company,
                    is_active=True
                ).first()
                
                if not assignment:
                    flash("Invalid shipping agent selection.", "danger")
                    return redirect(url_for("customer_portal.sea_import"))

                shipment_type = ShipmentType.query.filter_by(
                    id=form.shipTypeid.data,
                    company_id=selected_assigned_company
                ).first()
                
                if not shipment_type:
                    flash("Invalid shipment type for selected shipping agent.", "danger")
                    return redirect(url_for("customer_portal.sea_import"))

                print(f"DEBUG: Retrieved shipment type from DB: {shipment_type}")

                new_doc_num = shipment_type.lastDocNumber + 1
                doc_serial = f"{shipment_type.docCode}{new_doc_num}"
                print(f"DEBUG: Generated new doc number: {new_doc_num}")
                print(f"DEBUG: Generated doc serial: {doc_serial}")

                open_status = DocumentStatus.query.filter(
                    DocumentStatus.doctypeid == form.shipTypeid.data,
                    db.func.lower(DocumentStatus.docStatusName) == "open",
                ).first()
                print(f"DEBUG: Re-fetched Open status: {open_status}")

                if not open_status:
                    print("DEBUG: Open status not found, redirecting")
                    flash("Could not find 'Open' status for this document type.", "danger")
                    return redirect(url_for("customer_portal.sea_import"))
                
                current_time_sri_lanka = get_sri_lanka_time()

                entry = ShipDocumentEntryMaster(
                    assigned_clearing_company_id=selected_assigned_company,  # New field
                    shipTypeid=form.shipTypeid.data,
                    docCode=shipment_type.docCode,
                    docnum=new_doc_num,
                    docserial=doc_serial,
                    dateCreated=current_time_sri_lanka,
                    dealineDate=form.dealineDate.data,
                    docStatusID=open_status.docStatusID,
                    custComment=form.custComment.data,
                    cusOriginalReady=form.cusOriginalReady.data,
                    shipCategory=form.shipCategory.data,
                    user_id=current_user.id,
                    customer_id=customer.id,
                    company_id=current_user.company_id
                )
                print(f"DEBUG: Created new document entry: {entry}")

                shipment_type.lastDocNumber = new_doc_num
                print(f"DEBUG: Updated shipment_type.lastDocNumber to {new_doc_num}")

                db.session.add(entry)
                db.session.commit()
                print("DEBUG: Committed new entry to database")

                flash("Document entry created successfully!", "success")
                return redirect(url_for("customer_portal.sea_import"))

            except Exception as e:
                db.session.rollback()
                print(f"DEBUG: Error in form submission: {str(e)}")
                flash(f"Error in form submission", "danger")
                return redirect(url_for("customer_portal.sea_import"))
    else:
        print("DEBUG: Handling GET request")
        # For GET requests, initialize empty dependent dropdowns
        ship_categories = []
        doc_statuses = []
        shipment_types = []

    form.shipCategory.choices = [(sc.id, sc.catname) for sc in ship_categories]
    form.docStatusID.choices = [
        (ds.docStatusID, ds.docStatusName) for ds in doc_statuses
    ]
    print(f"DEBUG: Set form.shipCategory choices: {form.shipCategory.choices}")
    print(f"DEBUG: Set form.docStatusID choices: {form.docStatusID.choices}")

    # Find the 'Open' status ID
    open_status = None
    if doc_statuses:
        open_status = next(
            (
                status
                for status in doc_statuses
                if status.docStatusName.lower() == "open"
            ),
            None,
        )
        print(f"DEBUG: Found 'Open' status: {open_status}")

    if open_status:
        form.docStatusID.data = open_status.docStatusID
        print(f"DEBUG: Set default form.docStatusID to Open: {form.docStatusID.data}")

    # GET FILTER PARAMETERS
    shipment_type_filter = request.args.get('shipment_type', type=int)
    doc_level_filter = request.args.get('doc_level', type=int)
    search_term = request.args.get('search', '')
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 5, type=int)
    
    print(f"DEBUG: Filter params - Status: '{status_filter}', Shipment Type: {shipment_type_filter}, Doc Level: {doc_level_filter}, Search: '{search_term}', Page: {page}, Per Page: {per_page}")

    # BUILD FILTERED QUERY
    query = (
        ShipDocumentEntryMaster.query
        .join(ShipmentType, ShipDocumentEntryMaster.shipTypeid == ShipmentType.id)
        .join(ShipCategory, ShipDocumentEntryMaster.shipCategory == ShipCategory.id)
        .join(DocumentStatus, ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID)
        .outerjoin(CompanyInfo, ShipDocumentEntryMaster.assigned_clearing_company_id == CompanyInfo.id)  # Join for assigned shipping agent
        .options(
            db.joinedload(ShipDocumentEntryMaster.shipment_type),
            db.joinedload(ShipDocumentEntryMaster.ship_category_rel),
            db.joinedload(ShipDocumentEntryMaster.document_status),
            db.joinedload(ShipDocumentEntryMaster.assigned_clearing_company),  # Load assigned shipping agent
        )
        .filter(ShipDocumentEntryMaster.customer_id == customer.id)
    )

    if status_filter:
        print(f"DEBUG: Applying status filter: '{status_filter}'")
        if status_filter.lower() == 'open':
            query = query.filter(db.func.lower(DocumentStatus.docStatusName).like('%open%'))
        elif status_filter.lower() == 'new':
            query = query.filter(db.func.lower(DocumentStatus.docStatusName).like('%new%'))
        elif status_filter.lower() == 'ongoing':
            query = query.filter(
                ~db.func.lower(DocumentStatus.docStatusName).like('%open%'),
                ~db.func.lower(DocumentStatus.docStatusName).like('%new%'),
                ~db.func.lower(DocumentStatus.docStatusName).like('%complete%'),
                ~db.func.lower(DocumentStatus.docStatusName).like('%done%')
            )
        elif status_filter.lower() == 'completed':
            query = query.filter(
                db.or_(
                    db.func.lower(DocumentStatus.docStatusName).like('%complete%'),
                    db.func.lower(DocumentStatus.docStatusName).like('%done%')
                )
            )

    # Apply shipment type filter if specified
    # Apply shipment type filter if specified
    if shipment_type_filter:
        print(f"DEBUG: Applying shipment type filter: {shipment_type_filter}")
        # Filter by base type ID instead of individual shipment type ID
        query = query.join(ShipmentTypeBase, ShipmentType.base_type_id == ShipmentTypeBase.id)
        query = query.filter(ShipmentTypeBase.id == shipment_type_filter)

    if doc_level_filter is not None:
        print(f"DEBUG: Applying doc level filter: {doc_level_filter}")
        query = query.filter(ShipDocumentEntryMaster.docLevel == doc_level_filter)

    # Apply search filter if specified
    if search_term:
        print(f"DEBUG: Applying search filter: '{search_term}'")
        search_pattern = f"%{search_term}%"
        query = query.filter(
            db.or_(
                ShipDocumentEntryMaster.docserial.ilike(search_pattern),
                ShipCategory.catname.ilike(search_pattern),
                ShipmentType.shipment_name.ilike(search_pattern),
                DocumentStatus.docStatusName.ilike(search_pattern),
                CompanyInfo.company_name.ilike(search_pattern)  # Add search for shipping agent
            )
        )

    # Apply ordering and pagination
    query = query.order_by(ShipDocumentEntryMaster.dateCreated.desc())
    entries = query.paginate(page=page, per_page=per_page, error_out=False)

    print(f"DEBUG: Retrieved {len(entries.items)} entries for customer after filtering")

    # Calculate document counts for each entry
    for entry in entries.items:
        entry.required_documents = ShipCatDocument.query.filter_by(
            shipCatid=entry.shipCategory, shipmentTypeid=entry.shipTypeid
        ).all()

        existing_attachments = ShipDocumentEntryAttachment.query.filter_by(
            shipDocEntryMasterID=entry.id
        ).all()
        
        entry.attachments = existing_attachments

        entry.accepted_docs_count = len(
            [doc for doc in existing_attachments if doc.docAccepted == 'accepted']
        )
        
        entry.rejected_docs_count = len(
            [doc for doc in existing_attachments if doc.docAccepted == 'rejected']
        )

        print(f"DEBUG: Entry {entry.docserial} has {len(entry.required_documents)} required documents, {len(existing_attachments)} attachments")

    # Get all available shipment types for the filter dropdown (from all assigned companies)
    # Get all available shipment types for the filter dropdown (from all assigned companies)
    available_shipment_types = []
    if assigned_companies:
        company_ids = [comp.id for comp in assigned_companies]
        
        # Query with join to base table and group by base type to eliminate duplicates
        available_shipment_types = (
            db.session.query(
                ShipmentTypeBase.id.label('base_id'),
                ShipmentTypeBase.base_code.label('base_code')
            )
            .join(ShipmentType, ShipmentType.base_type_id == ShipmentTypeBase.id)
            .filter(
                ShipmentType.company_id.in_(company_ids),
                ShipmentType.is_active == True
            )
            .group_by(ShipmentTypeBase.id, ShipmentTypeBase.base_code)
            .all()
        )
    
    # Pass current datetime for deadline calculations
    from datetime import datetime
    current_time_sri_lanka = get_sri_lanka_time()
    now = current_time_sri_lanka

    base_query = (
        ShipDocumentEntryMaster.query
        .join(ShipmentType, ShipDocumentEntryMaster.shipTypeid == ShipmentType.id)
        .join(ShipCategory, ShipDocumentEntryMaster.shipCategory == ShipCategory.id)
        .join(DocumentStatus, ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID)
        .outerjoin(CompanyInfo, ShipDocumentEntryMaster.assigned_clearing_company_id == CompanyInfo.id)
        .filter(ShipDocumentEntryMaster.customer_id == customer.id)
    )

    # Calculate counts for each status
    status_counts = {
        'total': base_query.count(),
        'open': base_query.filter(db.func.lower(DocumentStatus.docStatusName).like('%open%')).count(),
        'new': base_query.filter(db.func.lower(DocumentStatus.docStatusName).like('%new%')).count(),
        'ongoing': base_query.filter(
            ~db.func.lower(DocumentStatus.docStatusName).like('%open%'),
            ~db.func.lower(DocumentStatus.docStatusName).like('%new%'),
            ~db.func.lower(DocumentStatus.docStatusName).like('%complete%'),
            ~db.func.lower(DocumentStatus.docStatusName).like('%done%')
        ).count(),
        'completed': base_query.filter(
            db.or_(
                db.func.lower(DocumentStatus.docStatusName).like('%complete%'),
                db.func.lower(DocumentStatus.docStatusName).like('%done%')
            )
        ).count()
    }

    return render_template(
        "customer_portal/sea_import.html", 
        form=form, 
        entries=entries,
        customer=customer, 
        assigned_shipping_agents=assigned_companies,  # New data for first dropdown
        shipment_types=shipment_types if 'shipment_types' in locals() else [],
        available_shipment_types=available_shipment_types,
        now=now,
        status_counts=status_counts,
        status_filter=status_filter  # NEW: Pass status filter to template
    )



@bp.route("/sea-import/api/create", methods=["POST"])
@login_required
def sea_import_api_create():
    """API endpoint for creating sea import entries"""
    try:
        # Get the customer associated with the current user
        customer = Customer.query.filter_by(user_id=current_user.id).first()
        if not customer:
            return jsonify({"success": False, "message": "No customer profile found"})

        # Debug logging
        print("DEBUG API: Form data received:", request.form)
        
        # Get form data - CHANGED FIELD NAME
        assigned_clearing_company_id = request.form.get("assignedClearanceCompany")  # Updated field name
        shipment_type_id = request.form.get("shipTypeid")
        ship_category_id = request.form.get("shipCategory")
        deadline_date = request.form.get("dealineDate")
        comments = request.form.get("custComment")
        
        # Validate required fields
        if not assigned_clearing_company_id or not shipment_type_id or not ship_category_id or not deadline_date:
            missing_fields = []
            if not assigned_clearing_company_id: missing_fields.append("assigned clearance company")
            if not shipment_type_id: missing_fields.append("shipment type")
            if not ship_category_id: missing_fields.append("ship category")
            if not deadline_date: missing_fields.append("deadline date")
            
            return jsonify({
                "success": False, 
                "message": f"Missing required fields: {', '.join(missing_fields)}"
            })
        
        # Verify that the assigned clearance company belongs to current user
        assignment = CompanyAssignment.query.filter_by(
            assigned_by_user_id=current_user.id,
            assigned_company_id=assigned_clearing_company_id,
            is_active=True
        ).first()
        
        if not assignment:
            return jsonify({"success": False, "message": "Invalid clearance company selection"})
        
        # Get shipment type and verify it belongs to the selected company
        shipment_type = ShipmentType.query.filter_by(
            id=shipment_type_id,
            company_id=assigned_clearing_company_id  # Ensure shipment type belongs to selected company
        ).first()
        
        if not shipment_type:
            return jsonify({"success": False, "message": "Invalid shipment type for selected clearance company"})
            
        # Generate document number
        new_doc_num = shipment_type.lastDocNumber + 1
        doc_serial = f"{shipment_type.docCode}{new_doc_num}"
        
        # Find the 'Open' status for the selected shipment type
        print(f"DEBUG API: Looking for 'Open' status for shipment type ID: {shipment_type_id}")
        open_status = DocumentStatus.query.filter(
            DocumentStatus.doctypeid == shipment_type_id,
            db.func.lower(DocumentStatus.docStatusName) == "open",
        ).first()
        
        if not open_status:
            # If no "Open" status exists, let's try to get any status
            any_status = DocumentStatus.query.filter_by(doctypeid=shipment_type_id).first()
            if any_status:
                open_status = any_status
            else:
                return jsonify({"success": False, "message": "Could not find any document status for this document type"})
        
        # Convert deadline date from string to date object if necessary
        try:
            if isinstance(deadline_date, str):
                deadline_date = datetime.strptime(deadline_date, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"success": False, "message": "Invalid date format"})

        current_time_sri_lanka = get_sri_lanka_time()
    
        # Create new entry - FIXED FIELD NAME
        entry = ShipDocumentEntryMaster(
            assigned_clearing_company_id=assigned_clearing_company_id,  # CORRECTED: Use _id suffix
            shipTypeid=shipment_type_id,
            docCode=shipment_type.docCode,
            docnum=new_doc_num,
            docserial=doc_serial,
            dateCreated=current_time_sri_lanka,
            dealineDate=deadline_date,
            docStatusID=open_status.docStatusID,
            custComment=comments,
            cusOriginalReady="Yes" if request.form.get("cusOriginalReady") == "on" else "No",
            shipCategory=ship_category_id,
            user_id=current_user.id,
            customer_id=customer.id,
            company_id=current_user.company_id
        )
        
        # Update shipment type counter
        shipment_type.lastDocNumber = new_doc_num
        
        # Save to database
        db.session.add(entry)
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": "Shipment Entry created successfully",
            "entry_id": entry.id,
            "doc_serial": doc_serial
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG API: Error creating entry: {str(e)}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"})
        

@bp.route("/sea-export")
@login_required
def sea_export():
    return render_template("customer_portal/sea_export.html", title="Sea Export")


@bp.route("/air-import")
@login_required
@customer_required
def air_import():
    return render_template("customer_portal/air_import.html", title="Air Import")


@bp.route("/air-export")
@login_required
@customer_required
def air_export():
    return render_template("customer_portal/air_export.html", title="Air Export")


@bp.route("/transhipment")
@login_required
@customer_required
def transhipment():
    return render_template("customer_portal/transhipment.html", title="Transhipment")



@bp.route("/get-shipment-types-by-company/<int:company_id>")
@login_required
def get_shipment_types_by_company(company_id):
    """Get shipment types for a specific company"""
    try:
        # Verify that this company is assigned to the current user
        assignment = CompanyAssignment.query.filter_by(
            assigned_by_user_id=current_user.id,
            assigned_company_id=company_id,
            is_active=True
        ).first()
        
        if not assignment:
            return jsonify({"error": "Unauthorized access to this company"}), 403
        
        shipment_types = ShipmentType.query.filter_by(
            company_id=company_id, 
            is_active=True
        ).all()
        
        return jsonify([{
            'id': st.id,
            'shipment_name': st.shipment_name,
            'docCode': st.docCode
        } for st in shipment_types])
        
    except Exception as e:
        print(f"Error fetching shipment types: {str(e)}")
        return jsonify({"error": "Failed to fetch shipment types"}), 500

@bp.route("/get-ship-categories/<int:shipment_type_id>")
@login_required  
def get_ship_categories(shipment_type_id):
    """Get ship categories for a specific shipment type (existing endpoint - modify if needed)"""
    try:
        ship_categories = ShipCategory.query.filter_by(
            shipmentType=shipment_type_id
        ).all()
        
        return jsonify([{
            'id': sc.id,
            'name': sc.catname
        } for sc in ship_categories])
        
    except Exception as e:
        print(f"Error fetching ship categories: {str(e)}")
        return jsonify({"error": "Failed to fetch ship categories"}), 500

@bp.route("/get-document-statuses/<int:shipment_type_id>")
@login_required
def get_document_statuses(shipment_type_id):
    """Get document statuses for a specific shipment type (existing endpoint - modify if needed)"""
    try:
        doc_statuses = DocumentStatus.query.filter_by(
            doctypeid=shipment_type_id
        ).all()
        
        return jsonify([{
            'id': ds.docStatusID,
            'name': ds.docStatusName
        } for ds in doc_statuses])
        
    except Exception as e:
        print(f"Error fetching document statuses: {str(e)}")
        return jsonify({"error": "Failed to fetch document statuses"}), 500
    

@bp.route("/sea-import/<int:entry_id>", methods=["GET", "POST"])
@login_required
def edit_entry(entry_id):
    entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
    form = ShipDocumentEntryForm(obj=entry)

    # Get shipment types for dropdown
    shipment_types = ShipmentType.query.filter_by(is_active=True).all()
    form.shipTypeid.choices = [(st.id, st.shipment_name) for st in shipment_types]

    # Get document statuses based on the entry's shipment type
    doc_statuses = DocumentStatus.query.filter_by(doctypeid=entry.shipTypeid).all()
    form.docStatusID.choices = [
        (ds.docStatusID, ds.docStatusName) for ds in doc_statuses
    ]

    # Get ship categories for the entry's shipment type
    ship_categories = ShipCategory.query.filter_by(shipmentType=entry.shipTypeid).all()
    form.shipCategory.choices = [(sc.id, sc.catname) for sc in ship_categories]

    # Set choices for cusOriginalReady
    form.cusOriginalReady.choices = [("Yes", "Yes"), ("No", "No")]


    if form.validate_on_submit():
        action = request.form.get("action")

        if action == "submit":
            # Update docLevel to 1 when submitting
            entry.docLevel = 1

            current_time_sri_lanka = get_sri_lanka_time()

            # Record submission date
            entry.dateSubmitted = current_time_sri_lanka

            # Find the 'New' status for this shipment type
            new_status = DocumentStatus.query.filter(
                DocumentStatus.doctypeid == entry.shipTypeid,
                db.func.lower(DocumentStatus.docStatusName) == "new",
            ).first()

            if new_status:
                entry.docStatusID = new_status.docStatusID
            else:
                flash("Could not find 'New' status for this document type.", "warning")

        # Update other fields
        entry.dealineDate = form.dealineDate.data
        if action != "submit":  # Only update docStatusID if not submitting
            entry.docStatusID = form.docStatusID.data
        entry.custComment = form.custComment.data
        entry.cusOriginalReady = form.cusOriginalReady.data
        entry.shipCategory = form.shipCategory.data


        db.session.commit()

        company_email = entry.company.email
        company_name = entry.company.company_name
        customer_name = entry.customer.short_name
        entry_docserial = entry.docserial
        
        if action == "submit":
            flash("New entry submitted successfully!", "success")
            send_email(
                subject="New Document Has Been Submitted",
                recipient=company_email,
                template="email/new_entry_submitted.html",
                name=company_name,
                customer=customer_name,
                entry_docserial=entry_docserial,
            )
        else:
            flash("Document entry updated successfully!", "success")

        return redirect(url_for("customer_portal.sea_import"))

    # Set initial values for the form fields
    if request.method == "GET":
        form.dealineDate.data = entry.dealineDate
        form.docStatusID.data = entry.docStatusID
        form.custComment.data = entry.custComment
        form.cusOriginalReady.data = entry.cusOriginalReady
        form.shipCategory.data = entry.shipCategory
        form.shipTypeid.data = entry.shipTypeid
        # FIX: Set the clearing company data
        form.assigned_clearing_company.data = entry.assigned_clearing_company_id

    return render_template(
        "customer_portal/edit_entry.html", 
        form=form, 
        entry=entry
    )


@bp.route("/sea-import/delete/<int:entry_id>", methods=["POST"])
@login_required
def delete_entry(entry_id):
    try:
        # First, find all attachments related to this entry
        attachments = ShipDocumentEntryAttachment.query.filter_by(
            shipDocEntryMasterID=entry_id
        ).all()

        for attachment in attachments:
            # Delete related history records first
            ShipDocumentHistory.query.filter_by(attachment_id=attachment.id).delete()

            # Delete the file from S3 if it exists
            if attachment.attachement_path:
                try:
                    delete_file_from_s3(
                        current_app.config["S3_BUCKET_NAME"],
                        attachment.attachement_path,
                    )
                    print("File deleted successfully from S3")
                except Exception as e:
                    print(f"Error deleting file from S3: {str(e)}")

            # Delete the attachment record
            db.session.delete(attachment)

        # Use no_autoflush to avoid premature flush
        with db.session.no_autoflush:
            entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)

        # Check if the entry belongs to the current user
        if entry.user_id != current_user.id:
            return (
                jsonify(
                    {"success": False, "message": "Unauthorized to delete this entry"}
                ),
                403,
            )

        # Delete the main entry
        db.session.delete(entry)
        db.session.commit()

        return jsonify({"success": True, "message": "Entry deleted successfully"})
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting entry: {str(e)}")
        return jsonify({"success": False, "message": "Error deleting entry"}), 500
      

@bp.route("/view-sample-document/<path:file_path>")
@login_required
def view_sample_document(file_path):
    """
    CONVERTED: Securely serve sample document through app proxy
    """
    try:
        # The file path is the S3 key
        s3_key = file_path.replace("\\", "/")  # Normalize path separators
        print(f"Attempting to view sample file with S3 key: {s3_key}")

        # Serve directly through your app (secure)
        return serve_s3_file(s3_key)
        
    except Exception as e:
        print(f"Error viewing sample document: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f"Error viewing sample file", "danger")
        return redirect(url_for("customer_portal.sea_import"))



@bp.route("/get-required-documents/<int:ship_cat_id>/<int:ship_type_id>/<int:entry_id>")
@login_required
@customer_required
def get_required_documents(ship_cat_id, ship_type_id, entry_id):
    try:
        print(
            f"Getting documents for entry_id={entry_id}, shipCatid={ship_cat_id}, shipmentTypeid={ship_type_id}"
        )

        # First, get existing attachments
        existing_attachments = ShipDocumentEntryAttachment.query.filter_by(
            shipDocEntryMasterID=entry_id
        ).all()

        existing_descriptions = [att.description for att in existing_attachments]
        print(f"Found {len(existing_attachments)} existing attachments")

        # Get all required documents for this category and shipment type
        all_required_docs = ShipCatDocument.query.filter_by(
            shipCatid=ship_cat_id, shipmentTypeid=ship_type_id
        ).all()
        print(f"Found {len(all_required_docs)} total required documents")

        required_docs_map = {doc.description: doc for doc in all_required_docs}

        # Filter out documents that already have attachments
        # But include documents with multiple_document = 1 regardless of existing attachments
        new_required_docs = [
            doc
            for doc in all_required_docs
            if doc.description not in existing_descriptions or doc.multiple_document == 1
        ]
        print(f"Found {len(new_required_docs)} new required documents")

        # Create a complete list of all required documents with their configurations
        all_required_docs_data = [
            {
                "id": doc.id,
                "description": doc.description,
                "isMandatory": doc.isMandatory,
                "sample_file_path": doc.sample_file_path,
                "multiple_document": doc.multiple_document,
                "ai_validate": doc.ai_validate
            }
            for doc in all_required_docs
        ]

        return jsonify(
            {
                "existing_attachments": [
                    {
                        "id": att.id,
                        "description": att.description,
                        "isMandatory": att.isMandatory,
                        "attachement_path": att.attachement_path,
                        "note": att.note,
                        "is_existing": True,
                        # Include document approval status fields
                        "docAccepted": att.docAccepted,
                        "docAccepteDate": att.docAccepteDate.isoformat() if att.docAccepteDate else None,
                        "docAccepteComments": att.docAccepteComments,
                        "expiry_date": att.expiry_date.isoformat() if att.expiry_date else None,
                        "sample_file_path": required_docs_map.get(att.description, {}).sample_file_path if att.description in required_docs_map else None,
                        "ai_validated": att.ai_validated,
                        # Add multiple_document field for existing attachments
                        "multiple_document": required_docs_map.get(att.description, {}).multiple_document if att.description in required_docs_map else 0
                        # Also include the document ID for reference
                    }
                    for att in existing_attachments
                ],
                "new_required_documents": [
                    {
                        "id": doc.id,
                        "description": doc.description,
                        "isMandatory": doc.isMandatory,
                        "sample_file_path": doc.sample_file_path,
                        "is_existing": False,
                        # Add fields for multiple document support
                        "multiple_document": doc.multiple_document,
                        "ai_validate": doc.ai_validate
                    }
                    for doc in new_required_docs
                ],
                # Add complete list of all required documents
                "all_required_documents": all_required_docs_data
            }
        )
    except Exception as e:
        print(f"Error in get_required_documents: {str(e)}")
        import traceback

        traceback.print_exc()
        return jsonify(
            {"existing_attachments": [], "new_required_documents": [], "all_required_documents": [], "error": str(e)}
        )


@bp.route("/get-document-validation/<int:doc_id>")
@login_required
@customer_required
def get_document_validation(doc_id):
    try:
        # Get the document attachment
        document = ShipDocumentEntryAttachment.query.get_or_404(doc_id)
        
        # Check if document has been validated
        if document.ai_validated not in [1, 2]:
            return jsonify({
                "success": False,
                "message": "Document has not been validated yet"
            })
        
        # Parse the validation results and extracted content
        validation_results = {}
        extracted_content = {}
        
        if document.validation_results:
            try:
                validation_results = json.loads(document.validation_results)
                # If document_similarity is present at the root of validation_results, save it
                if isinstance(validation_results, dict) and 'document_similarity' in validation_results:
                    document_similarity = validation_results['document_similarity']
            except:
                validation_results = {}
                
        if document.extracted_content:
            try:
                extracted_content = json.loads(document.extracted_content)
            except:
                extracted_content = {}
        
        return jsonify({
            "success": True,
            "results": {
                "validation_results": validation_results,
                "extracted_content": extracted_content,
                "match_percentage": document.validation_percentage,
                "document_similarity": document.document_similarity_percentage / 100 if document.document_similarity_percentage else 0,
                "document_similarity_message": document.similarity_message,
                "validation_status": document.ai_validated,
                "error": False
            }
        })
    except Exception as e:
        print(f"Error in get_document_validation: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)})


def load_shipment_items_data(entry_id):
    """Load shipment items and related data for the items tab"""
    try:
        # Get shipment items with PO currency and HS code information
        shipment_items_query = db.session.query(
            ShipmentItem,
            POHeader.currency.label('po_currency'),
            POMaterial,
            HSCode
        ).outerjoin(
            PODetail, ShipmentItem.po_detail_id == PODetail.id
        ).outerjoin(
            POHeader, PODetail.po_header_id == POHeader.id
        ).outerjoin(
            POMaterial, db.or_(
                PODetail.material_id == POMaterial.id,  # For PO items
                db.and_(
                    ShipmentItem.source_type == 'manual',
                    POMaterial.material_code == ShipmentItem.material_code,
                    POMaterial.company_id == current_user.company_id
                )  # For manual items, try to match by material code
            )
        ).outerjoin(
            HSCode, POMaterial.hs_code_id == HSCode.id
        ).filter(
            ShipmentItem.shipment_id == entry_id,
            ShipmentItem.company_id == current_user.company_id
        ).order_by(ShipmentItem.created_at.desc())
        
        shipment_items_data = shipment_items_query.all()
        
        # Process items to include currency and HS code information
        shipment_items = []
        for item_data in shipment_items_data:
            item = item_data[0]  # ShipmentItem object
            po_currency = item_data[1] or 'LKR'  # Default to LKR if no PO currency
            po_material = item_data[2]  # POMaterial object
            hs_code = item_data[3]  # HSCode object
            
            # Add currency information to the item object
            item.po_currency = po_currency
            
            # Add HS code information
            item.hs_code = hs_code
            item.po_material = po_material
            
            # Get document count if HS code exists
            if hs_code:
                # Get required documents count
                required_docs_count = HSCodeDocument.query.filter_by(
                    hscode_id=hs_code.id
                ).count()
                
                # Get uploaded documents count for this material
                if po_material:
                    uploaded_docs_count = MaterialHSDocuments.query.filter_by(
                        material_id=po_material.id,
                        hs_code_id=hs_code.id,
                        company_id=current_user.company_id
                    ).count()
                else:
                    uploaded_docs_count = 0
                
                item.required_docs_count = required_docs_count
                item.uploaded_docs_count = uploaded_docs_count
            else:
                item.required_docs_count = 0
                item.uploaded_docs_count = 0
            
            shipment_items.append(item)
        
        # Get available PO items for this company that haven't been added to this shipment
        existing_po_detail_ids = [item.po_detail_id for item in shipment_items if item.po_detail_id]
        
        po_items_query = db.session.query(
            PODetail,
            POHeader.currency.label('currency'),
            POMaterial,
            HSCode
        ).join(
            POHeader, PODetail.po_header_id == POHeader.id
        ).outerjoin(
            POMaterial, PODetail.material_id == POMaterial.id
        ).outerjoin(
            HSCode, POMaterial.hs_code_id == HSCode.id
        ).filter(
            PODetail.quantity_pending > 0,
            PODetail.company_id == current_user.company_id
        )
        
        if existing_po_detail_ids:
            po_items_query = po_items_query.filter(
                ~PODetail.id.in_(existing_po_detail_ids)
            )
        
        available_po_items_data = po_items_query.order_by(
            PODetail.po_number.desc(),
            PODetail.material_code
        ).all()
        
        # Process PO items to include currency and HS code
        available_po_items = []
        for po_data in available_po_items_data:
            po_item = po_data[0]  # PODetail object
            currency = po_data[1] or 'LKR'  # Default to LKR
            po_material = po_data[2]  # POMaterial object
            hs_code = po_data[3]  # HSCode object
            
            # Add currency and HS code to the PO item object
            po_item.currency = currency
            po_item.hs_code = hs_code
            po_item.po_material = po_material
            
            # Get document counts for PO items too
            if hs_code and po_material:
                required_docs_count = HSCodeDocument.query.filter_by(
                    hscode_id=hs_code.id
                ).count()
                
                uploaded_docs_count = MaterialHSDocuments.query.filter_by(
                    material_id=po_material.id,
                    hs_code_id=hs_code.id,
                    company_id=current_user.company_id
                ).count()
                
                po_item.required_docs_count = required_docs_count
                po_item.uploaded_docs_count = uploaded_docs_count
            else:
                po_item.required_docs_count = 0
                po_item.uploaded_docs_count = 0
            
            available_po_items.append(po_item)
        
        # Get unique suppliers for filter
        available_suppliers = db.session.query(PODetail.supplier_name).filter(
            PODetail.quantity_pending > 0
        ).distinct().order_by(PODetail.supplier_name).all()
        available_suppliers = [s[0] for s in available_suppliers if s[0]]
        
        print(f"Loaded {len(shipment_items)} shipment items and {len(available_po_items)} available PO items with HS code data")
        
        return shipment_items, available_po_items, available_suppliers
        
    except Exception as e:
        print(f"Error loading shipment items data: {str(e)}")
        import traceback
        traceback.print_exc()
        return [], [], []


@bp.route("/order_shipment/<int:order_id>", methods=["GET"])
@login_required
def customer_order_shipment(order_id):
    """Customer view of order shipment details"""
    # Print statement to log the start of the function
    print(f"Entering customer_order_shipment route - Method: {request.method}")
    print(f"Order ID: {order_id}")

    # Initialize variables
    shipment = None
    order = None
    import_containers = []
    export_containers = []
    documents = []
    expenses = []
    customer_visible_expenses = []
    
    try:
        # First, fetch the order and verify ownership
        order = ShipDocumentEntryMaster.query.get_or_404(order_id)
        
        if not order or order.user_id != current_user.id:
            flash("You don't have permission to view this shipment", "danger")
            return redirect(url_for('customer_portal.sea_import'))
        
        # Check if order is submitted
        if order.docLevel not in [1, 5]:  # Assuming 1 is the status for 'Open'
            flash("This order has not been submitted yet", "warning")
            return redirect(url_for('customer_portal.sea_import'))
        
        # Once verified, fetch the shipment
        existing_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=order_id).first()
        
        if existing_shipment:
            shipment = existing_shipment
            print(f"Found shipment with ID: {existing_shipment.id}")

            # Fetch container details
            import_containers = ImportContainer.query.filter_by(shipment_id=order_id).all()
            export_containers = ExportContainer.query.filter_by(shipment_id=order_id).all()
            
            # Fetch documents (only non-confidential ones)
            documents = ShipDocumentEntryDocument.query.filter_by(
                ship_doc_entry_id=order_id, 
                is_confidential=False
            ).all()
            
            # Fetch all expenses for the shipment
            all_expenses = ShipmentExpense.query.filter_by(
                shipment_id=order_id
            ).all()
            
            # Filter expenses that are visible to customer
            customer_visible_expenses = [
                expense for expense in all_expenses 
                if expense.visible_to_customer == True
            ]
            
            # For logging purposes, track original expense count
            expenses = all_expenses
            
            print(f"Loaded shipment for customer view: {shipment}")
            print(f"Loaded {len(import_containers)} import containers and {len(export_containers)} export containers")
            print(f"Loaded {len(documents)} visible documents")
        else:
            print("No shipment details are available for this order yet", "info")
            
    except Exception as load_error:
        print(f"Error loading order/shipment: {str(load_error)}")
        flash(f"Error loading order", "danger")
        return redirect(url_for('customer_portal.sea_import'))
    
    # Fetch data for dropdown lists with error handling - needed for display only
    try:
        print("Fetching dropdown data")
        shipment_types = ShipmentType.query.all()
        customers = Customer.query.filter_by(id=current_user.id).all()  # Only current customer
        billing_parties = User.query.filter_by(company_id=current_user.company_id).all()
        sales_people = User.query.filter_by(company_id=current_user.company_id).all()
        cs_executives = User.query.filter_by(company_id=current_user.company_id).all()
        wharf_clerks = User.query.filter_by(company_id=current_user.company_id).all()
        branches = Branch.query.all()
        currencies = CurrencyMaster.query.all()
        income_expenses = IncomeExpense.query.filter_by(company_id=current_user.company_id, status=True).all()
        demurrages = ShipmentDemurrage.query.filter_by(shipment_id=order_id).all()

        # Tasks query - only visible tasks for the customer
        tasks = Task.query.filter(Task.shipment_id == order_id).all()
        
        print(f"Fetched {len(tasks)} tasks")
        
    except Exception as fetch_error:
        print(f"Error fetching dropdown data: {str(fetch_error)}")
        import traceback
        print(f"Full error details: {traceback.format_exc()}")
        
        # Set empty lists to prevent template rendering errors
        shipment_types = []
        customers = []
        billing_parties = []
        sales_people = []
        cs_executives = []
        branches = []
        currencies = []
        income_expenses = []
        tasks = []
    
    shipment_items, available_po_items, available_suppliers = load_shipment_items_data(order_id)
    print(f"Loaded items tab data: {len(shipment_items)} items, {len(available_po_items)} PO items")

    ship_doc_entry = ShipDocumentEntryMaster.query.get(order_id)
    if ship_doc_entry:
        company_info = CompanyInfo.query.get(ship_doc_entry.assigned_clearing_company_id)
    else:
        company_info = None


    # Log template rendering
    print("Rendering customer_order_shipment.html template")
    
    return render_template(
        "customer_portal/order_shipment_customer.html",
        title="Shipment Details",
        entry=order,  # Pass the order as entry for consistency
        shipment=shipment,
        order=order,
        view_only=True,  # Always true for customer view
        import_containers=import_containers,
        export_containers=export_containers,
        shipment_types=shipment_types,
        customers=customers,
        billing_parties=billing_parties,
        sales_people=sales_people,
        cs_executives=cs_executives,
        branches=branches,
        wharf_clerks=wharf_clerks,
        currencies=currencies,
        income_expenses=income_expenses,
        documents=documents,
        expenses=expenses,  # Original expenses for compatibility
        customer_visible_expenses=customer_visible_expenses,  # New filtered list for customer view
        tasks=tasks,
        shipment_items=shipment_items,
        available_po_items=available_po_items,  
        available_suppliers=available_suppliers,
        demurrages=demurrages,
        company_info=company_info
    )



@bp.route("/api/demurrage/shipment/<int:shipment_id>", methods=["GET"])
@login_required
def get_shipment_demurrage(shipment_id):
    """Get all demurrage records for a shipment"""
    try:
        print(f"[GET] Fetching demurrage for shipment ID: {shipment_id}")
        shipment = ShipDocumentEntryMaster.query.get_or_404(shipment_id)
        
        demurrage_records = db.session.query(
            ShipmentDemurrage,
            DemurrageReasons.reason_name,
            CurrencyMaster.CurrencyCode
        ).join(
            DemurrageReasons, ShipmentDemurrage.reason_id == DemurrageReasons.id
        ).join(
            CurrencyMaster, ShipmentDemurrage.currency_id == CurrencyMaster.currencyID
        ).filter(
            ShipmentDemurrage.shipment_id == shipment_id
        ).all()
        print(f"Found {len(demurrage_records)} demurrage records")

        import_containers = ImportContainer.query.filter_by(shipment_id=shipment_id).all()
        export_containers = ExportContainer.query.filter_by(shipment_id=shipment_id).all()
        print(f"Import containers: {len(import_containers)}, Export containers: {len(export_containers)}")

        container_map = {}
        for container in import_containers:
            container_map[f"import_{container.id}"] = container.container_number
        for container in export_containers:
            container_map[f"export_{container.id}"] = container.container_number

        result = []
        total_amount = 0

        for demurrage, reason_name, currency_code in demurrage_records:
            container_key = f"{demurrage.container_type}_{demurrage.container_id}"
            container_number = container_map.get(container_key, "Unknown")
            
            result.append({
                "id": demurrage.id,
                "container_number": container_number,
                "container_id": demurrage.container_id,
                "container_type": demurrage.container_type,
                "demurrage_date": demurrage.demurrage_date.strftime("%Y-%m-%d"),
                "amount": demurrage.amount,
                "currency_code": currency_code,
                "currency_id": demurrage.currency_id,
                "reason_name": reason_name,
                "reason_id": demurrage.reason_id,
                "created_at": demurrage.created_at.strftime("%Y-%m-%d %H:%M")
            })
            total_amount += demurrage.amount
        
        return jsonify({
            "success": True,
            "data": result,
            "total_amount": total_amount
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route("/expense/<int:expense_id>/attachment")
@login_required
def view_expense_attachment(expense_id):
    try:
        print(f"[DEBUG] Fetching expense with ID: {expense_id}")
        # Get the expense
        expense = ShipmentExpense.query.get_or_404(expense_id)
        print(f"[DEBUG] Found expense, shipment_id: {expense.shipment_id}, attachment_path: {expense.attachment_path}")
        

        # Get the order to verify customer ownership
        order = ShipDocumentEntryMaster.query.get(expense.shipment_id)
        if not order:
            print("[DEBUG] Order not found.")
            abort(404)
        if order.user_id != current_user.id:
            print(f"[DEBUG] Unauthorized access: current_user.id = {current_user.id}, order.user_id = {order.user_id}")
            abort(403)  # Forbidden
        
        # Security check: Verify both visibility flags
        if not expense.visible_to_customer:
            print("[DEBUG] Expense not visible to customer.")
            abort(403)
        if not expense.attachment_visible_to_customer:
            print("[DEBUG] Attachment not visible to customer.")
            abort(403)
        
        # If passed all checks, serve securely from S3
        if expense.attachment_path:
            s3_key = expense.attachment_path.replace("\\", "/")
            print(f"[DEBUG] Serving S3 file with key: {s3_key}")
            return serve_s3_file(s3_key)
        else:
            print("[DEBUG] No attachment path found.")
            abort(404)  # File not found
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[ERROR] Error serving expense attachment: {str(e)}")
        abort(500)  # Internal server error




@bp.route("/upload-documents", methods=["POST"])
@login_required
@customer_required
def upload_documents():
    try:
        entry_id = request.form.get("entryId")
        if not entry_id:
            return jsonify({"success": False, "message": "Entry ID is required"})

        # Get the entry to verify it exists and belongs to the current user
        entry = ShipDocumentEntryMaster.query.filter_by(
            id=entry_id, user_id=current_user.id
        ).first()

        if not entry:
            return jsonify({"success": False, "message": "Invalid entry"})

        # Get existing attachments to avoid duplicates - but allow multiple for same description
        existing_attachments = ShipDocumentEntryAttachment.query.filter_by(
            shipDocEntryMasterID=entry_id
        ).all()

        # Get all required documents
        required_docs = ShipCatDocument.query.filter_by(
            shipCatid=entry.shipCategory, shipmentTypeid=entry.shipTypeid
        ).all()

        # Create a map of document IDs for quick lookup
        doc_map = {doc.id: doc for doc in required_docs}

        # Process uploaded files
        uploaded_files = []
        
        # Iterate through all form data to find file uploads
        for key in request.files.keys():
            if key.startswith('document_'):
                # Extract doc_id and index from key (format: document_{doc_id}_{index})
                parts = key.split('_')
                if len(parts) >= 3:
                    doc_id = parts[1]
                    index = parts[2]
                    
                    # Get the document definition
                    doc = doc_map.get(int(doc_id))
                    if not doc:
                        continue
                    
                    file = request.files[key]
                    if file and file.filename:
                        # Get associated form fields
                        note_key = f"note_{doc_id}_{index}"
                        expiry_date_key = f"expiry_date_{doc_id}_{index}"
                        
                        # Check if expiry date is provided and valid
                        expiry_date_str = request.form.get(expiry_date_key)
                        expiry_date = None  # Initialize the variable

                        if expiry_date_str:  # Only validate if expiry date is provided
                        
                            try:
                                expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                                
                                today = get_sri_lanka_time().date()
                                
                                # Validate expiry date is in the future (only if provided)
                                if expiry_date <= today:
                                    return jsonify({
                                        "success": False, 
                                        "message": f"Expiry date for document '{doc.description}' must be in the future"
                                    })
                            except ValueError:
                                return jsonify({"success": False, "message": f"Invalid expiry date format for document: {doc.description}"})

                        # If multiple_document is 0, check if document already exists
                        if doc.multiple_document == 0:
                            existing_doc = next((att for att in existing_attachments if att.description == doc.description), None)
                            if existing_doc:
                                print(f"Skipping document {doc.description} - already exists and multiple not allowed")
                                continue

                        # Proceed with file upload
                        filename = secure_filename(file.filename)
                        # Create S3 key with proper structure
                        s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/{entry_id}/{filename}"

                        # Upload to S3
                        if upload_file_to_s3(
                            file, current_app.config["S3_BUCKET_NAME"], s3_key
                        ):
                            # Create attachment record with S3 path
                            attachment = ShipDocumentEntryAttachment(
                                shipDocEntryMasterID=entry_id,
                                description=doc.description,
                                isMandatory=doc.isMandatory,
                                attachement_path=s3_key,  # Store S3 key instead of local path
                                note=request.form.get(note_key, ""),
                                expiry_date=expiry_date,  # Add expiry date
                                user_id=current_user.id,
                                customer_id=entry.customer_id,
                                ship_category_id=entry.shipCategory,
                                ship_cat_document_id=doc.id,
                                ai_validated=0
                            )
                            db.session.add(attachment)
                            db.session.flush()

                            history_entry = ShipDocumentHistory(
                                attachment_id=attachment.id,
                                shipDocEntryMasterID=entry_id,
                                description=doc.description,
                                document_path=s3_key,  # Use the same S3 path as the attachment
                                action="uploaded",
                                note=request.form.get(note_key, ""),
                                action_comments=f"Document upload - {'Multiple' if doc.multiple_document == 1 else 'Single'}",
                                user_id=current_user.id,
                                customer_id=entry.customer_id,
                                created_at=get_sri_lanka_time()
                            )
                            db.session.add(history_entry)
                            uploaded_files.append({
                                'description': doc.description,
                                'filename': filename,
                                'multiple_allowed': doc.multiple_document == 1
                            })
                            print(f"Created attachment record for {filename} (Doc: {doc.description})")
                        else:
                            return (
                                jsonify(
                                    {
                                        "success": False,
                                        "message": f"Error uploading file {filename} to S3",
                                    }
                                ),
                                500,
                            )

        if not uploaded_files:
            return jsonify({"success": False, "message": "No valid files were uploaded"})

        db.session.commit()
        
        # Send email notifications if docLevel is 1
        if entry.docLevel == 1:
            try:
                # Get company email if company_id exists
                company_email = None
                company_name = None
                if entry.company_id and entry.company:
                    company_email = entry.company.email
                    company_name = entry.company.company_name  # Assuming company has a name field
                
                # Get currently assigned person's email
                assigned_user_email = None
                assigned_user_name = None
                current_assignment = EntryAssignmentHistory.query.filter_by(
                    entry_id=entry_id,
                    currently_assigned=True
                ).first()
                
                
                if current_assignment and current_assignment.assigned_to:
                    assigned_user_email = current_assignment.assigned_to.email
                    assigned_user_name = current_assignment.assigned_to.name  # Assuming user has a name field
                    print('Assigned user found:', assigned_user_email, assigned_user_name)

                # Base email data
                base_email_data = {
                    'entry_id': entry.id,
                    'docserial': entry.docserial,
                    'customer_name': entry.customer.short_name if entry.customer else 'Unknown Customer',
                    'document_count': len(uploaded_files),
                    'uploaded_files': uploaded_files,
                    'upload_date': get_sri_lanka_time().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                # Send email to company if email exists
                if company_email:
                    company_email_data = base_email_data.copy()
                    company_email_data.update({
                        'recipient_name': company_name or 'Company',
                        'is_company': True
                    })
                    send_email(
                        subject=f"New Documents Uploaded - Entry {entry.docserial}",
                        recipient=company_email,
                        template="email/document_upload_notification.html",
                        **company_email_data
                    )
                    print(f"Email sent to company: {company_email}")
                
                # Send email to assigned person if email exists
                if assigned_user_email:
                    user_email_data = base_email_data.copy()
                    user_email_data.update({
                        'recipient_name': assigned_user_name or 'User',
                        'is_company': False
                    })
                    send_email(
                        subject=f"New Documents Uploaded - Entry {entry.docserial}",
                        recipient=assigned_user_email,
                        template="email/document_upload_notification.html",
                        **user_email_data
                    )
                    print(f"Email sent to assigned user: {assigned_user_email}")
                    
            except Exception as email_error:
                # Log email error but don't fail the upload
                print(f"Error sending email notifications: {str(email_error)}")
        
        # Return success with details about uploaded files
        return jsonify({
            "success": True,
            "message": f"Successfully uploaded {len(uploaded_files)} document(s)",
            "uploaded_files": uploaded_files
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error in upload_documents: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
        

@bp.route("/resubmit-document", methods=["POST"])
@login_required
@customer_required
def resubmit_document():
    """Handle document resubmission when a document has been rejected."""
    try:
        # Get form data
        doc_id = request.form.get("docId")
        entry_id = request.form.get("entryId")
        expiry_date = request.form.get("expiryDate")
        note = request.form.get("note", "")
        if not note:
            note = "Resubmitted"

        
        if not doc_id or not entry_id or not expiry_date:
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        # Check if the file was included
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400
            
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400
        
        # Get the document record
        document = ShipDocumentEntryAttachment.query.get(doc_id)
        if not document:
            return jsonify({"success": False, "message": "Document not found"}), 404
            
        # Get the entry record
        entry = ShipDocumentEntryMaster.query.get(entry_id)
        if not entry:
            return jsonify({"success": False, "message": "Entry not found"}), 404
            
        # Check if the entry belongs to the current customer
        if entry.user_id != current_user.id:
            return jsonify({"success": False, "message": "Unauthorized access"}), 403
            
        # Check if the entry is still editable (not submitted)
        if entry.docLevel == 1:
            return jsonify({"success": False, "message": "Cannot resubmit document for a submitted entry"}), 403
            
        if entry.docLevel == 2:
            entry.docLevel = 5  # Set to resubmitted state if not already
        # Validate expiry date
        if expiry_date:  # Only validate if expiry date is provided
            try:
                expiry_date_obj = datetime.strptime(expiry_date, "%Y-%m-%d").date()
                today = get_sri_lanka_time().date()
                
                # Validate expiry date is in the future (only if provided)
                if expiry_date_obj <= today:
                    return jsonify({
                        "success": False, 
                        "message": f"Expiry date for document must be in the future"
                    })
            except ValueError:
                return jsonify({"success": False, "message": "Invalid expiry date format"}), 400
        else:
            expiry_date_obj = None
            
        # Generate S3 key in the same format as upload_documents
        filename = secure_filename(file.filename)
        s3_key = f"{current_app.config['S3_BASE_FOLDER']}/documents/{entry_id}/{filename}"
        
        # Upload to S3
        if upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key):
            # Store old path for logging and history
            old_path = document.attachement_path
            
            # Create history entry for the resubmission
            history_entry = ShipDocumentHistory(
                attachment_id=document.id,
                shipDocEntryMasterID=entry_id,
                description=document.description,
                document_path=old_path,  # Old document path
                action="resubmitted",
                note=note,
                action_comments="Document resubmitted",
                user_id=current_user.id,
                customer_id=entry.customer_id,
                created_at=get_sri_lanka_time()
            )
            db.session.add(history_entry)
            
            # Update document record
            document.attachement_path = s3_key  # Now using S3 key format
            document.note = note
            document.expiry_date = expiry_date_obj
            document.docAccepted = None  # Reset to pending
            document.docAccepteDate = None
            document.docAccepteComments = None
            document.docAccepteUserID = None
            document.ai_validated = 0
            document.validation_results = None
            document.validation_percentage = None
            document.extracted_content = None
            
            # Log the resubmission
            print(f"Document {doc_id} resubmitted. Old path: {old_path}, New path: {s3_key}")
            
            db.session.commit()
            
            # Send email notifications after successful resubmission
            try:
                # Prepare resubmission data
                resubmission_data = {
                    'customer_name': entry.customer.customer_name if entry.customer else current_user.name or current_user.username,
                    'document_name': document.description,
                    'filename': filename,
                    'entry_id': entry.id,
                    'docserial': entry.docserial,
                    'company_name': entry.company.company_name if entry.company else 'Your Service Provider',
                    'resubmission_date': get_sri_lanka_time().strftime('%Y-%m-%d %H:%M:%S'),
                    'expiry_date': expiry_date_obj.strftime('%Y-%m-%d'),
                    'note': note,
                    'has_note': bool(note.strip())
                }
                
                # Send email to company if company email exists
                if entry.company and entry.company.email:
                    company_email_data = resubmission_data.copy()
                    company_email_data.update({
                        'recipient_name': entry.company.company_name,
                        'is_company': True
                    })
                    
                    send_email(
                        subject=f"Document Resubmitted - Entry {entry.docserial}",
                        recipient=entry.company.email,
                        template="email/document_resubmission_notification.html",
                        **company_email_data
                    )
                    print(f"Resubmission email sent to company: {entry.company.email}")
                
                # Send email to assigned person if exists
                current_assignment = EntryAssignmentHistory.query.filter_by(
                    entry_id=entry_id,
                    currently_assigned=True
                ).first()
                
                if current_assignment and current_assignment.assigned_to and current_assignment.assigned_to.email:
                    assigned_email_data = resubmission_data.copy()
                    assigned_email_data.update({
                        'recipient_name': current_assignment.assigned_to.name or current_assignment.assigned_to.username,
                        'is_company': False
                    })
                    
                    send_email(
                        subject=f"Document Resubmitted - Entry {entry.docserial}",
                        recipient=current_assignment.assigned_to.email,
                        template="email/document_resubmission_notification.html",
                        **assigned_email_data
                    )
                    print(f"Resubmission email sent to assigned user: {current_assignment.assigned_to.email}")
                    
            except Exception as email_error:
                # Log email error but don't fail the resubmission
                print(f"Error sending resubmission email notifications: {str(email_error)}")
                import traceback
                traceback.print_exc()
            
            return jsonify({
                "success": True, 
                "message": "Document resubmitted successfully"
            })
        else:
            return jsonify({
                "success": False,
                "message": "Error uploading file to S3"
            }), 500
        
    except Exception as e:
        db.session.rollback()
        print(f"Error resubmitting document: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"An error occurred: {str(e)}"}), 500
    

@bp.route("/get-entry-documents/<int:entry_id>")
@login_required
@customer_required
def get_entry_documents(entry_id):
    # Get the entry
    entry = ShipDocumentEntryMaster.query.filter_by(
        id=entry_id, user_id=current_user.id
    ).first_or_404()

    # Get existing attachments
    existing_documents = ShipDocumentEntryAttachment.query.filter_by(
        shipDocEntryMasterID=entry_id
    ).all()

    # Get required documents based on shipCategory and shipType
    required_documents = ShipCatDocument.query.filter_by(
        shipCatid=entry.shipCategory,
        shipmentTypeid=entry.shipTypeid,  # Changed from shipmentType to shipmentTypeid
    ).all()

    return jsonify(
        {
            "existing_documents": [
                {
                    "id": doc.id,
                    "description": doc.description,
                    "attachement_path": doc.attachement_path,
                    "note": doc.note,
                    "docAccepted": doc.docAccepted,
                    "isMandatory": doc.isMandatory,
                }
                for doc in existing_documents
            ],
            "required_documents": [
                {
                    "id": doc.id,
                    "description": doc.description,
                    "isMandatory": doc.isMandatory,
                }
                for doc in required_documents
            ],
        }
    )


@bp.route("/remove-document/<int:doc_id>", methods=["POST"])
@login_required
@customer_required
def remove_document(doc_id):
    try:
        # Get the document
        document = ShipDocumentEntryAttachment.query.filter_by(
            id=doc_id, user_id=current_user.id
        ).first_or_404()

        # Delete the actual file
        file_path = os.path.join(
            current_app.config["UPLOAD_FOLDER"], document.attachement_path
        )
        if os.path.exists(file_path):
            os.remove(file_path)

        # Delete the database record
        db.session.delete(document)
        db.session.commit()

        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})


@bp.route("/update-documents", methods=["POST"])
@login_required
@customer_required
def update_documents():
    try:
        entry_id = request.form.get("entryId")
        if not entry_id:
            return jsonify({"success": False, "message": "Entry ID is required"})

        # Get the entry
        entry = ShipDocumentEntryMaster.query.filter_by(
            id=entry_id, user_id=current_user.id
        ).first_or_404()

        # Get required documents
        required_docs = ShipCatDocument.query.filter_by(
            shipCatid=entry.shipCategory,
            shipmentTypeid=entry.shipTypeid,  # Changed from shipmentType to shipmentTypeid
        ).all()

        # Create upload directory if it doesn't exist
        upload_dir = os.path.join(
            current_app.config["UPLOAD_FOLDER"], "documents", str(entry_id)
        )
        os.makedirs(upload_dir, exist_ok=True)

        for doc in required_docs:
            file_key = f"document_{doc.id}"
            note_key = f"note_{doc.id}"

            if file_key in request.files:
                file = request.files[file_key]
                if file and file.filename:
                    # Check if document already exists
                    existing_doc = ShipDocumentEntryAttachment.query.filter_by(
                        shipDocEntryMasterID=entry_id, description=doc.description
                    ).first()

                    if existing_doc:
                        # Update existing document
                        if os.path.exists(
                            os.path.join(
                                current_app.config["UPLOAD_FOLDER"],
                                existing_doc.attachement_path,
                            )
                        ):
                            os.remove(
                                os.path.join(
                                    current_app.config["UPLOAD_FOLDER"],
                                    existing_doc.attachement_path,
                                )
                            )

                        filename = secure_filename(file.filename)
                        file_path = os.path.join("documents", str(entry_id), filename)
                        file.save(
                            os.path.join(current_app.config["UPLOAD_FOLDER"], file_path)
                        )

                        existing_doc.attachement_path = file_path
                        existing_doc.note = request.form.get(note_key, "")
                    else:
                        # Create new document
                        filename = secure_filename(file.filename)
                        file_path = os.path.join("documents", str(entry_id), filename)
                        file.save(
                            os.path.join(current_app.config["UPLOAD_FOLDER"], file_path)
                        )

                        attachment = ShipDocumentEntryAttachment(
                            shipDocEntryMasterID=entry_id,
                            description=doc.description,
                            isMandatory=doc.isMandatory,
                            attachement_path=file_path,
                            note=request.form.get(note_key, ""),
                            user_id=current_user.id,
                            customer_id=entry.customer_id,
                        )
                        db.session.add(attachment)



        db.session.commit()
        return jsonify({"success": True})

    except Exception as e:
        db.session.rollback()
        print(f"Error in update_documents: {str(e)}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)})


@bp.route("/view-document/<path:file_path>")
@login_required
def view_document(file_path):
    """
    FIXED: Directly serve the file instead of redirecting to avoid loops
    """
    try:
        # The file path is the S3 key
        s3_key = file_path.replace("\\", "/")  # Normalize path separators
        print(f"Attempting to view file with S3 key: {s3_key}")

        # OPTION 1: Serve directly (recommended - no redirect)
        return serve_s3_file(s3_key)
        
        # OPTION 2: If you prefer redirect, use url_for properly
        # return redirect(url_for('secure.serve_secure_document_simple', s3_key=s3_key))
        
    except Exception as e:
        print(f"Error viewing document: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": "Error viewing document"}), 500


@bp.route("/replace-document", methods=["POST"])
@login_required
def replace_document():
    try:
        if "document" not in request.files:
            return jsonify({"success": False, "message": "No file provided"}), 400

        file = request.files["document"]
        if file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        doc_id = request.form.get("docId")
        entry_id = request.form.get("entryId")
        note = request.form.get("note", "")

        if not doc_id or not entry_id:
            return (
                jsonify({"success": False, "message": "Missing document or entry ID"}),
                400,
            )

        # Get the existing attachment
        attachment = ShipDocumentEntryAttachment.query.get_or_404(doc_id)

        # Verify the entry belongs to the current user
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        if entry.user_id != current_user.id:
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        # Delete the old file from S3 if it exists
        if attachment.attachement_path:
            try:
                delete_file_from_s3(
                    current_app.config["S3_BUCKET_NAME"], attachment.attachement_path
                )
            except Exception as e:
                print(f"Error deleting old file from S3: {str(e)}")

        # Upload the new file to S3
        filename = secure_filename(file.filename)
        s3_key = (
            f"{current_app.config['S3_BASE_FOLDER']}/documents/{entry_id}/{filename}"
        )
        print(f"Uploading file to S3 with key: {s3_key}")

        if upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key):
            # Update the attachment record
            attachment.attachement_path = s3_key
            attachment.note = note
            db.session.commit()
            print(f"File uploaded successfully to S3: {s3_key}")

            return jsonify(
                {
                    "success": True,
                    "message": "Document replaced successfully",
                    "file_path": s3_key,
                }
            )
        else:
            print("Failed to upload file to S3")
            return (
                jsonify({"success": False, "message": "Error uploading file to S3"}),
                500,
            )

    except Exception as e:
        db.session.rollback()
        print(f"Error replacing document: {str(e)}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "message": "Error replacing document"}), 500


@bp.route("/delete-document/<int:doc_id>/<int:entry_id>", methods=["DELETE"])
@login_required
def delete_document(doc_id, entry_id):
    try:
        print(f"Attempting to delete document {doc_id} for entry {entry_id}")
        print(f"Current user ID: {current_user.id}")

        # Get the attachment record
        attachment = ShipDocumentEntryAttachment.query.get(doc_id)
        if not attachment:
            print(f"Document {doc_id} not found")
            return jsonify({"success": False, "message": "Document not found"}), 404

        # Verify the attachment belongs to the specified entry
        if attachment.shipDocEntryMasterID != entry_id:
            print(f"Document {doc_id} does not belong to entry {entry_id}")
            return jsonify({"success": False, "message": "Invalid document"}), 400

        # Verify user has access to this entry
        entry = ShipDocumentEntryMaster.query.get(entry_id)
        if not entry:
            print(f"Entry {entry_id} not found")
            return jsonify({"success": False, "message": "Entry not found"}), 404

        print(f"Entry user_id: {entry.user_id}, Current user ID: {current_user.id}")
        if entry.user_id != current_user.id:
            print(f"Unauthorized: User {current_user.id} does not own entry {entry_id}")
            return jsonify({"success": False, "message": "Unauthorized"}), 403

        # Delete the file from S3 if it exists
        if attachment.attachement_path:
            try:
                print(
                    f"Attempting to delete file from S3: {attachment.attachement_path}"
                )
                # Test S3 permissions first
                s3_client = get_s3_client()
                try:
                    s3_client.head_object(
                        Bucket=current_app.config["S3_BUCKET_NAME"],
                        Key=attachment.attachement_path,
                    )
                    print("S3 file exists and is accessible")
                except Exception as e:
                    print(f"S3 head_object error: {str(e)}")
                    # Continue with deletion even if head_object fails

                # Delete the file
                if delete_file_from_s3(
                    current_app.config["S3_BUCKET_NAME"], attachment.attachement_path
                ):
                    print("File deleted successfully from S3")
                else:
                    print("Failed to delete file from S3")
            except Exception as e:
                print(f"Error deleting file from S3: {str(e)}")
                # Continue with deletion even if S3 deletion fails

        # Delete related records in ship_document_history table first
        try:
            print(f"Deleting history records for attachment {doc_id}")
            
            # Delete all history records for this attachment
            history_records = ShipDocumentHistory.query.filter_by(attachment_id=doc_id).all()
            for record in history_records:
                print(f"Deleting history record {record.id}")
                db.session.delete(record)
            
            print(f"Deleted {len(history_records)} history records")
        except Exception as e:
            print(f"Error deleting history records: {str(e)}")
            db.session.rollback()
            return jsonify({"success": False, "message": "Error deleting related history records"}), 500

        # Delete the attachment record
        db.session.delete(attachment)
        db.session.commit()
        print("Attachment record deleted successfully")

        return jsonify({"success": True, "message": "Document deleted successfully"})

    except Exception as e:
        print(f"Error deleting document: {str(e)}")
        db.session.rollback()
        return jsonify({"success": False, "message": "Error deleting document"}), 500
    
    

@bp.route("/get-entry/<int:entry_id>")
@login_required
@customer_required
def get_entry(entry_id):
    """Get entry details"""
    entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
    return jsonify(
        {"id": entry.id, "docLevel": entry.docLevel, "docserial": entry.docserial}
    )


@bp.route("/download-document/<path:file_path>")
@login_required
def download_document(file_path):
    """Download a sample document from S3"""
    try:
        # Normalize path separators
        file_path = file_path.replace("\\", "/")
        print(f"Attempting to download sample document: {file_path}")
        
        # Extract filename for the Content-Disposition header
        filename = os.path.basename(file_path)
        print(f"Filename: {filename}")
        
        # Construct the S3 URL for the sample document
        s3_url = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{file_path}"
        print(f"S3 URL for sample document: {s3_url}")
        
        # Use requests to get the content
        import requests
        response = requests.get(s3_url, stream=True)
        
        # Check if successful
        if response.status_code != 200:
            print(f"Error fetching sample document: Status code {response.status_code}")
            raise Exception(f"Failed to fetch file: HTTP {response.status_code}")
        
        # Create response with download headers
        flask_response = Response(
            response.iter_content(chunk_size=8192),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": response.headers.get("Content-Type", "application/octet-stream")
            },
            direct_passthrough=True
        )
        
        return flask_response
            
    except Exception as e:
        print(f"Error downloading sample document: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": f"Error downloading document: {str(e)}"}), 500
    
    

@bp.route("/check-mandatory-documents/<int:entry_id>")
@login_required
@customer_required
def check_mandatory_documents(entry_id):
    """Check if all mandatory documents are attached and AI validated (when required)"""
    try:
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)

        # Get all required documents for this entry
        required_docs = ShipCatDocument.query.filter_by(
            shipCatid=entry.shipCategory, shipmentTypeid=entry.shipTypeid
        ).all()

        # Get all attached documents
        attached_docs = ShipDocumentEntryAttachment.query.filter_by(
            shipDocEntryMasterID=entry_id
        ).all()

        # Check if all mandatory documents are attached
        all_mandatory_attached = True
        all_ai_validated = True
        has_pending_validation = False
        
        # Create a set of descriptions that have attachments
        attached_descriptions = {att.description for att in attached_docs}
        
        for doc in required_docs:
            if doc.isMandatory:
                # Check if this document type has at least one attachment
                if doc.description not in attached_descriptions:
                    all_mandatory_attached = False
                    break
                
                # For documents that allow multiple uploads, check all instances
                matching_docs = [
                    attached for attached in attached_docs 
                    if attached.description == doc.description
                ]
                
                # Only check AI validation if ai_validate is enabled for this document type
                if doc.ai_validate == 1:
                    # Check AI validation status for all instances of this document type
                    for matching_doc in matching_docs:
                        # Check if AI validation is pending (status 0)
                        if matching_doc.ai_validated == 0:
                            has_pending_validation = True
                            all_ai_validated = False
                            break
                            
                        # Check if AI validation failed (status 2, 5, 6, 7, 8)
                        elif matching_doc.ai_validated in [2, 5, 6, 7, 8]:
                            all_ai_validated = False
                            break
                    
                    # If we found validation issues, break out of the document loop
                    if not all_ai_validated:
                        break

        return jsonify({
            "success": True, 
            "all_mandatory_attached": all_mandatory_attached,
            "all_ai_validated": all_ai_validated,
            "has_pending_validation": has_pending_validation
        })

    except Exception as e:
        print(f"Error in check_mandatory_documents: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
       


@bp.route('/validate-pending-documents', methods=['GET'])
@login_required
def validate_pending_documents():
    """Validate all pending documents"""
    print("\n" + "="*80)
    print("STARTING BATCH DOCUMENT VALIDATION")
    print("="*80)
    
    try:
        # Get all documents that need validation (ai_validated = 0 AND must be marked for AI validation)
        # Join with ShipCatDocument to check ai_validate flag
        pending_documents = db.session.query(ShipDocumentEntryAttachment)\
            .join(ShipCatDocument, ShipDocumentEntryAttachment.ship_cat_document_id == ShipCatDocument.id)\
            .filter(
                ShipDocumentEntryAttachment.ai_validated == 0,
                ShipCatDocument.ai_validate == 1  # New condition: only validate documents marked for AI validation
            ).all()
        
        print(f"Found {len(pending_documents)} pending documents for AI validation")
        
        if not pending_documents:
            print("No pending documents found for AI validation")
            return jsonify({
                "success": True,
                "message": "No pending documents found for AI validation",
                "validated_count": 0
            })
        
        validated_count = 0
        validation_results = []
        
        # Track which customers/entries need to receive emails
        customers_to_notify = {}
        
        for document in pending_documents:
            # print(f"\nProcessing document ID: {document.id}, Description: {document.description}")
            result = process_document_validation(document)
            
            # Make sure to pass through all results directly
            if result.get("success", False) and result.get("status") != "no_sample":
                validated_count += 1
                
                # Get the entry and customer for this document
                entry = ShipDocumentEntryMaster.query.get(document.shipDocEntryMasterID)
                if entry and entry.customer_id:
                    if entry.customer_id not in customers_to_notify:
                        customers_to_notify[entry.customer_id] = set()
                    customers_to_notify[entry.customer_id].add(entry.id)
                
            validation_results.append({
                "attachment_id": document.id,
                "result": result
            })
        
        # Send validation emails to all customers who had documents validated
        emails_sent = 0
        for customer_id, entry_ids in customers_to_notify.items():
            for entry_id in entry_ids:
                # Check if all documents in this entry have been validated
                total_docs = ShipDocumentEntryAttachment.query.filter_by(
                    shipDocEntryMasterID=entry_id
                ).count()
                
                validated_docs = ShipDocumentEntryAttachment.query.filter(
                    ShipDocumentEntryAttachment.shipDocEntryMasterID==entry_id,
                    ShipDocumentEntryAttachment.ai_validated!=0
                ).count()
                
                if validated_docs == total_docs:
                    # All documents validated, send email
                    if send_document_validation_results_email(customer_id, entry_id):
                        emails_sent += 1
        
        print("\n" + "="*80)
        print(f"BATCH VALIDATION COMPLETED: {validated_count} of {len(pending_documents)} documents validated")
        print(f"Email notifications sent to {emails_sent} entries")
        print("="*80 + "\n")
            
        return jsonify({
            "success": True,
            "message": f"Successfully processed {len(pending_documents)} documents",
            "validated_count": validated_count,
            "emails_sent": emails_sent,
            "results": validation_results
        })
            
    except Exception as e:
        db.session.rollback()
        print(f"ERROR in validate_pending_documents: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


@bp.route('/validate-document/<int:attachment_id>', methods=['GET'])
@login_required
def validate_specific_document(attachment_id):
    """Validate a specific document by attachment ID"""
    try:
        # Get the document
        document = ShipDocumentEntryAttachment.query.get_or_404(attachment_id)
        print(f"Validating specific document: ID={attachment_id}, Description={document.description}")
        
        # Process the document validation
        result = process_document_validation(document)
        
        return jsonify(result)
            
    except Exception as e:
        db.session.rollback()
        print(f"ERROR in validate_specific_document: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    


# INVOICE TAB

@bp.route("/shipments/<int:shipment_id>/invoices", methods=["GET"])
@login_required
def get_customer_shipment_invoices(shipment_id):
    """Get all invoices for a customer's shipment."""
    print(f"=== STARTING INVOICE FETCH ===")
    print(f"Shipment ID: {shipment_id}")
    print(f"Current user ID: {current_user.id}")
    print(f"Current user role: {current_user.role}")
    print(f"Current user name: {current_user.name}")
    
    try:
        print(f"Step 1: Attempting to get shipment with ID {shipment_id}")
        # Get the shipment
        shipment = OrderShipment.query.filter_by(id=shipment_id).first_or_404()
        print(f"✅ Found shipment: ID={shipment.id}, customer_id={shipment.customer_id}, ship_doc_entry_id={shipment.ship_doc_entry_id}")
        
        # Verify this shipment belongs to one of the user's customers
        authorized = False
        print(f"Step 2: Checking authorization...")
        print(f"Shipment customer_id: {shipment.customer_id}")
        
        # Handle different types of customer relationships
        if hasattr(current_user, 'customer'):
            print(f"✅ User has customer attribute")
            print(f"Customer attribute type: {type(current_user.customer)}")
            print(f"Customer attribute value: {current_user.customer}")
            
            if isinstance(current_user.customer, list) or hasattr(current_user.customer, '__iter__'):
                # If customer is a list/collection, check if any match
                customer_ids = [c.id for c in current_user.customer if hasattr(c, 'id')]
                authorized = shipment.customer_id in customer_ids
                print(f"Customer is a list/iterable")
                print(f"Customer IDs from list: {customer_ids}")
                print(f"Shipment customer_id in list: {shipment.customer_id in customer_ids}")
            elif hasattr(current_user.customer, 'id'):
                # If customer is a single object
                authorized = shipment.customer_id == current_user.customer.id
                print(f"Customer is a single object")
                print(f"Customer ID: {current_user.customer.id}")
                print(f"Shipment customer_id matches: {shipment.customer_id == current_user.customer.id}")
            else:
                print(f"❌ Customer attribute exists but has no 'id' attribute")
        else:
            print(f"❌ User has no customer attribute")
            print(f"Available user attributes: {[attr for attr in dir(current_user) if not attr.startswith('_')]}")
        
        print(f"Authorization result: {authorized}")
        
        if not authorized:
            print(f"❌ Authorization failed - user not authorized for this shipment")
            current_app.logger.warning(f"User {current_user.id} attempted to access unauthorized shipment {shipment_id}")
            abort(403)  # Forbidden if not the customer's shipment
        
        print(f"✅ Authorization successful")
        
        # Get ship_doc_entry_id from the shipment
        ship_doc_entry_id = shipment.ship_doc_entry_id
        print(f"Step 3: Using ship_doc_entry_id: {ship_doc_entry_id}")
        
        print(f"Step 4: Querying invoices...")
        # Query invoices sorted by created date descending
        invoices = InvoiceHeader.query.filter_by(
            ship_doc_entry_id=ship_doc_entry_id, submitted=True
        ).order_by(InvoiceHeader.created_at.desc()).all()
        
        print(f"✅ Found {len(invoices)} invoices")
        
        # Process invoices for the response
        invoice_list = []
        print(f"Step 5: Processing invoices...")
        for i, invoice in enumerate(invoices):
            print(f"Processing invoice {i+1}/{len(invoices)}: ID={invoice.id}, Number={invoice.invoice_number}")
            try:
                invoice_data = {
                    "id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
                    "total": invoice.total,
                    "formatted_total": f"LKR {invoice.total:,.2f}" if invoice.total else "LKR 0.00",
                    "payment_status": invoice.payment_status,
                    "payment_status_text": get_payment_status_text(invoice.payment_status),
                    "created_at": invoice.created_at.isoformat() if invoice.created_at else None
                }
                invoice_list.append(invoice_data)
                print(f"✅ Successfully processed invoice {invoice.id}")
            except Exception as invoice_error:
                print(f"❌ Error processing invoice {invoice.id}: {str(invoice_error)}")
                print(f"Invoice attributes: {[attr for attr in dir(invoice) if not attr.startswith('_')]}")
                raise invoice_error
        
        print(f"✅ Successfully processed all {len(invoice_list)} invoices")
        print(f"Step 6: Returning response...")
        
        # Return invoices
        response_data = {
            "success": True,
            "invoices": invoice_list
        }
        print(f"Response data: {response_data}")
        print(f"=== INVOICE FETCH COMPLETED SUCCESSFULLY ===")
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ ERROR OCCURRED: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print(f"Full traceback:")
        print(traceback.format_exc())
        
        current_app.logger.error(f"Error getting customer shipment invoices: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"An error occurred while retrieving the invoices: {str(e)}"
        }), 500

        
def get_payment_status_text(status_code):
    """Convert payment status code to text representation."""
    status_map = {
        0: "Pending",
        1: "Partially Paid",
        2: "Paid",
        3: "Cancelled"
    }
    return status_map.get(status_code, "Unknown")

@bp.route("/shipments/<int:shipment_id>/invoices/<int:invoice_id>", methods=["GET"])
@login_required
def get_customer_shipment_invoice(shipment_id, invoice_id):
    """Get a specific invoice with its details for a customer."""
    try:
        # Get the shipment
        shipment = OrderShipment.query.filter_by(id=shipment_id).first_or_404()
        
        # Verify this shipment belongs to one of the user's customers
        authorized = False
        
        # Handle different types of customer relationships
        if hasattr(current_user, 'customer'):
            if isinstance(current_user.customer, list) or hasattr(current_user.customer, '__iter__'):
                # If customer is a list/collection, check if any match
                customer_ids = [c.id for c in current_user.customer if hasattr(c, 'id')]
                authorized = shipment.customer_id in customer_ids
            elif hasattr(current_user.customer, 'id'):
                # If customer is a single object
                authorized = shipment.customer_id == current_user.customer.id
        
        if not authorized:
            current_app.logger.warning(f"User {current_user.id} attempted to access unauthorized shipment {shipment_id}")
            abort(403)  # Forbidden if not the customer's shipment
        
        # Get ship_doc_entry_id from the shipment
        ship_doc_entry_id = shipment.ship_doc_entry_id
        
        # Get invoice and verify it belongs to the shipment
        invoice = InvoiceHeader.query.get_or_404(invoice_id)
        
        if invoice.ship_doc_entry_id != ship_doc_entry_id:
            abort(404)  # Not found if invoice doesn't belong to this shipment
        
        # Get invoice details
        details = []
        for detail in invoice.details:
            # Only include details where the expense is marked as visible to customer
            expense = detail.expense if detail.expense_id else None
            if expense and hasattr(expense, 'visible_to_customer') and expense.visible_to_customer:
                detail_data = {
                    "expense_type": detail.expense.expense_type.description if detail.expense and detail.expense.expense_type else "Item",
                    "description": detail.description,
                    "original_amount": detail.original_amount,
                    "margin": detail.margin,
                    "original_chargeable_amount": detail.original_chargeable_amount,
                    "final_amount": detail.final_amount
                }
                details.append(detail_data)
        
        # Get customer name - handle different scenarios
        customer_name = "Customer"
        if hasattr(invoice, 'customer'):
            if invoice.customer:
                if isinstance(invoice.customer, list) or hasattr(invoice.customer, '__iter__'):
                    # If it's a list, use the first customer's name or a generic name
                    for c in invoice.customer:
                        if hasattr(c, 'customer_name'):
                            customer_name = c.customer_name
                            break
                elif hasattr(invoice.customer, 'customer_name'):
                    # If it's a single object with customer_name
                    customer_name = invoice.customer.customer_name
        
        # Alternatively, use the shipment's customer name
        if customer_name == "Customer" and hasattr(shipment, 'customer'):
            if shipment.customer:
                if hasattr(shipment.customer, 'customer_name'):
                    customer_name = shipment.customer.customer_name
        
        # Format invoice data
        invoice_data = {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            "narration": invoice.narration,
            "customer_name": customer_name,
            "total": invoice.total,
            "formatted_total": f"${invoice.total:,.2f}" if invoice.total else "$0.00",
            "payment_status": invoice.payment_status,
            "payment_status_text": get_payment_status_text(invoice.payment_status),
            "created_by": invoice.creator.name if hasattr(invoice, 'creator') and invoice.creator else "System",
            "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
            "details": details
        }
        
        return jsonify({
            "success": True,
            "invoice": invoice_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting customer shipment invoice: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred while retrieving the invoice"
        }), 500


@bp.route("/shipments/<int:shipment_id>/invoices/<int:invoice_id>/pdf", methods=["GET"])
@login_required
def get_customer_invoice_pdf(shipment_id, invoice_id):
    """Generate and download a PDF for a specific invoice."""
    try:
        # Get the shipment
        shipment = OrderShipment.query.filter_by(id=shipment_id).first_or_404()
        
        # Verify this shipment belongs to one of the user's customers
        authorized = False
        
        # Handle different types of customer relationships
        if hasattr(current_user, 'customer'):
            if isinstance(current_user.customer, list) or hasattr(current_user.customer, '__iter__'):
                # If customer is a list/collection, check if any match
                customer_ids = [c.id for c in current_user.customer if hasattr(c, 'id')]
                authorized = shipment.customer_id in customer_ids
            elif hasattr(current_user.customer, 'id'):
                # If customer is a single object
                authorized = shipment.customer_id == current_user.customer.id
        
        # Temporarily bypass authorization for testing
        # TODO: Re-enable this before production
        authorized = True
        
        if not authorized:
            current_app.logger.warning(f"User {current_user.id} attempted to access unauthorized shipment {shipment_id}")
            abort(403)  # Forbidden if not the customer's shipment
        
        # Get ship_doc_entry_id from the shipment
        ship_doc_entry_id = shipment.ship_doc_entry_id
        
        # Get invoice and verify it belongs to the shipment
        invoice = InvoiceHeader.query.get_or_404(invoice_id)
        
        if invoice.ship_doc_entry_id != ship_doc_entry_id:
            abort(404)  # Not found if invoice doesn't belong to this shipment
        
        # Get customer name - handle different scenarios
        customer_name = "Customer"
        if hasattr(invoice, 'customer'):
            if invoice.customer:
                if isinstance(invoice.customer, list) or hasattr(invoice.customer, '__iter__'):
                    # If it's a list, use the first customer's name or a generic name
                    for c in invoice.customer:
                        if hasattr(c, 'customer_name'):
                            customer_name = c.customer_name
                            break
                elif hasattr(invoice.customer, 'customer_name'):
                    # If it's a single object with customer_name
                    customer_name = invoice.customer.customer_name
        
        # Alternatively, use the shipment's customer name
        if customer_name == "Customer" and hasattr(shipment, 'customer'):
            if shipment.customer:
                if hasattr(shipment.customer, 'customer_name'):
                    customer_name = shipment.customer.customer_name
        
        # Create PDF generation logic
        try:

            # Create a BytesIO buffer to receive the PDF data
            buffer = BytesIO()
            
            # Create the PDF document
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=0.5*inch,
                leftMargin=0.5*inch,
                topMargin=0.5*inch,
                bottomMargin=0.5*inch
            )
            
            # Container for the elements to be added to the PDF
            elements = []
            
            # Get styles
            styles = getSampleStyleSheet()
            title_style = styles['Heading1']
            subtitle_style = styles['Heading2']
            normal_style = styles['Normal']
            
            # Add invoice title and details
            elements.append(Paragraph("INVOICE", title_style))
            elements.append(Spacer(1, 0.1*inch))
            elements.append(Paragraph(f"Invoice #: {invoice.invoice_number}", subtitle_style))
            elements.append(Paragraph(f"Date: {invoice.invoice_date.strftime('%B %d, %Y') if invoice.invoice_date else 'N/A'}", normal_style))
            
            # Get payment status text
            status_map = {
                0: "Pending",
                1: "Partially Paid",
                2: "Paid",
                3: "Cancelled"
            }
            payment_status_text = status_map.get(invoice.payment_status, "Unknown")
            
            elements.append(Paragraph(f"Status: {payment_status_text}", normal_style))
            elements.append(Spacer(1, 0.2*inch))
            
            # Add customer information
            elements.append(Paragraph("Bill To:", subtitle_style))
            elements.append(Paragraph(f"Customer: {customer_name}", normal_style))
            elements.append(Spacer(1, 0.2*inch))
            
            # Add invoice description/narration if available
            if invoice.narration:
                elements.append(Paragraph("Description:", subtitle_style))
                elements.append(Paragraph(invoice.narration, normal_style))
                elements.append(Spacer(1, 0.2*inch))
            
            # Add items table
            elements.append(Paragraph("Invoice Items", subtitle_style))
            elements.append(Spacer(1, 0.1*inch))
            
            # Create data for the table
            table_data = [["Item/Service", "Description", "Amount"]]
            
            # Add invoice details to table
            for detail in invoice.details:
                # Skip items not visible to customer if the attribute exists
                if hasattr(detail, 'expense') and detail.expense:
                    if hasattr(detail.expense, 'visible_to_customer') and not detail.expense.visible_to_customer:
                        continue
                        
                # Format the expense type name
                expense_type = "Item"
                if hasattr(detail, 'expense') and detail.expense:
                    if hasattr(detail.expense, 'expense_type') and detail.expense.expense_type:
                        if hasattr(detail.expense.expense_type, 'description'):
                            expense_type = detail.expense.expense_type.description
                    
                # Format the amount
                amount = f"${detail.final_amount:,.2f}" if detail.final_amount else "$0.00"
                
                # Add the row to the table
                table_data.append([
                    expense_type,
                    detail.description or "",
                    amount
                ])
            
            # Add total row
            table_data.append(["", "Total", f"${invoice.total:,.2f}" if invoice.total else "$0.00"])
            
            # Create the table
            table = Table(table_data, colWidths=[2*inch, 3*inch, 1.5*inch])
            
            # Add style to the table
            table.setStyle(TableStyle([
                # Headers
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                
                # Cells
                ('BACKGROUND', (0, 1), (-1, -2), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('ALIGN', (0, 1), (1, -2), 'LEFT'),  # Left align text columns
                ('ALIGN', (2, 1), (2, -1), 'RIGHT'),  # Right align amount column
                
                # Total row
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightgrey),
                
                # All cells
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
            ]))
            
            elements.append(table)
            
            # Add payment information and footer
            elements.append(Spacer(1, 0.3*inch))
            elements.append(Paragraph("Payment Information:", subtitle_style))
            elements.append(Paragraph("Please include the invoice number in your payment reference.", normal_style))
            
            # Add payment details if available
            if hasattr(invoice, 'payment_instructions') and invoice.payment_instructions:
                elements.append(Paragraph(invoice.payment_instructions, normal_style))
            else:
                elements.append(Paragraph("Please contact us for payment details.", normal_style))
            
            # Add footer with thank you note
            elements.append(Spacer(1, 0.5*inch))
            elements.append(Paragraph("Thank you for your business!", normal_style))
            
            # Build the PDF
            doc.build(elements)
            
            # Get the PDF data from the buffer
            pdf_data = buffer.getvalue()
            buffer.close()
            
        except Exception as e:
            current_app.logger.error(f"Error generating PDF: {str(e)}")
            raise
        
        # Return the PDF as a downloadable file
        response = Response(
            pdf_data,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename=Invoice_{invoice.invoice_number}.pdf'
            }
        )
        
        return response
        
    except Exception as e:
        current_app.logger.error(f"Error generating customer invoice PDF: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred while generating the invoice PDF: " + str(e)
        }), 500
    
@bp.route("/shipments/<int:shipment_id>/invoice-pdf", methods=["GET"])
@login_required
def download_latest_customer_invoice_pdf(shipment_id):
    """Download the latest invoice PDF for a shipment."""
    try:
        # Get the shipment
        shipment = OrderShipment.query.filter_by(id=shipment_id).first_or_404()
        
        # Temporarily bypass authorization for testing
        # TODO: Re-enable proper authorization before production
        
        # Get ship_doc_entry_id from the shipment
        ship_doc_entry_id = shipment.ship_doc_entry_id
        
        # Get the latest invoice for this shipment
        invoice = InvoiceHeader.query.filter_by(
            ship_doc_entry_id=ship_doc_entry_id
        ).order_by(InvoiceHeader.created_at.desc()).first_or_404()
        
        # Redirect to the specific invoice PDF route
        return redirect(url_for('customer_portal.get_customer_invoice_pdf', 
                               shipment_id=shipment_id, 
                               invoice_id=invoice.id))
        
    except Exception as e:
        current_app.logger.error(f"Error redirecting to customer invoice PDF: {str(e)}")
        return jsonify({
            "success": False,
            "message": "An error occurred while accessing the invoice PDF"
        }), 500

# Calendar

@bp.route('/api/customer/shipments/eta')
@login_required
def get_customer_eta_data():
    """
    Get ETA data for shipments belonging to the current customer or assigned to clearing agent
    """
    try:
        user_id = current_user.id
        role = current_user.role.lower()
        result = []

        print(f"🔍 Current User ID: {user_id}, Role: {role}")

        if role == 'customer':
            customer = Customer.query.filter_by(user_id=user_id).first()
            customer_id = customer.id if customer else None
            print(f"✅ Customer Role Detected - Customer ID: {customer_id}")

            if not customer_id:
                print("⚠️ No customer ID found for this user. Returning empty list.")
                return jsonify([])

            shipments = db.session.query(
                OrderShipment,
                Customer,
                User.name.label('sales_person_name')
            ).join(
                Customer, OrderShipment.customer_id == Customer.id, isouter=True
            ).join(
                User, OrderShipment.sales_person_id == User.id, isouter=True
            ).filter(
                OrderShipment.eta != None,
                OrderShipment.customer_id == customer_id
            ).all()

            print(f"📦 Shipments found for customer: {len(shipments)}")

        elif role == 'clearing_agent':
            print("✅ Clearing Agent Role Detected")

            assigned_entries = db.session.query(
                EntryClearingAgentHistory.entry_id
            ).filter_by(
                assigned_to_clearing_agent_id=user_id,
                currently_assigned=True
            ).all()

            entry_ids = [entry_id for (entry_id,) in assigned_entries]
            print(f"📄 Assigned Entry IDs to Clearing Agent: {entry_ids}")

            if not entry_ids:
                print("⚠️ No currently assigned entries found for clearing agent. Returning empty list.")
                return jsonify([])

            shipments = db.session.query(
                OrderShipment,
                Customer,
                User.name.label('sales_person_name')
            ).join(
                Customer, OrderShipment.customer_id == Customer.id, isouter=True
            ).join(
                User, OrderShipment.sales_person_id == User.id, isouter=True
            ).filter(
                OrderShipment.eta != None,
                OrderShipment.ship_doc_entry_id.in_(entry_ids)
            ).all()

            print(f"📦 Shipments found for clearing agent: {len(shipments)}")

        else:
            print("❌ Unsupported role or no access.")
            return jsonify([])

        # Print detailed shipment data
        for idx, (shipment, customer, sales_person_name) in enumerate(shipments, 1):
            print(f"➡️ Shipment {idx}:")
            print(f"   - ID: {shipment.id}")
            print(f"   - ETA: {shipment.eta}")
            print(f"   - Customer ID: {shipment.customer_id}")
            print(f"   - Import ID: {shipment.import_id}")
            print(f"   - Sales Person: {sales_person_name}")

            result.append({
                'id': shipment.id,
                'import_id': shipment.import_id,
                'bl_no': shipment.bl_no,
                'vessel': shipment.vessel,
                'voyage': shipment.voyage,
                'eta': shipment.eta.isoformat() if shipment.eta else None,
                'port_of_loading': shipment.port_of_loading,
                'port_of_discharge': shipment.port_of_discharge,
                'cargo_description': shipment.cargo_description,
                'remarks': shipment.remarks,
                'sales_person_name': sales_person_name
            })

        print(f"✅ Total ETA records returned: {len(result)}")
        return jsonify(result)

    except Exception as e:
        print(f"❌ Error occurred in /api/customer/shipments/eta: {str(e)}")
        return jsonify({'error': str(e)}), 500


# Alternative implementation if customer_id is stored differently
@bp.route('/api/customer/shipments/eta/alternative')
def get_customer_eta_data_alternative():
    """
    Alternative implementation - if customer info is linked differently
    """
    try:
        # If customer email is linked to Customer model
        customer_email = current_user.email
        customer = Customer.query.filter_by(email=customer_email).first()
        
        if not customer:
            return jsonify([])
        
        customer_id = customer.id
        print(f"Found customer ID: {customer_id} for email: {customer_email}")

        # Rest of the query logic remains the same
        shipments = db.session.query(
            OrderShipment,
            Customer,
            User.name.label('sales_person_name')
        ).join(
            Customer, 
            OrderShipment.customer_id == Customer.id,
            isouter=True
        ).join(
            User,
            OrderShipment.sales_person_id == User.id,
            isouter=True
        ).filter(
            OrderShipment.eta != None,
            OrderShipment.customer_id == customer_id
        ).all()

        result = []
        for shipment, customer, sales_person_name in shipments:
            result.append({
                'id': shipment.id,
                'import_id': shipment.import_id,
                'bl_no': shipment.bl_no,
                'vessel': shipment.vessel,
                'voyage': shipment.voyage,
                'eta': shipment.eta.isoformat() if shipment.eta else None,
                'port_of_loading': shipment.port_of_loading,
                'port_of_discharge': shipment.port_of_discharge,
                'cargo_description': shipment.cargo_description,
                'remarks': shipment.remarks,
                'sales_person_name': sales_person_name
            })

        return jsonify(result)
    except Exception as e:
        print(f"Error occurred: {str(e)}")
        return jsonify({'error': str(e)}), 500



# AGENT ASSIGNMENT
# customer_portal/routes.py - Add these routes to your customer_portal blueprint



@bp.route('/agent-management')
@login_required
def agent_management():
    """Main agent management page"""
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '', type=str)
    
    # Get available agents (clearing_agent role, not assigned to current company)
    assigned_agent_ids = db.session.query(AgentAssignment.assigned_agent_id).filter(
        AgentAssignment.assigned_by_user_id == current_user.id,
        AgentAssignment.is_active == True
    ).subquery()
    
    available_agents_query = User.query.filter(
        User.role == 'clearing_agent',
        User.is_active == True,
        ~User.id.in_(assigned_agent_ids)
    )
    
    # Apply search filter for available agents
    if search:
        available_agents_query = available_agents_query.filter(
            or_(
                User.name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.username.ilike(f'%{search}%')
            )
        )
    
    # Get assigned agents
    assigned_agents_query = db.session.query(
        User, AgentAssignment
    ).join(
        AgentAssignment, User.id == AgentAssignment.assigned_agent_id
    ).filter(
        AgentAssignment.assigned_by_user_id == current_user.id,
        AgentAssignment.is_active == True
    )
    
    # Apply search filter for assigned agents
    if search:
        assigned_agents_query = assigned_agents_query.filter(
            or_(
                User.name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.username.ilike(f'%{search}%')
            )
        )
    
    # Paginate available agents
    available_agents = available_agents_query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Paginate assigned agents  
    assigned_agents = assigned_agents_query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template(
        'customer_portal/agent_management.html',
        available_agents=available_agents,
        assigned_agents=assigned_agents,
        search=search,
        per_page=per_page
    )

@bp.route('/assign-agent', methods=['POST'])
@login_required
def assign_agent():
    """Assign an agent to the current user's company"""
    try:
        data = request.get_json()
        agent_id = data.get('agent_id')
        
        if not agent_id:
            return jsonify({'success': False, 'message': 'Agent ID is required'})
        
        # Check if agent exists and is a clearing agent
        agent = User.query.filter_by(id=agent_id, role='clearing_agent', is_active=True).first()
        if not agent:
            return jsonify({'success': False, 'message': 'Invalid agent selected'})
        
        # Check if already assigned
        existing_assignment = AgentAssignment.query.filter_by(
            assigned_agent_id=agent_id,
            assigned_by_user_id=current_user.id,
            is_active=True
        ).first()
        
        if existing_assignment:
            return jsonify({'success': False, 'message': 'Agent is already assigned to your company'})
        
        # Create new assignment
        assignment = AgentAssignment(
            assigned_by_user_id=current_user.id,
            assigned_agent_id=agent_id,
            company_id=current_user.company_id,
            assignment_date=datetime.now()
        )
        
        db.session.add(assignment)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Agent {agent.name} has been successfully assigned to your company'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error assigning agent: {str(e)}'})

@bp.route('/unassign-agent', methods=['POST'])
@login_required
def unassign_agent():
    """Remove an agent assignment"""
    try:
        data = request.get_json()
        agent_id = data.get('agent_id')
        
        if not agent_id:
            return jsonify({'success': False, 'message': 'Agent ID is required'})
        
        # Find the assignment
        assignment = AgentAssignment.query.filter_by(
            assigned_agent_id=agent_id,
            assigned_by_user_id=current_user.id,
            is_active=True
        ).first()
        
        if not assignment:
            return jsonify({'success': False, 'message': 'Agent assignment not found'})
        
        # Soft delete - set is_active to False
        assignment.is_active = False
        assignment.updated_at = datetime.now()
        
        db.session.commit()
        
        agent = User.query.get(agent_id)
        return jsonify({
            'success': True, 
            'message': f'Agent {agent.name if agent else "Unknown"} has been unassigned from your company'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error unassigning agent: {str(e)}'})

@bp.route('/get-available-agents')
@login_required
def get_available_agents():
    """AJAX endpoint for available agents"""
    try:
        search = request.args.get('search', '', type=str)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Get agents not assigned to current company
        assigned_agent_ids = db.session.query(AgentAssignment.assigned_agent_id).filter(
            AgentAssignment.assigned_by_user_id == current_user.id,
            AgentAssignment.is_active == True
        ).subquery()
        
        query = User.query.filter(
            User.role == 'clearing_agent',
            User.is_active == True,
            ~User.id.in_(assigned_agent_ids)
        )
        
        if search:
            query = query.filter(
                or_(
                    User.name.ilike(f'%{search}%'),
                    User.email.ilike(f'%{search}%'),
                    User.username.ilike(f'%{search}%')
                )
            )
        
        agents = query.paginate(page=page, per_page=per_page, error_out=False)
        
        agents_data = []
        for agent in agents.items:
            agents_data.append({
                'id': agent.id,
                'name': agent.name or agent.username,
                'email': agent.email,
                'contact_number': agent.contact_number,
                'username': agent.username
            })
        
        return jsonify({
            'success': True,
            'agents': agents_data,
            'pagination': {
                'page': agents.page,
                'per_page': agents.per_page,
                'total': agents.total,
                'pages': agents.pages,
                'has_next': agents.has_next,
                'has_prev': agents.has_prev
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching agents: {str(e)}'})

@bp.route('/get-assigned-agents')
@login_required
def get_assigned_agents():
    """AJAX endpoint for assigned agents"""
    try:
        search = request.args.get('search', '', type=str)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        query = db.session.query(
            User, AgentAssignment
        ).join(
            AgentAssignment, User.id == AgentAssignment.assigned_agent_id
        ).filter(
            AgentAssignment.assigned_by_user_id == current_user.id,
            AgentAssignment.is_active == True
        )
        
        if search:
            query = query.filter(
                or_(
                    User.name.ilike(f'%{search}%'),
                    User.email.ilike(f'%{search}%'),
                    User.username.ilike(f'%{search}%')
                )
            )
        
        agents = query.paginate(page=page, per_page=per_page, error_out=False)
        
        agents_data = []
        for user, assignment in agents.items:
            agents_data.append({
                'id': user.id,
                'name': user.name or user.username,
                'email': user.email,
                'contact_number': user.contact_number,
                'username': user.username,
                'assignment_date': assignment.assignment_date.strftime('%Y-%m-%d %H:%M') if assignment.assignment_date else '',
                'assigned_by': assignment.assigned_by.name if assignment.assigned_by else 'Unknown'
            })
        
        return jsonify({
            'success': True,
            'agents': agents_data,
            'pagination': {
                'page': agents.page,
                'per_page': agents.per_page,
                'total': agents.total,
                'pages': agents.pages,
                'has_next': agents.has_next,
                'has_prev': agents.has_prev
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching assigned agents: {str(e)}'})




# CLEARING COMPANY ASSIGNMENT
#####################################

# customer_portal/routes.py - Add these routes to your customer_portal blueprint


@bp.route('/company-management')
@login_required
def company_management():
    """Main clearing company management page"""
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '', type=str)
    
    # Get available clearing companies (role='clearing_company' and role_id=9, not assigned to current company)
    assigned_company_ids = db.session.query(CompanyAssignment.assigned_company_id).filter(
        CompanyAssignment.assigned_by_user_id == current_user.id,
        CompanyAssignment.is_active == True
    ).subquery()
    
    available_companies_query = CompanyInfo.query.filter(
        CompanyInfo.is_active == True,
        CompanyInfo.is_cha == True,  # Assuming is_cha indicates clearing company
        ~CompanyInfo.id.in_(assigned_company_ids)
    )
    
    # Apply search filter for available companies
    if search:
        available_companies_query = available_companies_query.filter(
            or_(
                CompanyInfo.company_name.ilike(f'%{search}%'),
                CompanyInfo.email.ilike(f'%{search}%'),
                CompanyInfo.website.ilike(f'%{search}%')
            )
        )
    
    # Get assigned clearing companies
    assigned_companies_query = db.session.query(
        CompanyInfo, CompanyAssignment
    ).join(
        CompanyAssignment, CompanyInfo.id == CompanyAssignment.assigned_company_id
    ).filter(
        CompanyInfo.is_active == True,
        CompanyInfo.is_cha == True,  # Assuming is_cha indicates clearing company
        CompanyAssignment.assigned_by_user_id == current_user.id,
        CompanyAssignment.is_active == True
    )
    
    # Apply search filter for assigned companies
    if search:
        assigned_companies_query = assigned_companies_query.filter(
            or_(
                CompanyInfo.company_name.ilike(f'%{search}%'),
                CompanyInfo.email.ilike(f'%{search}%'),
                CompanyInfo.website.ilike(f'%{search}%')
            )
        )
    
    # Paginate available companies
    available_companies = available_companies_query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Paginate assigned companies  
    assigned_companies = assigned_companies_query.paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template(
        'customer_portal/company_management.html',
        available_companies=available_companies,
        assigned_companies=assigned_companies,
        search=search,
        per_page=per_page
    )


@bp.route('/assign-company', methods=['POST'])
@login_required
def assign_company():
    """Assign a clearing company to the current user's company"""
    try:
        data = request.get_json()
        company_id = data.get('company_id')
        
        if not company_id:
            return jsonify({'success': False, 'message': 'Company ID is required'})
        
        # Check if company exists and is a clearing company
        company = CompanyInfo.query.filter_by(
            id=company_id
        ).first()
        
        if not company:
            return jsonify({'success': False, 'message': 'Invalid clearing company selected'})
        
        # Check if already assigned
        existing_assignment = CompanyAssignment.query.filter_by(
            assigned_company_id=company_id,
            assigned_by_user_id=current_user.id,
            is_active=True
        ).first()
        
        if existing_assignment:
            return jsonify({'success': False, 'message': 'Clearing company is already assigned to your company'})
        
        # Create new assignment
        assignment = CompanyAssignment(
            assigned_by_user_id=current_user.id,
            assigned_company_id=company_id,
            company_id=current_user.company_id,
            assignment_date=datetime.now()
        )
        
        db.session.add(assignment)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Clearing company {company.company_name} has been successfully assigned to your company'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error assigning clearing company: {str(e)}'})

@bp.route('/unassign-company', methods=['POST'])
@login_required
def unassign_company():
    """Remove a clearing company assignment"""
    try:
        data = request.get_json()
        company_id = data.get('company_id')
        
        if not company_id:
            return jsonify({'success': False, 'message': 'Company ID is required'})
        
        # Find the assignment
        assignment = CompanyAssignment.query.filter_by(
            assigned_company_id=company_id,
            assigned_by_user_id=current_user.id,
            is_active=True
        ).first()
        
        if not assignment:
            return jsonify({'success': False, 'message': 'Company assignment not found'})
        
        # Soft delete - set is_active to False
        assignment.is_active = False
        assignment.updated_at = datetime.now()
        
        db.session.commit()
        
        company = CompanyInfo.query.get(company_id)
        return jsonify({
            'success': True, 
            'message': f'Clearing company {company.company_name if company else "Unknown"} has been unassigned from your company'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error unassigning clearing company: {str(e)}'})

@bp.route('/get-available-companies')
@login_required
def get_available_companies():
    """AJAX endpoint for available clearing companies"""
    try:
        search = request.args.get('search', '', type=str)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Get clearing companies not assigned to current company
        assigned_company_ids = db.session.query(CompanyAssignment.assigned_company_id).filter(
            CompanyAssignment.assigned_by_user_id == current_user.id,
            CompanyAssignment.is_active == True
        ).subquery()
        
        query = CompanyInfo.query.filter(
            ~CompanyInfo.id.in_(assigned_company_ids)
        )
        
        if search:
            query = query.filter(
                or_(
                    CompanyInfo.company_name.ilike(f'%{search}%'),
                    CompanyInfo.email.ilike(f'%{search}%'),
                    CompanyInfo.website.ilike(f'%{search}%')
                )
            )
        
        companies = query.paginate(page=page, per_page=per_page, error_out=False)
        
        companies_data = []
        for company in companies.items:
            companies_data.append({
                'id': company.id,
                'name': company.company_name,
                'email': company.email,
                'contact_number': company.contact_num,
                'country': company.country_info.countryName,
                'address': company.address
            })
        
        return jsonify({
            'success': True,
            'companies': companies_data,
            'pagination': {
                'page': companies.page,
                'per_page': companies.per_page,
                'total': companies.total,
                'pages': companies.pages,
                'has_next': companies.has_next,
                'has_prev': companies.has_prev
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching clearing companies: {str(e)}'})

@bp.route('/get-assigned-companies')
@login_required
def get_assigned_companies():
    """AJAX endpoint for assigned clearing companies"""
    try:
        search = request.args.get('search', '', type=str)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        query = db.session.query(
            CompanyInfo, CompanyAssignment
        ).join(
            CompanyAssignment, CompanyInfo.id == CompanyAssignment.assigned_company_id
        ).filter(
            CompanyAssignment.assigned_by_user_id == current_user.id,
            CompanyAssignment.is_active == True
        )
        
        if search:
            query = query.filter(
                or_(
                    CompanyInfo.company_name.ilike(f'%{search}%'),
                    CompanyInfo.email.ilike(f'%{search}%'),
                    CompanyInfo.website.ilike(f'%{search}%')
                )
            )
        
        companies = query.paginate(page=page, per_page=per_page, error_out=False)
        
        companies_data = []
        for user, assignment in companies.items:
            companies_data.append({
                'id': user.id,
                'name': user.company_name,
                'email': user.email,
                'contact_number': user.contact_num,
                'country': user.country,
                'address': user.address,
                'assignment_date': assignment.assignment_date.strftime('%Y-%m-%d %H:%M') if assignment.assignment_date else '',
                'assigned_by': assignment.assigned_by.name if assignment.assigned_by else 'Unknown'
            })
        
        return jsonify({
            'success': True,
            'companies': companies_data,
            'pagination': {
                'page': companies.page,
                'per_page': companies.per_page,
                'total': companies.total,
                'pages': companies.pages,
                'has_next': companies.has_next,
                'has_prev': companies.has_prev
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error fetching assigned clearing companies: {str(e)}'})






# ===============================
# ITEMS TAB
# ===============================

@bp.route("/orders/shipment/<int:entry_id>/items/manual", methods=["POST"])
@login_required
def add_manual_item(entry_id):
    """Add manual item to shipment"""
    try:
        # Verify entry belongs to current user's company
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)
        
        # Get form data
        material_code = request.form.get('material_code', '').strip()
        material_name = request.form.get('material_name', '').strip()
        quantity = request.form.get('quantity')
        order_unit = request.form.get('order_unit', '').strip()
        net_price = request.form.get('net_price')
        supplier_name = request.form.get('supplier_name', '').strip()
        po_number = request.form.get('po_number', '').strip()  # New field
        delivery_date = request.form.get('delivery_date')
        remarks = request.form.get('remarks', '').strip()
        line_total = request.form.get('line_total')
        submit_action = request.form.get('submit_action', 'save_close')
        
        # Validate required fields
        if not all([material_code, material_name, quantity, order_unit]):
            flash("Please fill in all required fields", "danger")
            return redirect(url_for('customer_portal.customer_order_shipment', order_id=entry_id, tab='items'))
        
        # Prepare item data
        item_data = {
            'shipment_id': entry_id,
            'source_type': 'manual',
            'material_code': material_code,
            'material_name': material_name,
            'quantity': Decimal(quantity),
            'order_unit': order_unit,
            'net_price': Decimal(net_price) if net_price else None,
            'line_total': Decimal(line_total) if line_total else None,
            'supplier_name': supplier_name if supplier_name else None,
            'po_number': po_number if po_number else None,  # New field
            'delivery_date': datetime.strptime(delivery_date, '%Y-%m-%d').date() if delivery_date else None,
            'remarks': remarks if remarks else None,
            'company_id': current_user.company_id,
            'created_by': current_user.id
        }
        
        # Create and save item
        item = ShipmentItem(**item_data)
        db.session.add(item)
        db.session.commit()
        
        flash(f"Item '{material_code}' added successfully!", "success")
        
        # Redirect based on submit action
        if submit_action == 'add_another':
            return redirect(url_for('customer_portal.customer_order_shipment', order_id=entry_id, tab='items', action='add_another'))
        else:
            return redirect(url_for('customer_portal.customer_order_shipment', order_id=entry_id, tab='items'))
            
    except Exception as e:
        db.session.rollback()
        print(f"Error adding manual item: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f"Error adding item: {str(e)}", "danger")
        return redirect(url_for('customer_portal.customer_order_shipment', order_id=entry_id, tab='items'))


@bp.route("/api/shipment-item/<int:item_id>", methods=["GET"])
@login_required
def get_shipment_item_api(item_id):
    """Get shipment item data via API"""
    try:
        # Get item and verify access
        item = ShipmentItem.query.get_or_404(item_id)

        
        # Convert item to dictionary
        item_data = {
            'id': item.id,
            'material_code': item.material_code,
            'material_name': item.material_name,
            'quantity': float(item.quantity) if item.quantity else 0,
            'order_unit': item.order_unit,
            'net_price': float(item.net_price) if item.net_price else 0,
            'line_total': float(item.line_total) if item.line_total else 0,
            'supplier_name': item.supplier_name,
            'po_number': item.po_number,
            'delivery_date': item.delivery_date.strftime('%Y-%m-%d') if item.delivery_date else None,
            'remarks': item.remarks,
            'source_type': item.source_type
        }
        
        return jsonify(item_data)
        
    except Exception as e:
        print(f"Error getting item data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route("/api/shipment-item/<int:item_id>/edit", methods=["POST"])
@login_required
def edit_shipment_item_api(item_id):
    """Edit shipment item via API"""
    try:
        # Get item and verify access
        item = ShipmentItem.query.get_or_404(item_id)

        
        # Update item data
        item.material_code = request.form.get('material_code', '').strip()
        item.material_name = request.form.get('material_name', '').strip()
        item.quantity = Decimal(request.form.get('quantity'))
        item.order_unit = request.form.get('order_unit', '').strip()
        
        net_price = request.form.get('net_price')
        item.net_price = Decimal(net_price) if net_price else None
        
        line_total = request.form.get('line_total')
        item.line_total = Decimal(line_total) if line_total else None
        
        item.supplier_name = request.form.get('supplier_name', '').strip() or None
        item.po_number = request.form.get('po_number', '').strip() or None
        
        delivery_date = request.form.get('delivery_date')
        item.delivery_date = datetime.strptime(delivery_date, '%Y-%m-%d').date() if delivery_date else None
        
        item.remarks = request.form.get('remarks', '').strip() or None
        item.updated_at = get_sri_lanka_time()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Item '{item.material_code}' updated successfully!"
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error editing item: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route("/api/shipment-item/<int:item_id>/delete", methods=["DELETE"])
@login_required
def delete_shipment_item_api(item_id):
    """Delete shipment item via API"""
    try:
        # Get item and verify access
        item = ShipmentItem.query.get_or_404(item_id)
        
        
        material_code = item.material_code
        
        db.session.delete(item)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Item '{material_code}' deleted successfully!"
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting item: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route("/orders/shipment/<int:entry_id>/items/po", methods=["POST"])
@login_required
def add_po_items(entry_id):
    """Add items from PO to shipment"""
    try:
        # Verify entry belongs to current user's company
        entry = ShipDocumentEntryMaster.query.get_or_404(entry_id)

        
        # Get selected PO item IDs
        selected_po_items = request.form.getlist('selected_po_items')
        
        if not selected_po_items:
            flash("Please select at least one item to add", "warning")
            return redirect(url_for('customer_portal.customer_order_shipment', order_id=entry_id, tab='items'))
        
        added_count = 0
        
        for po_detail_id in selected_po_items:
            # Get PO detail
            po_detail = PODetail.query.get(int(po_detail_id))
      
            
            # Check if this item is already added to this shipment
            existing_item = ShipmentItem.query.filter_by(
                shipment_id=entry_id,
                po_detail_id=po_detail.id
            ).first()
            
            if existing_item:
                continue  # Skip if already added
            
            # Create shipment item from PO detail
            item_data = {
                'shipment_id': entry_id,
                'source_type': 'po',
                'po_detail_id': po_detail.id,
                'po_header_id': po_detail.po_header_id,
                'po_number': po_detail.po_number,
                'material_code': po_detail.material_code,
                'material_name': po_detail.material_name,
                'quantity': po_detail.quantity_pending,  # Use pending quantity
                'order_unit': po_detail.order_unit,
                'net_price': po_detail.net_price,
                'line_total': po_detail.quantity_pending * po_detail.net_price,
                'supplier_name': po_detail.supplier_name,
                'delivery_date': po_detail.delivery_date,
                'company_id': current_user.company_id,
                'created_by': current_user.id
            }
            
            item = ShipmentItem(**item_data)
            db.session.add(item)
            added_count += 1
        
        db.session.commit()
        
        if added_count > 0:
            flash(f"Successfully added {added_count} item(s) from PO", "success")
        else:
            flash("No new items were added (items may already exist in this shipment)", "info")
        
        return redirect(url_for('customer_portal.customer_order_shipment', order_id=entry_id, tab='items'))
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding PO items: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f"Error adding PO items: {str(e)}", "danger")
        return redirect(url_for('customer_portal.customer_order_shipment', order_id=entry_id, tab='items'))



# Add these simplified routes to your customer_portal/routes.py file

@bp.route('/api/shipment-document-alerts/<int:entry_id>')
@login_required
def get_shipment_document_alerts(entry_id):
    """Get document expiry alerts for a specific shipment"""
    try:
        # Get the shipment entry
        entry = ShipDocumentEntryMaster.query.filter_by(
            id=entry_id,
            company_id=current_user.company_id
        ).first()
        
        if not entry:
            return jsonify({'success': False, 'message': 'Shipment not found'}), 404
        
        # Get the related OrderShipment to check for ETA
        order_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=entry_id).first()
        
        # Determine the comparison date (ETA if available, otherwise deadline)
        comparison_date = None
        date_source = None
        
        if order_shipment and order_shipment.eta:
            comparison_date = order_shipment.eta
            date_source = 'eta'
        elif entry.dealineDate:
            comparison_date = entry.dealineDate
            date_source = 'deadline'
        
        if not comparison_date:
            return jsonify({
                'success': True,
                'has_alerts': False,
                'message': 'No ETA or deadline date available for comparison'
            })
        
        # Get all shipment items for this entry
        shipment_items = db.session.query(ShipmentItem).filter_by(
            shipment_id=entry_id
        ).all()
        
        alerts = []
        has_critical_alerts = False
        
        for item in shipment_items:
            # Get material documents for this item
            if item.po_detail_id:
                # For PO items, get material from PO
                po_detail = PODetail.query.get(item.po_detail_id)
                if po_detail and po_detail.material_id:
                    material_docs = MaterialHSDocuments.query.filter_by(
                        material_id=po_detail.material_id,
                        company_id=current_user.company_id
                    ).filter(
                        MaterialHSDocuments.expiry_date.isnot(None)
                    ).all()
                    
                    for doc in material_docs:
                        if doc.expiry_date < comparison_date:
                            has_critical_alerts = True
                            alerts.append({
                                'item_id': item.id,
                                'material_id': po_detail.material_id,
                                'material_code': po_detail.po_material.material_code if po_detail.po_material else 'Unknown',
                                'material_name': po_detail.po_material.material_name if po_detail.po_material else 'Unknown',
                                'document_id': doc.id,
                                'document_name': doc.file_name,
                                'expiry_date': doc.expiry_date.isoformat(),
                                'comparison_date': comparison_date.isoformat(),
                                'date_source': date_source,
                                'days_before_expiry': (comparison_date - doc.expiry_date).days
                            })
        
        return jsonify({
            'success': True,
            'has_alerts': has_critical_alerts,
            'alert_count': len(alerts),
            'alerts': alerts,
            'comparison_date': comparison_date.isoformat(),
            'date_source': date_source
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting shipment document alerts: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


from datetime import datetime

@bp.route('/api/material-document-alerts/<int:material_id>/<int:shipment_id>')
@login_required
def get_material_document_alerts(material_id, shipment_id):
    """Get document expiry alerts for a specific material in a shipment"""
    try:
        # Get the shipment entry
        entry = ShipDocumentEntryMaster.query.filter_by(
            id=shipment_id,
            company_id=current_user.company_id
        ).first()
        
        if not entry:
            return jsonify({'success': False, 'message': 'Shipment not found'}), 404
        
        # Get the related OrderShipment to check for ETA
        order_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=shipment_id).first()
        
        # Determine the comparison date
        comparison_date = None
        date_source = None
        
        if order_shipment and order_shipment.eta:
            comparison_date = order_shipment.eta.date()  # Convert datetime to date
            date_source = 'eta'
        elif entry.dealineDate:
            comparison_date = entry.dealineDate  # Already a date
            date_source = 'deadline'
        
        if not comparison_date:
            return jsonify({
                'success': True,
                'has_alerts': False,
                'expiring_documents': []
            })
        
        # Get material documents with joins
        material_docs = db.session.query(
            MaterialHSDocuments,
            HSCodeDocument,
            HSCodeIssueBody,
            HSDocumentCategory
        ).join(
            HSCodeDocument, MaterialHSDocuments.document_id == HSCodeDocument.id
        ).join(
            HSCodeIssueBody, HSCodeDocument.issuing_body_id == HSCodeIssueBody.id
        ).join(
            HSDocumentCategory, HSCodeDocument.document_category_id == HSDocumentCategory.id
        ).filter(
            MaterialHSDocuments.material_id == material_id,
            MaterialHSDocuments.company_id == current_user.company_id,
            MaterialHSDocuments.expiry_date.isnot(None)
        ).all()
        
        expiring_documents = []
        has_alerts = False
        
        for material_doc, hs_doc, issuing_body, doc_category in material_docs:
            expiry_date = material_doc.expiry_date  # Always a date
            is_expiring = expiry_date < comparison_date
            if is_expiring:
                has_alerts = True
            
            expiring_documents.append({
                'document_id': material_doc.id,
                'file_name': material_doc.file_name,
                'expiry_date': expiry_date.isoformat(),
                'issuing_body': issuing_body.name,
                'document_category': doc_category.name,
                'is_expiring': is_expiring,
                'days_difference': (comparison_date - expiry_date).days if is_expiring else (expiry_date - comparison_date).days
            })
        
        return jsonify({
            'success': True,
            'has_alerts': has_alerts,
            'expiring_documents': expiring_documents,
            'comparison_date': comparison_date.isoformat(),
            'date_source': date_source
        })
    
    except Exception as e:
        current_app.logger.error(f"Error getting material document alerts: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/api/all-shipments-alert-status')
@login_required
def get_all_shipments_alert_status():
    """Get alert status for all shipments to highlight rows in sea_import page"""
    try:
        # Get all entries for the current customer
        entries = ShipDocumentEntryMaster.query.filter_by(
            company_id=current_user.company_id
        ).all()
        
        print(f"Found {len(entries)} entries for customer {current_user.company_id}")
        
        alert_status = {}
        
        for entry in entries:
            print(f"\nProcessing Entry ID: {entry.id}, DocSerial: {entry.docserial}")
            
            # Get the related OrderShipment to check for ETA
            order_shipment = OrderShipment.query.filter_by(ship_doc_entry_id=entry.id).first()
            if order_shipment:
                print(f"  Found OrderShipment with ETA: {order_shipment.eta}")
            else:
                print("  No OrderShipment found")

            # Determine the comparison date
            comparison_date = None
            if order_shipment and order_shipment.eta:
                comparison_date = order_shipment.eta
            elif entry.dealineDate:
                comparison_date = entry.dealineDate
            
            print(f"  Comparison date set to: {comparison_date}")
            
            has_alerts = False
            
            if comparison_date:
                # Get all shipment items for this entry
                shipment_items = db.session.query(ShipmentItem).filter_by(
                    shipment_id=entry.id
                ).all()
                print(f"  Found {len(shipment_items)} shipment items")
                
                for item in shipment_items:
                    print(f"    Processing ShipmentItem ID: {item.id}")
                    if item.po_detail_id:
                        po_detail = PODetail.query.get(item.po_detail_id)
                        if po_detail and po_detail.material_id:
                            print(f"      Found PODetail with Material ID: {po_detail.material_id}")
                            
                            # Check if any documents expire before the comparison date
                            expiring_docs = MaterialHSDocuments.query.filter(
                                MaterialHSDocuments.material_id == po_detail.material_id,
                                MaterialHSDocuments.company_id == current_user.company_id,
                                MaterialHSDocuments.expiry_date.isnot(None),
                                MaterialHSDocuments.expiry_date < comparison_date
                            ).first()
                            
                            if expiring_docs:
                                print(f"      ALERT: Expiring document found with expiry date {expiring_docs.expiry_date}")
                                has_alerts = True
                                break
                            else:
                                print("      No expiring document found")
                    
                    if has_alerts:
                        break
            
            alert_status[entry.id] = {
                'has_alerts': has_alerts,
                'entry_id': entry.id,
                'docserial': entry.docserial
            }
            print(f"  Final alert status for entry: {has_alerts}")
        
        print("\n--- Final Alert Status Result ---")
        for eid, status in alert_status.items():
            print(f"Entry ID: {eid}, Has Alerts: {status['has_alerts']}")

        return jsonify({
            'success': True,
            'alert_status': alert_status
        })
        
    except Exception as e:
        current_app.logger.error(f"Error getting all shipments alert status: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

    
# DEMURRAGE TAB





# Customer Portal Demurrage Routes
# Add these routes to your customer_portal blueprint

# Customer Portal Demurrage Routes
# Add these routes to your customer_portal blueprint

@bp.route("/api/demurrage/shipment/<int:shipment_id>", methods=["GET"])
@login_required
def get_customer_demurrage_records(shipment_id):
    """Get demurrage records for a shipment (customer view)"""
    try:
        # Verify customer has access to this shipment
        from app.models.cha import ShipDocumentEntryMaster
        shipment = ShipDocumentEntryMaster.query.filter_by(
            id=shipment_id,
            customer_id=current_user.customer.id  # Ensure customer can only see their shipments
        ).first()
        
        if not shipment:
            return jsonify({
                "success": False,
                "message": "Shipment not found or access denied"
            }), 404
        
        demurrage_records = db.session.query(
            ShipmentDemurrage,
            DemurrageReasons.reason_name,
            CurrencyMaster.CurrencyCode
        ).join(
            DemurrageReasons, ShipmentDemurrage.reason_id == DemurrageReasons.id
        ).join(
            CurrencyMaster, ShipmentDemurrage.currency_id == CurrencyMaster.currencyID
        ).filter(
            ShipmentDemurrage.shipment_id == shipment_id
        ).order_by(ShipmentDemurrage.demurrage_date.desc()).all()

        # Get container information
        import_containers = ImportContainer.query.filter_by(shipment_id=shipment_id).all()
        export_containers = ExportContainer.query.filter_by(shipment_id=shipment_id).all()

        container_map = {}
        for container in import_containers:
            container_map[f"import_{container.id}"] = container.container_number
        for container in export_containers:
            container_map[f"export_{container.id}"] = container.container_number

        result = []
        total_amount = 0

        for demurrage, reason_name, currency_code in demurrage_records:
            container_key = f"{demurrage.container_type}_{demurrage.container_id}"
            container_number = container_map.get(container_key, "Unknown")
            
            result.append({
                "id": demurrage.id,
                "container_number": container_number,
                "container_id": demurrage.container_id,
                "container_type": demurrage.container_type,
                "demurrage_date": demurrage.demurrage_date.strftime("%Y-%m-%d"),
                "amount": float(demurrage.amount),
                "currency_code": currency_code,
                "currency_id": demurrage.currency_id,
                "reason_name": reason_name,
                "reason_id": demurrage.reason_id,
                "created_at": demurrage.created_at.strftime("%Y-%m-%d %H:%M:%S") if demurrage.created_at else None
            })
            total_amount += float(demurrage.amount)
        
        return jsonify({
            "success": True,
            "data": result,
            "total_amount": total_amount,
            "count": len(result)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching customer demurrage records: {str(e)}")
        return jsonify({
            "success": False,
            "message": "Failed to fetch demurrage records"
        }), 500


@bp.route("/api/demurrage/<int:demurrage_id>", methods=["GET"])
@login_required
def get_customer_demurrage_details(demurrage_id):
    """Get detailed demurrage information (customer view)"""
    try:
        
        # Get demurrage record with shipment verification
        demurrage = db.session.query(ShipmentDemurrage).join(
            ShipDocumentEntryMaster, ShipmentDemurrage.shipment_id == ShipDocumentEntryMaster.id
        ).filter(
            ShipmentDemurrage.id == demurrage_id,
            ShipDocumentEntryMaster.customer_id == current_user.customer.id  # Ensure customer access
        ).first()
        
        if not demurrage:
            return jsonify({
                "success": False,
                "message": "Demurrage record not found or access denied"
            }), 404
        
        # Get related data
        reason = DemurrageReasons.query.get(demurrage.reason_id)
        currency = CurrencyMaster.query.get(demurrage.currency_id)
        
        # Get container information
        container_number = "Unknown"
        container_size = ""
        
        if demurrage.container_type == 'import':
            container = ImportContainer.query.get(demurrage.container_id)
            if container:
                container_number = container.container_number
                # Handle new foreign key structure for container size/type
                try:
                    if container.container_size_id and container.container_size:
                        size_name = container.container_size.name
                    else:
                        size_name = "Unknown"
                    
                    if container.container_type_id and container.container_type:
                        type_name = container.container_type.name
                    else:
                        type_name = "Unknown"
                    
                    container_size = f"{size_name} {type_name}"
                except:
                    container_size = "Unknown Size/Type"
                    
        elif demurrage.container_type == 'export':
            container = ExportContainer.query.get(demurrage.container_id)
            if container:
                container_number = container.container_number
                # Handle container size info for export containers
                try:
                    if hasattr(container, 'container_size_id') and container.container_size:
                        size_name = container.container_size.name
                        type_name = container.container_type.name if container.container_type else "Unknown"
                        container_size = f"{size_name} {type_name}"
                    else:
                        # Fallback to old string format if exists
                        container_size = f"{getattr(container, 'container_size', 'Unknown')} {getattr(container, 'container_type', '')}"
                except:
                    container_size = "Unknown Size/Type"
        
        record_data = {
            "id": demurrage.id,
            "shipment_id": demurrage.shipment_id,
            "container_id": demurrage.container_id,
            "container_type": demurrage.container_type,
            "container_number": container_number,
            "container_size": container_size,
            "demurrage_date": demurrage.demurrage_date.strftime("%Y-%m-%d"),
            "amount": float(demurrage.amount),
            "currency_id": demurrage.currency_id,
            "currency_code": currency.CurrencyCode if currency else "USD",
            "currency_name": getattr(currency, 'CurrencyName', 'US Dollar') if currency else "US Dollar",
            "reason_id": demurrage.reason_id,
            "reason_name": reason.reason_name if reason else "Unknown",
            "created_at": demurrage.created_at.strftime("%Y-%m-%d %H:%M:%S") if demurrage.created_at else None
        }
        
        return jsonify({
            "success": True,
            "data": record_data
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching customer demurrage details: {str(e)}")
        return jsonify({
            "success": False,
            "message": "Failed to fetch demurrage details"
        }), 500


@bp.route("/api/demurrage/<int:demurrage_id>/attachments", methods=["GET"])
@login_required
def get_customer_demurrage_attachments(demurrage_id):
    """Get attachments for a demurrage record (customer view)"""
    try:
        from app.models.cha import ShipmentDemurrage, ShipmentDemurrageAttachment, ShipDocumentEntryMaster
        
        # Verify customer has access to this demurrage record
        demurrage = db.session.query(ShipmentDemurrage).join(
            ShipDocumentEntryMaster, ShipmentDemurrage.shipment_id == ShipDocumentEntryMaster.id
        ).filter(
            ShipmentDemurrage.id == demurrage_id,
            ShipDocumentEntryMaster.customer_id == current_user.customer.id
        ).first()
        
        if not demurrage:
            return jsonify({
                "success": False,
                "message": "Demurrage record not found or access denied"
            }), 404
        
        # Get attachments
        attachments = ShipmentDemurrageAttachment.query.filter_by(
            shipment_demurrage_id=demurrage_id
        ).order_by(ShipmentDemurrageAttachment.created_at.desc()).all()
        
        attachments_data = []
        for att in attachments:
            attachment_data = {
                "id": att.id,
                "file_name": att.file_name,
                "date": att.date.strftime("%Y-%m-%d") if att.date else None,
                "comment": att.comment,
                "created_at": att.created_at.strftime("%Y-%m-%d %H:%M:%S") if att.created_at else None
            }
            attachments_data.append(attachment_data)
        
        return jsonify({
            "success": True,
            "data": attachments_data,
            "count": len(attachments_data)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching customer demurrage attachments: {str(e)}")
        return jsonify({
            "success": False,
            "message": "Failed to fetch attachments"
        }), 500


@bp.route("/view-demurrage-document/<int:attachment_id>")
@login_required
def view_customer_demurrage_document(attachment_id):
    """SECURE: Serve demurrage attachment through app proxy (customer view)"""
    try:
        from app.models.cha import ShipmentDemurrageAttachment, ShipmentDemurrage, ShipDocumentEntryMaster
        
        # Get attachment with customer access verification
        attachment = db.session.query(ShipmentDemurrageAttachment).join(
            ShipmentDemurrage, ShipmentDemurrageAttachment.shipment_demurrage_id == ShipmentDemurrage.id
        ).join(
            ShipDocumentEntryMaster, ShipmentDemurrage.shipment_id == ShipDocumentEntryMaster.id
        ).filter(
            ShipmentDemurrageAttachment.id == attachment_id,
            ShipDocumentEntryMaster.customer_id == current_user.customer.id  # Ensure customer access
        ).first()
        
        if not attachment:
            return jsonify({
                "success": False,
                "message": "Document not found or access denied"
            }), 404
        
        print(f"Customer attempting to view demurrage document: {attachment.attachment_path}")

        # REMOVED: Presigned URL generation (unsafe)
        # url = get_s3_url(current_app.config["S3_BUCKET_NAME"], attachment.attachment_path, expires_in=3600)
        # return redirect(url)

        # ADDED: Secure serving through app proxy
        s3_key = attachment.attachment_path.replace("\\", "/")  # Normalize path separators
        
        print(f"Serving demurrage document securely: {s3_key}")
        return serve_s3_file(s3_key)

    except Exception as e:
        print(f"Error serving customer demurrage document: {str(e)}")
        current_app.logger.error(f"Error serving customer demurrage document: {str(e)}")
        return jsonify({
            "success": False, 
            "message": "Error accessing file"
        }), 500


