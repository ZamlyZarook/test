from app import create_app, db
from app.models import Merchant


def create_test_merchants():
    app = create_app()

    with app.app_context():
        # Create test merchants if they don't exist
        test_merchants = [
            {
                "merchant_code": "M001",
                "name": "Test Merchant 1",
                "address": "123 Test Street",
                "country": "Test Country",
                "email": "merchant1@test.com",
                "website": "www.merchant1.com",
                "contact_number": "1234567890",
                "is_active": True,
            },
            {
                "merchant_code": "M002",
                "name": "Test Merchant 2",
                "address": "456 Test Avenue",
                "country": "Test Country",
                "email": "merchant2@test.com",
                "website": "www.merchant2.com",
                "contact_number": "0987654321",
                "is_active": True,
            },
        ]

        for merchant_data in test_merchants:
            # Check if merchant already exists
            existing_merchant = Merchant.query.filter_by(
                merchant_code=merchant_data["merchant_code"]
            ).first()

            if not existing_merchant:
                merchant = Merchant(**merchant_data)
                db.session.add(merchant)

        try:
            db.session.commit()
            print("Test merchants created successfully!")
        except Exception as e:
            db.session.rollback()
            print(f"Error creating test merchants: {str(e)}")


if __name__ == "__main__":
    create_test_merchants()
