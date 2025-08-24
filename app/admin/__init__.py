from flask import Blueprint

bp = Blueprint("admin_panel", __name__)

from app.admin import routes
