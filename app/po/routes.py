# po.py - Updated Blueprint for PO Dashboard with Enhanced Pagination

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app, abort
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from app.po import bp
from app import db
import pandas as pd
import openpyxl
from werkzeug.utils import secure_filename
import os
from decimal import Decimal, InvalidOperation
from app.models.po import POHeader, PODetail, POSupplier, POMaterial, POOrderUnit, ShipmentItem
from app.models.cha import OrderShipment, ShipDocumentEntryDocument, ShipDocumentEntryMaster, ShipCatDocument, ShipDocumentEntryAttachment
from sqlalchemy import func, or_
from botocore.exceptions import ClientError
from app.utils_cha.s3_utils import upload_file_to_s3, get_s3_url, serve_s3_file

@bp.route('/purchase_orders', methods=['GET'])
@login_required
def purchase_orders():
    """PO Dashboard - List all purchase orders with status, materials, and shipment documents"""
    
    # Get filter parameters with proper defaults
    search = request.args.get('search', '', type=str)
    status = request.args.get('status', '', type=str)
    per_page = request.args.get('per_page', 10, type=int)
    page = request.args.get('page', 1, type=int)
    
    # Validate per_page values
    valid_per_page = [5, 10, 25, 50]
    if per_page not in valid_per_page:
        per_page = 10
    
    # Base query with aggregated status information
    query = db.session.query(
        POHeader,
        func.sum(PODetail.order_quantity).label('total_quantity'),
        func.sum(PODetail.quantity_received).label('total_received'),
        func.sum(PODetail.quantity_pending).label('total_pending')
    ).join(
        PODetail, POHeader.id == PODetail.po_header_id
    )

    # Apply role-based filter
    if current_user.role == 'customer':
        query = query.filter(POHeader.company_id == current_user.company_id)
    else:
        query = query.filter(POHeader.created_by == current_user.id)

    # Group by POHeader
    query = query.group_by(POHeader.id)

    # Apply search filter
    if search:
        query = query.filter(
            db.or_(
                POHeader.po_number.contains(search),
                POHeader.sysdocnum.contains(search),
                POHeader.supplier.has(POSupplier.supplier_name.contains(search))
            )
        )
    
    # Apply status filter
    if status:
        if status == 'pending':
            query = query.having(func.sum(PODetail.quantity_received) == 0)
        elif status == 'partial':
            query = query.having(
                db.and_(
                    func.sum(PODetail.quantity_received) > 0,
                    func.sum(PODetail.quantity_received) < func.sum(PODetail.order_quantity)
                )
            )
        elif status == 'completed':
            query = query.having(func.sum(PODetail.quantity_received) >= func.sum(PODetail.order_quantity))
    
    # Order by creation date (newest first)
    query = query.order_by(POHeader.id.asc())
    
    # ===== FIX: Calculate summary stats from ALL results (before pagination) =====
    all_results = query.all()
    total_count = len(all_results)
    
    # Calculate status counts for summary
    summary_stats = {
        'total_orders': total_count,
        'pending_orders': 0,
        'partial_orders': 0,
        'completed_orders': 0
    }
    
    for po_header, total_qty, total_received, total_pending in all_results:
        if total_received == 0:
            summary_stats['pending_orders'] += 1
        elif total_received > 0 and total_received < total_qty:
            summary_stats['partial_orders'] += 1
        elif total_received >= total_qty:
            summary_stats['completed_orders'] += 1
    
    # Calculate pagination
    total_pages = (total_count - 1) // per_page + 1 if total_count > 0 else 1
    
    # Ensure page is within valid range
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages
    
    # Calculate start and end indices for display
    start_index = (page - 1) * per_page + 1
    end_index = min(page * per_page, total_count)
    
    # Execute query with pagination (get only the page results)
    results = query.offset((page - 1) * per_page).limit(per_page).all()
    
    # Prepare PO data with status, materials, and shipment document info
    po_data = []
    for po_header, total_qty, total_received, total_pending in results:
        # Calculate status
        status_info = calculate_po_status(total_qty, total_received)
        
        # Get ALL materials for this PO (no limit)
        all_materials = PODetail.query.filter_by(
            po_header_id=po_header.id
        ).order_by(PODetail.item_number).all()
        
        # Get shipment information for this PO
        shipment_info = get_po_shipment_info(po_header.id)
        
        po_data.append({
            'po_header': po_header,
            'total_quantity': total_qty or 0,
            'total_received': total_received or 0,
            'total_pending': total_pending or 0,
            'status': status_info['status'],
            'status_class': status_info['class'],
            'status_icon': status_info['icon'],
            'all_materials': all_materials,
            'shipment_info': shipment_info
        })
    
    # Create enhanced pagination info
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total_count,
        'pages': total_pages,
        'start_index': start_index if total_count > 0 else 0,
        'end_index': end_index if total_count > 0 else 0
    }
    
    return render_template('po/purchase_orders.html', 
                         po_data=po_data,
                         pagination=pagination,
                         summary_stats=summary_stats)  # NEW: Pass summary stats

def get_po_shipment_info(po_header_id):
    """Get shipment document information for a PO - Returns JSON serializable data"""
    try:
        # Find shipment items connected to this PO
        shipment_items = ShipmentItem.query.filter_by(
            po_header_id=po_header_id
        ).first()  # Get the first shipment connected to this PO
        
        if not shipment_items:
            return {
                'has_shipment': False,
                'message': 'Not Assigned'
            }
        
        # Get the shipment entry
        shipment_entry = ShipDocumentEntryMaster.query.get(shipment_items.shipment_id)
        
        if not shipment_entry:
            return {
                'has_shipment': False,
                'message': 'Shipment Not Found'
            }
        
        # Get required documents for this shipment - Convert to serializable data
        required_documents_query = ShipCatDocument.query.filter_by(
            shipCatid=shipment_entry.shipCategory,
            shipmentTypeid=shipment_entry.shipTypeid
        ).all()
        
        # Get uploaded documents for this shipment
        uploaded_documents = ShipDocumentEntryAttachment.query.filter_by(
            shipDocEntryMasterID=shipment_entry.id
        ).all()
        
        # Count required vs uploaded
        total_required = len([doc for doc in required_documents_query if doc.isMandatory])
        total_uploaded = len(uploaded_documents)
        approved_docs = len([doc for doc in uploaded_documents if doc.docAccepted == 'accepted'])
        rejected_docs = len([doc for doc in uploaded_documents if doc.docAccepted == 'rejected'])
        
        # Convert required documents to serializable format
        required_documents_data = []
        for doc in required_documents_query:
            required_documents_data.append({
                'id': doc.id,
                'description': doc.description,
                'isMandatory': doc.isMandatory,
                'sample_file_path': doc.sample_file_path
            })
        
        # Convert uploaded documents to serializable format
        uploaded_documents_data = []
        for doc in uploaded_documents:
            uploaded_documents_data.append({
                'id': doc.id,
                'description': doc.description,
                'attachement_path': doc.attachement_path,
                'docAccepted': doc.docAccepted,
                'docAccepteComments': doc.docAccepteComments,
                'docAccepteDate': doc.docAccepteDate.isoformat() if doc.docAccepteDate else None,
                'note': doc.note,
                'expiry_date': doc.expiry_date.isoformat() if doc.expiry_date else None,
                'ai_validated': doc.ai_validated if hasattr(doc, 'ai_validated') else None
            })
        
        return {
            'has_shipment': True,
            'shipment_id': shipment_entry.id,
            'shipment_job_no': shipment_entry.docserial,
            'ship_category_id': shipment_entry.shipCategory,
            'shipment_type_id': shipment_entry.shipTypeid,
            'total_required': total_required,
            'total_uploaded': total_uploaded,
            'approved_docs': approved_docs,
            'rejected_docs': rejected_docs,
            'required_documents': required_documents_data,  # Now serializable
            'uploaded_documents': uploaded_documents_data   # Now serializable
        }
        
    except Exception as e:
        print(f"Error getting shipment info for PO {po_header_id}: {str(e)}")
        return {
            'has_shipment': False,
            'message': 'Error Loading'
        }
    

# Add this route to your po.py blueprint

@bp.route('/get-po-info/<int:po_id>')
@login_required
def get_po_info(po_id):
    """Get PO information for document modal"""
    try:
        # Get PO header with supplier info
        po_header = POHeader.query.filter_by(id=po_id).first()
        
        if not po_header:
            return jsonify({'success': False, 'message': 'PO not found'}), 404
        
        # Check authorization
        if current_user.role == 'customer':
            if po_header.company_id != current_user.company_id:
                return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        else:
            if po_header.created_by != current_user.id:
                return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Get shipment info
        shipment_items = ShipmentItem.query.filter_by(po_header_id=po_id).first()
        shipment_job_no = None
        
        if shipment_items:
            shipment_entry = ShipDocumentEntryMaster.query.get(shipment_items.shipment_id)
            if shipment_entry:
                shipment_job_no = shipment_entry.docserial
        
        return jsonify({
            'success': True,
            'po_number': po_header.po_number,
            'sysdocnum': po_header.sysdocnum,
            'supplier_name': po_header.supplier.supplier_name if po_header.supplier else 'N/A',
            'po_date': po_header.po_date.isoformat() if po_header.po_date else None,
            'total_value': float(po_header.total_value) if po_header.total_value else 0,
            'currency': po_header.currency,
            'shipment_job_no': shipment_job_no
        })
        
    except Exception as e:
        print(f"Error getting PO info: {str(e)}")
        return jsonify({'success': False, 'message': 'Error retrieving PO information'}), 500
    
    
def calculate_po_status(total_quantity, total_received):
    """Calculate PO status based on quantities"""
    
    if not total_quantity or total_quantity == 0:
        return {
            'status': 'No Items',
            'class': 'secondary',
            'icon': 'ri-question-line'
        }
    
    if not total_received or total_received == 0:
        return {
            'status': 'Pending',
            'class': 'primary',
            'icon': 'ri-time-line'
        }
    elif total_received >= total_quantity:
        return {
            'status': 'Completed',
            'class': 'success',
            'icon': 'ri-check-double-line'
        }
    else:
        return {
            'status': 'Partial',
            'class': 'warning',
            'icon': 'ri-truck-line'
        }

