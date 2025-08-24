from flask import render_template
from flask_login import login_required
from app.clearing import bp


@bp.route("/")
@login_required
def index():
    """Main clearing dashboard."""
    return render_template("clearing/index.html", title="Clearing Dashboard")


@bp.route("/sea-import")
@login_required
def sea_import():
    """SEA Import listing page."""
    return render_template("clearing/sea_import.html", title="SEA Import")


@bp.route("/sea-export")
@login_required
def sea_export():
    """SEA Export listing page."""
    return render_template("clearing/sea_export.html", title="SEA Export")


@bp.route("/air-import")
@login_required
def air_import():
    """AIR Import listing page."""
    return render_template("clearing/air_import.html", title="AIR Import")


@bp.route("/air-export")
@login_required
def air_export():
    """AIR Export listing page."""
    return render_template("clearing/air_export.html", title="AIR Export")


@bp.route("/transhipment")
@login_required
def transhipment():
    """Transhipment listing page."""
    return render_template("clearing/transhipment.html", title="Transhipment")
