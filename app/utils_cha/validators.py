import os
from werkzeug.utils import secure_filename
from flask import current_app


def validate_file(file):
    """
    Validate uploaded file based on allowed extensions and size
    Returns: (is_valid, error_message)
    """
    if not file:
        return False, "No file selected"

    # Get file extension
    filename = secure_filename(file.filename)
    file_ext = os.path.splitext(filename)[1].lower()

    # Check file extension
    allowed_extensions = current_app.config.get(
        "ALLOWED_EXTENSIONS", {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"}
    )
    if file_ext not in allowed_extensions:
        return (
            False,
            f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}",
        )

    # Check file size (default 10MB)
    max_size = current_app.config.get("MAX_CONTENT_LENGTH", 10 * 1024 * 1024)
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > max_size:
        return False, f"File too large. Maximum size is {max_size / (1024 * 1024)}MB"

    return True, None