@bp.route('/upload', methods=['POST'])
@login_required
def upload_excel():
    """Upload and process Excel file with item-level processing and completion tracking"""
    
    print(f"=== PO Excel Upload Started ===")
    print(f"User ID: {current_user.id}")
    print(f"User Role: {current_user.role}")
    print(f"Company ID: {current_user.company_id}")
    
    if 'excel_file' not in request.files:
        print("ERROR: No file selected in request")
        flash('No file selected', 'danger')
        return redirect(url_for('po.purchase_orders'))
    
    file = request.files['excel_file']
    
    if file.filename == '':
        print("ERROR: Empty filename")
        flash('No file selected', 'danger')
        return redirect(url_for('po.purchase_orders'))
    
    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        print(f"ERROR: Invalid file type: {file.filename}")
        flash('Please upload an Excel file (.xlsx or .xls)', 'danger')
        return redirect(url_for('po.purchase_orders'))
    
    try:
        print(f"Reading Excel file: {file.filename}")
        # Read Excel file
        df = pd.read_excel(file)
        print(f"Excel file read successfully. Rows: {len(df)}")
        
        # Validate required columns
        required_columns = [
            'Purchasing Document', 'Document Date', 'Supplier/Supplying Plant',
            'Material', 'Short Text', 'Order Unit', 'Order Quantity',
            'Net Price', 'Item', 'Delivery Date'
        ]
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            print(f"ERROR: Missing columns: {missing_columns}")
            flash(f'Missing required columns: {", ".join(missing_columns)}', 'danger')
            return redirect(url_for('po.purchase_orders'))
        
        print(f"All required columns found")
        
        # Process data with new item-level logic
        processed_results = process_excel_data_with_completion_tracking(df)
        
        print(f"Processing completed: {processed_results}")
        
        flash_message = f'''Purchase Orders processed Successfully'''
        
        flash(flash_message, 'success')
        print(f"=== PO Excel Upload Completed ===")
        
    except Exception as e:
        print(f"ERROR in Excel upload: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        flash(f'Error processing file: {str(e)}', 'danger')
    
    return redirect(url_for('po.purchase_orders'))


def process_excel_data_with_completion_tracking(df):
    """Process Excel data with item-level processing and completion tracking"""
    
    print(f"=== Processing Excel Data with Completion Tracking ===")
    
    # Statistics tracking
    stats = {
        'new_pos': 0,
        'new_items': 0,
        'updated_items': 0,
        'completed_items': 0,
        'completed_pos': 0
    }
    
    try:
        # Step 1: Get all current PO items for this company that are not completed
        print(f"Step 1: Getting existing incomplete PO items for company {current_user.company_id}")
        
        # Apply role-based filter for existing POs
        existing_pos_query = db.session.query(PODetail).join(POHeader)
        
        if current_user.role == 'customer':
            print(f"User role: Filtering by company_id = {current_user.company_id}")
            existing_pos_query = existing_pos_query.filter(
                POHeader.company_id == current_user.company_id,
                PODetail.is_completed == False
            )
        else:
            print(f"Non-user role: Filtering by created_by = {current_user.id}")
            existing_pos_query = existing_pos_query.filter(
                POHeader.created_by == current_user.id,
                PODetail.is_completed == False
            )
        
        existing_po_items = existing_pos_query.all()
        
        print(f"Found {len(existing_po_items)} existing incomplete PO items")
        
        # Create a set of items from current Excel for comparison
        excel_items = set()
        
        # Step 2: Process each row in the Excel file
        print(f"Step 2: Processing {len(df)} rows from Excel")
        
        # Group by PO Number first
        po_groups = df.groupby('Purchasing Document')
        
        for po_number, po_data in po_groups:
            po_number = str(po_number)
            print(f"Processing PO: {po_number} with {len(po_data)} items")
            
            # Check if PO header exists
            po_header_query = POHeader.query.filter_by(po_number=po_number)
            
            # Apply role-based filter for PO header
            if current_user.role == 'customer':
                po_header_query = po_header_query.filter_by(company_id=current_user.company_id)
            else:
                po_header_query = po_header_query.filter_by(created_by=current_user.id)
            
            existing_po_header = po_header_query.first()
            
            if not existing_po_header:
                print(f"  Creating new PO header for {po_number}")
                # Create new PO header
                po_header = create_new_po_header(po_data.iloc[0], po_number)
                stats['new_pos'] += 1
            else:
                print(f"  Using existing PO header for {po_number} (ID: {existing_po_header.id})")
                po_header = existing_po_header
                # Reset completion status as we're processing it again
                po_header.is_completed = False
            
            # Process each item in this PO
            total_value = Decimal('0.00')
            
            for _, row in po_data.iterrows():
                material_code = str(row['Material'])
                item_number = int(row['Item'])
                
                # Add to Excel items set for completion tracking
                excel_items.add((po_number, material_code, item_number))
                
                print(f"    Processing item: {material_code} (Item #{item_number})")
                
                # Check if this specific item exists
                existing_item = PODetail.query.filter_by(
                    po_header_id=po_header.id,
                    material_code=material_code,
                    item_number=item_number
                ).first()
                
                if existing_item:
                    print(f"      Found existing item - checking for updates")
                    
                    # FEATURE 3: Calculate quantity_received from order_quantity - quantity_pending
                    new_qty_pending = Decimal(str(float(row.get('Still to be delivered (qty)', row['Order Quantity']))))
                    new_qty_received = Decimal(str(float(row['Order Quantity']))) - new_qty_pending
                    
                    # FEATURE 2: Check delivery_date changes too
                    new_delivery_date = None
                    if 'Delivery Date' in row and pd.notna(row['Delivery Date']):
                        try:
                            new_delivery_date = pd.to_datetime(row['Delivery Date']).date()
                        except:
                            new_delivery_date = existing_item.delivery_date
                    
                    # Check if quantities OR delivery date have changed
                    quantities_changed = (existing_item.quantity_received != new_qty_received or 
                                        existing_item.quantity_pending != new_qty_pending)
                    
                    delivery_date_changed = (existing_item.delivery_date != new_delivery_date)
                    
                    if quantities_changed or delivery_date_changed:
                        print(f"      Updating item:")
                        
                        if quantities_changed:
                            print(f"        Quantities: Received {existing_item.quantity_received} -> {new_qty_received}, Pending {existing_item.quantity_pending} -> {new_qty_pending}")
                            existing_item.quantity_received = new_qty_received
                            existing_item.quantity_pending = new_qty_pending
                        
                        if delivery_date_changed:
                            print(f"        Delivery Date: {existing_item.delivery_date} -> {new_delivery_date}")
                            existing_item.delivery_date = new_delivery_date
                        
                        existing_item.is_completed = False  # Reset completion status
                        existing_item.updated_at = datetime.utcnow()
                        
                        stats['updated_items'] += 1
                    else:
                        print(f"      No changes in quantities or delivery date - skipping")
                    
                    # Add to total value calculation
                    total_value += existing_item.line_total
                    
                else:
                    print(f"      Creating new item")
                    # Create new item
                    new_item = create_new_po_detail(po_header, row, po_number)
                    stats['new_items'] += 1
                    total_value += new_item.line_total
            
            # Update PO header total value
            po_header.total_value = total_value
            print(f"  Updated PO {po_number} total value: {total_value}")
        
        # Step 3: Mark items as completed if they don't appear in current Excel
        print(f"Step 3: Marking items as completed")
        
        for existing_item in existing_po_items:
            item_key = (existing_item.po_number, existing_item.material_code, existing_item.item_number)
            
            if item_key not in excel_items:
                print(f"  Marking item as completed: PO {existing_item.po_number}, Material {existing_item.material_code}")
                
                # FEATURE 1: Set quantities for completed items
                existing_item.is_completed = True
                existing_item.quantity_received = existing_item.order_quantity  # Set received = ordered
                existing_item.quantity_pending = Decimal('0.00')  # Set pending = 0
                existing_item.updated_at = datetime.utcnow()
                
                print(f"    Updated quantities: Received = {existing_item.quantity_received}, Pending = 0")
                stats['completed_items'] += 1
        
        # Step 4: Check and mark PO headers as completed if all items are completed
        print(f"Step 4: Checking PO header completion status")
        
        # Get all PO headers that might need completion status update
        po_headers_to_check_query = db.session.query(POHeader).filter(POHeader.is_completed == False)
        
        # Apply role-based filter
        if current_user.role == 'customer':
            po_headers_to_check_query = po_headers_to_check_query.filter(POHeader.company_id == current_user.company_id)
        else:
            po_headers_to_check_query = po_headers_to_check_query.filter(POHeader.created_by == current_user.id)
        
        po_headers_to_check = po_headers_to_check_query.all()
        
        for po_header in po_headers_to_check:
            # Check if all items in this PO are completed
            incomplete_items = PODetail.query.filter_by(
                po_header_id=po_header.id,
                is_completed=False
            ).count()
            
            if incomplete_items == 0:
                print(f"  Marking PO header as completed: {po_header.po_number}")
                po_header.is_completed = True
                po_header.updated_at = datetime.utcnow()
                stats['completed_pos'] += 1
            else:
                print(f"  PO {po_header.po_number} still has {incomplete_items} incomplete items")
        
        # Commit all changes
        db.session.commit()
        print(f"All changes committed to database")
        
        print(f"Final statistics: {stats}")
        print(f"=== End Processing Excel Data ===")
        
        return stats
        
    except Exception as e:
        print(f"ERROR in process_excel_data_with_completion_tracking: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        db.session.rollback()
        raise e


def create_new_po_header(first_row, po_number):
    """Create a new PO header"""
    
    print(f"    Creating new PO header for {po_number}")
    
    # Extract and process supplier info
    supplier_info = str(first_row['Supplier/Supplying Plant']).strip()
    supplier_parts = supplier_info.split(None, 1)
    supplier_code = supplier_parts[0] if supplier_parts else 'UNKNOWN'
    supplier_name = supplier_parts[1] if len(supplier_parts) > 1 else supplier_info
    
    print(f"    Supplier: {supplier_code} - {supplier_name}")
    
    # Get or create supplier
    supplier = get_or_create_supplier(supplier_code, supplier_name)
    
    # Create PO Header
    po_header = POHeader(
        sysdocnum=POHeader.generate_sysdocnum(),
        po_number=po_number,
        po_date=pd.to_datetime(first_row['Document Date']).date(),
        supplier_id=supplier.id,
        company_id=current_user.company_id,
        created_by=current_user.id,
        is_completed=False  # New field
    )
    
    db.session.add(po_header)
    db.session.flush()  # Get the ID
    
    print(f"    Created PO header with ID: {po_header.id}")
    return po_header


def create_new_po_detail(po_header, row, po_number):
    """Create a new PO detail item"""
    
    material_code = str(row['Material'])
    material_name = str(row['Short Text'])
    item_number = int(row['Item'])
    
    print(f"      Creating new PO detail: {material_code} - {material_name}")
    
    # Get or create material
    material = get_or_create_material(material_code, material_name)
    
    # Get or create order unit
    order_unit_str = str(row['Order Unit'])
    order_unit = get_or_create_order_unit(order_unit_str)
    
    # Calculate quantities and prices
    try:
        order_quantity = Decimal(str(float(row['Order Quantity'])))
        net_price = Decimal(str(float(row['Net Price'])))
        line_total = order_quantity * net_price
        
        # Handle optional quantities
        quantity_received = Decimal(str(float(row.get('Quantity Received', 0))))
        quantity_pending = Decimal(str(float(row.get('Still to be delivered (qty)', order_quantity))))
        
        print(f"      Quantities: Order={order_quantity}, Received={quantity_received}, Pending={quantity_pending}")
        
    except (ValueError, InvalidOperation) as e:
        print(f"      ERROR: Invalid number in row: {e}")
        raise e
    
    # Create PO Detail
    po_detail = PODetail(
        po_header_id=po_header.id,
        po_number=po_number,
        sysdocnum=po_header.sysdocnum,
        item_number=item_number,
        material_id=material.id,
        material_code=material_code,
        material_name=material_name,
        order_unit_id=order_unit.id,
        order_unit=order_unit_str,
        order_quantity=order_quantity,
        quantity_received=quantity_received,
        quantity_pending=quantity_pending,
        delivery_date=pd.to_datetime(row['Delivery Date']).date() if pd.notna(row['Delivery Date']) else None,
        net_price=net_price,
        line_total=line_total,
        supplier_id=po_header.supplier_id,
        supplier_code=po_header.supplier.supplier_code,
        supplier_name=po_header.supplier.supplier_name,
        company_id=current_user.company_id,
        is_completed=False  # New field
    )
    
    db.session.add(po_detail)
    db.session.flush()
    
    print(f"      Created PO detail with ID: {po_detail.id}")
    return po_detail


def get_or_create_supplier(supplier_code, supplier_name):
    """Get existing supplier or create new one"""
    
    print(f"      Getting/creating supplier: {supplier_code}")
    
    supplier_query = POSupplier.query.filter_by(supplier_code=supplier_code)
    
    # Apply role-based filter for suppliers
    if current_user.role == 'customer':
        supplier_query = supplier_query.filter_by(company_id=current_user.company_id)
    else:
        # For non-user roles, we still filter by company_id for suppliers
        # as suppliers should be company-specific
        supplier_query = supplier_query.filter_by(company_id=current_user.company_id)
    
    supplier = supplier_query.first()
    
    if not supplier:
        print(f"      Creating new supplier: {supplier_code} - {supplier_name}")
        supplier = POSupplier(
            supplier_code=supplier_code,
            supplier_name=supplier_name,
            company_id=current_user.company_id
        )
        db.session.add(supplier)
        db.session.flush()
    else:
        print(f"      Using existing supplier: {supplier.supplier_name}")
    
    return supplier


def get_or_create_material(material_code, material_name):
    """Get existing material or create new one"""
    
    print(f"      Getting/creating material: {material_code}")
    
    material_query = POMaterial.query.filter_by(material_code=material_code)
    
    # Apply role-based filter for materials
    if current_user.role == 'customer':
        material_query = material_query.filter_by(company_id=current_user.company_id)
    else:
        # For non-user roles, we still filter by company_id for materials
        # as materials should be company-specific
        material_query = material_query.filter_by(company_id=current_user.company_id)
    
    material = material_query.first()
    
    if not material:
        print(f"      Creating new material: {material_code} - {material_name}")
        material = POMaterial(
            material_code=material_code,
            material_name=material_name,
            company_id=current_user.company_id
        )
        db.session.add(material)
        db.session.flush()
    else:
        print(f"      Using existing material: {material.material_name}")
    
    return material


def get_or_create_order_unit(order_unit_str):
    """Get existing order unit or create new one"""
    
    print(f"      Getting/creating order unit: {order_unit_str}")
    
    order_unit = POOrderUnit.query.filter_by(order_unit=order_unit_str).first()
    
    if not order_unit:
        print(f"      Creating new order unit: {order_unit_str}")
        order_unit = POOrderUnit(order_unit=order_unit_str)
        db.session.add(order_unit)
        db.session.flush()
    else:
        print(f"      Using existing order unit: {order_unit.order_unit}")
    
    return order_unit

@bp.route('/view/<int:po_id>')
@login_required
def view_po(po_id):
    """View purchase order details with support for multiple shipments."""
    try:
        # Step 1: Get PO Header
        print(f"### TRACE: Fetching POHeader with ID {po_id} for company_id {current_user.company_id}")
        po_header = POHeader.query.filter_by(
            id=po_id,
            company_id=current_user.company_id
        ).first_or_404()
        print(f"### TRACE: Found PO Header: po_number={po_header.po_number}, id={po_header.id}")
        
        # Step 2: Get PO Details
        print("### TRACE: Fetching PODetail items for this PO")
        po_details = PODetail.query.filter_by(
            po_header_id=po_header.id
        ).order_by(PODetail.item_number).all()
        print(f"### TRACE: Found {len(po_details)} PO detail items")

        # Step 3: Initialize shipment data containers
        shipment_info = None
        shipment_documents = []
        all_shipments = []

        # Step 4: Find ShipmentItems linked to this PO (no company filter needed)
        print("### TRACE: Finding ShipmentItems linked to this PO")
        
        try:
            # Find ShipmentItems by po_number
            shipment_items_by_po = ShipmentItem.query.filter_by(
                po_number=po_header.po_number,
                company_id=current_user.company_id
            ).all()
            print(f"### TRACE: Found {len(shipment_items_by_po)} ShipmentItems by po_number")
            
            # Find ShipmentItems by po_header_id
            shipment_items_by_header = ShipmentItem.query.filter_by(
                po_header_id=po_header.id,
                company_id=current_user.company_id
            ).all()
            print(f"### TRACE: Found {len(shipment_items_by_header)} ShipmentItems by po_header_id")
            
            # Combine and deduplicate
            all_shipment_items = list(set(shipment_items_by_po + shipment_items_by_header))
            print(f"### TRACE: Total unique ShipmentItems: {len(all_shipment_items)}")
            
            # Debug: Show the shipment_ids we found
            if all_shipment_items:
                shipment_ids = [item.shipment_id for item in all_shipment_items]
                print(f"### TRACE: ShipDocumentEntryMaster IDs from ShipmentItems: {shipment_ids}")
                
                # Show details of each ShipmentItem
                for item in all_shipment_items:
                    print(f"### TRACE: ShipmentItem - ID: {item.id}, shipment_id: {item.shipment_id}, material: {item.material_code}")
            
        except Exception as e:
            print(f"### TRACE: Error finding ShipmentItems: {e}")
            all_shipment_items = []

        # Step 5: Get OrderShipments using the ShipDocumentEntryMaster IDs
        if all_shipment_items:
            try:
                # Extract unique shipment_ids (these are ShipDocumentEntryMaster.id values)
                ship_doc_entry_ids = list(set([item.shipment_id for item in all_shipment_items]))
                print(f"### TRACE: Looking for OrderShipments with ship_doc_entry_ids: {ship_doc_entry_ids}")
                
                # Find OrderShipments where ship_doc_entry_id matches our ShipDocumentEntryMaster IDs
                all_shipments = OrderShipment.query.filter(
                    OrderShipment.ship_doc_entry_id.in_(ship_doc_entry_ids)
                ).all()
                
                print(f"### TRACE: Found {len(all_shipments)} OrderShipments")
                
                # Debug: Show details of found OrderShipments
                for shipment in all_shipments:
                    print(f"### TRACE: OrderShipment - ID: {shipment.id}, ship_doc_entry_id: {shipment.ship_doc_entry_id}")
                    print(f"###                     import_id: {shipment.import_id}, license: {shipment.license_number}")
                
            except Exception as e:
                print(f"### TRACE: Error finding OrderShipments: {e}")
                all_shipments = []
        else:
            print("### TRACE: No ShipmentItems found, cannot lookup OrderShipments")

        # Step 6: Process shipment info if found
        if all_shipments:
            print("### TRACE: Processing OrderShipment data for display")
            import_ids, license_numbers = [], []
            shipment_deadlines, ports_of_loading, ports_of_discharge = [], [], []

            for shipment in all_shipments:
                # Collect unique values
                if shipment.import_id and shipment.import_id not in import_ids:
                    import_ids.append(shipment.import_id)
                if shipment.license_number and shipment.license_number not in license_numbers:
                    license_numbers.append(shipment.license_number)
                if shipment.shipment_deadline:
                    deadline = shipment.shipment_deadline.strftime('%Y-%m-%d')
                    if deadline not in shipment_deadlines:
                        shipment_deadlines.append(deadline)
                if shipment.port_of_loading and shipment.port_of_loading not in ports_of_loading:
                    ports_of_loading.append(shipment.port_of_loading)
                if shipment.port_of_discharge and shipment.port_of_discharge not in ports_of_discharge:
                    ports_of_discharge.append(shipment.port_of_discharge)

            print(f"### TRACE: Collected data:")
            print(f"###   import_ids: {import_ids}")
            print(f"###   license_numbers: {license_numbers}")
            print(f"###   shipment_deadlines: {shipment_deadlines}")
            print(f"###   ports_of_loading: {ports_of_loading}")
            print(f"###   ports_of_discharge: {ports_of_discharge}")

            # Create shipment_info dictionary
            shipment_info = {
                'import_ids': import_ids,
                'license_numbers': license_numbers,
                'shipment_deadlines': shipment_deadlines,
                'ports_of_loading': ports_of_loading,
                'ports_of_discharge': ports_of_discharge,
                'shipment_count': len(all_shipments),
                # Single values for backward compatibility
                'import_id': import_ids[0] if import_ids else None,
                'license_number': license_numbers[0] if license_numbers else None,
                'shipment_deadline': datetime.strptime(shipment_deadlines[0], '%Y-%m-%d').date() if shipment_deadlines else None,
                'port_of_loading': ports_of_loading[0] if ports_of_loading else None,
                'port_of_discharge': ports_of_discharge[0] if ports_of_discharge else None,
            }

        # Step 7: Fetch Shipment Documents
        if all_shipments:
            try:
                ship_doc_entry_ids = list(set([s.ship_doc_entry_id for s in all_shipments]))
                print(f"### TRACE: Fetching ShipDocumentEntryDocuments for IDs: {ship_doc_entry_ids}")
                
                shipment_documents = ShipDocumentEntryDocument.query.filter(
                    ShipDocumentEntryDocument.ship_doc_entry_id.in_(ship_doc_entry_ids)
                ).order_by(
                    ShipDocumentEntryDocument.document_type,
                    ShipDocumentEntryDocument.created_at.desc()
                ).all()
                
                print(f"### TRACE: Found {len(shipment_documents)} shipment documents")
                
            except Exception as e:
                print(f"### TRACE: Error fetching shipment documents: {e}")
                shipment_documents = []

        # Step 8: Final summary
        print("### TRACE: Final data summary")
        print(f"###   PO Details: {len(po_details)}")
        print(f"###   ShipmentItems: {len(all_shipment_items) if 'all_shipment_items' in locals() else 0}")
        print(f"###   OrderShipments: {len(all_shipments)}")
        print(f"###   Shipment Documents: {len(shipment_documents)}")
        print(f"###   Shipment Info: {'Created' if shipment_info else 'None'}")

        return render_template('po/view_po.html',
                             po_header=po_header,
                             po_details=po_details,
                             shipment_info=shipment_info,
                             shipment_documents=shipment_documents)

    except Exception as e:
        print(f"### ERROR: Failed in view_po: {e}")
        import traceback
        print(f"Traceback:\n{traceback.format_exc()}")
        flash('An error occurred while loading the purchase order.', 'error')
        return redirect(url_for('po.purchase_orders'))


@bp.route('/view/<int:po_id>/document/<int:document_id>/view')
@login_required
def view_po_document(po_id, document_id):
    """SECURE: View a document from the related shipment through app proxy."""
    try:

        
        # Verify the PO belongs to the current user's company
        po_header = POHeader.query.filter_by(
            id=po_id,
            company_id=current_user.company_id
        ).first_or_404()
        
        # Get the document
        document = ShipDocumentEntryDocument.query.get_or_404(document_id)
        
        # Verify document exists and has a file path
        if not document.file_path:
            flash('No file path found for this document', 'error')
            return redirect(url_for('po.view_po', po_id=po_id))
        
        # Optional: Add more specific authorization checks here
        # For example, verify the document is actually related to this PO:
        # if not document_belongs_to_po(document, po_header):
        #     flash('Document does not belong to this PO', 'error')
        #     return redirect(url_for('po.view_po', po_id=po_id))
        
        # Normalize the S3 key path
        s3_key = document.file_path.replace("\\", "/")
        
        print(f"Serving PO document securely: {s3_key} for PO {po_id}")
        
        # REMOVED: Direct S3 URL construction and redirect
        # direct_url = f"{current_app.config['S3_ENDPOINT_URL']}/{current_app.config['S3_BUCKET_NAME']}/{document.file_path}"
        # return redirect(direct_url)
        
        # ADDED: Direct secure serving through app proxy
        return serve_s3_file(s3_key)
    
    except ClientError as e:
        # Handle S3-specific errors
        current_app.logger.error(f"S3 error viewing PO document: {str(e)}")
        print(f"S3 error viewing PO document: {str(e)}")
        
        if e.response['Error']['Code'] == 'NoSuchKey':
            flash('Document file not found in storage', 'error')
        else:
            flash('Error accessing document from storage', 'error')
            
        return redirect(url_for('po.view_po', po_id=po_id))
    
    except Exception as e:
        current_app.logger.error(f"Error viewing PO document: {str(e)}")
        print(f"Error viewing PO document: {str(e)}")
        flash('An error occurred while viewing the document', 'error')
        return redirect(url_for('po.view_po', po_id=po_id))
    


@bp.route('/delete/<int:po_id>', methods=['POST'])
@login_required
def delete_po(po_id):
    """Delete PO"""
    
    po_header = POHeader.query.filter_by(
        id=po_id,
        company_id=current_user.company_id
    ).first_or_404()
    
    try:
        db.session.delete(po_header)
        db.session.commit()
        flash('Purchase Order deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting Purchase Order', 'danger')
    
    return redirect(url_for('po.purchase_orders'))

@bp.route('/get_all_po_ids', methods=['POST'])
@login_required
def get_all_po_ids():
    """Get all PO IDs for select all functionality"""
    
    try:
        data = request.get_json()
        search = data.get('search', '')
        status = data.get('status', '')
        
        print(f"=== Get All PO IDs ===")
        print(f"Search: '{search}', Status: '{status}'")
        
        # Build query with same logic as main view
        query = db.session.query(
            POHeader.id,
            POHeader.po_number,
            func.sum(PODetail.order_quantity).label('total_quantity'),
            func.sum(PODetail.quantity_received).label('total_received')
        ).join(
            PODetail, POHeader.id == PODetail.po_header_id
        )

        # Apply role-based filter
        if current_user.role == 'customer':
            query = query.filter(POHeader.company_id == current_user.company_id)
        else:
            query = query.filter(POHeader.created_by == current_user.id)

        # Group by POHeader
        query = query.group_by(POHeader.id, POHeader.po_number)
        
        # Apply search filter
        if search:
            query = query.filter(
                db.or_(
                    POHeader.po_number.contains(search),
                    POHeader.sysdocnum.contains(search),
                    POHeader.supplier.has(POSupplier.supplier_name.contains(search))
                )
            )
        
        # Apply status filter
        if status:
            if status == 'pending':
                query = query.having(func.sum(PODetail.quantity_received) == 0)
            elif status == 'partial':
                query = query.having(
                    db.and_(
                        func.sum(PODetail.quantity_received) > 0,
                        func.sum(PODetail.quantity_received) < func.sum(PODetail.order_quantity)
                    )
                )
            elif status == 'completed':
                query = query.having(func.sum(PODetail.quantity_received) >= func.sum(PODetail.order_quantity))
        
        # Execute query to get all matching PO IDs
        results = query.all()
        po_ids = [str(result[0]) for result in results]  # Convert to strings for consistency
        
        print(f"Found {len(po_ids)} PO IDs matching criteria")
        
        return jsonify({
            'success': True, 
            'po_ids': po_ids,
            'count': len(po_ids)
        })
        
    except Exception as e:
        print(f"ERROR getting all PO IDs: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Error getting PO IDs: {str(e)}'}), 500


@bp.route('/bulk_delete', methods=['POST'])
@login_required
def bulk_delete_pos():
    """Bulk delete POs based on different criteria"""
    
    try:
        data = request.get_json()
        delete_type = data.get('delete_type')  # 'selected', 'all', 'date_range', 'filtered'
        
        print(f"=== Bulk Delete POs ===")
        print(f"User ID: {current_user.id}")
        print(f"User Role: {current_user.role}")
        print(f"Company ID: {current_user.company_id}")
        print(f"Delete Type: {delete_type}")
        print(f"Request data: {data}")
        
        deleted_count = 0
        
        if delete_type == 'selected':
            # Delete specific PO IDs
            po_ids = data.get('po_ids', [])
            if not po_ids:
                return jsonify({'success': False, 'message': 'No POs selected for deletion'}), 400
            
            print(f"Deleting selected POs: {po_ids}")
            deleted_count = delete_selected_pos(po_ids)
            
        elif delete_type == 'all':
            # Delete all POs for the company/user
            print(f"Deleting all POs")
            deleted_count = delete_all_pos()
            
        elif delete_type == 'date_range':
            # Delete POs within date range
            start_date = data.get('start_date')
            end_date = data.get('end_date')
            
            print(f"Date range data received - Start: '{start_date}', End: '{end_date}'")
            
            if not start_date or not end_date:
                return jsonify({'success': False, 'message': 'Start date and end date are required'}), 400
            
            # Validate date format
            if not start_date.strip() or not end_date.strip():
                return jsonify({'success': False, 'message': 'Start date and end date cannot be empty'}), 400
            
            print(f"Deleting POs in date range: {start_date} to {end_date}")
            deleted_count = delete_pos_by_date_range(start_date, end_date)
            
        elif delete_type == 'filtered':
            # Delete POs based on current filters
            search = data.get('search', '')
            status = data.get('status', '')
            
            print(f"Deleting filtered POs: search='{search}', status='{status}'")
            deleted_count = delete_filtered_pos(search, status)
            
        else:
            return jsonify({'success': False, 'message': 'Invalid delete type'}), 400
        
        if deleted_count > 0:
            db.session.commit()
            message = f'Successfully deleted {deleted_count} purchase order{"s" if deleted_count != 1 else ""}'
            print(f"SUCCESS: {message}")
            return jsonify({'success': True, 'message': message, 'deleted_count': deleted_count})
        else:
            return jsonify({'success': False, 'message': 'No purchase orders found to delete'}), 400
            
    except Exception as e:
        db.session.rollback()
        print(f"ERROR in bulk delete: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Error deleting purchase orders: {str(e)}'}), 500


def delete_selected_pos(po_ids):
    """Delete specific PO IDs"""
    
    # Build query with role-based filtering
    query = POHeader.query.filter(POHeader.id.in_(po_ids))
    
    if current_user.role == 'customer':
        query = query.filter(POHeader.company_id == current_user.company_id)
    else:
        query = query.filter(POHeader.created_by == current_user.id)
    
    pos_to_delete = query.all()
    print(f"Found {len(pos_to_delete)} POs to delete from selected IDs")
    
    for po in pos_to_delete:
        print(f"Deleting PO: {po.po_number} (ID: {po.id})")
        db.session.delete(po)
    
    return len(pos_to_delete)


def delete_all_pos():
    """Delete all POs for the current user/company"""
    
    # Build query with role-based filtering
    if current_user.role == 'customer':
        query = POHeader.query.filter(POHeader.company_id == current_user.company_id)
    else:
        query = POHeader.query.filter(POHeader.created_by == current_user.id)
    
    pos_to_delete = query.all()
    print(f"Found {len(pos_to_delete)} POs to delete (all)")
    
    for po in pos_to_delete:
        print(f"Deleting PO: {po.po_number} (ID: {po.id})")
        db.session.delete(po)
    
    return len(pos_to_delete)


def delete_pos_by_date_range(start_date_str, end_date_str):
    """Delete POs within a date range"""
    
    try:
        from datetime import datetime
        
        # Parse dates with better error handling
        try:
            start_date = datetime.strptime(start_date_str.strip(), '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str.strip(), '%Y-%m-%d').date()
        except ValueError as ve:
            print(f"Date parsing error: {ve}")
            raise ValueError("Invalid date format. Please use YYYY-MM-DD format")
        
        print(f"Parsed date range: {start_date} to {end_date}")
        
        if start_date > end_date:
            raise ValueError("Start date cannot be after end date")
        
        # Build query with role-based filtering and date range
        query = POHeader.query.filter(
            POHeader.po_date >= start_date,
            POHeader.po_date <= end_date
        )
        
        if current_user.role == 'customer':
            query = query.filter(POHeader.company_id == current_user.company_id)
        else:
            query = query.filter(POHeader.created_by == current_user.id)
        
        pos_to_delete = query.all()
        print(f"Found {len(pos_to_delete)} POs to delete in date range")
        
        for po in pos_to_delete:
            print(f"Deleting PO: {po.po_number} (Date: {po.po_date})")
            db.session.delete(po)
        
        return len(pos_to_delete)
        
    except ValueError as e:
        print(f"Date validation error: {e}")
        raise e
    except Exception as e:
        print(f"Unexpected error in date range deletion: {e}")
        raise e


def delete_filtered_pos(search, status):
    """Delete POs based on current filter criteria"""
    
    # Base query with aggregated status information (same as main view)
    query = db.session.query(
        POHeader,
        func.sum(PODetail.order_quantity).label('total_quantity'),
        func.sum(PODetail.quantity_received).label('total_received'),
        func.sum(PODetail.quantity_pending).label('total_pending')
    ).join(
        PODetail, POHeader.id == PODetail.po_header_id
    )

    # Apply role-based filter
    if current_user.role == 'customer':
        query = query.filter(POHeader.company_id == current_user.company_id)
    else:
        query = query.filter(POHeader.created_by == current_user.id)

    # Group by POHeader
    query = query.group_by(POHeader.id)
    
    # Apply search filter
    if search:
        query = query.filter(
            db.or_(
                POHeader.po_number.contains(search),
                POHeader.sysdocnum.contains(search),
                POHeader.supplier.has(POSupplier.supplier_name.contains(search))
            )
        )
    
    # Apply status filter
    if status:
        if status == 'pending':
            query = query.having(func.sum(PODetail.quantity_received) == 0)
        elif status == 'partial':
            query = query.having(
                db.and_(
                    func.sum(PODetail.quantity_received) > 0,
                    func.sum(PODetail.quantity_received) < func.sum(PODetail.order_quantity)
                )
            )
        elif status == 'completed':
            query = query.having(func.sum(PODetail.quantity_received) >= func.sum(PODetail.order_quantity))
    
    # Execute query to get filtered results
    filtered_results = query.all()
    print(f"Found {len(filtered_results)} POs matching filter criteria")
    
    # Extract PO headers and delete them
    pos_to_delete = [result[0] for result in filtered_results]  # result[0] is the POHeader
    
    for po in pos_to_delete:
        print(f"Deleting filtered PO: {po.po_number} (ID: {po.id})")
        db.session.delete(po)
    
    return len(pos_to_delete)


@bp.route('/count_pos_for_deletion', methods=['POST'])
@login_required
def count_pos_for_deletion():
    """Count POs that would be deleted for preview"""
    
    try:
        data = request.get_json()
        delete_type = data.get('delete_type')
        
        print(f"=== Count POs for deletion ===")
        print(f"Delete Type: {delete_type}")
        print(f"Request data: {data}")
        
        count = 0
        
        if delete_type == 'all':
            # Count all POs
            if current_user.role == 'customer':
                count = POHeader.query.filter(POHeader.company_id == current_user.company_id).count()
            else:
                count = POHeader.query.filter(POHeader.created_by == current_user.id).count()
                
        elif delete_type == 'selected':
            # Count selected PO IDs
            po_ids = data.get('po_ids', [])
            print(f"Counting selected PO IDs: {po_ids}")
            
            if not po_ids:
                return jsonify({'success': True, 'count': 0})
            
            # Build query with role-based filtering
            query = POHeader.query.filter(POHeader.id.in_(po_ids))
            
            if current_user.role == 'customer':
                query = query.filter(POHeader.company_id == current_user.company_id)
            else:
                query = query.filter(POHeader.created_by == current_user.id)
            
            count = query.count()
            print(f"Found {count} selected POs that user can delete")
                
        elif delete_type == 'date_range':
            # Count POs in date range
            start_date_str = data.get('start_date')
            end_date_str = data.get('end_date')
            
            print(f"Count date range - Start: '{start_date_str}', End: '{end_date_str}'")
            
            if not start_date_str or not end_date_str:
                return jsonify({'success': False, 'message': 'Start date and end date are required'}), 400
            
            # Validate date format
            if not start_date_str.strip() or not end_date_str.strip():
                return jsonify({'success': False, 'message': 'Start date and end date cannot be empty'}), 400
            
            from datetime import datetime
            try:
                start_date = datetime.strptime(start_date_str.strip(), '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str.strip(), '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date format. Please use YYYY-MM-DD format'}), 400
            
            if start_date > end_date:
                return jsonify({'success': False, 'message': 'Start date cannot be after end date'}), 400
            
            query = POHeader.query.filter(
                POHeader.po_date >= start_date,
                POHeader.po_date <= end_date
            )
            
            if current_user.role == 'customer':
                query = query.filter(POHeader.company_id == current_user.company_id)
            else:
                query = query.filter(POHeader.created_by == current_user.id)
            
            count = query.count()
            
        elif delete_type == 'filtered':
            # Count filtered POs (same logic as delete_filtered_pos but just count)
            search = data.get('search', '')
            status = data.get('status', '')
            
            query = db.session.query(POHeader).join(PODetail, POHeader.id == PODetail.po_header_id)
            
            if current_user.role == 'customer':
                query = query.filter(POHeader.company_id == current_user.company_id)
            else:
                query = query.filter(POHeader.created_by == current_user.id)
            
            query = query.group_by(POHeader.id)
            
            if search:
                query = query.filter(
                    db.or_(
                        POHeader.po_number.contains(search),
                        POHeader.sysdocnum.contains(search),
                        POHeader.supplier.has(POSupplier.supplier_name.contains(search))
                    )
                )
            
            if status:
                if status == 'pending':
                    query = query.having(func.sum(PODetail.quantity_received) == 0)
                elif status == 'partial':
                    query = query.having(
                        db.and_(
                            func.sum(PODetail.quantity_received) > 0,
                            func.sum(PODetail.quantity_received) < func.sum(PODetail.order_quantity)
                        )
                    )
                elif status == 'completed':
                    query = query.having(func.sum(PODetail.quantity_received) >= func.sum(PODetail.order_quantity))
            
            count = query.count()
        
        else:
            return jsonify({'success': False, 'message': 'Invalid delete type'}), 400
        
        print(f"Count result: {count} POs would be deleted")
        return jsonify({'success': True, 'count': count})
        
    except Exception as e:
        print(f"ERROR counting POs: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'Error counting POs: {str(e)}'}), 500


@bp.route('/remarks/<int:po_id>', methods=['GET'])
@login_required
def get_remarks(po_id):
    """Get remarks for a specific PO"""
    po_header = POHeader.query.filter_by(
        id=po_id).first_or_404()
    
    return jsonify({
        'success': True,
        'remarks': po_header.remarks or '',
        'po_number': po_header.po_number,
        'sysdocnum': po_header.sysdocnum
    })

@bp.route('/remarks/<int:po_id>', methods=['POST'])
@login_required
def update_remarks(po_id):
    """Update remarks for a specific PO"""
    po_header = POHeader.query.filter_by(
        id=po_id,
        company_id=current_user.company_id
    ).first_or_404()
    
    try:
        data = request.get_json()
        remarks = data.get('remarks', '').strip()
        
        po_header.remarks = remarks if remarks else None
        po_header.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Remarks updated successfully',
            'remarks': po_header.remarks or ''
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error updating remarks: {str(e)}'
        }), 500
    

# PO DASHBOARD

# Add these routes to your po/routes.py file

@bp.route('/dashboard')
@login_required
def po_dashboard():
    """PO Dashboard - Show PO statistics and calendar"""
    
    try:
        print(f"=== PO Dashboard Access ===")
        print(f"User ID: {current_user.id}")
        print(f"User Role: {current_user.role}")
        print(f"Company ID: {current_user.company_id}")
        
        # Calculate PO statistics
        company_id = current_user.company_id
        
        # Base query for PO headers with aggregated status
        base_query = db.session.query(
            POHeader,
            func.sum(PODetail.order_quantity).label('total_quantity'),
            func.sum(PODetail.quantity_received).label('total_received'),
            func.sum(PODetail.quantity_pending).label('total_pending')
        ).join(
            PODetail, POHeader.id == PODetail.po_header_id
        )

        # Apply role-based filter
        print(f"Applying role-based filter...")
        if current_user.role == 'customer':
            print(f"Customer role: Filtering by company_id = {company_id}")
            base_query = base_query.filter(POHeader.company_id == company_id)
        else:
            print(f"Non-user role: Filtering by created_by = {current_user.id}")
            base_query = base_query.filter(POHeader.created_by == current_user.id)
        
        base_query = base_query.group_by(POHeader.id)
        
        # Get all POs with their status
        all_pos = base_query.all()
        print(f"Total POs found: {len(all_pos)}")
        
        # Calculate basic statistics
        total_pos = len(all_pos)
        pending_pos = 0
        partial_pos = 0
        
        for po_header, total_qty, total_received, total_pending in all_pos:
            print(f"PO {po_header.po_number}: Total={total_qty}, Received={total_received}, Pending={total_pending}")
            if not total_received or total_received == 0:
                pending_pos += 1
                print(f"  -> Status: PENDING")
            elif total_received > 0 and total_received < total_qty:
                partial_pos += 1
                print(f"  -> Status: PARTIAL")
            else:
                print(f"  -> Status: COMPLETED (unexpected in dashboard)")
        
        # Calculate overdue POs
        today = datetime.now().date()
        # overdue_query = db.session.query(POHeader.id).distinct().join(
        #     PODetail, POHeader.id == PODetail.po_header_id
        # ).filter(
        #     PODetail.delivery_date < today,
        #     PODetail.is_completed == False
        # )

        overdue_query = db.session.query(POHeader.id).distinct().join(
            PODetail, POHeader.id == PODetail.po_header_id
        ).filter(
            PODetail.date_delivered != None,
            PODetail.date_delivered > PODetail.delivery_date,
            PODetail.is_completed == False
        )
        
        # Apply same role-based filter for overdue
        if current_user.role == 'customer':
            overdue_query = overdue_query.filter(POHeader.company_id == company_id)
        else:
            overdue_query = overdue_query.filter(POHeader.created_by == current_user.id)
        
        overdue_pos = overdue_query.count()
        print(f"Overdue POs found: {overdue_pos}")
        
        statistics = {
            'total_pos': total_pos,
            'pending_pos': pending_pos,
            'partial_pos': partial_pos,
            'overdue_pos': overdue_pos  # NEW STAT
        }
        
        print(f"Final Statistics: {statistics}")
        print(f"=== End PO Dashboard ===")
        
        return render_template('po/dashboard.html', statistics=statistics)
        
    except Exception as e:
        print(f"ERROR in PO Dashboard: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        current_app.logger.error(f"Error loading PO dashboard: {str(e)}")
        flash('An error occurred while loading the dashboard.', 'error')
        return redirect(url_for('po.purchase_orders'))

@bp.route('/api/overdue_po_details')
@login_required
def get_overdue_po_details():
    """Get detailed information about overdue PO items"""
    try:
        today = datetime.now().date()
        
        # Base query for overdue PO details - UPDATED TO MATCH DASHBOARD LOGIC
        query = db.session.query(
            POHeader,
            PODetail
        ).join(
            PODetail, POHeader.id == PODetail.po_header_id
        ).filter(
            PODetail.date_delivered != None,
            PODetail.date_delivered > PODetail.delivery_date,
            PODetail.is_completed == False
        )
        
        # Apply role-based filter
        if current_user.role == 'customer':
            query = query.filter(POHeader.company_id == current_user.company_id)
        else:
            query = query.filter(POHeader.created_by == current_user.id)
        
        # Order by delivery date (most overdue first)
        results = query.order_by(PODetail.delivery_date.asc()).all()
        
        # Group by PO Header
        overdue_data = {}
        for po_header, po_detail in results:
            if po_header.id not in overdue_data:
                overdue_data[po_header.id] = {
                    'po_header': {
                        'id': po_header.id,
                        'po_number': po_header.po_number,
                        'sysdocnum': po_header.sysdocnum,
                        'supplier_name': po_header.supplier.supplier_name,
                        'total_value': float(po_header.total_value),
                        'currency': po_header.currency,
                        'po_date': po_header.po_date.strftime('%Y-%m-%d')
                    },
                    'overdue_items': []
                }
            
            # Calculate days overdue - UPDATED TO USE ACTUAL DELIVERY DATE
            days_overdue = (po_detail.date_delivered - po_detail.delivery_date).days
            
            overdue_data[po_header.id]['overdue_items'].append({
                'id': po_detail.id,
                'item_number': po_detail.item_number,
                'material_code': po_detail.material_code,
                'material_name': po_detail.material_name,
                'delivery_date': po_detail.delivery_date.strftime('%Y-%m-%d'),
                'date_delivered': po_detail.date_delivered.strftime('%Y-%m-%d'),  # ADDED ACTUAL DELIVERY DATE
                'days_overdue': days_overdue,
                'order_quantity': float(po_detail.order_quantity),
                'quantity_received': float(po_detail.quantity_received),
                'quantity_pending': float(po_detail.quantity_pending),
                'order_unit': po_detail.order_unit,
                'net_price': float(po_detail.net_price),
                'line_total': float(po_detail.line_total),
                'completion_percentage': po_detail.get_completion_percentage(),
                'status': po_detail.get_status()
            })
        
        # Convert to list and sort by most overdue
        overdue_list = list(overdue_data.values())
        overdue_list.sort(key=lambda x: min(item['days_overdue'] for item in x['overdue_items']), reverse=True)
        
        return jsonify({
            'success': True,
            'data': overdue_list,
            'total_overdue_pos': len(overdue_list),
            'total_overdue_items': sum(len(po['overdue_items']) for po in overdue_list)
        })
        
    except Exception as e:
        current_app.logger.error(f"Error fetching overdue PO details: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500             

@bp.route('/api/po_calendar_data')
@login_required
def get_po_calendar_data():
    """API endpoint to get PO calendar data for shipments"""
    
    try:
        print(f"=== PO Calendar Data API ===")
        print(f"User ID: {current_user.id}")
        print(f"User Role: {current_user.role}")
        print(f"Company ID: {current_user.company_id}")
        
        company_id = current_user.company_id
        
        # Get all shipments that have PO items connected to them
        # and either have ETA or shipment deadline
        shipments_query = db.session.query(
            OrderShipment.ship_doc_entry_id,
            OrderShipment.import_id,
            OrderShipment.eta,
            OrderShipment.shipment_deadline,
            OrderShipment.vessel,
            OrderShipment.voyage,
            OrderShipment.port_of_loading,
            OrderShipment.port_of_discharge,
            func.count(func.distinct(ShipmentItem.po_number)).label('po_count')
        ).join(
            ShipmentItem, OrderShipment.ship_doc_entry_id == ShipmentItem.shipment_id
        )
        
        # Apply role-based filter for shipments
        print(f"Applying role-based filter for shipments...")
        if current_user.role == 'customer':
            print(f"User role: Filtering shipments by company_id = {company_id}")
            shipments_query = shipments_query.filter(OrderShipment.company_id == company_id)
        else:
            print(f"Non-user role: Filtering shipments by created_by = {current_user.id}")
            # For non-user roles, we need to filter by POs that belong to this user
            # First get PO numbers created by this user
            user_po_numbers = db.session.query(POHeader.po_number).filter(
                POHeader.created_by == current_user.id
            ).subquery()
            
            shipments_query = shipments_query.filter(
                ShipmentItem.po_number.in_(user_po_numbers)
            )
        
        shipments_query = shipments_query.filter(
            ShipmentItem.po_number.isnot(None),  # Only shipments with PO items
            db.or_(
                OrderShipment.eta.isnot(None),
                OrderShipment.shipment_deadline.isnot(None)
            )
        ).group_by(
            OrderShipment.ship_doc_entry_id,
            OrderShipment.import_id,
            OrderShipment.eta,
            OrderShipment.shipment_deadline,
            OrderShipment.vessel,
            OrderShipment.voyage,
            OrderShipment.port_of_loading,
            OrderShipment.port_of_discharge
        )
        
        shipments_data = shipments_query.all()
        print(f"Found {len(shipments_data)} shipments with PO connections")
        
        result = []
        
        for i, shipment_data in enumerate(shipments_data):
            (ship_doc_entry_id, import_id, eta, shipment_deadline, 
             vessel, voyage, port_of_loading, port_of_discharge, po_count) = shipment_data
            
            print(f"Processing shipment {i+1}: ID={ship_doc_entry_id}, Import={import_id}, PO_Count={po_count}")
            
            # Determine display date (ETA takes priority over shipment deadline)
            display_date = None
            if eta:
                display_date = eta.isoformat()
                print(f"  Using ETA: {display_date}")
            elif shipment_deadline:
                display_date = shipment_deadline.isoformat()
                print(f"  Using Shipment Deadline: {display_date}")
            
            if not display_date:
                print(f"  Skipping - no date available")
                continue  # Skip if no date available
            
            # Get detailed PO information for this shipment
            print(f"  Getting PO details for shipment {ship_doc_entry_id}")
            pos_in_shipment = get_pos_for_shipment(ship_doc_entry_id, company_id, current_user.role, current_user.id)
            print(f"  Found {len(pos_in_shipment)} POs in shipment")
            
            result.append({
                'ship_doc_entry_id': ship_doc_entry_id,
                'import_id': import_id,
                'display_date': display_date,
                'vessel': vessel,
                'voyage': voyage,
                'port_of_loading': port_of_loading,
                'port_of_discharge': port_of_discharge,
                'po_count': po_count,
                'pos': pos_in_shipment
            })
        
        print(f"Returning {len(result)} calendar events")
        print(f"=== End PO Calendar Data API ===")
        return jsonify(result)
        
    except Exception as e:
        print(f"ERROR in PO Calendar Data API: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        current_app.logger.error(f"Error fetching PO calendar data: {str(e)}")
        return jsonify({'error': str(e)}), 500


def get_pos_for_shipment(ship_doc_entry_id, company_id, user_role, user_id):
    """Get detailed PO information for a specific shipment"""
    
    try:
        print(f"  === Getting POs for Shipment {ship_doc_entry_id} ===")
        print(f"  Company ID: {company_id}, User Role: {user_role}, User ID: {user_id}")
        
        # Get all unique PO numbers for this shipment
        po_numbers_query = db.session.query(
            func.distinct(ShipmentItem.po_number)
        ).filter(
            ShipmentItem.shipment_id == ship_doc_entry_id,
            ShipmentItem.po_number.isnot(None)
        )
        
        # Apply role-based filter for shipment items
        if user_role == 'customer':
            print(f"  User role: Filtering shipment items by company_id = {company_id}")
            po_numbers_query = po_numbers_query.filter(ShipmentItem.company_id == company_id)
        else:
            print(f"  Non-user role: Filtering by POs created by user {user_id}")
            # For non-user roles, only get PO numbers that were created by this user
            user_po_numbers = db.session.query(POHeader.po_number).filter(
                POHeader.created_by == user_id
            ).subquery()
            po_numbers_query = po_numbers_query.filter(
                ShipmentItem.po_number.in_(user_po_numbers)
            )
        
        po_numbers = po_numbers_query.all()
        po_numbers = [po[0] for po in po_numbers if po[0]]
        print(f"  Found PO numbers: {po_numbers}")
        
        pos_details = []
        
        for po_number in po_numbers:
            print(f"  Processing PO: {po_number}")
            
            # Get PO header information with role-based filtering
            po_header_query = db.session.query(
                POHeader,
                POSupplier.supplier_name,
                func.sum(PODetail.order_quantity).label('total_quantity'),
                func.sum(PODetail.quantity_received).label('total_received'),
                func.sum(PODetail.quantity_pending).label('total_pending'),
                func.count(PODetail.id).label('item_count')
            ).join(
                POSupplier, POHeader.supplier_id == POSupplier.id
            ).join(
                PODetail, POHeader.id == PODetail.po_header_id
            ).filter(
                POHeader.po_number == po_number
            )
            
            # Apply role-based filter for PO headers
            if user_role == 'customer':
                po_header_query = po_header_query.filter(POHeader.company_id == company_id)
            else:
                po_header_query = po_header_query.filter(POHeader.created_by == user_id)
            
            po_header_query = po_header_query.group_by(
                POHeader.id,
                POSupplier.supplier_name
            )
            
            po_header_result = po_header_query.first()
            
            if not po_header_result:
                print(f"  No PO header found for {po_number}")
                continue
                
            (po_header, supplier_name, total_qty, total_received, 
             total_pending, item_count) = po_header_result
            
            print(f"  PO Header found: Supplier={supplier_name}, Items={item_count}")
            print(f"  Quantities: Total={total_qty}, Received={total_received}, Pending={total_pending}")
            
            # Calculate status
            status = 'pending'
            if total_received and total_received > 0:
                if total_received >= total_qty:
                    status = 'completed'
                else:
                    status = 'partial'
            
            print(f"  Status: {status}")
            
            # Get items for this PO that are in the shipment
            po_items_query = db.session.query(
                PODetail.material_code,
                PODetail.material_name,
                PODetail.order_quantity,
                PODetail.quantity_received,
                PODetail.quantity_pending,
                PODetail.order_unit
            ).join(
                ShipmentItem, 
                db.and_(
                    ShipmentItem.po_number == PODetail.po_number,
                    ShipmentItem.material_code == PODetail.material_code
                )
            ).filter(
                PODetail.po_header_id == po_header.id,
                ShipmentItem.shipment_id == ship_doc_entry_id
            )
            
            # Apply role-based filter for shipment items in the join
            if user_role == 'customer':
                po_items_query = po_items_query.filter(ShipmentItem.company_id == company_id)
            # Note: For non-user roles, we already filtered the PO numbers above
            
            po_items = po_items_query.all()
            print(f"  Found {len(po_items)} items in shipment")
            
            # Convert items to list of dictionaries
            items_list = []
            for item in po_items:
                items_list.append({
                    'material_code': item.material_code,
                    'material_name': item.material_name,
                    'order_quantity': float(item.order_quantity) if item.order_quantity else 0,
                    'quantity_received': float(item.quantity_received) if item.quantity_received else 0,
                    'quantity_pending': float(item.quantity_pending) if item.quantity_pending else 0,
                    'order_unit': item.order_unit
                })
                print(f"    Item: {item.material_code} - {item.material_name}")
            
            pos_details.append({
                'po_number': po_number,
                'supplier_name': supplier_name,
                'status': status,
                'item_count': item_count,
                'total_quantity': float(total_qty) if total_qty else 0,
                'total_received': float(total_received) if total_received else 0,
                'total_pending': float(total_pending) if total_pending else 0,
                'items': items_list
            })
        
        print(f"  Returning {len(pos_details)} PO details")
        print(f"  === End Getting POs for Shipment ===")
        return pos_details
        
    except Exception as e:
        print(f"  ERROR getting POs for shipment {ship_doc_entry_id}: {str(e)}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")
        current_app.logger.error(f"Error getting POs for shipment {ship_doc_entry_id}: {str(e)}")
        return []


@bp.route('/api/po_statistics')
@login_required
def get_po_statistics():
    """API endpoint to get real-time PO statistics"""
    
    try:
        print(f"=== PO Statistics API ===")
        print(f"User ID: {current_user.id}")
        print(f"User Role: {current_user.role}")
        print(f"Company ID: {current_user.company_id}")
        
        company_id = current_user.company_id
        
        # Base query for PO headers with aggregated status
        base_query = db.session.query(
            POHeader,
            func.sum(PODetail.order_quantity).label('total_quantity'),
            func.sum(PODetail.quantity_received).label('total_received'),
            func.sum(PODetail.quantity_pending).label('total_pending')
        ).join(
            PODetail, POHeader.id == PODetail.po_header_id
        )
        
        # Apply role-based filter
        print(f"Applying role-based filter for statistics...")
        if current_user.role == 'customer':
            print(f"User role: Filtering by company_id = {company_id}")
            base_query = base_query.filter(POHeader.company_id == company_id)
        else:
            print(f"Non-user role: Filtering by created_by = {current_user.id}")
            base_query = base_query.filter(POHeader.created_by == current_user.id)
        
        base_query = base_query.group_by(POHeader.id)
        
        # Get all POs with their status
        all_pos = base_query.all()
        print(f"Total POs found for statistics: {len(all_pos)}")
        
        # Calculate statistics
        total_pos = len(all_pos)
        pending_pos = 0
        partial_pos = 0
        completed_pos = 0
        
        for po_header, total_qty, total_received, total_pending in all_pos:
            print(f"Statistics - PO {po_header.po_number}: Total={total_qty}, Received={total_received}")
            if not total_received or total_received == 0:
                pending_pos += 1
                print(f"  -> PENDING")
            elif total_received >= total_qty:
                completed_pos += 1
                print(f"  -> COMPLETED")
            else:
                partial_pos += 1
                print(f"  -> PARTIAL")
        
        statistics = {
            'total_pos': total_pos,
            'pending_pos': pending_pos,
            'partial_pos': partial_pos,
            'completed_pos': completed_pos
        }
        
        print(f"Final Statistics: {statistics}")
        print(f"=== End PO Statistics API ===")
        
        return jsonify(statistics)
        
    except Exception as e:
        print(f"ERROR in PO Statistics API: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        current_app.logger.error(f"Error fetching PO statistics: {str(e)}")
        return jsonify({'error': str(e)}), 500


# Add this route to your main blueprint registration or app routes
@bp.route('/po_shipment_details/<int:ship_doc_entry_id>')
@login_required
def get_po_shipment_details(ship_doc_entry_id):
    """Get detailed PO and shipment information for a specific shipment"""
    
    try:
        print(f"=== PO Shipment Details API ===")
        print(f"Ship Doc Entry ID: {ship_doc_entry_id}")
        print(f"User ID: {current_user.id}")
        print(f"User Role: {current_user.role}")
        print(f"Company ID: {current_user.company_id}")
        
        company_id = current_user.company_id
        
        # Get shipment information with role-based filtering
        shipment_query = OrderShipment.query.filter_by(
            ship_doc_entry_id=ship_doc_entry_id
        )
        
        # Apply role-based filter for shipments
        if current_user.role == 'customer':
            print(f"User role: Filtering shipment by company_id = {company_id}")
            shipment_query = shipment_query.filter_by(company_id=company_id)
        else:
            print(f"Non-user role: Checking if shipment has POs created by user {current_user.id}")
            # For non-user roles, check if this shipment has any POs created by this user
            user_po_numbers = db.session.query(POHeader.po_number).filter(
                POHeader.created_by == current_user.id
            ).subquery()
            
            # Check if any shipment items belong to this user's POs
            has_user_pos = db.session.query(ShipmentItem).filter(
                ShipmentItem.shipment_id == ship_doc_entry_id,
                ShipmentItem.po_number.in_(user_po_numbers)
            ).first()
            
            if not has_user_pos:
                print(f"No POs created by user {current_user.id} found in shipment {ship_doc_entry_id}")
                return jsonify({'error': 'Shipment not found or access denied'}), 404
        
        shipment = shipment_query.first()
        
        if not shipment:
            print(f"Shipment {ship_doc_entry_id} not found")
            return jsonify({'error': 'Shipment not found'}), 404
        
        print(f"Shipment found: Import ID = {shipment.import_id}")
        
        # Get PO details for this shipment with role-based filtering
        print(f"Getting PO details for shipment...")
        pos_details = get_pos_for_shipment(ship_doc_entry_id, company_id, current_user.role, current_user.id)
        print(f"Found {len(pos_details)} POs in shipment")
        
        shipment_data = {
            'ship_doc_entry_id': shipment.ship_doc_entry_id,
            'import_id': shipment.import_id,
            'vessel': shipment.vessel,
            'voyage': shipment.voyage,
            'eta': shipment.eta.isoformat() if shipment.eta else None,
            'shipment_deadline': shipment.shipment_deadline.isoformat() if shipment.shipment_deadline else None,
            'port_of_loading': shipment.port_of_loading,
            'port_of_discharge': shipment.port_of_discharge,
            'bl_no': shipment.bl_no,
            'cargo_description': shipment.cargo_description,
            'pos': pos_details
        }
        
        print(f"Returning shipment data with {len(pos_details)} POs")
        print(f"=== End PO Shipment Details API ===")
        
        return jsonify(shipment_data)
        
    except Exception as e:
        print(f"ERROR in PO Shipment Details API: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        current_app.logger.error(f"Error fetching PO shipment details: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/po_detail_calendar_data')
@login_required
def get_po_detail_calendar_data():
    """API endpoint to get PO detail calendar data for delivery dates with max 3 unique POs per date"""
    
    try:
        print(f"=== PO Detail Calendar Data API ===")
        print(f"User ID: {current_user.id}")
        print(f"User Role: {current_user.role}")
        print(f"Company ID: {current_user.company_id}")
        
        company_id = current_user.company_id
        
        # Get all PO details that have delivery dates - Fixed GROUP BY clause
        po_details_query = db.session.query(
            PODetail.delivery_date,
            PODetail.po_number,
            PODetail.supplier_name,
            POHeader.po_date,
            POHeader.sysdocnum,
            func.count(PODetail.id).label('item_count'),
            func.sum(PODetail.order_quantity).label('total_quantity'),
            func.sum(PODetail.quantity_received).label('total_received'),
            func.sum(PODetail.quantity_pending).label('total_pending'),
            func.sum(PODetail.line_total).label('total_value')
        ).join(
            POHeader, PODetail.po_header_id == POHeader.id
        ).filter(
            PODetail.delivery_date.isnot(None),
            PODetail.is_completed == False    # Only items with delivery dates
        )
        
        # Apply role-based filter for PO details
        print(f"Applying role-based filter for PO details...")
        if current_user.role == 'customer':
            print(f"User role: Filtering PO details by company_id = {company_id}")
            po_details_query = po_details_query.filter(PODetail.company_id == company_id)
        else:
            print(f"Non-user role: Filtering PO details by created_by = {current_user.id}")
            po_details_query = po_details_query.filter(POHeader.created_by == current_user.id)
        
        # Group by delivery_date, po_number, supplier_name, po_date, sysdocnum to get unique POs per date
        po_details_query = po_details_query.group_by(
            PODetail.delivery_date,
            PODetail.po_number,
            PODetail.supplier_name,
            POHeader.po_date,
            POHeader.sysdocnum
        ).order_by(
            PODetail.delivery_date,
            PODetail.po_number
        )
        
        po_details_data = po_details_query.all()
        print(f"Found {len(po_details_data)} unique PO groups with delivery dates")
        
        # Group by delivery date and limit to 3 unique POs per date
        date_groups = {}
        for po_detail in po_details_data:
            delivery_date = po_detail.delivery_date.isoformat()
            
            if delivery_date not in date_groups:
                date_groups[delivery_date] = []
            
            date_groups[delivery_date].append(po_detail)
        
        print(f"Grouped into {len(date_groups)} delivery dates")
        
        result = []
        
        for delivery_date, pos_for_date in date_groups.items():
            print(f"Processing date {delivery_date} with {len(pos_for_date)} unique POs")
            
            # Limit to maximum 3 unique POs per date
            visible_pos = pos_for_date[:3]
            has_more = len(pos_for_date) > 3
            
            print(f"  Showing {len(visible_pos)} POs, has_more: {has_more}")
            
            # Create events for visible POs
            for i, po_detail in enumerate(visible_pos):
                # Calculate status for this PO
                total_qty = float(po_detail.total_quantity)
                total_received = float(po_detail.total_received or 0)
                
                if total_received == 0:
                    status = 'pending'
                elif total_received >= total_qty:
                    status = 'completed'
                else:
                    status = 'partial'
                
                # Calculate completion percentage
                completion_percentage = 0
                if total_qty > 0:
                    completion_percentage = (total_received / total_qty) * 100
                
                result.append({
                    'id': f"po_detail_{delivery_date}_{po_detail.po_number}_{i}",
                    'po_number': po_detail.po_number,
                    'sysdocnum': po_detail.sysdocnum,
                    'supplier_name': po_detail.supplier_name,
                    'delivery_date': delivery_date,
                    'po_date': po_detail.po_date.isoformat(),
                    'status': status,
                    'completion_percentage': round(completion_percentage, 1),
                    'item_count': po_detail.item_count,
                    'total_quantity': total_qty,
                    'total_received': total_received,
                    'total_pending': float(po_detail.total_pending or 0),
                    'total_value': float(po_detail.total_value or 0),
                    'position_in_date': i + 1,
                    'has_more_pos': has_more and i == len(visible_pos) - 1,  # Show "more" indicator on last visible PO
                    'total_pos_for_date': len(pos_for_date)
                })
        
        print(f"Returning {len(result)} PO detail calendar events")
        print(f"=== End PO Detail Calendar Data API ===")
        return jsonify(result)
        
    except Exception as e:
        print(f"ERROR in PO Detail Calendar Data API: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        current_app.logger.error(f"Error fetching PO detail calendar data: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/po_detail/<int:po_detail_id>')
@login_required
def get_po_detail_info(po_detail_id):
    """API endpoint to get detailed information for a specific PO detail item"""
    
    try:
        print(f"=== PO Detail Info API ===")
        print(f"PO Detail ID: {po_detail_id}")
        print(f"User ID: {current_user.id}")
        print(f"Company ID: {current_user.company_id}")
        
        # Get the PO detail with join to header for additional info
        po_detail_query = db.session.query(
            PODetail,
            POHeader.po_date,
            POHeader.sysdocnum,
            POHeader.total_value,
            POHeader.remarks
        ).join(
            POHeader, PODetail.po_header_id == POHeader.id
        ).filter(
            PODetail.id == po_detail_id
        )
        
        # Apply role-based filter
        if current_user.role == 'customer':
            po_detail_query = po_detail_query.filter(PODetail.company_id == current_user.company_id)
        else:
            po_detail_query = po_detail_query.filter(POHeader.created_by == current_user.id)
        
        po_detail_result = po_detail_query.first()
        
        if not po_detail_result:
            print(f"PO Detail {po_detail_id} not found or access denied")
            return jsonify({'error': 'PO Detail not found or access denied'}), 404
        
        po_detail, po_date, sysdocnum, total_value, remarks = po_detail_result
        
        print(f"PO Detail found: {po_detail.po_number} - {po_detail.material_code}")
        
        # Calculate status and completion percentage
        if po_detail.is_completed:
            status = 'completed'
        elif not po_detail.quantity_received or po_detail.quantity_received == 0:
            status = 'pending'
        elif po_detail.quantity_received > 0 and po_detail.quantity_received < po_detail.order_quantity:
            status = 'partial'
        else:
            status = 'unknown'
        
        completion_percentage = 0
        if po_detail.order_quantity > 0:
            completion_percentage = (float(po_detail.quantity_received or 0) / float(po_detail.order_quantity)) * 100
        
        result = {
            'id': po_detail.id,
            'po_number': po_detail.po_number,
            'sysdocnum': sysdocnum,
            'po_date': po_date.isoformat(),
            'total_value': float(total_value or 0),
            'remarks': remarks,
            'material_code': po_detail.material_code,
            'material_name': po_detail.material_name,
            'item_number': po_detail.item_number,
            'order_quantity': float(po_detail.order_quantity),
            'quantity_received': float(po_detail.quantity_received or 0),
            'quantity_pending': float(po_detail.quantity_pending or 0),
            'delivery_date': po_detail.delivery_date.isoformat() if po_detail.delivery_date else None,
            'order_unit': po_detail.order_unit,
            'net_price': float(po_detail.net_price),
            'line_total': float(po_detail.line_total),
            'supplier_code': po_detail.supplier_code,
            'supplier_name': po_detail.supplier_name,
            'status': status,
            'completion_percentage': round(completion_percentage, 1),
            'is_completed': po_detail.is_completed,
            'created_at': po_detail.created_at.isoformat(),
            'updated_at': po_detail.updated_at.isoformat() if po_detail.updated_at else None
        }
        
        print(f"Returning PO detail info for {po_detail.po_number}")
        print(f"=== End PO Detail Info API ===")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"ERROR in PO Detail Info API: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        current_app.logger.error(f"Error fetching PO detail info: {str(e)}")
        return jsonify({'error': str(e)}), 500


# Backend Route for Calendar Data (add this to your dashboard routes)

from sqlalchemy import func, extract
from datetime import datetime, date

@bp.route('/api/calendar/po-summary')
@login_required
def get_po_calendar_summary():
    """Get summarized PO data for calendar display"""
    try:
        # Base query with role-based filtering
        base_query = db.session.query(
            POHeader.po_date,
            func.count(POHeader.id).label('total_count'),
            func.sum(POHeader.total_value).label('total_value'),
            POHeader.currency
        ).join(PODetail, POHeader.id == PODetail.po_header_id).filter(
            PODetail.is_completed == False  # Only include active POs   
        )    
        
        if current_user.role == 'customer':
            base_query = base_query.filter(POHeader.company_id == current_user.company_id)
        else:
            base_query = base_query.filter(POHeader.created_by == current_user.id)
        
        # Group by date and currency
        summary_data = base_query.group_by(
            POHeader.po_date, 
            POHeader.currency
        ).all()
        
        # Format data for calendar
        calendar_events = []
        date_summary = {}
        
        for item in summary_data:
            date_str = item.po_date.strftime('%Y-%m-%d')
            
            if date_str not in date_summary:
                date_summary[date_str] = {
                    'total_pos': 0,
                    'currencies': {},
                    'date': date_str
                }
            
            date_summary[date_str]['total_pos'] += item.total_count
            if item.currency not in date_summary[date_str]['currencies']:
                date_summary[date_str]['currencies'][item.currency] = 0
            date_summary[date_str]['currencies'][item.currency] += item.total_value
        
        # Create calendar events
        for date_str, summary in date_summary.items():
            total_pos = summary['total_pos']
            
            # Create title with PO count
            if total_pos == 1:
                title = f"{total_pos} Purchase Order"
            else:
                title = f"{total_pos} Purchase Orders"
            
            # Add total value if single currency
            currencies = summary['currencies']
            if len(currencies) == 1:
                currency, value = list(currencies.items())[0]
                title += f"\n{currency} {value:,.2f}"
            elif len(currencies) > 1:
                title += f"\n{len(currencies)} currencies"
            
            calendar_events.append({
                'id': f"po-summary-{date_str}",
                'title': title,
                'start': date_str,
                'end': date_str,
                'className': 'po-summary-event',
                'extendedProps': {
                    'type': 'po_summary',
                    'po_count': total_pos,
                    'currencies': currencies,
                    'date': date_str
                }
            })
        
        return jsonify({
            'success': True,
            'events': calendar_events
        })
        
    except Exception as e:
        print(f"Error getting calendar summary: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@bp.route('/api/po_details_for_date/<date>')
@login_required
def get_po_details_for_date(date):
    """API endpoint to get all individual PO detail items for a specific delivery date with shipment info"""
    
    try:
        print(f"=== PO Details for Date API (Individual Items with Shipment Info) ===")
        print(f"Date: {date}")
        print(f"User ID: {current_user.id}")
        print(f"Company ID: {current_user.company_id}")
        
        # Parse the date
        target_date = datetime.strptime(date, '%Y-%m-%d').date()
        company_id = current_user.company_id
        
        # Get all individual PO detail items for this delivery date
        po_details_query = db.session.query(
            PODetail.id,
            PODetail.po_number,
            PODetail.material_code,
            PODetail.material_name,
            PODetail.item_number,
            PODetail.order_quantity,
            PODetail.quantity_received,
            PODetail.quantity_pending,
            PODetail.order_unit,
            PODetail.net_price,
            PODetail.line_total,
            PODetail.supplier_name,
            PODetail.is_completed,
            POHeader.id.label('po_header_id'),
            POHeader.po_date,
            POHeader.sysdocnum,
            POHeader.currency
        ).join(
            POHeader, PODetail.po_header_id == POHeader.id
        ).filter(
            PODetail.delivery_date == target_date,
            PODetail.is_completed == False  # Only include items that are not completed
        )
        
        # Apply role-based filter
        if current_user.role == 'customer':
            po_details_query = po_details_query.filter(PODetail.company_id == company_id)
        else:
            po_details_query = po_details_query.filter(POHeader.created_by == current_user.id)
        
        # Order by PO number and item number
        po_details_query = po_details_query.order_by(PODetail.po_number, PODetail.item_number)
        
        po_details_data = po_details_query.all()
        print(f"Found {len(po_details_data)} individual PO detail items for date {date}")
        
        items_data = []
        processed_po_headers = {}  # Cache shipment info per PO header
        
        for po_detail in po_details_data:
            # Calculate status for individual item
            order_qty = float(po_detail.order_quantity)
            received_qty = float(po_detail.quantity_received or 0)
            
            if po_detail.is_completed:
                status = 'completed'
                status_class = 'success'
                status_icon = 'ri-check-double-line'
            elif received_qty == 0:
                status = 'pending'
                status_class = 'danger'
                status_icon = 'ri-time-line'
            elif received_qty >= order_qty:
                status = 'completed'
                status_class = 'success'
                status_icon = 'ri-check-double-line'
            else:
                status = 'partial'
                status_class = 'warning'
                status_icon = 'ri-truck-line'
            
            # Calculate completion percentage
            completion_percentage = 0
            if order_qty > 0:
                completion_percentage = (received_qty / order_qty) * 100
            
            # Get shipment info for this PO (cache results per PO header)
            shipment_info = None
            if po_detail.po_header_id not in processed_po_headers:
                processed_po_headers[po_detail.po_header_id] = get_po_shipment_info(po_detail.po_header_id)
            
            shipment_info = processed_po_headers[po_detail.po_header_id]
            
            items_data.append({
                'id': po_detail.id,
                'po_number': po_detail.po_number,
                'po_header_id': po_detail.po_header_id,  # Add this for document modal
                'sysdocnum': po_detail.sysdocnum,
                'po_date': po_detail.po_date.isoformat(),
                'supplier_name': po_detail.supplier_name,
                'material_code': po_detail.material_code,
                'material_name': po_detail.material_name,
                'item_number': po_detail.item_number,
                'order_quantity': order_qty,
                'quantity_received': received_qty,
                'quantity_pending': float(po_detail.quantity_pending or 0),
                'order_unit': po_detail.order_unit,
                'net_price': float(po_detail.net_price),
                'line_total': float(po_detail.line_total),
                'currency': po_detail.currency,
                'status': status,
                'status_class': status_class,
                'status_icon': status_icon,
                'completion_percentage': round(completion_percentage, 1),
                'is_completed': po_detail.is_completed,
                'shipment_info': shipment_info  # Add shipment info for documents
            })
        
        print(f"Returning {len(items_data)} individual PO detail items for date {date}")
        print(f"=== End PO Details for Date API ===")
        
        return jsonify({
            'success': True,
            'date': date,
            'item_count': len(items_data),
            'items': items_data
        })
        
    except Exception as e:
        print(f"ERROR in PO Details for Date API: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        current_app.logger.error(f"Error fetching PO details for date {date}: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/update_delivered_date/<int:po_detail_id>', methods=['POST'])
@login_required
def update_delivered_date(po_detail_id):
    """Update delivered date for a PO detail item."""
    
    print(f"Received request to update delivered date for PO Detail ID: {po_detail_id}")
    
    try:
        delivered_date_str = request.form.get('delivered_date')
        print(f"Delivered Date String from form: {delivered_date_str}")
        
        if not delivered_date_str:
            print("No date provided in request.")
            return jsonify({'success': False, 'message': 'No date provided'}), 400

        try:
            delivered_date = datetime.strptime(delivered_date_str, '%Y-%m-%d').date()
            print(f"Parsed Delivered Date: {delivered_date}")
        except ValueError as e:
            print(f"Invalid date format encountered: {e}")
            return jsonify({'success': False, 'message': 'Invalid date format'}), 400

        # Check if PO detail exists and belongs to the current user's company
        po_detail = PODetail.query.filter_by(
            id=po_detail_id,
            company_id=current_user.company_id  # Add security check
        ).first()
        
        if not po_detail:
            print(f"PO Detail not found or access denied for ID: {po_detail_id}")
            return jsonify({'success': False, 'message': 'PO Detail not found'}), 404

        print(f"PO Detail fetched from DB: ID={po_detail.id}, Current Delivered Date={po_detail.date_delivered}")

        # Update the delivered date
        old_date = po_detail.date_delivered
        po_detail.date_delivered = delivered_date
        po_detail.updated_at = datetime.utcnow()
        
        # If delivered date is set, you might want to update completion status
        # Uncomment the following lines if you want this behavior:
        # if delivered_date and po_detail.quantity_received >= po_detail.order_quantity:
        #     po_detail.is_completed = True

        try:
            db.session.commit()
            print(f"Successfully updated delivered date from {old_date} to {po_detail.date_delivered}")
            print(f"Updated At set to: {po_detail.updated_at}")
            
            return jsonify({
                'success': True, 
                'message': 'Delivered date updated successfully',
                'delivered_date': po_detail.date_delivered.strftime('%Y-%m-%d') if po_detail.date_delivered else None
            })
            
        except Exception as db_error:
            db.session.rollback()
            print(f"Database error occurred: {db_error}")
            return jsonify({'success': False, 'message': 'Database error occurred'}), 500
            
    except Exception as e:
        print(f"Unexpected error occurred: {e}")
        return jsonify({'success': False, 'message': 'An unexpected error occurred'}), 500




@bp.route('/<int:po_id>/update-payment-term', methods=['POST'])
def update_payment_term(po_id):
    """Update payment term for a purchase order"""
    try:
        # Get the payment term from form data
        payment_term = request.form.get('payment_term', '').strip()
        
        # Validate input
        if not payment_term:
            return jsonify({
                'success': False,
                'message': 'Payment term cannot be empty'
            }), 400
            
        if len(payment_term) > 100:
            return jsonify({
                'success': False,
                'message': 'Payment term cannot exceed 500 characters'
            }), 400
        
        # Find the purchase order
        po_header = POHeader.query.get_or_404(po_id)
        
        # Update the payment term
        po_header.payment_term = payment_term
        
        # Commit the changes
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Payment term updated successfully',
            'payment_term': payment_term
        })
        
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Database error occurred while updating payment term'
        }), 500
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'An unexpected error occurred: {str(e)}'
        }), 500








