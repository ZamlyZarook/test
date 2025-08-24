from functools import wraps
from flask import jsonify, request, redirect, url_for, render_template
from flask_login import current_user


def admin_required(f):
    """
    Decorator to ensure the user is an admin
    Returns 403 if user is not an admin
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Please log in to access this resource.",
                        }
                    ),
                    401,
                )
            return redirect(url_for("auth.login"))

        if not current_user.is_admin:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "You do not have permission to access this resource.",
                        }
                    ),
                    403,
                )
            return (
                render_template(
                    "errors/unauthorized.html",
                    message="You do not have permission to access this page.",
                ),
                403,
            )

        return f(*args, **kwargs)

    return decorated_function
