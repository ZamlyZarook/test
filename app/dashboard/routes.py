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
from app.models.user import User, CountryMaster, CurrencyMaster
from app.models.cha import (
    Customer, Department, ShipmentType, BLStatus, FreightTerm, RequestType, DocumentType, ShippingLine, Terminal, Runner, WharfProfile, Branch, ShipCategory, ShipCatDocument,
    Order, OrderItem, OrderDocument, DocumentStatus, ShipDocumentEntryMaster, ShipDocumentEntryAttachment, ChatThread, ChatMessage, ChatParticipant,ChatAttachment,
    ShipDocumentHistory,OrderShipment, ShipCatDocumentAICheck, ExportContainer, ImportContainer, ShipDocumentEntryDocument, IncomeExpense,
    ShipmentExpense, CompanyAssignment, OsJobType
    )
from app.models.demurrage import DemurrageRateCard, CompanyDemurrageConfig, DemurrageCalculationDetail, DemurrageReasons, ShipmentDemurrage, ShipmentDemurrageAttachment, ShipmentDemurrageBearer, DemurrageRateCardTier
from app.models.company import CompanyInfo
from flask_login import login_required, current_user
from app import db
from app.dashboard import bp
from flask import send_file, make_response
from collections import Counter, defaultdict
from calendar import month_name



