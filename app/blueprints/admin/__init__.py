from flask import Blueprint

bp = Blueprint("admin", __name__)

# Import routes at the bottom to avoid circular imports
from app.blueprints.admin import routes  # noqa
