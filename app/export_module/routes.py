from flask import (
    Blueprint,
    render_template,
    request,
    send_file,
    flash,
    redirect,
    url_for,
)
from flask_login import login_required, current_user
from app import db
import pandas as pd
from io import BytesIO
from app.models.cha import (
    Customer,
    Department,
    ShipmentType,
    BLStatus,
    FreightTerm,
    RequestType,
    DocumentType,
    ShippingLine,
    Terminal,
)
from app.models.user import CountryMaster, CurrencyMaster

from app.export_module import bp


def get_company_id():
    return current_user.company_id


@bp.route("/export", methods=["GET", "POST"])
@login_required
def export_data():
    if request.method == "POST":
        try:
            data_type = request.form.get("data_type")
            output = BytesIO()

            if data_type == "customers":
                data = Customer.query.filter_by(company_id=get_company_id()).all()
                df = pd.DataFrame(
                    [
                        {
                            "name": c.name,
                            "country": c.country,
                            "address": c.address,
                            "email": c.email,
                            "telephone": c.telephone,
                            "website": c.website,
                        }
                        for c in data
                    ]
                )

            elif data_type == "departments":
                data = Department.query.filter_by(company_id=get_company_id()).all()
                df = pd.DataFrame([{"name": d.name} for d in data])

            elif data_type == "shipment_types":
                data = ShipmentType.query.filter_by(company_id=get_company_id()).all()
                df = pd.DataFrame([{"name": st.name} for st in data])

            elif data_type == "bl_status":
                data = BLStatus.query.filter_by(company_id=get_company_id()).all()
                df = pd.DataFrame([{"name": bs.name} for bs in data])

            elif data_type == "freight_terms":
                data = FreightTerm.query.filter_by(company_id=get_company_id()).all()
                df = pd.DataFrame([{"name": ft.name} for ft in data])

            elif data_type == "request_types":
                data = RequestType.query.filter_by(company_id=get_company_id()).all()
                df = pd.DataFrame([{"name": rt.name} for rt in data])

            elif data_type == "document_types":
                data = DocumentType.query.filter_by(company_id=get_company_id()).all()
                df = pd.DataFrame([{"name": dt.name} for dt in data])

            elif data_type == "shipping_lines":
                data = ShippingLine.query.filter_by(company_id=get_company_id()).all()
                df = pd.DataFrame([{"name": sl.name} for sl in data])

            elif data_type == "countries":
                data = CountryMaster.query.filter_by(companyID=get_company_id()).all()
                df = pd.DataFrame([{"name": c.name} for c in data])

            elif data_type == "currencies":
                data = CurrencyMaster.query.filter_by(companyID=get_company_id()).all()
                df = pd.DataFrame([{"name": c.name, "code": c.code} for c in data])

            elif data_type == "terminals":
                data = Terminal.query.filter_by(company_id=get_company_id()).all()
                df = pd.DataFrame([{"name": t.name} for t in data])

            # Create Excel writer
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(
                    writer, index=False, sheet_name=data_type.replace("_", " ").title()
                )

            output.seek(0)

            return send_file(
                output,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                as_attachment=True,
                download_name=f"{data_type}.xlsx",
            )

        except Exception as e:
            flash(f"Error exporting data: {str(e)}", "danger")
            return redirect(url_for("export.export_data"))

    return render_template("export/export.html", title="Export Data")
