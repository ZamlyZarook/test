from flask import current_app, render_template
from flask_mail import Message
from threading import Thread
from datetime import datetime
from app import mail
from app.utils import get_sri_lanka_time


def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)


def send_email(subject, recipient, template, **kwargs):
    msg = Message(
        subject,
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
        recipients=[recipient],
    )

    # Add the current year to the template context
    kwargs["current_year"] = get_sri_lanka_time().year

    msg.html = render_template(template, **kwargs)

    # Send email asynchronously
    Thread(
        target=send_async_email, args=(current_app._get_current_object(), msg)
    ).start()


def send_transaction_confirmation(user, transaction, wallet):
    send_email(
        subject="ZALVO - Transaction Confirmation",
        recipient=user.email,
        template="email/transaction_confirmation.html",
        user=user,
        transaction=transaction,
        wallet=wallet,
    )
