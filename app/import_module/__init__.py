from flask import Blueprint

bp = Blueprint("import", __name__)

from app.import_module import routes  # noqa
