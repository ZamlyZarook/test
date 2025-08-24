from datetime import datetime, timedelta, date
from sqlalchemy import and_
from app.utils import get_sri_lanka_time
from app.models.demurrage import NonWorkingDay, CompanyDemurrageConfig
from app.models.company import CompanyInfo
from app.models.cha import OrderShipment
from app import db


def is_working_day(check_date, country_id):
    """
    Check if a given date is a working day for a specific country
    Returns True if it's a working day, False if it's a non-working day
    """
    non_working_day = NonWorkingDay.query.filter(
        and_(
            NonWorkingDay.date == check_date,
            NonWorkingDay.country_id == country_id,
            NonWorkingDay.is_active == True
        )
    ).first()
    
    return non_working_day is None

def calculate_demurrage_start_date(eta_date, country_id, free_days=3):
    """
    Calculate the date when demurrage starts based on ETA and free working days
    
    Args:
        eta_date: The ETA date of the shipment
        country_id: Country ID to check non-working days
        free_days: Number of free working days (default: 3)
    
    Returns:
        Date when demurrage starts
    """
    print(f"Calculating demurrage start date for ETA: {eta_date}, Country ID: {country_id}")
    
    current_date = eta_date.date() if isinstance(eta_date, datetime) else eta_date
    working_days_counted = 0
    
    print(f"Starting from ETA date: {current_date}")
    
    while working_days_counted < free_days:
        current_date += timedelta(days=1)
        
        if is_working_day(current_date, country_id):
            working_days_counted += 1
            print(f"Working day #{working_days_counted}: {current_date}")
        else:
            print(f"Non-working day skipped: {current_date}")
    
    # The demurrage starts at the beginning of the next working day
    demurrage_start_date = current_date + timedelta(days=1)
    
    # Find the next working day if the calculated date falls on a non-working day
    while not is_working_day(demurrage_start_date, country_id):
        demurrage_start_date += timedelta(days=1)
        print(f"Demurrage start date adjusted (non-working day): {demurrage_start_date}")
    
    print(f"Final demurrage start date: {demurrage_start_date}")
    return demurrage_start_date

def daily_demurrage_check():
    """
    Main function to run daily at 12:01 AM Sri Lanka time
    Checks all shipments and updates demurrage status
    """
    print("=" * 50)
    print("DAILY DEMURRAGE CHECK STARTED")
    print("=" * 50)
    
    # Configuration
    
    try:
        # Get current Sri Lankan time and date
        current_sri_lanka_time = get_sri_lanka_time()
        current_date = current_sri_lanka_time.date()
        
        print(f"Current Sri Lanka time: {current_sri_lanka_time}")
        print(f"Current date: {current_date}")
        
        # Get all shipments that are not yet marked for demurrage
        shipments = OrderShipment.query.filter(
            OrderShipment.is_demurrage == False
        ).all()
        
        print(f"Found {len(shipments)} shipments to check for demurrage")
        
        demurrage_count = 0
        
        for shipment in shipments:
            print(f"\n--- Checking Shipment ID: {shipment.id} ---")
            print(f"BL Number: {shipment.bl_no}")
            print(f"Vessel: {shipment.vessel}")
            print(f"ETA: {shipment.eta}")
            print(f"Company ID: {shipment.company_id}")
            
            # Skip if ETA is None
            if not shipment.eta:
                print("Skipping: ETA is None")
                continue
            
            # Get company information to find country
            company = CompanyInfo.query.get(shipment.company_id)
            if not company:
                print(f"Warning: Company not found for ID {shipment.company_id}")
                continue

            country_id = company.country
            print(f"Company: {company.company_name}")
            print(f"Country ID: {country_id}")

            Country_demurrage_data = (
                CompanyDemurrageConfig.query
                .filter_by(country_id=country_id, is_active=True)
                .first()
            )

            if Country_demurrage_data:
                FREE_DEMURRAGE_DAYS = Country_demurrage_data.demurrage_days_threshold
                print(f"Free demurrage days for country: {FREE_DEMURRAGE_DAYS}")
            else:
                FREE_DEMURRAGE_DAYS = 3  # or some default value
                print("No specific demurrage config found, using default 3 days")

            
            
            
            # Calculate when demurrage should start for this shipment
            demurrage_start_date = calculate_demurrage_start_date(
                shipment.eta, 
                country_id, 
                FREE_DEMURRAGE_DAYS
            )
            
            print(f"Demurrage starts on: {demurrage_start_date}")
            print(f"Current date: {current_date}")
            
            # Check if current date is on or after demurrage start date
            if current_date >= demurrage_start_date:
                print(f"DEMURRAGE TRIGGERED for Shipment ID: {shipment.id}")
                
                # Update the shipment to mark it as in demurrage
                shipment.is_demurrage = True
                shipment.updated_at = current_sri_lanka_time
                shipment.demurrage_from = demurrage_start_date
                
                demurrage_count += 1
                
                print(f"Updated shipment {shipment.id} - is_demurrage set to True")
            else:
                days_remaining = (demurrage_start_date - current_date).days
                print(f"Not in demurrage yet. {days_remaining} days remaining.")
        
        # Commit all changes to database
        if demurrage_count > 0:
            db.session.commit()
            print(f"\nDatabase updated successfully!")
            print(f"Total shipments moved to demurrage: {demurrage_count}")
        else:
            print(f"\nNo shipments moved to demurrage today.")
        
        print("\n" + "=" * 50)
        print("DAILY DEMURRAGE CHECK COMPLETED SUCCESSFULLY")
        print("=" * 50)
        
        return {
            'success': True,
            'message': f'Demurrage check completed. {demurrage_count} shipments updated.',
            'shipments_updated': demurrage_count,
            'total_checked': len(shipments)
        }
        
    except Exception as e:
        print(f"ERROR in daily demurrage check: {str(e)}")
        db.session.rollback()
        
        print("\n" + "=" * 50)
        print("DAILY DEMURRAGE CHECK FAILED")
        print("=" * 50)
        
        return {
            'success': False,
            'message': f'Error occurred: {str(e)}',
            'shipments_updated': 0,
            'total_checked': 0
        }

# Optional: Function to manually trigger the check (useful for testing)
def manual_demurrage_check():
    """
    Manual trigger for demurrage check - useful for testing
    """
    print("MANUAL DEMURRAGE CHECK TRIGGERED")
    return daily_demurrage_check()

# Optional: Function to check specific shipment demurrage status
def check_shipment_demurrage_status(shipment_id):
    """
    Check demurrage status for a specific shipment
    """
    print(f"Checking demurrage status for shipment ID: {shipment_id}")
    
    shipment = OrderShipment.query.get(shipment_id)
    if not shipment:
        print(f"Shipment not found: {shipment_id}")
        return None
    
    company = CompanyInfo.query.get(shipment.company_id)
    if not company:
        print(f"Company not found for shipment: {shipment_id}")
        return None
    
    if not shipment.eta:
        print(f"ETA not set for shipment: {shipment_id}")
        return None
    
    demurrage_start_date = calculate_demurrage_start_date(
        shipment.eta, 
        company.country, 
        3
    )
    
    current_date = get_sri_lanka_time().date()
    
    return {
        'shipment_id': shipment_id,
        'eta': shipment.eta,
        'demurrage_start_date': demurrage_start_date,
        'current_date': current_date,
        'is_in_demurrage': current_date >= demurrage_start_date,
        'is_demurrage_flag': shipment.is_demurrage
    }