from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_admin import Admin
from flask_mail import Mail
from flask_bcrypt import Bcrypt

# Initialize Flask extensions
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
flask_admin = Admin(template_mode="bootstrap4")
mail = Mail()
bcrypt = Bcrypt()

# Configure login manager
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "info"


# Add the user loader here
@login_manager.user_loader
def load_user(user_id):
    from app.models.user import User  # Import here to avoid circular imports

    return User.query.get(int(user_id))
