from flask import Flask
from config import Config
from app.extensions import db, migrate, login_manager, flask_admin, mail
import os
from flask import redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit
from app.demurrage_scheduler import daily_demurrage_check



def setup_scheduler(app):
    # Create the scheduler
    scheduler = BackgroundScheduler()
    
    # Function to call the validation endpoint
    def call_validation_endpoint():
        """
        Background scheduler task that validates pending documents and sends emails.
        
        Improvements:
        1. Now handles all validation statuses correctly
        2. Prevents duplicate emails 
        3. Better tracking and logging
        """
        with app.app_context():
            # Import necessary functions
            from app.models.cha import ShipDocumentEntryAttachment, ShipDocumentEntryMaster
            from app.customer_portal.routes import process_document_validation, send_document_validation_results_email
            
            try:
                # Get all documents that need validation (ai_validated = 0)
                pending_documents = ShipDocumentEntryAttachment.query.filter_by(ai_validated=0).all()
                
                print(f"Found {len(pending_documents)} pending documents for validation")
                
                if not pending_documents:
                    print("No pending documents found")
                    return
                
                validated_count = 0
                
                # Track which entries have documents that were validated
                # We'll use this to determine which entries need email notifications
                entries_to_notify = set()
                
                for document in pending_documents:
                    print(f"\nProcessing document ID: {document.id}, Description: {document.description}")
                    
                    # Process document validation
                    result = process_document_validation(document)
                    
                    # If document was successfully validated with any status, add to notification list
                    if result.get("success", False):
                        validated_count += 1
                        
                        # Track this entry for notification if we have customer info
                        if document.shipDocEntryMasterID and document.customer_id:
                            entries_to_notify.add((document.shipDocEntryMasterID, document.customer_id))
                
                # Now handle email notifications - ONE email per entry
                emails_sent = 0
                
                for entry_id, customer_id in entries_to_notify:
                    # Get entry info
                    entry = ShipDocumentEntryMaster.query.get(entry_id)
                    if not entry:
                        continue
                    
                    # Check if all documents in this entry have been validated
                    total_docs = ShipDocumentEntryAttachment.query.filter_by(
                        shipDocEntryMasterID=entry_id
                    ).count()
                    
                    validated_docs = ShipDocumentEntryAttachment.query.filter(
                        ShipDocumentEntryAttachment.shipDocEntryMasterID==entry_id,
                        ShipDocumentEntryAttachment.ai_validated!=0  # Any non-pending status
                    ).count()
                    
                    # Only send email if all documents have been validated
                    if validated_docs == total_docs:
                        # Send email notification with all document results
                        if send_document_validation_results_email(customer_id, entry_id):
                            emails_sent += 1
                
                print(f"BATCH VALIDATION COMPLETED: {validated_count} of {len(pending_documents)} documents validated")
                print(f"Email notifications sent for {emails_sent} entries")
                
            except Exception as e:
                print(f"ERROR in scheduled task: {str(e)}")
                import traceback
                traceback.print_exc()


    # Add the job to the scheduler - runs every 5 minutes
    scheduler.add_job(func=call_validation_endpoint, trigger="interval", minutes=5)
    
    # Start the scheduler
    scheduler.start()
    
    # Shut down the scheduler when exiting the app
    atexit.register(lambda: scheduler.shutdown())

