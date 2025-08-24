from flask import (
    Blueprint,
    render_template,
    url_for,
    flash,
    redirect,
    request,
    current_app,
    abort,
    jsonify,
    json
)
from datetime import datetime, timedelta
from app.models.user import User
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
    Runner,
    WharfProfile,
    Branch,
    ShipCategory,
    ShipCatDocument,
    Order,
    OrderItem,
    OrderDocument,
    DocumentStatus,
    ShipDocumentEntryMaster,
    ShipDocumentEntryAttachment,
    ChatThread,
    ChatMessage,
    ChatParticipant,
    ChatAttachment,
    ShipDocumentHistory,
    OrderShipment,
    ShipCatDocumentAICheck,
    ExportContainer,
    ImportContainer,
    ShipDocumentEntryDocument,
    IncomeExpense,
    ShipmentExpense, CompanyAssignment
    )
from flask_login import login_required, current_user
from app import db
from app.reports import bp
from flask import send_file, make_response
import pandas as pd
import io
import csv
from app.utils import get_sri_lanka_time

@bp.route("/daily_status")
@login_required
def daily_status():
    # Get filter parameters from request
    status1 = request.args.get('status1')
    customer_id = request.args.get('customer_id')
    branch_id = request.args.get('branch_id')
    business_type = request.args.get('business_type')
    date_range = request.args.get('date_range')
    sales_person_id = request.args.get('sales_person_id')
    cnts_sizes = request.args.get('cnts_sizes')
    shipment_type_id = request.args.get('shipment_type_id')
    
    # Get customers, branches, sales people, ports for dropdowns
    customers = Customer.query.all()
    branches = Branch.query.all()
    sales_people = User.query.filter_by(company_id=current_user.company_id).all()  # Assuming role_id 3 is for sales people
    billing_party = User.query.filter_by(company_id=current_user.company_id).all()  # Assuming role_id 3 is for sales people
    wharf_clerks = WharfProfile.query.filter_by(company_id=current_user.company_id).all()  # Assuming role_id 3 is for sales people
    cs_executives = User.query.filter_by(company_id=current_user.company_id).all()  # Assuming role_id 3 is for sales people

    
    # loading_ports = Port.query.filter_by(port_type='loading').all()
    # discharge_ports = Port.query.filter_by(port_type='discharge').all()
    
    # Build query for OrderShipment with joins to ShipDocumentEntryMaster
    # Build query for OrderShipment with joins to ShipDocumentEntryMaster, DocumentStatus, and Customer
    query = db.session.query(
        OrderShipment, ShipDocumentEntryMaster, DocumentStatus, Customer
    ).join(
        ShipDocumentEntryMaster, 
        OrderShipment.ship_doc_entry_id == ShipDocumentEntryMaster.id
    ).join(
        DocumentStatus,
        ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID
    ).join(  # NEW: Add INNER JOIN with CompanyAssignment
        CompanyAssignment,
        db.and_(
            ShipDocumentEntryMaster.company_id == CompanyAssignment.company_id,
            CompanyAssignment.assigned_company_id == current_user.company_id,
            CompanyAssignment.is_active == True
        )
    ).outerjoin(  # Using outerjoin in case some shipments don't have a customer
        Customer,
        OrderShipment.customer_id == Customer.id
    )
    
    # Filter by user's company
    query = query.filter(ShipDocumentEntryMaster.assigned_clearing_company_id == current_user.company_id)
    
    # Apply filters if provided
    if status1:
        # Map status1 values to docStatusID values
        status_map = {
            'open': 'Open',    # Assuming 1 is active status
            'new': 'New', # Assuming 2 is completed status
            'ongoing': 'Ongoing',   # Assuming 3 is pending status
            'completed': 'Completed'    # Assuming 4 is on-hold status
        }
        if status1 in status_map:
            query = query.filter(DocumentStatus.docStatusName == status_map[status1])
    
    if customer_id:
        query = query.filter(OrderShipment.customer_id == customer_id)
    
    if branch_id:
        query = query.filter(OrderShipment.branch_id == branch_id)
    
    if business_type:
        query = query.filter(OrderShipment.business_type_id == business_type)
    
    if date_range:
        # Parse date range in format "d M, Y - d M, Y"
        try:
            dates = date_range.split(' - ')
            start_date = datetime.strptime(dates[0], '%d %b, %Y')
            end_date = datetime.strptime(dates[1], '%d %b, %Y')
            # Add one day to end_date to include the entire end date
            end_date = end_date + timedelta(days=1)
            query = query.filter(OrderShipment.eta >= start_date, OrderShipment.eta < end_date)
        except (ValueError, IndexError):
            # Handle invalid date format
            pass
    
    if sales_person_id:
        query = query.filter(OrderShipment.sales_person_id == sales_person_id)
    
    # if port_of_loading:
    #     query = query.filter(OrderShipment.port_of_loading == port_of_loading)
    
    # if port_of_discharge:
    #     query = query.filter(OrderShipment.port_of_discharge == port_of_discharge)
    
    if cnts_sizes:
        # This would need a join to a container table if one exists
        # For now, assuming there's a relationship to be defined
        pass
    
    if shipment_type_id:
        query = query.filter(OrderShipment.shipment_type_id == shipment_type_id)
    
    # Paginate results
    page = request.args.get('page', 1, type=int)
    per_page = 10
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    shipments = pagination.items
    
    return render_template(
        "reports/daily_status_report.html",
        shipments=shipments,
        pagination=pagination,
        customers=customers,
        branches=branches,
        sales_people=sales_people,
        billing_party=billing_party,
        wharf_clerks=wharf_clerks,
        cs_executives=cs_executives
    )


# Add this route to your existing Flask blueprint (reports.py)

