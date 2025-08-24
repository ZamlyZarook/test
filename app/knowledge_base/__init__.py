from flask import Blueprint
from flask import jsonify, current_app
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

kb_bp = Blueprint("knowledge_base", __name__, 
                        template_folder='templates',  
                        static_folder='static',       
                        static_url_path='/static/knowledge_base')

# Import routes to register them with the blueprint
from app.knowledge_base import routes