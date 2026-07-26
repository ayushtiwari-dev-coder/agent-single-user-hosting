# tests/test_database.py
import pytest
import os
from database.connection import get_connection, DATABASE_PATH
from database.table_generator import create_tables


def test_database_initialization():
    """Validates that database tables are initialized, file exists, and run is safe repeatedly."""
    # 1. Run the table generation code
    try:
        create_tables()
    except Exception as e:
        pytest.fail(f"create_tables() failed on initial run: {e}")

    # 2. Verify that the database file actually exists at the correct path
    assert os.path.exists(
        DATABASE_PATH
    ), f"Database file was not created at '{DATABASE_PATH}'."

    # 3. Query SQLite system table to verify the expected tables exist
    expected_tables = {
        "users",
        "projects",
        "tasks",
        "conversations",
        "messages",
        "memories",
        "model_usage",
        "tool_logs",
        "summaries",
        "memory_categories",
    }

    conn = get_connection()
    try:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = {row["name"] for row in cursor.fetchall()}

        missing_tables = expected_tables - existing_tables
        assert (
            not missing_tables
        ), f"Missing expected tables in database: {missing_tables}"
    finally:
        conn.close()

    # 4. Run create_tables() again to verify it is safe to run multiple times
    try:
        create_tables()
    except Exception as e:
        pytest.fail(f"create_tables() is not safe to run repeatedly: {e}")
