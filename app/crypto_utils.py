# crypto_utils.py
from cryptography.fernet import Fernet
from flask import current_app
import os

def get_encryption_key():
    """Get the encryption key from Flask app configuration."""
    try:
        # Get the key from Flask app config
        key = current_app.config.get('ENCRYPTION_KEY')
        if not key:
            raise ValueError("ENCRYPTION_KEY not found in app configuration")
        
        # Ensure the key is in bytes format
        if isinstance(key, str):
            key = key.encode()
        
        return key
    except Exception as e:
        raise Exception(f"Error getting encryption key: {str(e)}")

def encrypt_message(message: str) -> str:
    """Encrypt a message."""
    key = get_encryption_key()
    f = Fernet(key)
    encrypted_message = f.encrypt(message.encode())
    return encrypted_message.decode()

def decrypt_message(encrypted_message: str) -> str:
    """Decrypt a message."""
    key = get_encryption_key()
    f = Fernet(key)
    decrypted_message = f.decrypt(encrypted_message.encode())
    return decrypted_message.decode()