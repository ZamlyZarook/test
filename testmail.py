#!/usr/bin/env python3
# testmail.py - Super simple script to send a test email

from flask import Flask
from flask_mail import Mail, Message
from app import create_app

if __name__ == "__main__":
    # Create the Flask app
    app = create_app()
    mail = Mail(app)
    
    # Email details
    recipient = "asifmohamed915@gmail.com"
    subject = "ZALVO - Test Email"
    body = "This is a test email from the ZALVO application."
    
    with app.app_context():
        print("Sending test email...")
        
        # Create a simple message
        msg = Message(
            subject=subject,
            recipients=[recipient],
            body=body,
            sender=app.config["MAIL_DEFAULT_SENDER"]
        )
        
        # Send it directly
        mail.send(msg)
        
        print(f"Email sent to {recipient}!")