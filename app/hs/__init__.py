from flask import Blueprint

bp = Blueprint('hs', __name__)

from app.hs import routes