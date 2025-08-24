# po_import.py - Enhanced import functionality with flexible column mapping
import pandas as pd
from datetime import datetime
from app import db
from app.models.po import PurchaseOrder, POStatus, POTracking, POAlert
from app.models.user import User
import os
import tempfile
from werkzeug.utils import secure_filename

def create_column_mapping():
    """Create flexible column mapping to handle different Excel formats"""
    return {
        # Required columns with possible variations - INCLUDING YOUR EXACT COLUMN NAMES
        'po_number': [
            'Purchasing Document', 'PO No', 'PO Number', 'Purchase Order Number', 'Purchase Order No', 
            'PO_No', 'po_no', 'po_number', 'PurchaseOrderNumber'
        ],
        'po_line_item': [
            'Item', 'PO Line Item', 'Line Item', 'Line', 'PO Item',
            'po_line_item', 'line_item', 'item_number'
        ],
        'po_date': [
            'Document Date', 'PO Date', 'Purchase Order Date', 'Order Date', 'Date',
            'po_date', 'order_date', 'purchase_date'
        ],
        'supplier_name': [
            'Supplier/Supplying Plant', 'Supplier', 'Supplier Name', 'Vendor', 'Vendor Name', 
            'supplier_name', 'vendor_name', 'supplier', 'Supplying Plant'
        ],
        'supplier_code': [
            'Supplier Code', 'Vendor Code', 'Supplier ID', 'Vendor ID',
            'supplier_code', 'vendor_code', 'supplier_id'
        ],
        'total_value': [
            'Net Price', 'Value', 'Total Value', 'Amount', 'Total Amount', 'Price',
            'value', 'total_value', 'amount', 'net_value'
        ],
        'currency': [
            'Currency', 'Curr', 'currency', 'curr'
        ],
        'inco_term': [
            'Inco Term', 'Incoterm', 'Inco Terms', 'Terms',
            'inco_term', 'incoterm', 'delivery_terms'
        ],
        'payment_term': [
            'Payment Term', 'Payment Terms', 'Pay Terms',
            'payment_term', 'payment_terms', 'pay_terms'
        ],
        'delivery_date': [
            'Delivery Date', 'PO delivery date', 'Due Date', 'Expected Date',
            'delivery_date', 'due_date', 'expected_delivery_date'
        ],
        # Optional columns - INCLUDING YOUR EXACT COLUMN NAMES
        'material_code': [
            'Material', 'Material Code', 'Item Code', 'Product Code', 'SKU',
            'material_code', 'item_code', 'product_code'
        ],
        'material_description': [
            'Short Text', 'Material Description', 'Description', 'Item Description',
            'material_description', 'description', 'item_description'
        ],
        'order_quantity': [
            'Order Quantity', 'Quantity', 'Qty', 'Order Qty',
            'order_quantity', 'quantity', 'qty'
        ],
        'order_unit': [
            'Order Unit', 'Unit', 'UOM', 'Unit of Measure',
            'order_unit', 'unit', 'uom'
        ],
        'quantity_received': [
            'Quantity Received', 'Received Qty', 'Received',
            'quantity_received', 'received_qty', 'received'
        ],
        'still_to_deliver': [
            'Still to be delivered (qty)', 'Still to Deliver', 'Remaining Qty', 'Balance', 'Outstanding',
            'still_to_deliver', 'remaining_qty', 'balance'
        ],
        'net_price': [
            'Net Price', 'Unit Price', 'Price per Unit',
            'net_price', 'unit_price', 'price_per_unit'
        ],
        'license_required': [
            'License', 'License Required', 'License Req',
            'license', 'license_required', 'license_req'
        ],
        'teip_required': [
            'TEIP', 'TEIP Required', 'TEIP Req',
            'teip', 'teip_required', 'teip_req'
        ],
        'bank_info': [
            'Bank', 'Bank Info', 'Bank Information',
            'bank', 'bank_info', 'bank_information'
        ],
        'country_port': [
            'Country /Port', 'Country', 'Port', 'Country/Port',
            'country_port', 'country', 'port', 'origin'
        ]
    }

