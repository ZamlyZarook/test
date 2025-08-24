import sqlite3

# Paths to databases
SOURCE_DB = "appnew.db"  # Database with data
DESTINATION_DB = "app.db"  # Database with possible existing data

def get_table_names(conn):
    """Retrieve all table names from the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    return tables

def get_columns(conn, table_name):
    """Retrieve column names for a given table."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}  # row[1] contains column names

def copy_data(source_db, destination_db):
    """Copy data from source DB to destination DB, skipping duplicates."""
    source_conn = sqlite3.connect(source_db)
    dest_conn = sqlite3.connect(destination_db)

    source_tables = get_table_names(source_conn)
    dest_tables = get_table_names(dest_conn)

    # Identify common tables
    common_tables = source_tables & dest_tables

    if not common_tables:
        print("No matching tables found between the databases.")
        return

    print(f"Tables found in both databases: {common_tables}")

    for table in common_tables:
        try:
            print(f"Copying data from table: {table}...")

            # Fetch column names from both databases
            source_columns = get_columns(source_conn, table)
            dest_columns = get_columns(dest_conn, table)

            # Only use columns that exist in both source and destination
            common_columns = list(source_columns & dest_columns)

            if not common_columns:
                print(f"Skipping {table}: No matching columns found.")
                continue

            column_names = ", ".join(common_columns)
            placeholders = ", ".join(["?" for _ in common_columns])

            # Fetch data from source table (only common columns)
            source_cursor = source_conn.cursor()
            source_cursor.execute(f"SELECT {column_names} FROM {table}")
            rows = source_cursor.fetchall()

            if not rows:
                print(f"Skipping {table}: No data to copy.")
                continue

            # Insert data into destination table (ignoring duplicates)
            dest_cursor = dest_conn.cursor()
            dest_cursor.executemany(
                f"INSERT OR IGNORE INTO {table} ({column_names}) VALUES ({placeholders})", rows
            )
            dest_conn.commit()

            print(f"Successfully copied {len(rows)} rows into {table}.")

        except sqlite3.Error as e:
            print(f"Error copying data from {table}: {e}")

    # Close connections
    source_conn.close()
    dest_conn.close()
    print("Data migration complete.")

# Run the migration
copy_data(SOURCE_DB, DESTINATION_DB)
