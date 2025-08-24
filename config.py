import os
from dotenv import load_dotenv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Basic Flask config
    SECRET_KEY = 'ggJZNyqinNWe8VwOnaczTOExzJ7Z8Mng_g6iiUr4ojU='
    
    # Encryption key for database credentials (same as SECRET_KEY for simplicity)
    ENCRYPTION_KEY = 'ggJZNyqinNWe8VwOnaczTOExzJ7Z8Mng_g6iiUr4ojU='

    # Database config - Force SQLite
    # SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(basedir, "app.db")
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "root")
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_NAME = os.environ.get("DB_NAME", "navitrax")
    
    # Construct the database URI
    SQLALCHEMY_DATABASE_URI = f'mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}'
    
    STRIPE_PUBLIC_KEY = os.environ.get("STRIPE_PUBLIC_KEY")
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")

    # Mail config
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")

    # Security config
    SECURITY_PASSWORD_SALT = os.getenv("SECURITY_PASSWORD_SALT", "your-salt-here")
    SECURITY_REGISTERABLE = True
    SECURITY_SEND_REGISTER_EMAIL = True
    SECURITY_LOGIN_URL = "/login"
    SECURITY_LOGOUT_URL = "/logout"

    DEEPSEEK_API_KEY = "sk-c32b5df704424ae5a520b73c53f9af22"
    DEEPSEEK_API_URL = "https://api.deepseek.com/v1"

    # Upload config
    UPLOAD_FOLDER = os.path.join("app", "static", "uploads")
    QRCODE_FOLDER = os.path.join("app", "static", "uploads", "qrcodes")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

    TEMPLATES_AUTO_RELOAD = True
    SEND_FILE_MAX_AGE_DEFAULT = 0

    # AWS S3 Configuration
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION")
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
    S3_BASE_FOLDER = os.getenv("S3_BASE_FOLDER")     
    S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL") 


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
