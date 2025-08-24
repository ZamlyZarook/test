from functools import wraps
from flask import abort, request
from flask_login import current_user
from flask import current_app
from .models.user import Menu

def check_route_permission():
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            
            # Get the current route name
            route_name = f"{request.blueprint}.{f.__name__}"
            
            # Special case for admin role - full access
            if current_user.role == 'admin':
                return f(*args, **kwargs)
            
            # Check permission in database
            # if not current_user.assigned_role.has_route_permission(route_name):
            #     abort(403)
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def build_menu_tree(menus):
    menu_dict = {menu.id: menu for menu in menus}
    menu_tree = []
    
    for menu in menus:
        if menu.parent_id is None:
            menu_tree.append(menu)
        else:
            parent = menu_dict.get(menu.parent_id)
            if parent and not hasattr(parent, 'children'):
                parent.children = []
            if parent:
                parent.children.append(menu)
    
    return menu_tree

def get_menu_tree():
    """Fetch all menus and build hierarchical structure"""
    all_menus = Menu.query.order_by(Menu.order_index).all()
    menu_dict = {menu.id: {'menu': menu, 'children': []} for menu in all_menus}
    
    root_menus = []
    for menu in all_menus:
        if menu.parent_id is None:
            root_menus.append(menu_dict[menu.id])
        else:
            menu_dict[menu.parent_id]['children'].append(menu_dict[menu.id])
    
    return root_menus


def get_pending_review_notifications(user_id):
    """
    Get notifications for pending reviews that the current user needs to act on
    
    Args:
        user_id: ID of the current user
    
    Returns:
        dict: Dictionary with notification data
    """
    from .models import DocumentReviewer, TemplateReviewer, QhesEmployeeQuestionHeader, ResponseReview, MonthlySafetyHeader, TemplateResponseReview
    
    notifications = {
        'questionnaire_reviews': [],
        'monthly_safety_reviews': [],
        'total_count': 0
    }
    
    # Get questionnaire reviews that need this user's attention
    questionnaire_reviewers = DocumentReviewer.query.filter_by(reviewer_id=user_id).all()
    
    # Get IDs of reviews already completed by this user
    completed_questionnaire_reviews = ResponseReview.query.filter(
        ResponseReview.reviewer_id.in_([r.id for r in questionnaire_reviewers]),
        ResponseReview.is_reviewed == True
    ).with_entities(ResponseReview.reviewer_id, ResponseReview.response_id).all()
    
    # Create a set of (reviewer_id, response_id) tuples for quick lookup
    completed_q_set = set([(r.reviewer_id, r.response_id) for r in completed_questionnaire_reviews])
    
    # Check all submitted questionnaires that need review
    for reviewer in questionnaire_reviewers:
        # Find responses for this reviewer's header that are submitted but not reviewed
        if reviewer.header_id:
            pending_responses = QhesEmployeeQuestionHeader.query.filter(
                QhesEmployeeQuestionHeader.type_id == reviewer.header_id,
                QhesEmployeeQuestionHeader.is_submitted == 1
            ).all()
            
            for response in pending_responses:
                # Skip if this user has already reviewed this response
                if (reviewer.id, response.id) in completed_q_set:
                    continue
                
                notifications['questionnaire_reviews'].append({
                    'id': response.id,
                    'code': response.code,
                    'type': response.type,
                    'respondent': response.empName,
                    'timestamp': response.end_time,
                    'reviewer_id': reviewer.id
                })
    
    # Get monthly safety data reviews that need this user's attention
    template_reviewers = TemplateReviewer.query.filter_by(reviewer_id=user_id).all()
    
    # Get IDs of monthly safety reviews already completed by this user
    completed_monthly_reviews = TemplateResponseReview.query.filter(
        TemplateResponseReview.reviewer_id.in_([r.id for r in template_reviewers]),
        TemplateResponseReview.is_reviewed == True
    ).with_entities(TemplateResponseReview.reviewer_id, TemplateResponseReview.response_id).all()
    
    # Create a set of (reviewer_id, response_id) tuples for quick lookup
    completed_m_set = set([(r.reviewer_id, r.response_id) for r in completed_monthly_reviews])
    
    # Check all submitted monthly safety data that needs review
    for reviewer in template_reviewers:
        # Find responses for this reviewer's template that are submitted but not reviewed
        pending_responses = MonthlySafetyHeader.query.filter(
            MonthlySafetyHeader.templateType == reviewer.template_id,
            MonthlySafetyHeader.confirmedYN == 1,
            MonthlySafetyHeader.isDeleted == 0
        ).all()
        
        for response in pending_responses:
            # Skip if this user has already reviewed this response
            if (reviewer.id, response.monthlySafetyID) in completed_m_set:
                continue
            
            notifications['monthly_safety_reviews'].append({
                'id': response.monthlySafetyID,
                'code': response.documentCode,
                'timestamp': response.confirmedDate,
                'reviewer_id': reviewer.id
            })
    
    # Set total count of pending reviews
    notifications['total_count'] = len(notifications['questionnaire_reviews']) + len(notifications['monthly_safety_reviews'])
    
    return notifications


