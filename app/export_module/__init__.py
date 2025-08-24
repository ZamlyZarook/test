from flask import Blueprint

bp = Blueprint("export", __name__)

from app.export_module import routes  # noqa
