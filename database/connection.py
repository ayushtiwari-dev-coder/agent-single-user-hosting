# database/connection.py
import os
import sqlite3

# Define storage directory relative to project root
APP_DIR = os.environ.get("AGENT_STORAGE_DIR", os.path.abspath("./agent_data"))
DATABASE_PATH = os.path.join(APP_DIR, "assistant.db")

def get_connection() -> sqlite3.Connection:
    """Creates and returns a connection to the SQLite database."""
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.row_factory = sqlite3.Row
        return conn
    except (sqlite3.Error, OSError) as e:
        raise RuntimeError(f"Failed to connect to database: {e}") from e