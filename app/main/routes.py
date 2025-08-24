from flask import Blueprint, render_template, redirect, url_for, abort
from flask_login import current_user
from app.models.user import User
from app import db
from app.models.cha import (
    ShipDocumentEntryMaster,
    ShipmentType,
    DocumentStatus,
    ShipCategory,
    Customer,
    db,
    ShipCatDocument,
    ShipDocumentEntryAttachment,
    ChatThread,
    ChatMessage,
    ShipDocumentHistory, CompanyAssignment
)
from app.main import bp


# @bp.route("/")
# def index():
#     if not current_user.is_authenticated:
#         return redirect(url_for("auth.login"))
#     user_count = User.query.count()
#     return render_template("main/index.html", title="Dashboard", user_count=user_count)



@bp.route("/")
def index():
    print("==> Accessed Company Dashboard Index Page")
    print(f"User ID: {current_user.id}, Username: {current_user.name}, Company ID: {current_user.company_id}")

    # Add redirection for base_user role to assigned orders page
    if current_user.role == "base_user":
        print("==> Redirecting base_user to assigned orders page")
        return redirect(url_for("masters.assigned_orders"))

    company_id = current_user.company_id
    if not company_id:
        print("!! No company ID found for the current user.")
        return redirect(url_for("main.index"))

    from sqlalchemy import not_

    entries = (
        ShipDocumentEntryMaster.query.join(
            CompanyAssignment,
            ShipDocumentEntryMaster.company_id == CompanyAssignment.company_id
        )
        .filter(
            ShipDocumentEntryMaster.assigned_clearing_company_id == company_id,  # Existing filter
            ShipDocumentEntryMaster.docLevel != 0,  # Existing filter
            CompanyAssignment.assigned_company_id == company_id,  # New filter
            CompanyAssignment.is_active == True  # New filter
        )
        .all()
    )
    print(f"Total Shipment Entries Found for Company: {len(entries)}")

    doc_statuses = {
        status.docStatusID: status.docStatusName
        for status in DocumentStatus.query.all()
    }

    # Get shipment types for the current company
    company_shipment_types = ShipmentType.query.filter_by(
        company_id=company_id,
        is_active=True
    ).all()
    
    print(f"Found {len(company_shipment_types)} active shipment types for company")

    # Initialize shipment types dictionary dynamically
    shipment_types = {shipment_type.shipment_name: 0 for shipment_type in company_shipment_types}
    
    # Create a mapping for shipment type IDs to names for faster lookup
    shipment_type_mapping = {
        shipment_type.id: shipment_type.shipment_name 
        for shipment_type in company_shipment_types
    }

    new_shipments = ongoing_shipments = completed_shipments = 0
    recent_activities = []

    for entry in entries:
        status_name = doc_statuses.get(entry.docStatusID, "").lower()
        if "new" in status_name or "pending" in status_name:
            new_shipments += 1
        elif "complete" in status_name or "done" in status_name:
            completed_shipments += 1
        else:
            ongoing_shipments += 1

        # Use the mapping to get shipment type name by ID
        if hasattr(entry, 'shipment_type_id') and entry.shipment_type_id in shipment_type_mapping:
            shipment_type_name = shipment_type_mapping[entry.shipment_type_id]
            if shipment_type_name in shipment_types:
                shipment_types[shipment_type_name] += 1
        elif hasattr(entry, 'shipment_type') and entry.shipment_type:
            # Fallback to relationship if it exists
            shipment_type_name = entry.shipment_type.shipment_name
            if shipment_type_name in shipment_types:
                shipment_types[shipment_type_name] += 1

        recent_activities.append({
            "user": entry.user.name,
            "action": "created new shipment",
            "reference": entry.docserial,
            "timestamp": entry.dateCreated,
        })

    print(f"New: {new_shipments}, Ongoing: {ongoing_shipments}, Completed: {completed_shipments}")
    print(f"Shipment type breakdown: {shipment_types}")

    chat_activities = (
        ChatMessage.query.join(ChatThread)
        .join(ShipDocumentEntryMaster, ShipDocumentEntryMaster.id == ChatThread.reference_id)
        .join(
            CompanyAssignment,
            ShipDocumentEntryMaster.company_id == CompanyAssignment.company_id
        )
        .filter(
            ChatThread.module_name == "sea_import",
            ShipDocumentEntryMaster.assigned_clearing_company_id == company_id,  # Existing filter
            CompanyAssignment.assigned_company_id == company_id,  # New filter
            CompanyAssignment.is_active == True  # New filter
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(5)
        .all()
    )

    print(f"Recent chat messages found: {len(chat_activities)}")

    pending_replies = (
        ChatMessage.query.join(ChatThread)
        .join(ShipDocumentEntryMaster, ShipDocumentEntryMaster.id == ChatThread.reference_id)
        .join(
            CompanyAssignment,
            ShipDocumentEntryMaster.company_id == CompanyAssignment.company_id
        )
        .filter(
            ChatThread.module_name == "sea_import",
            ShipDocumentEntryMaster.assigned_clearing_company_id == company_id,  # Existing filter
            ChatMessage.sender_id != current_user.id,
            ChatMessage.is_read == False,
            CompanyAssignment.assigned_company_id == company_id,  # New filter
            CompanyAssignment.is_active == True  # New filter
        )
        .order_by(ChatMessage.created_at.desc())
        .all()
    )
    print(f"Pending chat replies found: {len(pending_replies)}")

    recent_chats = []
    for msg in chat_activities:
        entry = ShipDocumentEntryMaster.query.get(msg.thread.reference_id)
        if entry:
            recent_chats.append({
                "user": msg.sender.name,
                "message": (msg.message[:100] + "...") if len(msg.message) > 100 else msg.message,
                "timestamp": msg.created_at,
                "entry_id": entry.id,
                "doc_serial": entry.docserial,
            })

    pending_chat_list = []
    for msg in pending_replies:
        entry = ShipDocumentEntryMaster.query.get(msg.thread.reference_id)
        if entry:
            pending_chat_list.append({
                "user": msg.sender.name,
                "message": (msg.message[:100] + "...") if len(msg.message) > 100 else msg.message,
                "timestamp": msg.created_at,
                "entry_id": entry.id,
                "doc_serial": entry.docserial,
            })

    recent_activities.sort(key=lambda x: x["timestamp"], reverse=True)
    recent_activities = recent_activities[:5]

    statistics = {
        "total_shipments": len(entries),
        "new_shipments": new_shipments,
        "ongoing_shipments": ongoing_shipments,
        "completed_shipments": completed_shipments,
        "shipment_types": shipment_types,
        "recent_activities": recent_activities,
        "recent_chats": recent_chats,
        "pending_replies": pending_chat_list,
    }

    print("==> Rendering Company Dashboard with statistics")
    return render_template(
        "main/index.html",
        title="Company Dashboard",
        statistics=statistics,
    )

@bp.route("/about")
def about():
    return render_template("main/about.html", title="About")


@bp.route("/contact")
def contact():
    return render_template("main/contact.html", title="Contact")


@bp.route("/error")
def error():
    abort(500)
