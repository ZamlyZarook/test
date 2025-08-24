from flask import render_template, redirect, url_for
from flask_login import current_user
from app import db
from app.models import User
import logging
import os
from app.models.raffle import RaffleScheme, RaffleDraw, RaffleEntry

logger = logging.getLogger(__name__)






@app.route("/debug-template")
def debug_template():
    template_list = []
    for root, dirs, files in os.walk("app/templates"):
        for file in files:
            if file.endswith(".html"):
                template_list.append(os.path.join(root, file))
    return {"templates": template_list}
