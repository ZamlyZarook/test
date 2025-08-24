from flask import Blueprint

bp = Blueprint("demurrage", __name__)

from app.demurrage import routes  # noqa
