from flask_sqlalchemy import SQLAlchemy
from app import app, db
from app.models import User, Scheme, Coupon, Redemption, Revenue


def init_db():
    with app.app_context():
        # Create all database tables
        db.create_all()

        # Create admin user if it doesn't exist
        admin = User.query.filter_by(email="admin@admin.com").first()
        if not admin:
            admin = User(
                email="admin@admin.com",
                username="admin",
                role="admin",
            )
            admin.set_password("admin123")  # Set password using the method
            db.session.add(admin)
            db.session.commit()


if __name__ == "__main__":
    init_db()
