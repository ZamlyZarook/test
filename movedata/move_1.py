import sqlite3


def copy_table_data(source_db, destination_db, table_name):
    """Copy data from a specific table in source DB to destination DB."""
    try:
        # Connect to source and destination databases
        source_conn = sqlite3.connect(source_db)
        dest_conn = sqlite3.connect(destination_db)

        # Get column names from source table
        source_cursor = source_conn.cursor()
        source_cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in source_cursor.fetchall()]
        if not columns:
            print(f"Error: Table '{table_name}' does not exist in source database.")
            return

        column_names = ", ".join(columns)
        placeholders = ", ".join(["?" for _ in columns])

        # Fetch data from source table
        source_cursor.execute(f"SELECT {column_names} FROM {table_name}")
        rows = source_cursor.fetchall()

        if not rows:
            print(f"No data found in table '{table_name}', skipping.")
            return

        # Insert data into destination table
        dest_cursor = dest_conn.cursor()
        dest_cursor.executemany(
            f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})", rows
        )
        dest_conn.commit()

        print(f"Successfully copied {len(rows)} rows from '{table_name}'.")

    except sqlite3.Error as e:
        print(f"Error: {e}")
    finally:
        source_conn.close()
        dest_conn.close()


# Specify databases and table name
SOURCE_DB = "appb.db"  # Replace with actual source DB path
DESTINATION_DB = "app.db"  # Replace with actual destination DB path
TABLE_NAME = "user"  # Replace with the table you want to copy

# Run the data migration
copy_table_data(SOURCE_DB, DESTINATION_DB, TABLE_NAME)