@bp.route("/")
@login_required
def dashboard():
    # --- Month Names for Filter (define FIRST) ---
    month_names = [month_name[i] for i in range(1, 13)]  # ['January', ..., 'December']

    print("=" * 60)
    print("=== DASHBOARD ROUTE ACCESSED ===")
    print("=" * 60)
    print(f"Current User ID: {current_user.id}")
    print(f"Current User Role: {current_user.role}")
    print(f"Current User Company ID: {getattr(current_user, 'company_id', 'N/A')}")
    
    # Determine filter based on user role
    shipments = []
    customer = None
    
    if current_user.role == "user":
        company_id = current_user.company_id
        print(f"\n--- USER ROLE PROCESSING ---")
        print(f"Filtering by company_id: {company_id}")
        query = OrderShipment.query.filter_by(company_id=company_id)
        print(f"Initial query created for company_id: {company_id}")
        
    elif current_user.role == "customer":
        print(f"\n--- CUSTOMER ROLE PROCESSING ---")
        print(f"Looking for customer linked to user_id: {current_user.id}")
        customer = Customer.query.filter_by(user_id=current_user.id).first()
        
        if not customer:
            print("❌ ERROR: No customer found for this user.")
            return render_template("dashboard/dashboard.html", 
                                 summary_table=[], pie_labels=[], pie_data=[], 
                                 fcl_pie_labels=[], fcl_pie_data=[], clearance_table=[], 
                                 bar_labels=[], bar_on_time=[], bar_demurrage=[],
                                 cha_performance_table=[], cha_bar_labels=[], cha_bar_data=[],
                                 demurrage_reasons_table=[])
        
        print(f"✅ Customer found - ID: {customer.id}, Name: {customer.customer_name}")
        print(f"Customer Company ID: {customer.company_id}")
        query = OrderShipment.query.filter_by(customer_id=customer.id)
        print(f"Initial query created for customer_id: {customer.id}")
        
    else:
        print(f"\n--- UNKNOWN ROLE: {current_user.role} ---")
        print("❌ ERROR: Unknown role. Access denied or no data.")
        return render_template("dashboard/dashboard.html", 
                             summary_table=[], pie_labels=[], pie_data=[], 
                             fcl_pie_labels=[], fcl_pie_data=[], clearance_table=[], 
                             bar_labels=[], bar_on_time=[], bar_demurrage=[],
                             cha_performance_table=[], cha_bar_labels=[], cha_bar_data=[],
                             demurrage_reasons_table=[])

    # Optional filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    selected_month = request.args.get('month', '')  # This is for the dropdown
    year = request.args.get('year')

    print(f"\n--- DATE FILTERS ---")
    print(f"Start Date: {start_date}")
    print(f"End Date: {end_date}")
    print(f"Month: {selected_month}")
    print(f"Year: {year}")

    # Convert month name to number for filtering
    month = None
    if selected_month:
        if selected_month.isdigit():
            month = int(selected_month)
        else:
            try:
                month = month_names.index(selected_month) + 1
            except ValueError:
                month = None

    if start_date and end_date:
        print(f"✅ Applying date range filter: {start_date} to {end_date}")
        query = query.filter(OrderShipment.created_at >= start_date, OrderShipment.created_at <= end_date)
    elif month and year:
        print(f"✅ Applying month/year filter: {month}/{year}")
        query = query.filter(
            db.extract('month', OrderShipment.created_at) == month,
            db.extract('year', OrderShipment.created_at) == int(year)
        )
    else:
        print("ℹ️ No date filters applied")

    shipments = query.all()
    print(f"\n--- SHIPMENTS DATA ---")
    print(f"Total Shipments Retrieved: {len(shipments)}")
    
    if shipments:
        print("First 3 shipments details:")
        for i, shipment in enumerate(shipments[:3]):
            print(f"  Shipment {i+1}: ID={shipment.id}, Ship_Doc_Entry_ID={shipment.ship_doc_entry_id}")
            print(f"    Job Type: {shipment.job_type}, Company ID: {shipment.company_id}")
            print(f"    Customer ID: {getattr(shipment, 'customer_id', 'N/A')}")
            print(f"    BL No: {shipment.bl_no}, Demurrage: {shipment.is_demurrage}")
            print(f"    Created At: {shipment.created_at}")
    else:
        print("❌ No shipments found with current filters")

    # --- Rest of your existing logic remains the same ---
    job_types = OsJobType.query.all()
    job_type_map = {jt.id: jt.name for jt in job_types}
    print(f"\n--- JOB TYPES ---")
    print(f"Available Job Types: {len(job_types)}")
    print(f"Job Type Map: {job_type_map}")

    job_type_counts = Counter()
    for shipment in shipments:
        if shipment.job_type:
            job_type_counts[shipment.job_type] += 1

    print(f"Job Type Counts from Shipments: {dict(job_type_counts)}")

    summary_table = []
    total_on_time = 0
    total_demurrage = 0
    total_shipments = 0

    print(f"\n--- SUMMARY TABLE PROCESSING ---")
    for jt in job_types:
        jt_shipments = [s for s in shipments if s.job_type == jt.id]
        on_time = sum(1 for s in jt_shipments if not s.is_demurrage)
        demurrage = sum(1 for s in jt_shipments if s.is_demurrage)
        total = on_time + demurrage
        percent = (demurrage / total * 100) if total > 0 else 0

        print(f"  {jt.name} (ID: {jt.id}): On Time={on_time}, Demurrage={demurrage}, Total={total}, Percent={percent:.2f}%")

        summary_table.append({
            'job_type': jt.name,
            'on_time': on_time,
            'demurrage': demurrage,
            'total': total,
            'percent': round(percent, 2)
        })

        total_on_time += on_time
        total_demurrage += demurrage
        total_shipments += total

    total_percent = (total_demurrage / total_shipments * 100) if total_shipments > 0 else 0
    summary_table.append({
        'job_type': 'Total',
        'on_time': total_on_time,
        'demurrage': total_demurrage,
        'total': total_shipments,
        'percent': round(total_percent, 2)
    })

    print(f"TOTAL SUMMARY: On Time={total_on_time}, Demurrage={total_demurrage}, Total={total_shipments}, Percent={total_percent:.2f}%")

    pie_labels = [row['job_type'] for row in summary_table if row['job_type'] != 'Total']
    pie_data = [row['total'] for row in summary_table if row['job_type'] != 'Total']
    print(f"\n--- PIE CHART DATA ---")
    print(f"Pie Labels: {pie_labels}")
    print(f"Pie Data: {pie_data}")

    FCL_JOB_TYPE_ID = 1
    fcl_shipments = [s for s in shipments if s.job_type == FCL_JOB_TYPE_ID]
    fcl_demurrage = sum(1 for s in fcl_shipments if s.is_demurrage)
    fcl_on_time = sum(1 for s in fcl_shipments if not s.is_demurrage)

    fcl_pie_labels = ["Demurrage", "On Time Clearance"]
    fcl_pie_data = [fcl_demurrage, fcl_on_time]
    print(f"\n--- FCL PIE CHART DATA ---")
    print(f"FCL Shipments Count: {len(fcl_shipments)}")
    print(f"FCL Pie Labels: {fcl_pie_labels}")
    print(f"FCL Pie Data: {fcl_pie_data}")

    clearance_table = summary_table.copy()
    bar_labels = [row['job_type'] for row in summary_table if row['job_type'] != 'Total']
    bar_on_time = [row['on_time'] for row in summary_table if row['job_type'] != 'Total']
    bar_demurrage = [row['demurrage'] for row in summary_table if row['job_type'] != 'Total']
    print(f"\n--- BAR CHART DATA ---")
    print(f"Bar Labels: {bar_labels}")
    print(f"Bar On Time: {bar_on_time}")
    print(f"Bar Demurrage: {bar_demurrage}")

    # CHA Performance Data (only for customer role)
    cha_performance_table = []
    cha_bar_labels = []
    cha_bar_data = []
    
    if current_user.role == "customer":
        print(f"\n" + "=" * 50)
        print("=== PROCESSING CHA PERFORMANCE DATA ===")
        print("=" * 50)
        
        # Get all unique company IDs from shipments
        company_ids = list(set([s.company_id for s in shipments if s.company_id]))
        print(f"Unique Company IDs found in shipments: {company_ids}")
        
        # Get company information
        companies = CompanyInfo.query.filter(CompanyInfo.id.in_(company_ids)).all()
        company_map = {c.id: c.company_name for c in companies}
        print(f"Company Map (ID -> Name): {company_map}")
        
        # Group shipments by company and job type
        cha_data = defaultdict(lambda: defaultdict(int))
        
        print(f"\nProcessing {len(shipments)} shipments for CHA data...")
        for i, shipment in enumerate(shipments):
            if shipment.company_id and shipment.job_type:
                company_name = company_map.get(shipment.company_id, f"Company {shipment.company_id}")
                job_type_name = job_type_map.get(shipment.job_type, f"Job Type {shipment.job_type}")
                cha_data[company_name][job_type_name] += 1
                if i < 5:  # Log first 5 for debugging
                    print(f"  Shipment {i+1}: Company={company_name}, Job Type={job_type_name}")
        
        print(f"\nCHA Data Structure:")
        for company_name, job_data in cha_data.items():
            print(f"  {company_name}: {dict(job_data)}")
        
        # Create CHA performance table
        print(f"\nCreating CHA performance table...")
        for company_name in sorted(cha_data.keys()):
            total_shipments = sum(cha_data[company_name].values())
            row = {
                'company_name': company_name,
                'total_shipments': total_shipments,
                'job_types': dict(cha_data[company_name])
            }
            cha_performance_table.append(row)
            print(f"  Added: {company_name} - Total: {total_shipments}, Job Types: {dict(cha_data[company_name])}")
        
        # Prepare data for bar chart
        cha_bar_labels = list(sorted(cha_data.keys()))
        print(f"\nCHA Bar Chart Labels: {cha_bar_labels}")
        
        # Create series data for each job type
        job_type_series = {}
        print(f"\nCreating bar chart series data...")
        for job_type in job_types:
            job_type_series[job_type.name] = []
            for company_name in cha_bar_labels:
                count = cha_data[company_name].get(job_type.name, 0)
                job_type_series[job_type.name].append(count)
            print(f"  {job_type.name}: {job_type_series[job_type.name]}")
        
        # Convert to format expected by ApexCharts
        cha_bar_data = [
            {
                'name': job_type_name,
                'data': counts
            }
            for job_type_name, counts in job_type_series.items()
            if any(counts)  # Only include job types that have data
        ]
        
        print(f"\nFinal CHA Bar Data for ApexCharts:")
        for series in cha_bar_data:
            print(f"  Series: {series['name']} -> Data: {series['data']}")
        
        print(f"\nCHA PERFORMANCE SUMMARY:")
        print(f"  - Performance Table Rows: {len(cha_performance_table)}")
        print(f"  - Bar Chart Labels: {len(cha_bar_labels)}")
        print(f"  - Bar Chart Series: {len(cha_bar_data)}")
    else:
        print(f"\n--- CHA PERFORMANCE SKIPPED ---")
        print(f"Reason: User role is '{current_user.role}', not 'customer'")

    # Demurrage Reasons Data (for both user and customer roles)
    print(f"\n" + "=" * 50)
    print("=== PROCESSING DEMURRAGE REASONS DATA ===")
    print("=" * 50)
    demurrage_reasons_table = []
    
    try:
        # Get all demurrage records that match our shipments (FCL only - job_type = 1)
        # First, get all ship_doc_entry_ids from our filtered shipments where job_type = 1 (FCL)
        fcl_shipments_ids = [s.ship_doc_entry_id for s in shipments if s.job_type == 1]
        print(f"FCL Shipment IDs (job_type=1): {fcl_shipments_ids}")
        print(f"Total FCL Shipments for demurrage check: {len(fcl_shipments_ids)}")
        
        if fcl_shipments_ids:
            print(f"\nQuerying demurrage records for {len(fcl_shipments_ids)} FCL shipments...")
            
            # Get demurrage records for these shipments
            demurrage_query = db.session.query(
                ShipmentDemurrage,
                OrderShipment,
                DemurrageReasons,
                CurrencyMaster
            ).join(
                OrderShipment, ShipmentDemurrage.shipment_id == OrderShipment.ship_doc_entry_id
            ).join(
                DemurrageReasons, ShipmentDemurrage.reason_id == DemurrageReasons.id
            ).join(
                CurrencyMaster, ShipmentDemurrage.currency_id == CurrencyMaster.currencyID
            ).filter(
                ShipmentDemurrage.shipment_id.in_(fcl_shipments_ids),
                OrderShipment.job_type == 1  # FCL only
            )
            
            print(f"Base demurrage query created with joins...")
            
            # Apply same date filters as main query
            if start_date and end_date:
                print(f"Applying date range filter to demurrage query: {start_date} to {end_date}")
                demurrage_query = demurrage_query.filter(
                    OrderShipment.created_at >= start_date, 
                    OrderShipment.created_at <= end_date
                )
            elif month and year:
                print(f"Applying month/year filter to demurrage query: {month}/{year}")
                demurrage_query = demurrage_query.filter(
                    db.extract('month', OrderShipment.created_at) == month,
                    db.extract('year', OrderShipment.created_at) == int(year)
                )
            else:
                print("No additional date filters applied to demurrage query")
            
            demurrage_records = demurrage_query.all()
            print(f"✅ Demurrage Records Found: {len(demurrage_records)}")
            
            # Process demurrage records for the table
            print(f"\nProcessing demurrage records for table display...")
            # 1. Collect all customer_ids from the shipments you are processing
            customer_ids = set()
            for s in shipments:
                if hasattr(s, 'customer_id') and s.customer_id:
                    customer_ids.add(s.customer_id)

            # 2. Fetch all customers in one go
            customers = Customer.query.filter(Customer.id.in_(customer_ids)).all()
            customer_map = {c.id: c for c in customers}

            # 3. Collect all company_ids from these customers
            company_ids = set()
            for c in customers:
                if hasattr(c, 'company_id') and c.company_id:
                    company_ids.add(c.company_id)

            # 4. Fetch all companies in one go
            companies = CompanyInfo.query.filter(CompanyInfo.id.in_(company_ids)).all()
            company_map = {co.id: co.company_name for co in companies}

            for i, (dem_record, shipment, reason, currency) in enumerate(demurrage_records):
                # Get customer and company name
                customer = customer_map.get(getattr(shipment, 'customer_id', None))
                company_name = None
                if customer:
                    company_name = company_map.get(getattr(customer, 'company_id', None), 'N/A')
                else:
                    company_name = 'N/A'

                job_number = shipment.import_id or 'N/A'
                bl_no = shipment.bl_no or 'N/A'
                eta_formatted = shipment.eta.strftime('%d-%m-%Y') if shipment.eta else 'N/A'
                cleared_date_formatted = shipment.cleared_date.strftime('%d-%m-%Y') if shipment.cleared_date else 'N/A'
                demurrage_date_formatted = dem_record.demurrage_date.strftime('%d-%m-%Y') if dem_record.demurrage_date else 'N/A'
                currency_code = currency.CurrencyCode if currency else 'N/A'
                
                row = {
                    'company_name': company_name,  # <-- Add this as the first column
                    'job_number': job_number,
                    'bl_no': bl_no,
                    'consignment': 'FCL',  # Since we're filtering for job_type = 1
                    'eta': eta_formatted,
                    'cleared_date': cleared_date_formatted,
                    'demurrage_amount': f"{dem_record.amount:.2f}",
                    'currency': currency_code,
                    'reason': reason.reason_name,
                    'demurrage_date': demurrage_date_formatted
                }
                demurrage_reasons_table.append(row)
                
                if i < 3:  # Log first 3 records for debugging
                    print(f"  Record {i+1}:")
                    print(f"    Job Number: {job_number}")
                    print(f"    BL No: {bl_no}")
                    print(f"    ETA: {eta_formatted}")
                    print(f"    Cleared Date: {cleared_date_formatted}")
                    print(f"    Demurrage Date: {demurrage_date_formatted}")
                    print(f"    Amount: {dem_record.amount} {currency_code}")
                    print(f"    Reason: {reason.reason_name}")
        else:
            print("❌ No FCL shipments found for demurrage processing")
        
        print(f"\nDEMURRAGE SUMMARY:")
        print(f"  - Total demurrage records processed: {len(demurrage_reasons_table)}")
        print(f"  - FCL shipments checked: {len(fcl_shipments_ids)}")
        
    except Exception as e:
        print(f"❌ ERROR processing demurrage data: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        demurrage_reasons_table = []

    # --- Demurrage Reasons Pie Chart Data ---
    demurrage_reason_counter = Counter()
    for row in demurrage_reasons_table:
        demurrage_reason_counter[row['reason']] += 1

    demurrage_pie_labels = list(demurrage_reason_counter.keys())
    demurrage_pie_data = list(demurrage_reason_counter.values())

    # --- Month Names for Filter ---
    # month_names = [month_name[i] for i in range(1, 13)]  # ['January', ..., 'December'] # This line is now redundant

    print(f"\n" + "=" * 50)
    print("=== FINAL DATA SUMMARY ===")
    print("=" * 50)
    print(f"Summary Table Rows: {len(summary_table)}")
    print(f"Pie Chart Labels: {len(pie_labels)}")
    print(f"Pie Chart Data: {len(pie_data)}")
    print(f"FCL Pie Data: {fcl_pie_data}")
    print(f"Bar Chart Labels: {len(bar_labels)}")
    print(f"CHA Performance Table: {len(cha_performance_table)}")
    print(f"CHA Bar Labels: {len(cha_bar_labels)}")
    print(f"CHA Bar Data Series: {len(cha_bar_data)}")
    print(f"Demurrage Reasons Table: {len(demurrage_reasons_table)}")
    print(f"Job Types: {len(job_types)}")
    print("=" * 50)

    return render_template(
        "dashboard/dashboard.html",
        summary_table=summary_table,
        pie_labels=pie_labels,
        pie_data=pie_data,
        fcl_pie_labels=fcl_pie_labels,
        fcl_pie_data=fcl_pie_data,
        clearance_table=clearance_table,
        bar_labels=bar_labels,
        bar_on_time=bar_on_time,
        bar_demurrage=bar_demurrage,
        cha_performance_table=cha_performance_table,
        cha_bar_labels=cha_bar_labels,
        cha_bar_data=cha_bar_data,
        job_types=job_types,
        demurrage_reasons_table=demurrage_reasons_table,
        demurrage_pie_labels=demurrage_pie_labels,
        demurrage_pie_data=demurrage_pie_data,
        month_names=month_names,
        selected_month=selected_month,
    )




