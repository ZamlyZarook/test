from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
import pandas as pd
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

from app.import_module import bp


def get_company_id():
    return current_user.company_id


@bp.route("/import", methods=["GET", "POST"])
@login_required
def import_data():
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file selected", "danger")
            return redirect(request.url)

        file = request.files["file"]
        if file.filename == "":
            flash("No file selected", "danger")
            return redirect(request.url)

        if file and file.filename.endswith(".xlsx"):
            try:
                df = pd.read_excel(file)
                data_type = request.form.get("data_type")

                if data_type == "customers":
                    for _, row in df.iterrows():
                        customer = Customer(
                            name=row["name"],
                            country=row["country"],
                            address=row["address"],
                            email=row["email"],
                            telephone=row["telephone"],
                            website=row.get("website", ""),
                            company_id=get_company_id(),
                        )
                        db.session.add(customer)

                elif data_type == "departments":
                    for _, row in df.iterrows():
                        department = Department(
                            name=row["name"], company_id=get_company_id()
                        )
                        db.session.add(department)

                elif data_type == "shipment_types":
                    for _, row in df.iterrows():
                        shipment_type = ShipmentType(
                            name=row["name"], company_id=get_company_id()
                        )
                        db.session.add(shipment_type)

                elif data_type == "bl_status":
                    for _, row in df.iterrows():
                        bl_status = BLStatus(
                            name=row["name"], company_id=get_company_id()
                        )
                        db.session.add(bl_status)

                elif data_type == "freight_terms":
                    for _, row in df.iterrows():
                        freight_term = FreightTerm(
                            name=row["name"], company_id=get_company_id()
                        )
                        db.session.add(freight_term)

                elif data_type == "request_types":
                    for _, row in df.iterrows():
                        request_type = RequestType(
                            name=row["name"], company_id=get_company_id()
                        )
                        db.session.add(request_type)

                elif data_type == "document_types":
                    for _, row in df.iterrows():
                        document_type = DocumentType(
                            name=row["name"], company_id=get_company_id()
                        )
                        db.session.add(document_type)

                elif data_type == "shipping_lines":
                    for _, row in df.iterrows():
                        shipping_line = ShippingLine(
                            name=row["name"], company_id=get_company_id()
                        )
                        db.session.add(shipping_line)

                elif data_type == "countries":
                    for _, row in df.iterrows():
                        country = CountryMaster(name=row["name"], companyID=get_company_id())
                        db.session.add(country)

                elif data_type == "currencies":
                    for _, row in df.iterrows():
                        currency = CurrencyMaster(
                            name=row["name"],
                            code=row["code"],
                            company_id=get_company_id(),
                        )
                        db.session.add(currency)

                elif data_type == "terminals":
                    for _, row in df.iterrows():
                        terminal = Terminal(
                            name=row["name"], company_id=get_company_id()
                        )
                        db.session.add(terminal)

                db.session.commit()
                flash("Data imported successfully!", "success")
                return redirect(url_for("import.import_data"))

            except Exception as e:
                db.session.rollback()
                flash(f"Error importing data: {str(e)}", "danger")
                return redirect(url_for("import.import_data"))

        else:
            flash("Invalid file format. Please upload an Excel file.", "danger")
            return redirect(request.url)

    return render_template("import/import.html", title="Import Data")
