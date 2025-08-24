from app import create_app, db
from app.models import User
from sqlalchemy import text

app = create_app()

with app.app_context():
    # Drop all tables
    db.drop_all()

    # Drop alembic_version table manually using the new syntax
    with db.engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        conn.commit()

    # Create all tables
    db.create_all()

    # Create admin user
    admin = User(
        username="admin@mail.com",
        email="admin@mail.com",
        role="admin",
        status="active",
        # Add empty merchant fields for admin
        merchant_code=None,
        company_name=None,
        address=None,
        country=None,
        contact_number=None,
        website=None,
    )
    admin.set_password("admin123")

    # Add to database
    db.session.add(admin)
    db.session.commit()

    print("Database reset complete!")
    print("Admin user created:")
    print("Username: admin@mail.com")
    print("Email: admin@mail.com")
    print("Password: admin123")
