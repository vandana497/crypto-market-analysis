"""
Run this first after setting up .env and creating the database (schema.sql)
to confirm Python can actually reach your MySQL instance.

    python test_db_connection.py
"""

from src.db import test_connection

if __name__ == "__main__":
    if test_connection():
        print("Connected to MySQL successfully.")
    else:
        print("Connection failed - check MYSQL_* values in your .env and that MySQL is running.")
