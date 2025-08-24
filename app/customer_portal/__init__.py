from flask import Blueprint

bp = Blueprint("customer_portal", __name__)

from app.customer_portal import routes  # noqa
