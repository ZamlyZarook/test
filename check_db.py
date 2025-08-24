import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

# Load environment variables from .env
load_dotenv()

# Read database config from environment
DB_USER = os.environ.get("DB_USER", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_HOST = os.environ.get("DB_HOST", "")
DB_NAME = os.environ.get("DB_NAME", "")

# Construct SQLAlchemy URI
DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

# Create engine for checking connection
engine = create_engine(DATABASE_URI)

try:
    # Try connecting
    with engine.connect() as connection:
        # Optional: check if database exists
        result = connection.execute("SELECT * FROM user;")
        print("✅ Database connection successful!")
except OperationalError as e:
    # If database doesn't exist, try creating it
    if "Unknown database" in str(e):
        print(f"⚠️ Database '{DB_NAME}' does not exist. Attempting to create it...")
        # Connect without specifying database
        engine_no_db = create_engine(f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}")
        try:
            with engine_no_db.connect() as conn:
                conn.execute(f"CREATE DATABASE {DB_NAME};")
            print(f"✅ Database '{DB_NAME}' created successfully!")
        except Exception as create_err:
            print("❌ Failed to create database:", create_err)
    else:
        print("❌ Database connection failed:", e)