def map_columns(df, column_mapping):
    """Map actual column names to expected column names"""
    mapped_columns = {}
    available_columns = df.columns.tolist()
    
    print(f"Available columns in Excel: {available_columns}")
    
    for target_col, possible_names in column_mapping.items():
        found = False
        for possible_name in possible_names:
            # Check for exact match (case insensitive)
            for actual_col in available_columns:
                if actual_col.strip().lower() == possible_name.strip().lower():
                    mapped_columns[target_col] = actual_col
                    found = True
                    break
            if found:
                break
        
        if not found:
            print(f"Warning: Could not find column for '{target_col}' in {possible_names}")
    
    print(f"Mapped columns: {mapped_columns}")
    return mapped_columns

def validate_excel_structure(df):
    """Validate if Excel has required columns with flexible mapping"""
    column_mapping = create_column_mapping()
    mapped_columns = map_columns(df, column_mapping)
    
    # Define absolutely required columns
    required_fields = [
        'po_number', 'supplier_name', 'total_value', 'delivery_date'
    ]
    
    missing_columns = []
    for field in required_fields:
        if field not in mapped_columns:
            missing_columns.append(f"{field} (tried: {', '.join(column_mapping[field])})")
    
    return len(missing_columns) == 0, missing_columns, mapped_columns

def clean_excel_data(df, mapped_columns):
    """Clean and prepare Excel data for import using mapped columns"""
    print("Starting data cleaning...")
    
    # Create new DataFrame with mapped column names
    cleaned_df = pd.DataFrame()
    
    # Map each column
    for target_col, source_col in mapped_columns.items():
        if source_col in df.columns:
            cleaned_df[target_col] = df[source_col]
    
    # Handle date columns
    date_columns = ['po_date', 'delivery_date']
    for col in date_columns:
        if col in cleaned_df.columns:
            print(f"Converting {col} to datetime...")
            cleaned_df[col] = pd.to_datetime(cleaned_df[col], errors='coerce')
    
    # Handle numeric columns
    numeric_columns = ['total_value', 'order_quantity', 'quantity_received', 'still_to_deliver', 'net_price']
    for col in numeric_columns:
        if col in cleaned_df.columns:
            print(f"Converting {col} to numeric...")
            # Remove any currency symbols or commas
            if cleaned_df[col].dtype == 'object':
                cleaned_df[col] = cleaned_df[col].astype(str).str.replace(',', '').str.replace('$', '').str.replace('€', '').str.replace('£', '')
            cleaned_df[col] = pd.to_numeric(cleaned_df[col], errors='coerce')
    
    # Set defaults for missing columns
    defaults = {
        'po_line_item': '10',
        'currency': 'USD',
        'inco_term': '',
        'payment_term': '',
        'license_required': False,
        'teip_required': False,
        'bank_info': '',
        'country_port': '',
        'material_code': '',
        'material_description': '',
        'order_quantity': 1,
        'order_unit': 'EA',
        'quantity_received': 0,
        'net_price': 0
    }
    
    for col, default_value in defaults.items():
        if col not in cleaned_df.columns:
            cleaned_df[col] = default_value
    
    # Generate supplier_code from supplier_name if not provided
    if 'supplier_code' not in cleaned_df.columns and 'supplier_name' in cleaned_df.columns:
        print("Generating supplier codes from supplier names...")
        cleaned_df['supplier_code'] = cleaned_df['supplier_name'].apply(
            lambda x: ''.join([word[:3].upper() for word in str(x).split()[:2]]) if pd.notna(x) else 'UNK'
        )
    
    # Calculate still_to_deliver if not provided
    if 'still_to_deliver' not in cleaned_df.columns:
        cleaned_df['still_to_deliver'] = cleaned_df.get('order_quantity', 1) - cleaned_df.get('quantity_received', 0)
    
    # Calculate total_value if not provided (Net Price * Order Quantity)
    if 'total_value' not in cleaned_df.columns:
        print("Calculating total_value from net_price * order_quantity...")
        cleaned_df['total_value'] = cleaned_df.get('net_price', 0) * cleaned_df.get('order_quantity', 1)
    
    # Ensure net_price is set properly
    if 'net_price' not in cleaned_df.columns or cleaned_df['net_price'].isna().all():
        cleaned_df['net_price'] = cleaned_df['total_value'] / cleaned_df.get('order_quantity', 1)
    
    # Convert boolean fields
    boolean_fields = ['license_required', 'teip_required']
    for field in boolean_fields:
        if field in cleaned_df.columns:
            cleaned_df[field] = cleaned_df[field].astype(str).str.lower().isin(['true', '1', 'yes', 'y', 'x'])
    
    # Fill NaN values
    cleaned_df = cleaned_df.fillna({
        'currency': 'USD',
        'inco_term': '',
        'payment_term': '',
        'bank_info': '',
        'country_port': '',
        'material_code': '',
        'material_description': '',
        'order_unit': 'EA'
    })
    
    print(f"Cleaned DataFrame shape: {cleaned_df.shape}")
    print(f"Cleaned DataFrame columns: {cleaned_df.columns.tolist()}")
    
    return cleaned_df

