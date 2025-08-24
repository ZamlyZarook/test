from flask import (
    Blueprint,
    jsonify,
    request,
    current_app,
    redirect,
)
from flask_login import login_required, current_user
from app.models.cha import (
    db,
    ChatMessage,
    ChatThread,
    ChatParticipant,
    ChatAttachment,
    ShipDocumentEntryMaster,
    EntryAssignmentHistory
)
from datetime import datetime
from werkzeug.utils import secure_filename
import os
from app.utils_cha.s3_utils import upload_file_to_s3, delete_file_from_s3, get_s3_url
import uuid
import mimetypes
from app.utils import get_sri_lanka_time
from app.email import send_email, send_async_email
import json
from app.models.user import User

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/thread/<module_name>/<int:reference_id>", methods=["GET"])
@login_required
def get_or_create_thread(module_name, reference_id):
    print("\n=== GET/CREATE THREAD ===")
    print(f"Module: {module_name}")
    print(f"Reference ID: {reference_id}")
    print(f"Current User: {current_user.username} (ID: {current_user.id}, Role: {current_user.role})")

    try:
        # First, try to find any existing thread for this module and reference_id
        thread = ChatThread.query.filter(
            ChatThread.reference_id == reference_id
        ).first()

        if thread:
            print(f"Found existing thread: {thread.id}")
            print(f"Thread sender role: {thread.sender_role}")
            print(f"Thread recipient role: {thread.recipient_role}")
            
            # Improved access control logic
            has_access = False
            
            if current_user.role == 'customer':
                # Customer can access if they are the sender OR recipient
                has_access = thread.sender_role == 'customer' or thread.recipient_role == 'customer'
            elif current_user.role in ['user', 'base_user']:
                # Company users can access if:
                # 1. They are the sender, OR
                # 2. The thread is set up for company-customer communication
                has_access = (
                    thread.sender_role in ['user', 'base_user'] or 
                    thread.recipient_role in ['user', 'base_user'] or
                    # Allow access to customer threads (legacy fix)
                    thread.sender_role == 'customer' or
                    thread.recipient_role == 'customer'
                )
            elif current_user.role == 'admin':
                # Admin has access to everything
                has_access = True
            
            if not has_access:
                print("ACCESS DENIED: User role not in thread roles")
                print(f"User role: {current_user.role}")
                print(f"Thread sender_role: {thread.sender_role}")
                print(f"Thread recipient_role: {thread.recipient_role}")
                return jsonify({"error": "Access denied"}), 403
            
            # If access is granted, ensure user is a participant
            existing_participant = ChatParticipant.query.filter_by(
                thread_id=thread.id,
                user_id=current_user.id
            ).first()
            
            if not existing_participant:
                print(f"Adding user {current_user.id} as participant to thread {thread.id}")
                participant = ChatParticipant(
                    thread_id=thread.id,
                    user_id=current_user.id
                )
                db.session.add(participant)
                db.session.commit()
        else:
            print("Creating new thread...")
            
            # Determine thread roles based on current user's role
            if current_user.role == 'customer':
                sender_role = 'customer'
                recipient_role = 'user'  # Default to 'user' for company side
            else:
                sender_role = current_user.role  # 'user' or 'base_user'
                recipient_role = 'customer'
            
            # Create new thread with correct roles
            thread = ChatThread(
                module_name=module_name,
                reference_id=reference_id,
                sender_role=sender_role,
                recipient_role=recipient_role
            )
            db.session.add(thread)
            db.session.flush()
            
            # Add current user as participant
            participant = ChatParticipant(
                thread_id=thread.id,
                user_id=current_user.id
            )
            db.session.add(participant)
            
            # Add the other party as participant (if we can find them)
            # For now, we'll add participants when they first access the thread
            # This ensures both parties are added when they join
            
            db.session.commit()
            print(f"Created thread {thread.id} with roles: sender={sender_role}, recipient={recipient_role}")

        print("=== END GET/CREATE THREAD ===\n")
        return jsonify({
            "thread_id": thread.id,
            "reference_id": thread.reference_id,
            "module_name": thread.module_name,
            "created_at": thread.created_at.isoformat()
        })

    except Exception as e:
        print(f"Error in get_or_create_thread: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({"error": "Failed to initialize chat"}), 500



@chat_bp.route("/messages/<int:thread_id>", methods=["GET"])
@login_required
def get_messages(thread_id):
    print("\n=== GET MESSAGES ===")
    print(f"Thread ID: {thread_id}")
    print(f"Current User: {current_user.username} (ID: {current_user.id}, Role: {current_user.role})")
    
    # Get the thread
    thread = ChatThread.query.get_or_404(thread_id)
    print(f"Thread found: {thread.id}")
    print(f"Reference ID: {thread.reference_id}")
    print(f"Module: {thread.module_name}")
    
    # Get all messages for this reference_id and module
    messages = (
        ChatMessage.query.filter_by(
            reference_id=thread.reference_id
        )
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    
    print(f"\nFound {len(messages)} messages:")
    for msg in messages:
        print(f"\nMessage ID: {msg.id}")
        print(f"Reference ID: {msg.reference_id}")
        print(f"From: {msg.sender.username} (ID: {msg.sender.id}, Role: {msg.sender_role})")
        print(f"Message: {msg.message[:50]}{'...' if len(msg.message) > 50 else ''}")
        print(f"Time: {msg.created_at}")
        print(f"Is Read: {msg.is_read}")
        if msg.attachments:
            print(f"Attachments: {len(msg.attachments)}")
            for att in msg.attachments:
                print(f"  - {att.file_name} ({att.file_type})")

    print("=== END GET MESSAGES ===\n")
    return jsonify({
        "messages": [
            {
                "id": msg.id,
                "reference_id": msg.reference_id,
                "sender": {
                    "id": msg.sender.id, 
                    "name": msg.sender.name or msg.sender.username,
                    "role": msg.sender_role
                },
                "message": msg.message,
                "message_type": msg.message_type,
                "created_at": msg.created_at.isoformat(),
                "is_read": msg.is_read,
                "parent_message_id": msg.parent_message_id,
                # Include parent message data if it exists
                "parent_message": {
                    "id": msg.parent_message.id,
                    "message": msg.parent_message.message,
                    "sender": {
                        "id": msg.parent_message.sender.id,
                        "name": msg.parent_message.sender.name or msg.parent_message.sender.username,
                        "role": msg.parent_message.sender_role
                    }
                } if msg.parent_message else None,
                "attachments": [
                    {
                        "id": att.id,
                        "file_type": att.file_type,
                        "file_name": att.file_name,
                        "file_path": att.file_path,
                    }
                    for att in msg.attachments
                ],
            }
            for msg in messages
        ]
    })



# @chat_bp.route("/check-new-messages/<module_name>/<int:reference_id>", methods=["GET"])
# @login_required
# def check_new_messages(module_name, reference_id):
#     """Check for new messages in a specific thread"""
#     try:
#         # Query for unread messages using reference_id
#         unread_count = ChatMessage.query.filter(
#             ChatMessage.reference_id == reference_id,
#             ChatMessage.module_name == module_name,
#             ChatMessage.is_read == False,
#             ChatMessage.sender_role != current_user.role
#         ).count()
        
#         return jsonify({
#             "success": True,
#             "unread_count": unread_count
#         })
#     except Exception as e:
#         current_app.logger.error(f"Error in check_new_messages: {str(e)}")
#         return jsonify({"success": False, "message": str(e)}), 500



@chat_bp.route("/mark-messages-read/<module_name>/<int:reference_id>", methods=["POST"])
@login_required
def mark_messages_read(module_name, reference_id):
    """Mark messages as read for a specific thread with proper 3-role logic"""
    print("\n=== MARKING MESSAGES AS READ ===")
    print(f"Module: {module_name}")
    print(f"Reference ID: {reference_id}")
    print(f"Current User: {current_user.username} (ID: {current_user.id}, Role: {current_user.role})")
    
    try:
        # Find the thread 
        thread = ChatThread.query.filter_by(
            reference_id=reference_id
        ).first()
        
        if not thread:
            print("No thread found")
            return jsonify({"success": True, "message": "No thread found"})
        
        print(f"Found thread: {thread.id}")
        
        # Get messages to mark as read based on role-based logic
        if current_user.role == 'customer':
            # Customer marks messages from company users (user, base_user) as read
            unread_messages = ChatMessage.query.join(User, ChatMessage.sender_id == User.id).filter(
                ChatMessage.reference_id == reference_id,
                ChatMessage.is_read == False,
                ChatMessage.sender_id != current_user.id,  # Not sent by current user
                User.role.in_(['user', 'base_user'])  # Only from company users
            ).all()
        else:
            # Company users (user, base_user) mark messages from customers as read
            unread_messages = ChatMessage.query.join(User, ChatMessage.sender_id == User.id).filter(
                ChatMessage.reference_id == reference_id,
                ChatMessage.is_read == False,
                ChatMessage.sender_id != current_user.id,  # Not sent by current user
                User.role == 'customer'  # Only from customers
            ).all()
        
        print(f"Marking {len(unread_messages)} messages as read for {current_user.role} user")
        
        for message in unread_messages:
            message.is_read = True
            print(f"Marked message {message.id} from {message.sender.username} ({message.sender.role}) as read")
        
        # Update the participant's last read timestamp
        participant = ChatParticipant.query.filter_by(
            thread_id=thread.id,
            user_id=current_user.id
        ).first()
        
        if participant:
            participant.last_read_at = get_sri_lanka_time()
            print(f"Updated last_read_at for participant {participant.id}")
        
        db.session.commit()
        print("Changes committed to database")
        print("=== END MARKING MESSAGES AS READ ===\n")
        
        return jsonify({
            "success": True,
            "message": f"Marked {len(unread_messages)} messages as read"
        })
    except Exception as e:
        db.session.rollback()
        print(f"Error marking messages as read: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500
    


@chat_bp.route("/send-message/<module_name>/<int:reference_id>", methods=["POST"])
@login_required
def send_message(module_name, reference_id):

    print("\n=== SEND MESSAGE ===")
    print(f"Module: {module_name}")
    print(f"Reference ID: {reference_id}")
    print(f"Current User: {current_user.username} (ID: {current_user.id}, Role: {current_user.role})")
    print(f"Request files: {request.files}")
    print(f"Request form: {request.form}")
    
    try:
        # Find thread by module and reference_id only
        thread = ChatThread.query.filter(
            ChatThread.module_name == module_name,
            ChatThread.reference_id == reference_id
        ).first()
        
        if thread:
            print(f"Found existing thread: {thread.id}")
            # Ensure all relevant users are participants
            entry = ShipDocumentEntryMaster.query.get(reference_id)
            if entry:
                ensure_thread_participants(thread, entry)
        else:
            print("Creating new thread...")
            thread = ChatThread(
                module_name=module_name,
                reference_id=reference_id,
                sender_role='user',
                recipient_role='customer'
            )
            db.session.add(thread)
            db.session.flush()
            print(f"Created new thread: {thread.id}")

        # Get message details
        message_text = request.form.get("message", "")
        parent_message_id = request.form.get("parent_message_id")
        
        print(f"\nMessage Text: {message_text[:50]}{'...' if len(message_text) > 50 else ''}")
        print(f"Parent Message ID: {parent_message_id}")

        # Determine sender and recipient roles based on current user's role
        sender_role = current_user.role
        if current_user.role == 'customer':
            recipient_role = 'user'  # Customer sends to company
        else:
            recipient_role = 'customer'  # Company sends to customer
        
        print(f"Sender role: {sender_role}, Recipient role: {recipient_role}")

        # Create message with correct roles
        new_message = ChatMessage(
            thread_id=thread.id,
            reference_id=reference_id,
            module_name=module_name,
            sender_id=current_user.id,
            message=message_text,
            message_type="text",
            sender_role=sender_role,
            recipient_role=recipient_role,
            is_read=False,
            parent_message_id=parent_message_id,
            created_at=get_sri_lanka_time()
        )
        db.session.add(new_message)
        db.session.flush()
        
        print(f"\nCreated new message: {new_message.id}")
        print(f"Reference ID: {new_message.reference_id}")
        print(f"From: {current_user.username} (Role: {sender_role})")
        print(f"To Role: {recipient_role}")

        # Handle file attachment if present - using the working logic from your other routes
        if 'file' in request.files:
            file = request.files['file']
            print(f"\nProcessing file: {file.filename}, {file.content_type}")
            
            if file and file.filename:
                # Generate unique filename
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                
                # Determine file type
                mime_type = file.content_type or mimetypes.guess_type(filename)[0]
                file_type = "document"
                
                if mime_type and ('audio' in mime_type or file.filename.lower().endswith(('.mp3', '.wav', '.m4a', '.ogg'))):
                    file_type = "voice"
                    s3_folder = "voice"
                elif mime_type and 'image' in mime_type:
                    file_type = "image"
                    s3_folder = "images"
                else:
                    s3_folder = "attachments"
                
                # Set S3 key path
                s3_key = f"{current_app.config['S3_BASE_FOLDER']}/chat/{s3_folder}/{reference_id}/{unique_filename}"
                
                print(f"File type: {file_type}")
                print(f"S3 key: {s3_key}")
                
                # Upload to S3
                if upload_file_to_s3(file, current_app.config["S3_BUCKET_NAME"], s3_key):
                    print("File uploaded successfully to S3")
                    
                    # Create attachment record
                    attachment = ChatAttachment(
                        message_id=new_message.id,
                        file_name=filename,
                        file_path=s3_key,
                        file_type=file_type
                    )
                    db.session.add(attachment)
                    print(f"Attachment record created with file path: {s3_key}")
                else:
                    print("Failed to upload file to S3")
            else:
                print("No valid file received")
        else:
            print("No file in request")

        db.session.commit()
        print("Message and attachments successfully saved to database")
        
        # Send email notifications after successful message save
        try:
            # Get the entry details for email context
            entry = ShipDocumentEntryMaster.query.get(reference_id)
            if entry:
                # Determine who should receive the email based on sender role
                if is_company_role(current_user.role):
                    # Company user sent message to customer - notify customer
                    if entry.customer and entry.customer.email:
                        send_chat_notification_email(
                            recipient_email=entry.customer.email,
                            recipient_name=entry.customer.customer_name,
                            sender_name=current_user.name or current_user.username,
                            message_text=message_text,
                            entry=entry,
                            is_customer=True
                        )
                        print(f"Email sent to customer: {entry.customer.email}")
                
                elif current_user.role == 'customer':
                    # Customer sent message to company - notify company and assigned person
                    
                    # Send to company email
                    if entry.company and entry.company.email:
                        send_chat_notification_email(
                            recipient_email=entry.company.email,
                            recipient_name=entry.company.company_name,
                            sender_name=current_user.name or current_user.username,
                            message_text=message_text,
                            entry=entry,
                            is_customer=False
                        )
                        print(f"Email sent to company: {entry.company.email}")
                    
                    # Send to assigned person if exists
                    current_assignment = EntryAssignmentHistory.query.filter_by(
                        entry_id=reference_id,
                        currently_assigned=True
                    ).first()
                    
                    if current_assignment and current_assignment.assigned_to and current_assignment.assigned_to.email:
                        send_chat_notification_email(
                            recipient_email=current_assignment.assigned_to.email,
                            recipient_name=current_assignment.assigned_to.name or current_assignment.assigned_to.username,
                            sender_name=current_user.name or current_user.username,
                            message_text=message_text,
                            entry=entry,
                            is_customer=False
                        )
                        print(f"Email sent to assigned user: {current_assignment.assigned_to.email}")
                        
        except Exception as email_error:
            # Log email error but don't fail the message sending
            print(f"Error sending email notifications: {str(email_error)}")
        
        # Get the complete message with attachments
        message_with_attachments = ChatMessage.query.get(new_message.id)
        print(f"Attachments count: {len(message_with_attachments.attachments)}")
        
        print("=== END SEND MESSAGE ===\n")

        return jsonify({
            "success": True,
            "message": {
                "id": message_with_attachments.id,
                "reference_id": message_with_attachments.reference_id,
                "message": message_with_attachments.message,
                "sender": {
                    "id": current_user.id,
                    "name": current_user.name or current_user.username,
                    "role": current_user.role
                },
                "created_at": message_with_attachments.created_at.isoformat(),
                "parent_message_id": message_with_attachments.parent_message_id,
                "attachments": [
                    {
                        "id": att.id,
                        "file_type": att.file_type,
                        "file_name": att.file_name,
                        "file_path": att.file_path,
                    }
                    for att in message_with_attachments.attachments
                ]
            }
        })

    except Exception as e:
        db.session.rollback()
        print(f"\nERROR in send_message: {str(e)}")
        current_app.logger.error(f"Error in send_message: {str(e)}")
        print("=== END SEND MESSAGE (WITH ERROR) ===\n")
        return jsonify({"success": False, "error": str(e)}), 500


def send_chat_notification_email(recipient_email, recipient_name, sender_name, message_text, entry, is_customer):
    """Helper function to send chat notification emails"""
    try:
        # Prepare email data
        email_data = {
            'recipient_name': recipient_name,
            'sender_name': sender_name,
            'message_text': message_text,
            'entry_id': entry.id,
            'docserial': entry.docserial,
            'customer_name': entry.customer.customer_name if entry.customer else 'Unknown Customer',
            'company_name': entry.company.company_name if entry.company else 'Unknown Company',
            'message_date': get_sri_lanka_time().strftime('%Y-%m-%d %H:%M:%S'),
            'is_customer': is_customer
        }
        
        subject = f"New Message - Entry {entry.docserial}"
        
        send_email(
            subject=subject,
            recipient=recipient_email,
            template="email/chat_notification.html",
            **email_data
        )
        
    except Exception as e:
        print(f"Error in send_chat_notification_email: {str(e)}")
        raise e
    
# @chat_bp.route("/message/<int:message_id>/read", methods=["POST"])
# @login_required
# def mark_as_read(message_id):
#     """Mark a message as read"""
#     message = ChatMessage.query.get_or_404(message_id)
#     message.is_read = True

#     # Update participant's last read timestamp
#     participant = ChatParticipant.query.filter_by(
#         thread_id=message.thread_id, user_id=current_user.id
#     ).first()
#     if participant:
#         participant.last_read_at = get_sri_lanka_time()

#     db.session.commit()
#     return jsonify({"success": True})


@chat_bp.route("/thread/<int:thread_id>/participants", methods=["POST"])
@login_required
def add_participant(thread_id):
    """Add a participant to a thread"""
    user_id = request.json.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "User ID is required"}), 400

    participant = ChatParticipant(thread_id=thread_id, user_id=user_id)
    db.session.add(participant)
    db.session.commit()

    return jsonify({"success": True})


@chat_bp.route("/attachment/<path:file_path>")
@login_required
def get_attachment(file_path):
    """Get a presigned URL for an attachment and redirect to it"""
    try:
        # Generate a presigned URL that's valid for 1 hour
        url = get_s3_url(
            current_app.config["S3_BUCKET_NAME"], file_path, expires_in=3600
        )
        if url:
            return redirect(url)
        return jsonify({"success": False, "message": "File not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Error getting attachment: {str(e)}")
        return jsonify({"success": False, "message": "Error accessing file"}), 500



@chat_bp.route("/check-new-messages/<module_name>/<int:reference_id>", methods=["GET"])
@login_required
def check_new_messages(module_name, reference_id):
    """Check for new unread messages in a specific thread with proper 3-role logic"""
    try:
        # Get unread count based on role-based logic
        if current_user.role == 'customer':
            # Customer checks for messages from company users (user, base_user)
            unread_count = ChatMessage.query.join(User, ChatMessage.sender_id == User.id).filter(
                ChatMessage.reference_id == reference_id,
                ChatMessage.is_read == False,
                ChatMessage.sender_id != current_user.id,  # Not sent by current user
                User.role.in_(['user', 'base_user'])  # Only from company users
            ).count()
        else:
            # Company users check for messages from customers
            unread_count = ChatMessage.query.join(User, ChatMessage.sender_id == User.id).filter(
                ChatMessage.reference_id == reference_id,
                ChatMessage.is_read == False,
                ChatMessage.sender_id != current_user.id,  # Not sent by current user
                User.role == 'customer'  # Only from customers
            ).count()
        
        print(f"{unread_count} new messages in {module_name}/{reference_id} for {current_user.role} user")
        
        return jsonify({
            "success": True,
            "new_messages_exist": unread_count > 0,
            "unread_count": unread_count
        })
    except Exception as e:
        current_app.logger.error(f"Error in check_new_messages: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500


def is_company_role(role):
    """Check if role is on the company/clearing agent side"""
    return role in ['user', 'base_user']

def get_company_roles():
    """Get all roles that represent company/clearing agent side"""
    return ['user', 'base_user']

def validate_user_role(role):
    valid_roles = ['user', 'base_user', 'customer']
    if role not in valid_roles:
        raise ValueError(f"Invalid role: {role}")
    return role

# Both user and base_user can access the same thread
def has_thread_access(thread, user_role):
    if user_role == 'customer':
        return thread.recipient_role == 'customer'
    else:
        # Both user and base_user can access company-side threads
        return user_role in ['user', 'base_user'] and thread.sender_role in ['user', 'base_user']

# Allow multiple company users to join the same thread
@chat_bp.route("/thread/<int:thread_id>/join", methods=["POST"])
@login_required
def join_thread(thread_id):
    thread = ChatThread.query.get_or_404(thread_id)
    
    # Check if user can join this thread
    if current_user.role not in ['user', 'base_user']:
        return jsonify({"error": "Only company users can join threads"}), 403
    
    # Check if already a participant
    existing_participant = ChatParticipant.query.filter_by(
        thread_id=thread_id,
        user_id=current_user.id
    ).first()
    
    if not existing_participant:
        participant = ChatParticipant(
            thread_id=thread_id,
            user_id=current_user.id
        )
        db.session.add(participant)
        db.session.commit()
    
    return jsonify({"success": True, "message": "Joined thread successfully"})


# Add this route to check for new notifications

@chat_bp.route("/notifications/check-new")
@login_required
def check_new_notifications():
    """Check if user has new notifications"""
    try:
        from .utils_roles import get_all_notifications
        
        notifications = get_all_notifications(current_user.id)
        has_new = notifications['total_count'] > 0
        
        return jsonify({
            'success': True,
            'has_new_notifications': has_new,
            'total_count': notifications['total_count']
        })
    except Exception as e:
        current_app.logger.error(f"Error checking notifications: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@chat_bp.route("/message/<int:message_id>/mark-read", methods=["POST"])
@login_required
def mark_chat_message_read(message_id):
    """Mark a specific chat message as read"""
    try:
        from .models import ChatMessage
        
        message = ChatMessage.query.get_or_404(message_id)
        
        # Only mark as read if the current user is not the sender
        if message.sender_id != current_user.id:
            message.is_read = True
            db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error marking message as read: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# Add this utility function to fix existing threads
@chat_bp.route("/fix-thread-roles", methods=["POST"])
@login_required
def fix_thread_roles():
    """Fix existing threads with incorrect role assignments"""
    try:
        # Find threads with customer as both sender and recipient
        problematic_threads = ChatThread.query.filter(
            ChatThread.sender_role == 'customer',
            ChatThread.recipient_role == 'customer'
        ).all()
        
        fixed_count = 0
        for thread in problematic_threads:
            # Fix the thread roles to be company-customer
            thread.sender_role = 'user'  # Company side
            thread.recipient_role = 'customer'  # Customer side
            fixed_count += 1
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Fixed {fixed_count} threads",
            "fixed_count": fixed_count
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# Add this utility function to fix existing messages with incorrect roles
@chat_bp.route("/fix-message-roles", methods=["POST"])
@login_required
def fix_message_roles():
    """Fix existing messages with incorrect role assignments"""
    try:
        # Find messages where sender_role and recipient_role are both 'customer'
        problematic_messages = ChatMessage.query.filter(
            ChatMessage.sender_role == 'customer',
            ChatMessage.recipient_role == 'customer'
        ).all()
        
        fixed_count = 0
        for message in problematic_messages:
            # Fix the recipient role to be 'user' (company)
            message.recipient_role = 'user'
            fixed_count += 1
        
        # Find messages where sender_role and recipient_role are both 'user'
        problematic_messages2 = ChatMessage.query.filter(
            ChatMessage.sender_role == 'user',
            ChatMessage.recipient_role == 'user'
        ).all()
        
        for message in problematic_messages2:
            # Fix the recipient role to be 'customer'
            message.recipient_role = 'customer'
            fixed_count += 1
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Fixed {fixed_count} messages",
            "fixed_count": fixed_count
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# Add this function to ensure all relevant users are participants
def ensure_thread_participants(thread, entry):
    """Ensure all relevant users are participants in the thread"""
    from app.models.user import User
    
    # Get all users who should be participants
    participants_to_add = []
    
    # Add customer
    if entry.company_id:
        customer = User.query.filter_by(company_id=entry.company_id, role='customer').first()
        if customer:
            existing_customer_participant = ChatParticipant.query.filter_by(
                thread_id=thread.id,
                user_id=customer.id
            ).first()
            if not existing_customer_participant:
                participants_to_add.append(customer.id)
    
    # Add company users (assigned clearing company)
    if entry.assigned_clearing_company_id:
        company_users = User.query.filter(
            User.company_id == entry.assigned_clearing_company_id,
            User.role.in_(['user', 'base_user'])
        ).all()
        
        for user in company_users:
            existing_participant = ChatParticipant.query.filter_by(
                thread_id=thread.id,
                user_id=user.id
            ).first()
            if not existing_participant:
                participants_to_add.append(user.id)
    
    # Add new participants
    for user_id in participants_to_add:
        participant = ChatParticipant(
            thread_id=thread.id,
            user_id=user_id
        )
        db.session.add(participant)
        print(f"Added user {user_id} as participant to thread {thread.id}")
    
    if participants_to_add:
        db.session.commit()
        print(f"Added {len(participants_to_add)} new participants to thread {thread.id}")


# Add this route for debugging
@chat_bp.route("/debug-notifications/<int:user_id>")
@login_required
def debug_notifications(user_id):
    """Debug notifications for a specific user"""
    from .utils_roles import debug_notifications_for_user
    debug_notifications_for_user(user_id)
    return jsonify({"success": True, "message": "Check console for debug output"})

@chat_bp.route("/notifications/get-all")
@login_required
def get_all_notifications_data():
    """Get all notifications data for real-time updates"""
    try:
        from .utils_roles import get_all_notifications
        
        notifications = get_all_notifications(current_user.id)
        
        return jsonify({
            'success': True,
            'notifications': notifications,
            'total_count': notifications['total_count'],
            'chat_count': len(notifications['chat_notifications']),
            'questionnaire_count': len(notifications['questionnaire_reviews']),
            'safety_count': len(notifications['monthly_safety_reviews'])
        })
    except Exception as e:
        current_app.logger.error(f"Error getting notifications: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

