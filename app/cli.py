import click
from flask.cli import with_appcontext
from app import db
from app.models import User


def register_commands(app):
    @app.cli.command("create-admin")
    @click.argument("email")
    @click.argument("password")
    def create_admin(email, password):
        """Create an admin user."""
        user = User(username=email.split("@")[0], email=email, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created admin user: {email}")