def create_default_statuses():
    """Create default PO statuses based on requirements"""
    default_statuses = [
        # License Workflow
        {'name': 'License Application Submitted', 'category': 'license', 'order': 1},
        {'name': 'License Pending', 'category': 'license', 'order': 2},
        {'name': 'License Received', 'category': 'license', 'order': 3},
        
        # TEIP Workflow
        {'name': 'TEIP Application Submitted', 'category': 'teip', 'order': 4},
        {'name': 'TEIP Pending', 'category': 'teip', 'order': 5},
        {'name': 'TEIP Approved', 'category': 'teip', 'order': 6},
        
        # Shipping Workflow
        {'name': 'Shipping Documents Fully Received', 'category': 'shipping', 'order': 7},
        {'name': 'Shipping Documents Partially Received', 'category': 'shipping', 'order': 8},
        {'name': 'Shipment Updated - Vessel/ETD/ETA', 'category': 'shipping', 'order': 9},
        {'name': 'Shipping Document Delay', 'category': 'shipping', 'order': 10},
        
        # Bank Workflow
        {'name': 'Bank - Internal Signatures', 'category': 'bank', 'order': 11},
        {'name': 'Bank - Submitted to Bank', 'category': 'bank', 'order': 12},
        {'name': 'Bank - Endorsement Obtained', 'category': 'bank', 'order': 13},
        
        # Clearance Workflow
        {'name': 'Pending Clearance', 'category': 'clearance', 'order': 14},
        {'name': 'Cleared', 'category': 'clearance', 'order': 15},
        
        # Logistics Workflow
        {'name': 'Inland Logistics - Yard', 'category': 'logistics', 'order': 16},
        {'name': 'Inland Logistics - Warehouse', 'category': 'logistics', 'order': 17},
        {'name': 'Inland Logistics - Factory', 'category': 'logistics', 'order': 18},
        {'name': 'Inland Logistics - 3PL', 'category': 'logistics', 'order': 19},
        {'name': 'Delivered', 'category': 'logistics', 'order': 20},
        
        # CHA Workflow
        {'name': 'Clearing Bill Received', 'category': 'cha', 'order': 21},
        {'name': 'Clearing Bill Processing', 'category': 'cha', 'order': 22},
        {'name': 'Clearing Bill Completed', 'category': 'cha', 'order': 23},
        
        # Container & Freight
        {'name': 'Container Deposits - Submitted', 'category': 'container', 'order': 24},
        {'name': 'Container Deposits - Processing', 'category': 'container', 'order': 25},
        {'name': 'Container Deposits - Completed', 'category': 'container', 'order': 26},
        
        {'name': 'Freight Invoice - Submitted', 'category': 'freight', 'order': 27},
        {'name': 'Freight Invoice - Processing', 'category': 'freight', 'order': 28},
        {'name': 'Freight Invoice - Completed', 'category': 'freight', 'order': 29},
        
        # Insurance Claims
        {'name': 'Damaged Cargo - NCR Signed', 'category': 'insurance', 'order': 30},
        {'name': 'Insurance - Submitted', 'category': 'insurance', 'order': 31},
        {'name': 'Insurance - Processing', 'category': 'insurance', 'order': 32},
        {'name': 'Insurance - Completed', 'category': 'insurance', 'order': 33},
    ]
    
    for status_info in default_statuses:
        existing = POStatus.query.filter_by(status_name=status_info['name']).first()
        if not existing:
            status = POStatus(
                status_name=status_info['name'],
                status_category=status_info['category'],
                order_sequence=status_info['order']
            )
            db.session.add(status)
    
    db.session.commit()

