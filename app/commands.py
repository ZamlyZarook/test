import click
from flask.cli import with_appcontext
from app import db
from app.models import User


@click.command("create-admin")
@with_appcontext
def create_admin():
    """Create a default admin user"""
    # Check if admin already exists
    admin = User.query.filter_by(username="admin").first()
    if admin:
        click.echo("Admin user already exists!")
        return

    # Create admin user with default credentials
    admin = User(
        username="admin", email="admin@example.com", role="admin", status="active"
    )
    admin.set_password("admin123")

    # Add to database
    db.session.add(admin)
    db.session.commit()

    click.echo("Admin user created successfully!")
    click.echo("Username: admin")
    click.echo("Email: admin@example.com")
    click.echo("Password: admin123")
    click.echo("Please change these credentials after first login!")
