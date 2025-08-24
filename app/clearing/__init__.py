from flask import Blueprint

bp = Blueprint("clearing", __name__)

from app.clearing import routes  # noqa
