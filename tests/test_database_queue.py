# tests/test_database_queue.py
import pytest
import tempfile
import os
import threading
from unittest.mock import patch
import database.helper
from database.helper import execute_write, execute_read


@pytest.fixture(autouse=True)
def clean_queue_worker_sandbox():
    """Ensures that each test has its own isolated SQLite DatabaseWorker thread."""
    # 1. Cleanly shut down any existing background worker thread
    if hasattr(database.helper, "_db_worker") and database.helper._db_worker.is_alive():
        database.helper._db_worker.stop()
        database.helper._db_worker.join(timeout=2.0)

    # 2. Create fresh temp SQLite db file
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db_path = temp_db.name
    temp_db.close()

    # 3. Patch connection path
    db_path_patcher = patch("database.connection.DATABASE_PATH", temp_db_path)
    db_path_patcher.start()

    # 4. Generate SQLite schemas
    from database.table_generator import create_tables

    create_tables()

    # 5. Spin up a fresh local worker strictly bound to the sandboxed path
    database.helper._db_worker = database.helper.DatabaseWorker()
    database.helper._db_worker.start()

    yield temp_db_path

    # Tear Down
    if database.helper._db_worker.is_alive():
        database.helper._db_worker.stop()
        database.helper._db_worker.join(timeout=2.0)

    db_path_patcher.stop()
    try:
        os.remove(temp_db_path)
    except OSError:
        pass


def test_concurrent_database_writes_through_queue():
    """Verifies that multiple concurrent threads can issue write queries safely without lockups."""
    num_threads = 20
    results = []
    threads = []

    # Thread task: Insert unique user
    def write_task(thread_id):
        try:
            query = "INSERT INTO users (name, username) VALUES (?, ?);"
            execute_write(query, (f"Worker_{thread_id}", f"user_uname_{thread_id}"))
            results.append(True)
        except Exception as e:
            results.append(e)

    # Spawn concurrent tasks
    for i in range(num_threads):
        t = threading.Thread(target=write_task, args=(i,))
        threads.append(t)
        t.start()

    # Join threads
    for t in threads:
        t.join()

    # Check that every thread completed successfully
    for idx, res in enumerate(results):
        assert res is True, f"Thread {idx} failed with error: {res}."

    # Verify exact count through the worker
    users = execute_read("SELECT COUNT(*) as total FROM users;", fetch_one=True)
    assert users["total"] == num_threads
