from flask import Blueprint

bp = Blueprint("po", __name__)

from app.po import routes  # noqa
