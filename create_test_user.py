from app import create_app, db
from app.models import User


def create_test_data():
    app = create_app()

    with app.app_context():
        # Create test user
        user = User(
            username="admin@gmail.com",
            email="admin@gmail.com",
            role="super_admin",
            is_active="active",
            role_id=1
        )
        user.set_password("admin123")

        # Add to database
        db.session.add(user)
        db.session.commit()

        print("Test user created successfully!")
        print("Email: admin@gmail.com")
        print("Password: admin123")


if __name__ == "__main__":
    create_test_data()