def import_po_data(file_path, company_id, default_buyer_id=None):
    """Import PO data from Excel file with flexible column mapping"""
    try:
        print(f"Starting import from: {file_path}")
        
        # Read Excel file
        df = pd.read_excel(file_path)
        print(f"Excel file read successfully. Shape: {df.shape}")
        print(f"Original columns: {df.columns.tolist()}")
        
        # Validate structure and get column mapping
        is_valid, missing_cols, mapped_columns = validate_excel_structure(df)
        if not is_valid:
            return False, f"Missing required columns: {', '.join(missing_cols)}"
        
        # Clean data using mapped columns
        df = clean_excel_data(df, mapped_columns)
        print(f"Data cleaned successfully. Final shape: {df.shape}")
        
        success_count = 0
        error_count = 0
        errors = []
        
        # Get default status (first status)
        default_status = POStatus.query.first()
        
        for index, row in df.iterrows():
            try:
                print(f"Processing row {index + 1}...")
                
                # Check if PO already exists (check combination of PO number and line item)
                po_number = str(row.get('po_number', ''))
                po_line_item = str(row.get('po_line_item', '10'))
                
                if not po_number:
                    error_count += 1
                    errors.append(f"Row {index + 2}: Missing PO Number")
                    continue
                
                existing_po = PurchaseOrder.query.filter_by(
                    po_number=po_number,
                    po_line_item=po_line_item,
                    company_id=company_id
                ).first()
                
                if existing_po:
                    # Update existing PO
                    po = existing_po
                    print(f"Updating existing PO: {po_number}-{po_line_item}")
                else:
                    # Create new PO
                    po = PurchaseOrder()
                    print(f"Creating new PO: {po_number}-{po_line_item}")
                
                # Map Excel columns to PO fields safely
                po.po_number = po_number
                po.po_line_item = po_line_item
                po.po_date = row.get('po_date') if pd.notna(row.get('po_date')) else datetime.now()
                po.supplier_name = str(row.get('supplier_name', ''))
                po.supplier_code = str(row.get('supplier_code', ''))
                po.total_value = float(row.get('total_value', 0))
                po.currency = str(row.get('currency', 'USD'))
                po.inco_term = str(row.get('inco_term', ''))
                po.payment_term = str(row.get('payment_term', ''))
                po.delivery_date = row.get('delivery_date') if pd.notna(row.get('delivery_date')) else datetime.now()
                po.company_id = company_id
                po.buyer_id = default_buyer_id
                
                # Handle optional fields
                po.license_required = bool(row.get('license_required', False))
                po.teip_required = bool(row.get('teip_required', False))
                po.bank_info = str(row.get('bank_info', ''))
                po.country_port = str(row.get('country_port', ''))
                
                # Set material information
                po.material_code = str(row.get('material_code', ''))
                po.material_description = str(row.get('material_description', ''))
                po.order_quantity = float(row.get('order_quantity', 1))
                po.quantity_received = float(row.get('quantity_received', 0))
                po.still_to_deliver = float(row.get('still_to_deliver', po.order_quantity))
                po.net_price = float(row.get('net_price', po.total_value))
                po.order_unit = str(row.get('order_unit', 'EA'))
                
                # Set default status if new PO
                if not existing_po:
                    po.current_status_id = default_status.id if default_status else None
                
                po.updated_at = datetime.utcnow()
                
                if not existing_po:
                    db.session.add(po)
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                error_msg = f"Row {index + 2}: {str(e)}"
                errors.append(error_msg)
                print(f"Error processing row {index + 1}: {str(e)}")
                continue
        
        # Commit all changes
        db.session.commit()
        print(f"Import completed. Success: {success_count}, Errors: {error_count}")
        
        return True, {
            'success_count': success_count,
            'error_count': error_count,
            'errors': errors[:10]  # Return first 10 errors
        }
        
    except Exception as e:
        db.session.rollback()
        print(f"Import failed with exception: {str(e)}")
        return False, f"Import failed: {str(e)}"

