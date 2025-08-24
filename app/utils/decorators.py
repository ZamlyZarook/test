from functools import wraps
from flask import abort
from flask_login import current_user


def company_access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "id" in kwargs:
            model_class = None
            if "model" in kwargs:
                model_class = kwargs["model"]
                del kwargs["model"]
            else:
                # Determine model class based on endpoint
                # Add your logic here
                pass

            if model_class:
                item = model_class.query.get_or_404(kwargs["id"])
                if item.company_id != current_user.company_id:
                    abort(403)
        return f(*args, **kwargs)

    return decorated_function