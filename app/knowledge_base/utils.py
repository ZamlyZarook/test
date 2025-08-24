# blueprints/data_sync/utils.py

import mysql.connector
import pyodbc
from sqlalchemy import create_engine
from ..models import Credential, Database
from ..crypto_utils import decrypt_message
from flask import current_app
from .. import db
from flask_login import current_user

def get_db_connection(connection_name, database=None):
    """
    Establish a database connection using encrypted credentials from the database.
    """
    try:
        # Get encrypted credentials from database
        credential = Credential.query.filter_by(connection_name=connection_name).first()
        if not credential:
            raise ValueError(f"No credentials found for connection: {connection_name}")

        # Decrypt credentials using crypto_utils
        try:
            decrypted_host = decrypt_message(credential.host)
            decrypted_user = decrypt_message(credential.user)
            decrypted_password = decrypt_message(credential.password)
        except Exception as e:
            raise Exception(f"Error decrypting credentials: {str(e)}")

        db_type = credential.db_type.name if hasattr(credential.db_type, 'name') else credential.db_type

        if db_type.upper() == "MYSQL":
            connection = mysql.connector.connect(
                host=decrypted_host,
                user=decrypted_user,
                password=decrypted_password,
                database=database if database else None
            )
            return connection
        
        elif db_type.upper() == "SQL SERVER":
            if database:
                connection_string = f"DRIVER={{SQL Server}};SERVER={decrypted_host};DATABASE={database};UID={decrypted_user};PWD={decrypted_password}"
            else:
                connection_string = f"DRIVER={{SQL Server}};SERVER={decrypted_host};UID={decrypted_user};PWD={decrypted_password}"
            connection = pyodbc.connect(connection_string)
            return connection
        
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
            
    except Exception as e:
        raise Exception(f"Error establishing database connection: {str(e)}")

def get_connection_details(connection_name):
    """
    Retrieve and decrypt connection details for a given connection name.
    """
    try:
        credential = Credential.query.filter_by(connection_name=connection_name).first()
        if not credential:
            raise ValueError(f"No credentials found for connection: {connection_name}")

        # Decrypt credentials using crypto_utils
        try:
            decrypted_host = decrypt_message(credential.host)
            decrypted_user = decrypt_message(credential.user)
            decrypted_password = decrypt_message(credential.password)
        except Exception as e:
            raise Exception(f"Error decrypting credentials: {str(e)}")

        return {
            'host': decrypted_host,
            'user': decrypted_user,
            'password': decrypted_password,
            'db_type': credential.db_type.name if hasattr(credential.db_type, 'name') else credential.db_type,
            'base_api_endpoint': credential.base_api_endpoint
        }
    except Exception as e:
        raise Exception(f"Error retrieving connection details: {str(e)}")

def get_table_columns(connection_name, database, table):
    """Get columns for a specific table."""
    try:
        conn = None
        try:
            conn = get_db_connection(connection_name, database)
            details = get_connection_details(connection_name)
            db_type = details['db_type']

            if db_type.upper() == "MYSQL":
                cursor = conn.cursor()
                cursor.execute(f"SHOW COLUMNS FROM {table}")
                columns = [column[0] for column in cursor.fetchall()]
                return columns

            elif db_type.upper() == "SQL SERVER":
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT COLUMN_NAME 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_NAME = '{table}'
                """)
                columns = [row[0] for row in cursor.fetchall()]
                return columns

        finally:
            if conn:
                conn.close()

    except Exception as e:
        raise Exception(f"Error getting table columns: {str(e)}")

def get_tables(connection_name, database):
    """Get all tables from a database with improved error handling."""
    conn = None
    try:
        conn = get_db_connection(connection_name, database)
        details = get_connection_details(connection_name)
        db_type = details['db_type']

        if db_type.upper() == "MYSQL":
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            tables = [table[0] for table in cursor.fetchall()]
            return tables

        elif db_type.upper() == "SQL SERVER":
            cursor = conn.cursor()
            cursor.execute("""
                SELECT TABLE_NAME 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_TYPE = 'BASE TABLE'
            """)
            tables = [row[0] for row in cursor.fetchall()]
            return tables
        
        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    except Exception as e:
        print(f"Error in get_tables: {str(e)}")  # Debug logging
        raise
    
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                print(f"Error closing connection: {str(e)}") 
                
def check_access(connection):
    if current_user.role_id == 1:  # Admin
        return True
    elif current_user.role_id == 5:  # Company Admin
        return connection.company == current_user.company_id
    elif current_user.role_id == 2:  # Developer
        # Check user connection map
        has_access = UserConnectionMap.query.filter_by(
            user_id=current_user.id,
            connection_id=connection.id
        ).first()
        return has_access is not None
    return False