def get_all_notifications(user_id):
    """
    Get chat notifications for a user with proper 3-role system support
    
    Args:
        user_id: ID of the current user
    
    Returns:
        dict: Dictionary with chat notification data
    """
    print(f"\n=== GET ALL NOTIFICATIONS ===")
    print(f"User ID: {user_id}")
    
    from .models.cha import ChatMessage, ChatThread, ShipDocumentEntryMaster, ChatParticipant
    from .models.user import User
    
    # Initialize empty notifications structure
    all_notifications = {
        'chat_notifications': [],
        'questionnaire_reviews': [],
        'monthly_safety_reviews': [],
        'total_count': 0
    }
    
    try:
        print("Querying for unread chat messages...")
        
        # Get current user
        current_user = User.query.get(user_id)
        if not current_user:
            print(f"User {user_id} not found")
            return all_notifications
        
        print(f"Current user: {current_user.username}, Role: {current_user.role}, Company: {current_user.company_id}")
        
        # Get threads where the current user is a participant
        user_threads = ChatParticipant.query.filter_by(user_id=user_id).all()
        user_thread_ids = [pt.thread_id for pt in user_threads]
        
        print(f"User is participant in {len(user_thread_ids)} threads: {user_thread_ids}")
        
        if not user_thread_ids:
            print("User is not a participant in any threads")
            return all_notifications
        
        # Get unread messages based on role-based logic
        if current_user.role == 'customer':
            # Customer should see messages from company users (user, base_user) that are unread
            unread_messages = ChatMessage.query.join(User, ChatMessage.sender_id == User.id).filter(
                ChatMessage.is_read == False,
                ChatMessage.thread_id.in_(user_thread_ids),
                ChatMessage.sender_id != user_id,  # Not sent by current user
                User.role.in_(['user', 'base_user'])  # Only from company users
            ).order_by(ChatMessage.created_at.desc()).limit(10).all()
        else:
            # Company users (user, base_user) should see messages from customers that are unread
            unread_messages = ChatMessage.query.join(User, ChatMessage.sender_id == User.id).filter(
                ChatMessage.is_read == False,
                ChatMessage.thread_id.in_(user_thread_ids),
                ChatMessage.sender_id != user_id,  # Not sent by current user
                User.role == 'customer'  # Only from customers
            ).order_by(ChatMessage.created_at.desc()).limit(10).all()
        
        print(f"Found {len(unread_messages)} unread messages for user {user_id} (role: {current_user.role})")
        
        for i, message in enumerate(unread_messages):
            print(f"\nProcessing message {i+1}/{len(unread_messages)}:")
            print(f"  Message ID: {message.id}")
            print(f"  Thread ID: {message.thread_id}")
            print(f"  Sender ID: {message.sender_id}")
            print(f"  Sender Role: {message.sender.role}")
            print(f"  Is Read: {message.is_read}")
            print(f"  Message: {message.message[:50]}...")
            
            # Get thread information
            thread = ChatThread.query.get(message.thread_id)
            if thread:
                print(f"  Thread found: {thread.id}, Module: {thread.module_name}, Reference: {thread.reference_id}")
                
                # Get entry information
                entry = ShipDocumentEntryMaster.query.get(thread.reference_id)
                if entry:
                    print(f"  Entry found: {entry.id}, DocSerial: {entry.docserial}, Company: {entry.company_id}")
                    
                    # Additional company-level filtering for security
                    if current_user.role == 'customer':
                        # Customer can only see their own entries
                        if entry.company_id != current_user.company_id:
                            print(f"  ✗ Skipped - Customer can't access entry from company {entry.company_id}")
                            continue
                    else:
                        # Company users can see entries assigned to their company
                        if entry.assigned_clearing_company_id != current_user.company_id:
                            print(f"  ✗ Skipped - Company user can't access entry assigned to company {entry.assigned_clearing_company_id}")
                            continue
                else:
                    print(f"  Entry NOT found for reference_id: {thread.reference_id}")
                    continue
                
                # Get sender information
                sender = User.query.get(message.sender_id)
                if sender:
                    print(f"  Sender found: {sender.id}, Username: {sender.username}, Role: {sender.role}")
                else:
                    print(f"  Sender NOT found for sender_id: {message.sender_id}")
                    continue
                
                # Only add notification if we have all required data and passed security checks
                message_content = message.message[:100] + '...' if len(message.message) > 100 else message.message
                
                notification_data = {
                    'id': message.id,
                    'thread_id': message.thread_id,
                    'module_name': thread.module_name,
                    'entry_id': thread.reference_id,
                    'sender_name': sender.username,
                    'message': message_content,
                    'timestamp': message.created_at,
                    'docserial': entry.docserial if entry else 'N/A'
                }
                
                all_notifications['chat_notifications'].append(notification_data)
                print(f"  ✓ Added notification: {sender.username} ({sender.role}) -> {message_content[:50]}...")
            else:
                print(f"  ✗ Thread NOT found for thread_id: {message.thread_id}")
        
        # Set total count to only chat notifications
        all_notifications['total_count'] = len(all_notifications['chat_notifications'])
        
        print(f"\nFinal notification count: {all_notifications['total_count']}")
        print(f"Chat notifications: {len(all_notifications['chat_notifications'])}")
        print("=== END GET ALL NOTIFICATIONS ===\n")
        
    except Exception as e:
        print(f"ERROR in get_all_notifications: {str(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        # Return empty structure on error
        all_notifications = {
            'chat_notifications': [],
            'questionnaire_reviews': [],
            'monthly_safety_reviews': [],
            'total_count': 0
        }
    
    return all_notifications


