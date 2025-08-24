from app import create_app, db
import os
import shutil


def reset_migrations():
    app = create_app()

    with app.app_context():
        # Drop all tables
        db.drop_all()

        # Remove migrations folder
        if os.path.exists("migrations"):
            shutil.rmtree("migrations")

        # Remove SQLite database
        if os.path.exists("app.db"):
            os.remove("app.db")

        # Create all tables
        db.create_all()

        print("Database reset complete!")


if __name__ == "__main__":
    reset_migrations()
