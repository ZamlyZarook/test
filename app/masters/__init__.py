from flask import Blueprint

bp = Blueprint("masters", __name__)

from app.masters import routes  # noqa
