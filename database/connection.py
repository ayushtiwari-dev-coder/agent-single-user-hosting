import os
import sqlite3

# 1. Dynamically locate the user's home directory (works on Windows, Mac, and Linux)
HOME_DIR = os.path.expanduser("~")

# 2. Define the hidden folder path inside the home directory
APP_DIR = os.path.join(HOME_DIR, ".local_workflow_agent")

# 3. Path to the database file inside the hidden folder
DATABASE_PATH = os.path.join(APP_DIR, "assistant.db")


def get_connection() -> sqlite3.Connection:
    """
    Creates and returns a connection to the SQLite database.
    Ensures the central hidden directory exists before connecting.
    """
    try:
        # Create the hidden folder if it does not exist yet
        os.makedirs(APP_DIR, exist_ok=True)

        # Connect to the central database file
        conn = sqlite3.connect(DATABASE_PATH)

        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.row_factory = sqlite3.Row

        return conn

    except (sqlite3.Error, OSError) as e:
        raise RuntimeError(f"Failed to connect to database: {e}") from e
