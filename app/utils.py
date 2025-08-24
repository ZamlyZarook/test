from functools import wraps
from flask import abort
from flask_login import current_user


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role_id not in [1, 2]:
            abort(403)
        return f(*args, **kwargs)

    return decorated_function


def generate_merchant_code():
    import random
    import string

    prefix = "M"  # Add a prefix to make it clear this is a merchant code
    # Generate a random 7-character string (digits and uppercase letters)
    random_part = "".join(random.choices(string.ascii_uppercase + string.digits, k=7))
    return f"{prefix}{random_part}"  # Combine prefix and random part


def generate_scheme_id():
    import random
    import string

    return "SCH-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def generate_coupon_code():
    import random
    import string

    return "".join(random.choices(string.ascii_uppercase + string.digits, k=10))





from datetime import datetime, timedelta

# Simple timezone offset approach - No external packages needed
def get_sri_lanka_time():
    """
    Get current time in Sri Lanka timezone
    Sri Lanka is UTC+5:30 (5 hours and 30 minutes ahead of UTC)
    """
    
    # Step 1: Get UTC time
    utc_now = datetime.utcnow()
    
    # Step 2: Create offset
    sri_lanka_offset = timedelta(hours=5, minutes=30)
    
    # Step 3: Apply offset
    sri_lanka_time = utc_now + sri_lanka_offset
    
    # Step 4: Show the difference
    time_difference = sri_lanka_time - utc_now
    
    return sri_lanka_time