@bp.route("/api/daily_status")
@login_required
def api_daily_status():
    """API endpoint for AG Grid to fetch daily status data"""
    try:
        # Get filter parameters from request
        status1 = request.args.get('status1')
        customer_id = request.args.get('customer_id')
        branch_id = request.args.get('branch_id')
        business_type = request.args.get('business_type')
        date_range = request.args.get('date_range')
        sales_person_id = request.args.get('sales_person_id')
        cnts_sizes = request.args.get('cnts_sizes')
        shipment_type_id = request.args.get('shipment_type_id')
        
        # Build query for OrderShipment with joins
        query = db.session.query(
            OrderShipment, ShipDocumentEntryMaster, DocumentStatus, Customer
        ).join(
            ShipDocumentEntryMaster, 
            OrderShipment.ship_doc_entry_id == ShipDocumentEntryMaster.id
        ).join(
            DocumentStatus,
            ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID
        ).join(  # NEW: Add INNER JOIN with CompanyAssignment
            CompanyAssignment,
            db.and_(
                ShipDocumentEntryMaster.company_id == CompanyAssignment.company_id,
                CompanyAssignment.assigned_company_id == current_user.company_id,
                CompanyAssignment.is_active == True
            )
        ).outerjoin(
            Customer,
            OrderShipment.customer_id == Customer.id
        )
        
        # Filter by user's company
        query = query.filter(ShipDocumentEntryMaster.assigned_clearing_company_id == current_user.company_id)
        
        # Apply filters if provided
        if status1:
            status_map = {
                'open': 'Open',
                'new': 'New',
                'ongoing': 'Ongoing',
                'completed': 'Completed'
            }
            if status1 in status_map:
                query = query.filter(DocumentStatus.docStatusName == status_map[status1])
        
        if customer_id:
            query = query.filter(OrderShipment.customer_id == customer_id)
        
        if branch_id:
            query = query.filter(OrderShipment.branch_id == branch_id)
        
        if business_type:
            query = query.filter(OrderShipment.business_type_id == business_type)
        
        if date_range:
            try:
                dates = date_range.split(' - ')
                start_date = datetime.strptime(dates[0], '%d %b, %Y')
                end_date = datetime.strptime(dates[1], '%d %b, %Y')
                end_date = end_date + timedelta(days=1)
                query = query.filter(OrderShipment.eta >= start_date, OrderShipment.eta < end_date)
            except (ValueError, IndexError):
                pass
        
        if sales_person_id:
            query = query.filter(OrderShipment.sales_person_id == sales_person_id)
        
        if shipment_type_id:
            query = query.filter(OrderShipment.shipment_type_id == shipment_type_id)
        
        # Get all shipments (no pagination for AG Grid - it handles client-side pagination)
        shipments = query.all()
        
        # Get lookup data for foreign keys
        branches = {branch.id: branch.name for branch in Branch.query.all()}
        sales_people = {person.id: person.name for person in User.query.filter_by(company_id=current_user.company_id).all()}
        billing_parties = {person.id: person.name for person in User.query.filter_by(company_id=current_user.company_id).all()}
        wharf_clerks = {clerk.id: f"{clerk.first_name} {clerk.last_name}" for clerk in WharfProfile.query.filter_by(company_id=current_user.company_id).all()}
        cs_executives = {exec.id: exec.name for exec in User.query.filter_by(company_id=current_user.company_id).all()}
        
        # Format data for AG Grid
        formatted_data = []
        for shipment, doc_entry, doc_status, customer in shipments:
            # Format each field similar to your HTML template
            primary_job = f"Yes - {shipment.primary_job}" if shipment.primary_job_yn == 'Y' else "No"
            
            # Map shipment type
            shipment_type_map = {1: "Custom", 2: "BOI"}
            shipment_type = shipment_type_map.get(shipment.shipment_type_id, "N/A")
            
            # Map sub type
            sub_type_map = {1: "Tiep", 2: "Infac", 3: "Bond"}
            sub_type = sub_type_map.get(shipment.sub_type_id, "N/A")
            
            # Map customer category
            customer_category = "Direct" if shipment.customer_category_id == 1 else "N/A"
            
            # Map business type
            business_type_map = {
                1: "Sales Nomination",
                2: "Agent Nomination", 
                3: "Free hand"
            }
            business_type_text = business_type_map.get(shipment.business_type_id, "N/A")
            
            # Map job type
            job_type_map = {"1": "FCL", "2": "LCL"}
            job_type = job_type_map.get(shipment.job_type, "N/A")
            
            # Format dates safely
            def format_date(date_obj, format_str='%d-%m-%Y'):
                return date_obj.strftime(format_str) if date_obj else 'N/A'
                
            def format_datetime(datetime_obj):
                return datetime_obj.strftime('%d-%m-%Y %H:%M:%S') if datetime_obj else 'N/A'
            
            # Format on hold
            on_hold = f"Yes - {shipment.onhold_reason}" if shipment.onhold_yn == 'Y' else "No"
            
            # Create the data row with proper formatting
            row_data = {
                'id': shipment.id,
                'status': doc_status.docStatusName,
                'branch_name': branches.get(shipment.branch_id, 'N/A'),
                'import_id': shipment.import_id or doc_entry.docserial or 'N/A',
                'shipment_deadline': format_date(shipment.shipment_deadline),
                'bl_no': shipment.bl_no or 'N/A',
                'license_number': shipment.license_number or 'N/A',
                'primary_job': primary_job,
                'shipment_type': shipment_type,
                'sub_type': sub_type,
                'customer_category': customer_category,
                'business_type': business_type_text,
                'customer_name': customer.customer_name if customer else 'N/A',
                'billing_party': billing_parties.get(shipment.billing_party_id, 'N/A'),
                'clearing_agent': shipment.clearing_agent or 'N/A',
                'contact_person': shipment.contact_person or 'N/A',
                'sales_person': sales_people.get(shipment.sales_person_id, 'N/A'),
                'cs_executive': cs_executives.get(shipment.cs_executive_id, 'N/A'),
                'wharf_clerk': wharf_clerks.get(shipment.wharf_clerk_id, 'N/A'),
                'po_no': shipment.po_no or 'N/A',
                'invoice_no': shipment.invoice_no or 'N/A',
                'customer_ref_no': shipment.customer_ref_no or 'N/A',
                'customs_dti_no': shipment.customs_dti_no or 'N/A',
                'mbl_number': shipment.mbl_number or 'N/A',
                'vessel': shipment.vessel or 'N/A',
                'voyage': shipment.voyage or 'N/A',
                'eta': format_datetime(shipment.eta),
                'shipper': shipment.shipper or 'N/A',
                'port_of_loading': shipment.port_of_loading or 'N/A',
                'port_of_discharge': shipment.port_of_discharge or 'N/A',
                'job_type': job_type,
                'fcl_gate_out_date': format_date(shipment.fcl_gate_out_date),
                'pod_datetime': format_datetime(shipment.pod_datetime),
                'no_of_packages': shipment.no_of_packages or 'N/A',
                'package_type': shipment.package_type or 'N/A',
                'cbm': shipment.cbm or 'N/A',
                'gross_weight': shipment.gross_weight or 'N/A',
                'cargo_description': shipment.cargo_description or 'N/A',
                'liner': shipment.liner or 'N/A',
                'entrepot': shipment.entrepot or 'N/A',
                'job_currency': shipment.job_currency or 'N/A',
                'ex_rating_buying': shipment.ex_rating_buying or 'N/A',
                'ex_rating_selling': shipment.ex_rating_selling or 'N/A',
                'remarks': shipment.remarks or 'N/A',
                'on_hold': on_hold,
                'cleared_date': format_date(shipment.cleared_date),
                'estimated_job_closing_date': format_date(shipment.estimated_job_closing_date),
                'created_at': format_datetime(shipment.created_at),
                'updated_at': format_datetime(shipment.updated_at)
            }
            
            formatted_data.append(row_data)
        
        return jsonify({
            'success': True,
            'shipments': formatted_data,
            'total_count': len(formatted_data)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'shipments': [],
            'total_count': 0
        }), 500