def setup_daily_scheduler(app):
    """
    Setup the daily scheduler for demurrage checks
    """
    scheduler = BackgroundScheduler()
    
    # Schedule the demurrage check to run daily at 12:01 AM Sri Lanka time
    # Sri Lanka is UTC+5:30, so 12:01 AM Sri Lanka = 6:31 PM UTC (previous day)
    scheduler.add_job(
        func=daily_demurrage_check,
        trigger=CronTrigger(
            hour=18,      # 6 PM UTC
            minute=31,    # 31 minutes
            second=0      # 0 seconds
        ),
        id='daily_demurrage_check',
        name='Daily Demurrage Check',
        replace_existing=True,
        max_instances=1  # Prevent multiple instances running simultaneously
    )
    
    # Start the scheduler
    scheduler.start()
    print("Daily demurrage scheduler started - will run at 12:01 AM Sri Lanka time daily")
    
    # Shut down scheduler when Flask app shuts down
    atexit.register(lambda: scheduler.shutdown())
    
    return scheduler

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Get the absolute path to the instance folder
    instance_path = os.path.join(app.root_path, "instance")
    # Create instance folder if it doesn't exist
    if not os.path.exists(instance_path):
        os.makedirs(instance_path)

    # Initialize extensions with app
    
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    flask_admin.init_app(app)
    mail.init_app(app)


    # Register blueprints

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin_panel")

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    from app.super_admin import super_admin_bp as super_admin_bp
    app.register_blueprint(super_admin_bp, url_prefix="/super_admin")

    from app.chat.routes import chat_bp as chat_bp
    app.register_blueprint(chat_bp, url_prefix="/chat")

    from app.clearing import bp as clearing_bp
    app.register_blueprint(clearing_bp, url_prefix="/clearing")

    from app.customer_portal import bp as customer_portal_bp
    app.register_blueprint(customer_portal_bp, url_prefix="/customer_portal")

    from app.export_module import bp as export_module_bp
    app.register_blueprint(export_module_bp, url_prefix="/export_module")

    from app.import_module import bp as import_module_bp
    app.register_blueprint(import_module_bp, url_prefix="/import_module")

    from app.main import bp as main_bp
    app.register_blueprint(main_bp, url_prefix="/main")

    from app.masters import bp as masters_bp
    app.register_blueprint(masters_bp, url_prefix="/masters")

    from app.reports import bp as reports_bp
    app.register_blueprint(reports_bp, url_prefix="/reports")

    from app.tasks import tasks_bp as tasks_bp
    app.register_blueprint(tasks_bp, url_prefix="/tasks")

    from app.po import bp as po_bp
    app.register_blueprint(po_bp, url_prefix="/purchase_orders")

    from app.hs import bp as hs_bp
    app.register_blueprint(hs_bp, url_prefix="/hs")

    from app.user import bp as user_bp
    app.register_blueprint(user_bp, url_prefix="/user")

    from app.dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")

    from app.demurrage import bp as demurrage_bp
    app.register_blueprint(demurrage_bp, url_prefix="/demurrage")

    from app.knowledge_base import kb_bp as knowledge_base_bp
    app.register_blueprint(knowledge_base_bp, url_prefix="/knowledge_base")

    # Register CLI commands
    from app.commands import create_admin

    app.cli.add_command(create_admin)

    @app.context_processor
    def utility_processor():
        from .utils_roles import get_menu_tree
        return {
            'get_menu_tree': get_menu_tree
        }
    
    @app.context_processor
    def notifications_processor():
        """Make notifications available globally in templates"""
        from flask_login import current_user
        from .utils_roles import get_all_notifications
        
        print(f"\n=== NOTIFICATIONS CONTEXT PROCESSOR ===")
        print(f"Current user authenticated: {current_user.is_authenticated}")
        
        if current_user.is_authenticated:
            print(f"User ID: {current_user.id}, Username: {current_user.username}")
            try:
                notifications = get_all_notifications(current_user.id)
                print(f"Context processor - Total notifications: {notifications['total_count']}")
                print("=== END NOTIFICATIONS CONTEXT PROCESSOR ===\n")
                return {'notifications': notifications}
            except Exception as e:
                print(f"ERROR in notifications context processor: {str(e)}")
                import traceback
                print(f"Full traceback: {traceback.format_exc()}")
                # Return empty notifications structure
                empty_notifications = {
                    'chat_notifications': [],
                    'questionnaire_reviews': [],
                    'monthly_safety_reviews': [],
                    'total_count': 0
                }
                print("=== END NOTIFICATIONS CONTEXT PROCESSOR (ERROR) ===\n")
                return {'notifications': empty_notifications}
        else:
            print("User not authenticated, returning empty notifications")
            # Return empty notifications for non-authenticated users
            empty_notifications = {
                'chat_notifications': [],
                'questionnaire_reviews': [],
                'monthly_safety_reviews': [],
                'total_count': 0
            }
            print("=== END NOTIFICATIONS CONTEXT PROCESSOR (NOT AUTH) ===\n")
            return {'notifications': empty_notifications}
    
    @app.route("/")
    def root():
        return redirect(url_for("auth.landing"))
    
    setup_scheduler(app)

    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        # This prevents the scheduler from running twice in debug mode
        setup_daily_scheduler(app)

    return app



# Create the app instance
app = create_app()

# Move this import to the bottom to avoid circular imports
from app import models