def update_po_delivery_alerts():
    """Update delivery alerts for all POs"""
    try:
        # Get all POs that need alerts
        current_date = datetime.now()
        
        # Find overdue POs
        overdue_pos = PurchaseOrder.query.filter(
            PurchaseOrder.delivery_date < current_date
        ).all()
        
        # Find POs due within 7 days
        from datetime import timedelta
        due_soon_pos = PurchaseOrder.query.filter(
            PurchaseOrder.delivery_date >= current_date,
            PurchaseOrder.delivery_date <= current_date + timedelta(days=7)
        ).all()
        
        # Create alerts for overdue POs
        for po in overdue_pos:
            days_overdue = (current_date - po.delivery_date).days
            
            # Check if alert already exists for today
            existing_alert = POAlert.query.filter_by(
                po_id=po.id,
                alert_type='overdue'
            ).filter(
                POAlert.alert_date >= current_date.date()
            ).first()
            
            if not existing_alert:
                alert = POAlert(
                    po_id=po.id,
                    alert_type='overdue',
                    alert_message=f"PO {po.po_number} is {days_overdue} days overdue",
                    recipient_id=po.buyer_id
                )
                db.session.add(alert)
        
        # Create alerts for due soon POs
        for po in due_soon_pos:
            days_until = (po.delivery_date - current_date).days
            
            existing_alert = POAlert.query.filter_by(
                po_id=po.id,
                alert_type='due_soon'
            ).filter(
                POAlert.alert_date >= current_date.date()
            ).first()
            
            if not existing_alert:
                alert = POAlert(
                    po_id=po.id,
                    alert_type='due_soon',
                    alert_message=f"PO {po.po_number} is due in {days_until} days",
                    recipient_id=po.buyer_id
                )
                db.session.add(alert)
        
        db.session.commit()
        return True
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating delivery alerts: {str(e)}")
        return False

def generate_sample_excel_template():
    """Generate a sample Excel template for PO import"""
    sample_data = {
        'PO No': ['4700000001', '4700000002'],
        'PO Line Item': ['10', '10'],
        'PO Date': ['2024-01-15', '2024-01-20'],
        'Supplier': ['ABC Supplier Ltd', 'XYZ Manufacturing'],
        'Supplier Code': ['SUP001', 'SUP002'],
        'Material Code': ['MAT001', 'MAT002'],
        'Material Description': ['Raw Material A', 'Component B'],
        'Order Quantity': [100, 200],
        'Order Unit': ['EA', 'KG'],
        'Quantity Received': [0, 0],
        'Still to Deliver': [100, 200],
        'Net Price': [50.00, 25.00],
        'Value': [5000.00, 5000.00],
        'Currency': ['USD', 'USD'],
        'Inco Term': ['FOB', 'CIF'],
        'Payment Term': ['Net 30', 'Net 45'],
        'PO delivery date': ['2024-03-15', '2024-03-20'],
        'License': [True, False],
        'TEIP': [False, True],
        'Bank': ['Bank A', 'Bank B'],
        'Country /Port': ['Singapore', 'Shanghai']
    }
    
    df = pd.DataFrame(sample_data)
    
    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    df.to_excel(temp_file.name, index=False)
    return temp_file.name