@bp.route("/api/daily_status/export")
@login_required
def api_export_daily_status():
    """API endpoint to export filtered data with only selected columns"""
    try:
        # Get filter parameters
        status1 = request.args.get('status1')
        customer_id = request.args.get('customer_id')
        branch_id = request.args.get('branch_id')
        business_type = request.args.get('business_type')
        date_range = request.args.get('date_range')
        sales_person_id = request.args.get('sales_person_id')
        shipment_type_id = request.args.get('shipment_type_id')
        
        # Get selected columns (comma-separated list)
        selected_columns = request.args.get('columns', '').split(',')
        export_format = request.args.get('format', 'excel')  # excel or csv
        
        # Use the same query logic as the main API
        query = db.session.query(
            OrderShipment, ShipDocumentEntryMaster, DocumentStatus, Customer
        ).join(
            ShipDocumentEntryMaster, 
            OrderShipment.ship_doc_entry_id == ShipDocumentEntryMaster.id
        ).join(
            DocumentStatus,
            ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID
        ).outerjoin(
            Customer,
            OrderShipment.customer_id == Customer.id
        )
        
        # Apply same filters as API
        query = query.filter(ShipDocumentEntryMaster.company_id == current_user.company_id)
        
        if status1:
            status_map = {'open': 'Open', 'new': 'New', 'ongoing': 'Ongoing', 'completed': 'Completed'}
            if status1 in status_map:
                query = query.filter(DocumentStatus.docStatusName == status_map[status1])
        
        if customer_id:
            query = query.filter(OrderShipment.customer_id == customer_id)
        if branch_id:
            query = query.filter(OrderShipment.branch_id == branch_id)
        if business_type:
            query = query.filter(OrderShipment.business_type_id == business_type)
        if sales_person_id:
            query = query.filter(OrderShipment.sales_person_id == sales_person_id)
        if shipment_type_id:
            query = query.filter(OrderShipment.shipment_type_id == shipment_type_id)
        
        if date_range:
            try:
                dates = date_range.split(' - ')
                start_date = datetime.strptime(dates[0], '%d %b, %Y')
                end_date = datetime.strptime(dates[1], '%d %b, %Y') + timedelta(days=1)
                query = query.filter(OrderShipment.eta >= start_date, OrderShipment.eta < end_date)
            except (ValueError, IndexError):
                pass
        
        shipments = query.all()
        
        # Column mapping - maps field names to display names
        column_mapping = {
            'id': 'ID',
            'status': 'Status',
            'branch_name': 'Branch',
            'import_id': 'Import ID',
            'shipment_deadline': 'Shipment Deadline',
            'bl_no': 'BL No',
            'license_number': 'License Number',
            'primary_job': 'Primary Job',
            'shipment_type': 'Shipment Type',
            'sub_type': 'Sub Type',
            'customer_category': 'Customer Category',
            'business_type': 'Business Type',
            'customer_name': 'Customer',
            'billing_party': 'Billing Party',
            'clearing_agent': 'Clearing Agent',
            'contact_person': 'Contact Person',
            'sales_person': 'Sales Person',
            'cs_executive': 'CS Executive',
            'wharf_clerk': 'Wharf Clerk',
            'po_no': 'PO No',
            'invoice_no': 'Invoice No',
            'customer_ref_no': 'Customer Ref No',
            'customs_dti_no': 'Customs DTI No',
            'mbl_number': 'MBL Number',
            'vessel': 'Vessel',
            'voyage': 'Voyage',
            'eta': 'ETA',
            'shipper': 'Shipper',
            'port_of_loading': 'Port of Loading',
            'port_of_discharge': 'Port of Discharge',
            'job_type': 'Job Type',
            'fcl_gate_out_date': 'FCL Gate Out Date',
            'pod_datetime': 'POD Datetime',
            'no_of_packages': 'No of Packages',
            'package_type': 'Package Type',
            'cbm': 'CBM',
            'gross_weight': 'Gross Weight',
            'cargo_description': 'Cargo Description',
            'liner': 'Liner',
            'entrepot': 'Entrepot',
            'job_currency': 'Job Currency',
            'ex_rating_buying': 'Ex Rating Buying',
            'ex_rating_selling': 'Ex Rating Selling',
            'remarks': 'Remarks',
            'on_hold': 'On Hold',
            'cleared_date': 'Cleared Date',
            'estimated_job_closing_date': 'Est. Job Closing Date',
            'created_at': 'Created',
            'updated_at': 'Updated'
        }
        
        # Format data (reuse logic from main API)
        formatted_data = []
        for shipment, doc_entry, doc_status, customer in shipments:
            # [Same formatting logic as above - shortened for brevity]
            row_data = {
                'id': shipment.id,
                'status': doc_status.docStatusName,
                'customer_name': customer.customer_name if customer else 'N/A',
                # ... add all other fields as needed
            }
            formatted_data.append(row_data)
        
        # Filter data to only include selected columns
        if selected_columns and selected_columns[0]:  # Check if columns are specified
            filtered_data = []
            for row in formatted_data:
                filtered_row = {col: row.get(col, 'N/A') for col in selected_columns if col in row}
                filtered_data.append(filtered_row)
            
            # Create headers for selected columns only
            headers = [column_mapping.get(col, col) for col in selected_columns if col in column_mapping]
        else:
            # Export all columns if none specified
            filtered_data = formatted_data
            headers = list(column_mapping.values())
        
        current_date = get_sri_lanka_time().strftime('%d-%m-%Y')
        
        if export_format == 'csv':
            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            
            for row in filtered_data:
                writer.writerow([row.get(col, 'N/A') for col in selected_columns])
            
            csv_data = output.getvalue()
            response = make_response(csv_data)
            response.headers['Content-Disposition'] = f'attachment; filename=DSR_{current_date}.csv'
            response.headers['Content-Type'] = 'text/csv'
            return response
            
        else:  # Excel format
            # Create DataFrame with selected columns only
            df_data = []
            for row in filtered_data:
                df_data.append([row.get(col, 'N/A') for col in selected_columns])
            
            df = pd.DataFrame(df_data, columns=headers)
            output = io.BytesIO()
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Shipments', index=False)
                worksheet = writer.sheets['Shipments']
                
                # Auto-adjust column widths
                for i, col in enumerate(df.columns):
                    max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
                    worksheet.set_column(i, i, min(max_len, 50))
            
            output.seek(0)
            
            return send_file(
                output,
                as_attachment=True,
                download_name=f'DSR_{current_date}.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route("/api/daily_status/metadata")
@login_required 
def api_daily_status_metadata():
    """API endpoint to get dropdown options for filters"""
    try:
        customers = [{'id': c.id, 'name': c.customer_name} for c in Customer.query.all()]
        branches = [{'id': b.id, 'name': b.name} for b in Branch.query.all()]
        sales_people = [{'id': u.id, 'name': u.name} for u in User.query.filter_by(company_id=current_user.company_id).all()]
        
        return jsonify({
            'success': True,
            'customers': customers,
            'branches': branches,
            'sales_people': sales_people
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@bp.route('/daily_status/download/excel', methods=['GET'])
def download_daily_status_excel():
    """Download the daily status report as Excel file with only selected columns"""
    try:
        # Get selected columns (comma-separated list)
        selected_columns = request.args.get('columns', '').split(',')
        selected_columns = [col.strip() for col in selected_columns if col.strip()]
        
        if not selected_columns:
            flash("No columns selected for export", "error")
            return redirect(url_for('reports.daily_status'))
        
        # Get all the filter parameters
        status1 = request.args.get('status1', '')
        customer_id = request.args.get('customer_id', '')
        branch_id = request.args.get('branch_id', '')
        business_type = request.args.get('business_type', '')
        date_range = request.args.get('date_range', '')
        sales_person_id = request.args.get('sales_person_id', '')
        shipment_type_id = request.args.get('shipment_type_id', '')
        
        # Build query (same as API)
        query = db.session.query(
            OrderShipment, ShipDocumentEntryMaster, DocumentStatus, Customer
        ).join(
            ShipDocumentEntryMaster, 
            OrderShipment.ship_doc_entry_id == ShipDocumentEntryMaster.id
        ).join(
            DocumentStatus,
            ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID
        ).outerjoin(
            Customer,
            OrderShipment.customer_id == Customer.id
        )
        
        # Filter by user's company
        query = query.filter(ShipDocumentEntryMaster.company_id == current_user.company_id)
        
        # Apply filters (same logic as API)
        if status1:
            status_map = {
                'open': 'Open',
                'new': 'New', 
                'ongoing': 'Ongoing',
                'completed': 'Completed'
            }
            if status1 in status_map:
                query = query.filter(DocumentStatus.docStatusName == status_map[status1])
        
        if customer_id:
            query = query.filter(OrderShipment.customer_id == customer_id)
        if branch_id:
            query = query.filter(OrderShipment.branch_id == branch_id)
        if business_type:
            query = query.filter(OrderShipment.business_type_id == business_type)
        if sales_person_id:
            query = query.filter(OrderShipment.sales_person_id == sales_person_id)
        if shipment_type_id:
            query = query.filter(OrderShipment.shipment_type_id == shipment_type_id)
        
        if date_range:
            try:
                dates = date_range.split(' - ')
                start_date = datetime.strptime(dates[0], '%d %b, %Y')
                end_date = datetime.strptime(dates[1], '%d %b, %Y')
                end_date = end_date + timedelta(days=1)
                query = query.filter(OrderShipment.eta >= start_date, OrderShipment.eta < end_date)
            except (ValueError, IndexError):
                pass
        
        # Get all shipments
        shipments = query.all()
        
        # Get lookup data for foreign keys (same as API)
        branches = {branch.id: branch.name for branch in Branch.query.all()}
        sales_people = {person.id: person.name for person in User.query.filter_by(company_id=current_user.company_id).all()}
        billing_parties = {person.id: person.name for person in User.query.filter_by(company_id=current_user.company_id).all()}
        wharf_clerks = {clerk.id: f"{clerk.first_name} {clerk.last_name}" for clerk in WharfProfile.query.filter_by(company_id=current_user.company_id).all()}
        cs_executives = {exec.id: exec.name for exec in User.query.filter_by(company_id=current_user.company_id).all()}
        
        # Column mapping for headers
        column_headers = {
            'id': 'ID',
            'status': 'Status',
            'branch_name': 'Branch',
            'import_id': 'Import ID',
            'shipment_deadline': 'Shipment Deadline',
            'bl_no': 'BL No',
            'license_number': 'License Number',
            'primary_job': 'Primary Job',
            'shipment_type': 'Shipment Type',
            'sub_type': 'Sub Type',
            'customer_category': 'Customer Category',
            'business_type': 'Business Type',
            'customer_name': 'Customer',
            'billing_party': 'Billing Party',
            'clearing_agent': 'Clearing Agent',
            'contact_person': 'Contact Person',
            'sales_person': 'Sales Person',
            'cs_executive': 'CS Executive',
            'wharf_clerk': 'Wharf Clerk',
            'po_no': 'PO No',
            'invoice_no': 'Invoice No',
            'customer_ref_no': 'Customer Ref No',
            'customs_dti_no': 'Customs DTI No',
            'mbl_number': 'MBL Number',
            'vessel': 'Vessel',
            'voyage': 'Voyage',
            'eta': 'ETA',
            'shipper': 'Shipper',
            'port_of_loading': 'Port of Loading',
            'port_of_discharge': 'Port of Discharge',
            'job_type': 'Job Type',
            'fcl_gate_out_date': 'FCL Gate Out Date',
            'pod_datetime': 'POD Datetime',
            'no_of_packages': 'No of Packages',
            'package_type': 'Package Type',
            'cbm': 'CBM',
            'gross_weight': 'Gross Weight',
            'cargo_description': 'Cargo Description',
            'liner': 'Liner',
            'entrepot': 'Entrepot',
            'job_currency': 'Job Currency',
            'ex_rating_buying': 'Ex Rating Buying',
            'ex_rating_selling': 'Ex Rating Selling',
            'remarks': 'Remarks',
            'on_hold': 'On Hold',
            'cleared_date': 'Cleared Date',
            'estimated_job_closing_date': 'Est. Job Closing Date',
            'created_at': 'Created',
            'updated_at': 'Updated'
        }
        
        # Helper functions for formatting (same as API)
        def format_date(date_obj, format_str='%d-%m-%Y'):
            return date_obj.strftime(format_str) if date_obj else 'N/A'
            
        def format_datetime(datetime_obj):
            return datetime_obj.strftime('%d-%m-%Y %H:%M:%S') if datetime_obj else 'N/A'
        
        # Format data for each shipment (same logic as API)
        formatted_data = []
        for shipment, doc_entry, doc_status, customer in shipments:
            # Format each field exactly like in the API
            primary_job = f"Yes - {shipment.primary_job}" if shipment.primary_job_yn == 'Y' else "No"
            
            # Map shipment type
            shipment_type_map = {1: "Custom", 2: "BOI"}
            shipment_type = shipment_type_map.get(shipment.shipment_type_id, "N/A")
            
            # Map sub type
            sub_type_map = {1: "Tiep", 2: "Infac", 3: "Bond"}
            sub_type = sub_type_map.get(shipment.sub_type_id, "N/A")
            
            # Map customer category
            customer_category = "Direct" if shipment.customer_category_id == 1 else "N/A"
            
            # Map business type
            business_type_map = {
                1: "Sales Nomination",
                2: "Agent Nomination", 
                3: "Free hand"
            }
            business_type_text = business_type_map.get(shipment.business_type_id, "N/A")
            
            # Map job type
            job_type_map = {"1": "FCL", "2": "LCL"}
            job_type = job_type_map.get(shipment.job_type, "N/A")
            
            # Format on hold
            on_hold = f"Yes - {shipment.onhold_reason}" if shipment.onhold_yn == 'Y' else "No"
            
            # Create the complete row data (same as API)
            row_data = {
                'id': shipment.id,
                'status': doc_status.docStatusName,
                'branch_name': branches.get(shipment.branch_id, 'N/A'),
                'import_id': shipment.import_id or doc_entry.docserial or 'N/A',
                'shipment_deadline': format_date(shipment.shipment_deadline),
                'bl_no': shipment.bl_no or 'N/A',
                'license_number': shipment.license_number or 'N/A',
                'primary_job': primary_job,
                'shipment_type': shipment_type,
                'sub_type': sub_type,
                'customer_category': customer_category,
                'business_type': business_type_text,
                'customer_name': customer.customer_name if customer else 'N/A',
                'billing_party': billing_parties.get(shipment.billing_party_id, 'N/A'),
                'clearing_agent': shipment.clearing_agent or 'N/A',
                'contact_person': shipment.contact_person or 'N/A',
                'sales_person': sales_people.get(shipment.sales_person_id, 'N/A'),
                'cs_executive': cs_executives.get(shipment.cs_executive_id, 'N/A'),
                'wharf_clerk': wharf_clerks.get(shipment.wharf_clerk_id, 'N/A'),
                'po_no': shipment.po_no or 'N/A',
                'invoice_no': shipment.invoice_no or 'N/A',
                'customer_ref_no': shipment.customer_ref_no or 'N/A',
                'customs_dti_no': shipment.customs_dti_no or 'N/A',
                'mbl_number': shipment.mbl_number or 'N/A',
                'vessel': shipment.vessel or 'N/A',
                'voyage': shipment.voyage or 'N/A',
                'eta': format_datetime(shipment.eta),
                'shipper': shipment.shipper or 'N/A',
                'port_of_loading': shipment.port_of_loading or 'N/A',
                'port_of_discharge': shipment.port_of_discharge or 'N/A',
                'job_type': job_type,
                'fcl_gate_out_date': format_date(shipment.fcl_gate_out_date),
                'pod_datetime': format_datetime(shipment.pod_datetime),
                'no_of_packages': shipment.no_of_packages or 'N/A',
                'package_type': shipment.package_type or 'N/A',
                'cbm': shipment.cbm or 'N/A',
                'gross_weight': shipment.gross_weight or 'N/A',
                'cargo_description': shipment.cargo_description or 'N/A',
                'liner': shipment.liner or 'N/A',
                'entrepot': shipment.entrepot or 'N/A',
                'job_currency': shipment.job_currency or 'N/A',
                'ex_rating_buying': shipment.ex_rating_buying or 'N/A',
                'ex_rating_selling': shipment.ex_rating_selling or 'N/A',
                'remarks': shipment.remarks or 'N/A',
                'on_hold': on_hold,
                'cleared_date': format_date(shipment.cleared_date),
                'estimated_job_closing_date': format_date(shipment.estimated_job_closing_date),
                'created_at': format_datetime(shipment.created_at),
                'updated_at': format_datetime(shipment.updated_at)
            }
            
            formatted_data.append(row_data)
        
        # Filter data to only include selected columns
        filtered_data = []
        for row in formatted_data:
            filtered_row = []
            for col in selected_columns:
                filtered_row.append(row.get(col, 'N/A'))
            filtered_data.append(filtered_row)
        
        # Create headers for selected columns only
        headers = [column_headers.get(col, col) for col in selected_columns]
        
        # Create Excel file
        df = pd.DataFrame(filtered_data, columns=headers)
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Shipments', index=False)
            worksheet = writer.sheets['Shipments']
            
            # Auto-adjust column widths
            for i, col in enumerate(df.columns):
                max_len = max(
                    df[col].astype(str).map(len).max(),
                    len(str(col))
                ) + 2
                worksheet.set_column(i, i, min(max_len, 50))
        
        output.seek(0)
        current_date = get_sri_lanka_time().strftime('%d-%m-%Y')
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f'DSR_{current_date}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        flash(f"Error generating Excel: {str(e)}", "error")
        print(f"Error generating Excel: {str(e)}")
        return redirect(url_for('reports.daily_status'))


@bp.route('/daily_status/download/csv', methods=['GET'])
def download_daily_status_csv():
    """Download the daily status report as CSV file with only selected columns"""
    try:
        # Get selected columns (comma-separated list)
        selected_columns = request.args.get('columns', '').split(',')
        selected_columns = [col.strip() for col in selected_columns if col.strip()]
        
        if not selected_columns:
            flash("No columns selected for export", "error")
            return redirect(url_for('reports.daily_status'))
        
        # Get all the filter parameters
        status1 = request.args.get('status1', '')
        customer_id = request.args.get('customer_id', '')
        branch_id = request.args.get('branch_id', '')
        business_type = request.args.get('business_type', '')
        date_range = request.args.get('date_range', '')
        sales_person_id = request.args.get('sales_person_id', '')
        shipment_type_id = request.args.get('shipment_type_id', '')
        
        # Build query (same as Excel function)
        query = db.session.query(
            OrderShipment, ShipDocumentEntryMaster, DocumentStatus, Customer
        ).join(
            ShipDocumentEntryMaster, 
            OrderShipment.ship_doc_entry_id == ShipDocumentEntryMaster.id
        ).join(
            DocumentStatus,
            ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID
        ).outerjoin(
            Customer,
            OrderShipment.customer_id == Customer.id
        )
        
        # Filter by user's company
        query = query.filter(ShipDocumentEntryMaster.company_id == current_user.company_id)
        
        # Apply filters (same as Excel function)
        if status1:
            status_map = {
                'open': 'Open',
                'new': 'New', 
                'ongoing': 'Ongoing',
                'completed': 'Completed'
            }
            if status1 in status_map:
                query = query.filter(DocumentStatus.docStatusName == status_map[status1])
        
        if customer_id:
            query = query.filter(OrderShipment.customer_id == customer_id)
        if branch_id:
            query = query.filter(OrderShipment.branch_id == branch_id)
        if business_type:
            query = query.filter(OrderShipment.business_type_id == business_type)
        if sales_person_id:
            query = query.filter(OrderShipment.sales_person_id == sales_person_id)
        if shipment_type_id:
            query = query.filter(OrderShipment.shipment_type_id == shipment_type_id)
        
        if date_range:
            try:
                dates = date_range.split(' - ')
                start_date = datetime.strptime(dates[0], '%d %b, %Y')
                end_date = datetime.strptime(dates[1], '%d %b, %Y')
                end_date = end_date + timedelta(days=1)
                query = query.filter(OrderShipment.eta >= start_date, OrderShipment.eta < end_date)
            except (ValueError, IndexError):
                pass
        
        # Get all shipments
        shipments = query.all()
        
        # Get lookup data for foreign keys (same as Excel function)
        branches = {branch.id: branch.name for branch in Branch.query.all()}
        sales_people = {person.id: person.name for person in User.query.filter_by(company_id=current_user.company_id).all()}
        billing_parties = {person.id: person.name for person in User.query.filter_by(company_id=current_user.company_id).all()}
        wharf_clerks = {clerk.id: f"{clerk.first_name} {clerk.last_name}" for clerk in WharfProfile.query.filter_by(company_id=current_user.company_id).all()}
        cs_executives = {exec.id: exec.name for exec in User.query.filter_by(company_id=current_user.company_id).all()}
        
        # Column mapping for headers (same as Excel)
        column_headers = {
            'id': 'ID',
            'status': 'Status',
            'branch_name': 'Branch',
            'import_id': 'Import ID',
            'shipment_deadline': 'Shipment Deadline',
            'bl_no': 'BL No',
            'license_number': 'License Number',
            'primary_job': 'Primary Job',
            'shipment_type': 'Shipment Type',
            'sub_type': 'Sub Type',
            'customer_category': 'Customer Category',
            'business_type': 'Business Type',
            'customer_name': 'Customer',
            'billing_party': 'Billing Party',
            'clearing_agent': 'Clearing Agent',
            'contact_person': 'Contact Person',
            'sales_person': 'Sales Person',
            'cs_executive': 'CS Executive',
            'wharf_clerk': 'Wharf Clerk',
            'po_no': 'PO No',
            'invoice_no': 'Invoice No',
            'customer_ref_no': 'Customer Ref No',
            'customs_dti_no': 'Customs DTI No',
            'mbl_number': 'MBL Number',
            'vessel': 'Vessel',
            'voyage': 'Voyage',
            'eta': 'ETA',
            'shipper': 'Shipper',
            'port_of_loading': 'Port of Loading',
            'port_of_discharge': 'Port of Discharge',
            'job_type': 'Job Type',
            'fcl_gate_out_date': 'FCL Gate Out Date',
            'pod_datetime': 'POD Datetime',
            'no_of_packages': 'No of Packages',
            'package_type': 'Package Type',
            'cbm': 'CBM',
            'gross_weight': 'Gross Weight',
            'cargo_description': 'Cargo Description',
            'liner': 'Liner',
            'entrepot': 'Entrepot',
            'job_currency': 'Job Currency',
            'ex_rating_buying': 'Ex Rating Buying',
            'ex_rating_selling': 'Ex Rating Selling',
            'remarks': 'Remarks',
            'on_hold': 'On Hold',
            'cleared_date': 'Cleared Date',
            'estimated_job_closing_date': 'Est. Job Closing Date',
            'created_at': 'Created',
            'updated_at': 'Updated'
        }
        
        # Helper functions for formatting (same as Excel)
        def format_date(date_obj, format_str='%d-%m-%Y'):
            return date_obj.strftime(format_str) if date_obj else 'N/A'
            
        def format_datetime(datetime_obj):
            return datetime_obj.strftime('%d-%m-%Y %H:%M:%S') if datetime_obj else 'N/A'
        
        # Format data for each shipment (same as Excel)
        formatted_data = []
        for shipment, doc_entry, doc_status, customer in shipments:
            # Same formatting logic as Excel function
            primary_job = f"Yes - {shipment.primary_job}" if shipment.primary_job_yn == 'Y' else "No"
            
            shipment_type_map = {1: "Custom", 2: "BOI"}
            shipment_type = shipment_type_map.get(shipment.shipment_type_id, "N/A")
            
            sub_type_map = {1: "Tiep", 2: "Infac", 3: "Bond"}
            sub_type = sub_type_map.get(shipment.sub_type_id, "N/A")
            
            customer_category = "Direct" if shipment.customer_category_id == 1 else "N/A"
            
            business_type_map = {
                1: "Sales Nomination",
                2: "Agent Nomination", 
                3: "Free hand"
            }
            business_type_text = business_type_map.get(shipment.business_type_id, "N/A")
            
            job_type_map = {"1": "FCL", "2": "LCL"}
            job_type = job_type_map.get(shipment.job_type, "N/A")
            
            on_hold = f"Yes - {shipment.onhold_reason}" if shipment.onhold_yn == 'Y' else "No"
            
            # Create the complete row data (same as Excel)
            row_data = {
                'id': shipment.id,
                'status': doc_status.docStatusName,
                'branch_name': branches.get(shipment.branch_id, 'N/A'),
                'import_id': shipment.import_id or doc_entry.docserial or 'N/A',
                'shipment_deadline': format_date(shipment.shipment_deadline),
                'bl_no': shipment.bl_no or 'N/A',
                'license_number': shipment.license_number or 'N/A',
                'primary_job': primary_job,
                'shipment_type': shipment_type,
                'sub_type': sub_type,
                'customer_category': customer_category,
                'business_type': business_type_text,
                'customer_name': customer.customer_name if customer else 'N/A',
                'billing_party': billing_parties.get(shipment.billing_party_id, 'N/A'),
                'clearing_agent': shipment.clearing_agent or 'N/A',
                'contact_person': shipment.contact_person or 'N/A',
                'sales_person': sales_people.get(shipment.sales_person_id, 'N/A'),
                'cs_executive': cs_executives.get(shipment.cs_executive_id, 'N/A'),
                'wharf_clerk': wharf_clerks.get(shipment.wharf_clerk_id, 'N/A'),
                'po_no': shipment.po_no or 'N/A',
                'invoice_no': shipment.invoice_no or 'N/A',
                'customer_ref_no': shipment.customer_ref_no or 'N/A',
                'customs_dti_no': shipment.customs_dti_no or 'N/A',
                'mbl_number': shipment.mbl_number or 'N/A',
                'vessel': shipment.vessel or 'N/A',
                'voyage': shipment.voyage or 'N/A',
                'eta': format_datetime(shipment.eta),
                'shipper': shipment.shipper or 'N/A',
                'port_of_loading': shipment.port_of_loading or 'N/A',
                'port_of_discharge': shipment.port_of_discharge or 'N/A',
                'job_type': job_type,
                'fcl_gate_out_date': format_date(shipment.fcl_gate_out_date),
                'pod_datetime': format_datetime(shipment.pod_datetime),
                'no_of_packages': shipment.no_of_packages or 'N/A',
                'package_type': shipment.package_type or 'N/A',
                'cbm': shipment.cbm or 'N/A',
                'gross_weight': shipment.gross_weight or 'N/A',
                'cargo_description': shipment.cargo_description or 'N/A',
                'liner': shipment.liner or 'N/A',
                'entrepot': shipment.entrepot or 'N/A',
                'job_currency': shipment.job_currency or 'N/A',
                'ex_rating_buying': shipment.ex_rating_buying or 'N/A',
                'ex_rating_selling': shipment.ex_rating_selling or 'N/A',
                'remarks': shipment.remarks or 'N/A',
                'on_hold': on_hold,
                'cleared_date': format_date(shipment.cleared_date),
                'estimated_job_closing_date': format_date(shipment.estimated_job_closing_date),
                'created_at': format_datetime(shipment.created_at),
                'updated_at': format_datetime(shipment.updated_at)
            }
            
            formatted_data.append(row_data)
        
        # Create headers for selected columns only
        headers = [column_headers.get(col, col) for col in selected_columns]
        
        # Create CSV file
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        
        # Write data rows for selected columns only
        for row in formatted_data:
            csv_row = [row.get(col, 'N/A') for col in selected_columns]
            writer.writerow(csv_row)
        
        csv_data = output.getvalue()
        current_date = get_sri_lanka_time().strftime('%d-%m-%Y')

        response = make_response(csv_data)
        response.headers['Content-Disposition'] = f'attachment; filename=DSR_{current_date}.csv'
        response.headers['Content-Type'] = 'text/csv'
        
        return response
        
    except Exception as e:
        flash(f"Error generating CSV: {str(e)}", "error")
        return redirect(url_for('reports.daily_status'))



@bp.route('/daily_status/export_filtered', methods=['POST'])
@login_required
def export_filtered_daily_status():
    """Export filtered data from AG Grid"""
    try:
        # Get data from request
        if request.is_json:
            # If using fetch API
            data = request.get_json()
            filtered_data = data.get('filtered_data', [])
            selected_columns = data.get('columns', [])
            export_format = data.get('format', 'excel')
        else:
            # If using form submission
            filtered_data = json.loads(request.form.get('filtered_data', '[]'))
            selected_columns = request.form.get('columns', '').split(',')
            export_format = request.form.get('format', 'excel')
        
        # Clean up column list
        selected_columns = [col.strip() for col in selected_columns if col.strip()]
        
        if not selected_columns:
            return jsonify({'error': 'No columns selected for export'}), 400
        
        if not filtered_data:
            return jsonify({'error': 'No data to export'}), 400
        
        # Column mapping for headers
        column_headers = {
            'id': 'ID',
            'status': 'Status',
            'branch_name': 'Branch',
            'import_id': 'Import ID',
            'shipment_deadline': 'Shipment Deadline',
            'bl_no': 'BL No',
            'license_number': 'License Number',
            'primary_job': 'Primary Job',
            'shipment_type': 'Shipment Type',
            'sub_type': 'Sub Type',
            'customer_category': 'Customer Category',
            'business_type': 'Business Type',
            'customer_name': 'Customer',
            'billing_party': 'Billing Party',
            'clearing_agent': 'Clearing Agent',
            'contact_person': 'Contact Person',
            'sales_person': 'Sales Person',
            'cs_executive': 'CS Executive',
            'wharf_clerk': 'Wharf Clerk',
            'po_no': 'PO No',
            'invoice_no': 'Invoice No',
            'customer_ref_no': 'Customer Ref No',
            'customs_dti_no': 'Customs DTI No',
            'mbl_number': 'MBL Number',
            'vessel': 'Vessel',
            'voyage': 'Voyage',
            'eta': 'ETA',
            'shipper': 'Shipper',
            'port_of_loading': 'Port of Loading',
            'port_of_discharge': 'Port of Discharge',
            'job_type': 'Job Type',
            'fcl_gate_out_date': 'FCL Gate Out Date',
            'pod_datetime': 'POD Datetime',
            'no_of_packages': 'No of Packages',
            'package_type': 'Package Type',
            'cbm': 'CBM',
            'gross_weight': 'Gross Weight',
            'cargo_description': 'Cargo Description',
            'liner': 'Liner',
            'entrepot': 'Entrepot',
            'job_currency': 'Job Currency',
            'ex_rating_buying': 'Ex Rating Buying',
            'ex_rating_selling': 'Ex Rating Selling',
            'remarks': 'Remarks',
            'on_hold': 'On Hold',
            'cleared_date': 'Cleared Date',
            'estimated_job_closing_date': 'Est. Job Closing Date',
            'created_at': 'Created',
            'updated_at': 'Updated'
        }
        
        # Create headers for selected columns only
        headers = [column_headers.get(col, col) for col in selected_columns]
        
        # Prepare export data - filter each row to only include selected columns
        export_data = []
        for row in filtered_data:
            export_row = [row.get(col, 'N/A') for col in selected_columns]
            export_data.append(export_row)
        
        current_date = get_sri_lanka_time().strftime('%d-%m-%Y')
        
        if export_format == 'csv':
            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(export_data)
            
            csv_data = output.getvalue()
            response = make_response(csv_data)
            response.headers['Content-Disposition'] = f'attachment; filename=DSR_Filtered_{current_date}.csv'
            response.headers['Content-Type'] = 'text/csv'
            return response
            
        else:  # Excel format
            # Create DataFrame
            df = pd.DataFrame(export_data, columns=headers)
            output = io.BytesIO()
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Filtered Shipments', index=False)
                worksheet = writer.sheets['Filtered Shipments']
                
                # Auto-adjust column widths
                for i, col in enumerate(df.columns):
                    max_len = max(
                        df[col].astype(str).map(len).max() if len(df) > 0 else 0,
                        len(str(col))
                    ) + 2
                    worksheet.set_column(i, i, min(max_len, 50))
            
            output.seek(0)
            
            return send_file(
                output,
                as_attachment=True,
                download_name=f'DSR_Filtered_{current_date}.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            
    except Exception as e:
        print(f"Error in filtered export: {str(e)}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f"Error generating export: {str(e)}", "error")
            return redirect(url_for('reports.daily_status'))


# Alternative approach: Send filter state to backend (if you prefer this method)
@bp.route('/daily_status/export_with_filters', methods=['POST'])
@login_required
def export_with_ag_grid_filters():
    """Export data by applying AG Grid filter state on backend"""
    try:
        # Get AG Grid filter model and selected columns
        if request.is_json:
            data = request.get_json()
            filter_model = data.get('filter_model', {})
            selected_columns = data.get('columns', [])
            export_format = data.get('format', 'excel')
            sort_model = data.get('sort_model', [])
        else:
            filter_model = json.loads(request.form.get('filter_model', '{}'))
            selected_columns = request.form.get('columns', '').split(',')
            export_format = request.form.get('format', 'excel')
            sort_model = json.loads(request.form.get('sort_model', '[]'))
        
        # Clean up column list
        selected_columns = [col.strip() for col in selected_columns if col.strip()]
        
        if not selected_columns:
            return jsonify({'error': 'No columns selected for export'}), 400
        
        # Build base query (same as your existing API)
        query = db.session.query(
            OrderShipment, ShipDocumentEntryMaster, DocumentStatus, Customer
        ).join(
            ShipDocumentEntryMaster, 
            OrderShipment.ship_doc_entry_id == ShipDocumentEntryMaster.id
        ).join(
            DocumentStatus,
            ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID
        ).outerjoin(
            Customer,
            OrderShipment.customer_id == Customer.id
        )
        
        # Filter by user's company
        query = query.filter(ShipDocumentEntryMaster.company_id == current_user.company_id)
        
        # Apply AG Grid filters to the query
        query = apply_ag_grid_filters(query, filter_model)
        
        # Apply sorting if provided
        query = apply_ag_grid_sorting(query, sort_model)
        
        # Get all filtered shipments
        shipments = query.all()
        
        # Format data (same as your existing API)
        formatted_data = format_shipment_data(shipments)
        
        # Export the formatted data
        return export_formatted_data(formatted_data, selected_columns, export_format, 'Filtered')
        
    except Exception as e:
        print(f"Error in export with filters: {str(e)}")
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f"Error generating export: {str(e)}", "error")
            return redirect(url_for('reports.daily_status'))


def apply_ag_grid_filters(query, filter_model):
    """Apply AG Grid filters to SQLAlchemy query"""
    for field, filter_config in filter_model.items():
        filter_type = filter_config.get('filterType')
        
        if filter_type == 'text':
            # Handle text filters
            filter_value = filter_config.get('filter', '')
            filter_operator = filter_config.get('type', 'contains')
            
            if field == 'status':
                if filter_operator == 'contains':
                    query = query.filter(DocumentStatus.docStatusName.ilike(f'%{filter_value}%'))
                elif filter_operator == 'equals':
                    query = query.filter(DocumentStatus.docStatusName == filter_value)
                elif filter_operator == 'startsWith':
                    query = query.filter(DocumentStatus.docStatusName.ilike(f'{filter_value}%'))
                elif filter_operator == 'endsWith':
                    query = query.filter(DocumentStatus.docStatusName.ilike(f'%{filter_value}'))
            
            elif field == 'customer_name':
                if filter_operator == 'contains':
                    query = query.filter(Customer.customer_name.ilike(f'%{filter_value}%'))
                elif filter_operator == 'equals':
                    query = query.filter(Customer.customer_name == filter_value)
                # Add more fields as needed
            
            # Add more field mappings as needed
            
        elif filter_type == 'number':
            # Handle number filters
            filter_value = filter_config.get('filter')
            filter_operator = filter_config.get('type', 'equals')
            
            if field == 'id':
                if filter_operator == 'equals':
                    query = query.filter(OrderShipment.id == filter_value)
                elif filter_operator == 'greaterThan':
                    query = query.filter(OrderShipment.id > filter_value)
                elif filter_operator == 'lessThan':
                    query = query.filter(OrderShipment.id < filter_value)
                # Add more operators as needed
        
        elif filter_type == 'date':
            # Handle date filters
            date_from = filter_config.get('dateFrom')
            date_to = filter_config.get('dateTo')
            
            if field == 'eta' and date_from:
                start_date = datetime.strptime(date_from, '%Y-%m-%d')
                query = query.filter(OrderShipment.eta >= start_date)
                
                if date_to:
                    end_date = datetime.strptime(date_to, '%Y-%m-%d')
                    query = query.filter(OrderShipment.eta <= end_date)
    
    return query


def apply_ag_grid_sorting(query, sort_model):
    """Apply AG Grid sorting to SQLAlchemy query"""
    for sort_config in sort_model:
        field = sort_config.get('colId')
        sort_direction = sort_config.get('sort', 'asc')
        
        if field == 'id':
            if sort_direction == 'asc':
                query = query.order_by(OrderShipment.id.asc())
            else:
                query = query.order_by(OrderShipment.id.desc())
        elif field == 'status':
            if sort_direction == 'asc':
                query = query.order_by(DocumentStatus.docStatusName.asc())
            else:
                query = query.order_by(DocumentStatus.docStatusName.desc())
        elif field == 'customer_name':
            if sort_direction == 'asc':
                query = query.order_by(Customer.customer_name.asc())
            else:
                query = query.order_by(Customer.customer_name.desc())
        # Add more field mappings as needed
    
    return query


def format_shipment_data(shipments):
    """Format shipment data (extracted from your existing API logic)"""
    # Get lookup data for foreign keys
    branches = {branch.id: branch.name for branch in Branch.query.all()}
    sales_people = {person.id: person.name for person in User.query.filter_by(company_id=current_user.company_id).all()}
    billing_parties = {person.id: person.name for person in User.query.filter_by(company_id=current_user.company_id).all()}
    wharf_clerks = {clerk.id: f"{clerk.first_name} {clerk.last_name}" for clerk in WharfProfile.query.filter_by(company_id=current_user.company_id).all()}
    cs_executives = {exec.id: exec.name for exec in User.query.filter_by(company_id=current_user.company_id).all()}
    
    # Helper functions for formatting
    def format_date(date_obj, format_str='%d-%m-%Y'):
        return date_obj.strftime(format_str) if date_obj else 'N/A'
        
    def format_datetime(datetime_obj):
        return datetime_obj.strftime('%d-%m-%Y %H:%M:%S') if datetime_obj else 'N/A'
    
    # Format data for each shipment
    formatted_data = []
    for shipment, doc_entry, doc_status, customer in shipments:
        # Same formatting logic as your API
        primary_job = f"Yes - {shipment.primary_job}" if shipment.primary_job_yn == 'Y' else "No"
        
        shipment_type_map = {1: "Custom", 2: "BOI"}
        shipment_type = shipment_type_map.get(shipment.shipment_type_id, "N/A")
        
        sub_type_map = {1: "Tiep", 2: "Infac", 3: "Bond"}
        sub_type = sub_type_map.get(shipment.sub_type_id, "N/A")
        
        customer_category = "Direct" if shipment.customer_category_id == 1 else "N/A"
        
        business_type_map = {
            1: "Sales Nomination",
            2: "Agent Nomination", 
            3: "Free hand"
        }
        business_type_text = business_type_map.get(shipment.business_type_id, "N/A")
        
        job_type_map = {"1": "FCL", "2": "LCL"}
        job_type = job_type_map.get(shipment.job_type, "N/A")
        
        on_hold = f"Yes - {shipment.onhold_reason}" if shipment.onhold_yn == 'Y' else "No"
        
        # Create the complete row data
        row_data = {
            'id': shipment.id,
            'status': doc_status.docStatusName,
            'branch_name': branches.get(shipment.branch_id, 'N/A'),
            'import_id': shipment.import_id or doc_entry.docserial or 'N/A',
            'shipment_deadline': format_date(shipment.shipment_deadline),
            'bl_no': shipment.bl_no or 'N/A',
            'license_number': shipment.license_number or 'N/A',
            'primary_job': primary_job,
            'shipment_type': shipment_type,
            'sub_type': sub_type,
            'customer_category': customer_category,
            'business_type': business_type_text,
            'customer_name': customer.customer_name if customer else 'N/A',
            'billing_party': billing_parties.get(shipment.billing_party_id, 'N/A'),
            'clearing_agent': shipment.clearing_agent or 'N/A',
            'contact_person': shipment.contact_person or 'N/A',
            'sales_person': sales_people.get(shipment.sales_person_id, 'N/A'),
            'cs_executive': cs_executives.get(shipment.cs_executive_id, 'N/A'),
            'wharf_clerk': wharf_clerks.get(shipment.wharf_clerk_id, 'N/A'),
            'po_no': shipment.po_no or 'N/A',
            'invoice_no': shipment.invoice_no or 'N/A',
            'customer_ref_no': shipment.customer_ref_no or 'N/A',
            'customs_dti_no': shipment.customs_dti_no or 'N/A',
            'mbl_number': shipment.mbl_number or 'N/A',
            'vessel': shipment.vessel or 'N/A',
            'voyage': shipment.voyage or 'N/A',
            'eta': format_datetime(shipment.eta),
            'shipper': shipment.shipper or 'N/A',
            'port_of_loading': shipment.port_of_loading or 'N/A',
            'port_of_discharge': shipment.port_of_discharge or 'N/A',
            'job_type': job_type,
            'fcl_gate_out_date': format_date(shipment.fcl_gate_out_date),
            'pod_datetime': format_datetime(shipment.pod_datetime),
            'no_of_packages': shipment.no_of_packages or 'N/A',
            'package_type': shipment.package_type or 'N/A',
            'cbm': shipment.cbm or 'N/A',
            'gross_weight': shipment.gross_weight or 'N/A',
            'cargo_description': shipment.cargo_description or 'N/A',
            'liner': shipment.liner or 'N/A',
            'entrepot': shipment.entrepot or 'N/A',
            'job_currency': shipment.job_currency or 'N/A',
            'ex_rating_buying': shipment.ex_rating_buying or 'N/A',
            'ex_rating_selling': shipment.ex_rating_selling or 'N/A',
            'remarks': shipment.remarks or 'N/A',
            'on_hold': on_hold,
            'cleared_date': format_date(shipment.cleared_date),
            'estimated_job_closing_date': format_date(shipment.estimated_job_closing_date),
            'created_at': format_datetime(shipment.created_at),
            'updated_at': format_datetime(shipment.updated_at)
        }
        
        formatted_data.append(row_data)
    
    return formatted_data


def export_formatted_data(formatted_data, selected_columns, export_format, prefix=''):
    """Export formatted data to Excel or CSV"""
    # Column mapping for headers
    column_headers = {
        'id': 'ID',
        'status': 'Status',
        'branch_name': 'Branch',
        'import_id': 'Import ID',
        'shipment_deadline': 'Shipment Deadline',
        'bl_no': 'BL No',
        'license_number': 'License Number',
        'primary_job': 'Primary Job',
        'shipment_type': 'Shipment Type',
        'sub_type': 'Sub Type',
        'customer_category': 'Customer Category',
        'business_type': 'Business Type',
        'customer_name': 'Customer',
        'billing_party': 'Billing Party',
        'clearing_agent': 'Clearing Agent',
        'contact_person': 'Contact Person',
        'sales_person': 'Sales Person',
        'cs_executive': 'CS Executive',
        'wharf_clerk': 'Wharf Clerk',
        'po_no': 'PO No',
        'invoice_no': 'Invoice No',
        'customer_ref_no': 'Customer Ref No',
        'customs_dti_no': 'Customs DTI No',
        'mbl_number': 'MBL Number',
        'vessel': 'Vessel',
        'voyage': 'Voyage',
        'eta': 'ETA',
        'shipper': 'Shipper',
        'port_of_loading': 'Port of Loading',
        'port_of_discharge': 'Port of Discharge',
        'job_type': 'Job Type',
        'fcl_gate_out_date': 'FCL Gate Out Date',
        'pod_datetime': 'POD Datetime',
        'no_of_packages': 'No of Packages',
        'package_type': 'Package Type',
        'cbm': 'CBM',
        'gross_weight': 'Gross Weight',
        'cargo_description': 'Cargo Description',
        'liner': 'Liner',
        'entrepot': 'Entrepot',
        'job_currency': 'Job Currency',
        'ex_rating_buying': 'Ex Rating Buying',
        'ex_rating_selling': 'Ex Rating Selling',
        'remarks': 'Remarks',
        'on_hold': 'On Hold',
        'cleared_date': 'Cleared Date',
        'estimated_job_closing_date': 'Est. Job Closing Date',
        'created_at': 'Created',
        'updated_at': 'Updated'
    }
    
    # Create headers for selected columns only
    headers = [column_headers.get(col, col) for col in selected_columns]
    
    # Prepare export data
    export_data = []
    for row in formatted_data:
        export_row = [row.get(col, 'N/A') for col in selected_columns]
        export_data.append(export_row)
    
    current_date = get_sri_lanka_time().strftime('%d-%m-%Y')
    file_prefix = f'DSR_{prefix}_' if prefix else 'DSR_'
    
    if export_format == 'csv':
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(export_data)
        
        csv_data = output.getvalue()
        response = make_response(csv_data)
        response.headers['Content-Disposition'] = f'attachment; filename={file_prefix}{current_date}.csv'
        response.headers['Content-Type'] = 'text/csv'
        return response
        
    else:  # Excel format
        # Create DataFrame
        df = pd.DataFrame(export_data, columns=headers)
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, sheet_name='Shipments', index=False)
            worksheet = writer.sheets['Shipments']
            
            # Auto-adjust column widths
            for i, col in enumerate(df.columns):
                max_len = max(
                    df[col].astype(str).map(len).max() if len(df) > 0 else 0,
                    len(str(col))
                ) + 2
                worksheet.set_column(i, i, min(max_len, 50))
        
        output.seek(0)
        
        return send_file(
            output,
            as_attachment=True,
            download_name=f'{file_prefix}{current_date}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )






@bp.route('/api/shipments/eta')
def get_eta_data():
    try:
        # Get current user's company_id
        company_id = current_user.company_id
        print(f"Current user's company_id: {company_id}")  # 🔍 Debug

        # Query shipments with ETA dates and all necessary joins and filters
        shipments = db.session.query(
            OrderShipment,
            Customer,
            User.name.label('sales_person_name'),
            ShipDocumentEntryMaster,
            DocumentStatus
        ).join(
            ShipDocumentEntryMaster, 
            OrderShipment.ship_doc_entry_id == ShipDocumentEntryMaster.id
        ).join(
            DocumentStatus,
            ShipDocumentEntryMaster.docStatusID == DocumentStatus.docStatusID
        ).join(  # NEW: Add INNER JOIN with CompanyAssignment
            CompanyAssignment,
            db.and_(
                ShipDocumentEntryMaster.company_id == CompanyAssignment.company_id,
                CompanyAssignment.assigned_company_id == current_user.company_id,
                CompanyAssignment.is_active == True
            )
        ).join(
            Customer, 
            OrderShipment.customer_id == Customer.id,
            isouter=True
        ).join(
            User,
            OrderShipment.sales_person_id == User.id,
            isouter=True
        ).filter(
            OrderShipment.eta != None,
            OrderShipment.company_id == company_id,  # ✅ Existing filter by company_id
            ShipDocumentEntryMaster.assigned_clearing_company_id == current_user.company_id  # NEW: Clearing company filter
        ).all()

        # 🔍 Debug: Print all fetched records
        print(f"Total records fetched after filtering: {len(shipments)}")
        for idx, (shipment, customer, sales_person_name, doc_entry, doc_status) in enumerate(shipments, 1):
            print(f"Record {idx}: Shipment ID = {shipment.id}, ETA = {shipment.eta}, "
                  f"Company ID = {shipment.company_id}, Customer = {customer.customer_name if customer else 'None'}, "
                  f"Sales Person = {sales_person_name}, Doc Entry ID = {doc_entry.id}, "
                  f"Doc Status = {doc_status.docStatusName}, Assigned Clearing Company = {doc_entry.assigned_clearing_company_id}")

        result = []
        for shipment, customer, sales_person_name, doc_entry, doc_status in shipments:
            result.append({
                'id': shipment.id,
                'import_id': shipment.import_id,
                'ship_doc_entry_id': shipment.ship_doc_entry_id,
                'branch_id': shipment.branch_id,
                'shipment_deadline': shipment.shipment_deadline.isoformat() if shipment.shipment_deadline else None,
                'bl_no': shipment.bl_no,
                'vessel': shipment.vessel,
                'voyage': shipment.voyage,
                'eta': shipment.eta.isoformat() if shipment.eta else None,
                'port_of_loading': shipment.port_of_loading,
                'port_of_discharge': shipment.port_of_discharge,
                'customer_id': shipment.customer_id,
                'customer_name': customer.customer_name if customer else None,
                'customer_short_name': customer.short_name if customer else None,
                'sales_person_id': shipment.sales_person_id,
                'sales_person_name': sales_person_name,
                'cargo_description': shipment.cargo_description,
                'remarks': shipment.remarks,
                'po_no': shipment.po_no,
                'invoice_no': shipment.invoice_no,
                # NEW: Add document entry and status information
                'doc_serial': doc_entry.docserial,
                'doc_status': doc_status.docStatusName,
                'doc_status_id': doc_status.docStatusID,
                'assigned_clearing_company_id': doc_entry.assigned_clearing_company_id,
                'doc_company_id': doc_entry.company_id,
                'date_created': doc_entry.dateCreated.isoformat() if doc_entry.dateCreated else None,
                'deadline_date': doc_entry.dealineDate.isoformat() if doc_entry.dealineDate else None
            })

        return jsonify(result)
    except Exception as e:
        print(f"Error occurred: {str(e)}")  # 🔍 Debug: Print the error
        return jsonify({'error': "An Error Occured"}), 500

@bp.route('/eta_calendar')
def eta_calendar():
    return render_template('reports/apps-calendar.html')
