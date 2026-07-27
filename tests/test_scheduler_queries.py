# tests/test_scheduler_queries.py
import pytest
import tempfile
import os
from unittest.mock import patch
from database.table_generator import create_tables
from queries.user_queries import create_user
from queries.conversation_queries import create_conversation
from queries.scheduler_queries import (
    create_scheduled_task,
    get_due_tasks,
    update_task_status,
    reschedule_task,
    get_tasks_by_conversation,
    cancel_task,
    update_task_schedule
)

@pytest.fixture(autouse=True)
def temp_db_sandbox():
    """Sandboxes database connections for scheduler tests."""
    import database.helper  # <-- ADD THIS IMPORT
    
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db_path = temp_db.name
    temp_db.close()
    
    db_patcher = patch("database.connection.DATABASE_PATH", temp_db_path)
    db_patcher.start()
    
    # --- THE FIX: Revive the Database Worker if a previous test killed it ---
    if not hasattr(database.helper, "_db_worker") or not database.helper._db_worker.is_alive():
        database.helper._db_worker = database.helper.DatabaseWorker()
        database.helper._db_worker.start()
    
    create_tables()
    
    # Create a dummy user and conversation to satisfy Foreign Key constraints
    user = create_user("Test User", "testuser")
    conv = create_conversation(user["id"], "Test Chat")
    
    yield conv["id"]  # Yield the conversation_id for tests to use
    
    db_patcher.stop()
    try:
        os.remove(temp_db_path)
    except OSError:
        pass

def test_create_and_get_tasks(temp_db_sandbox):
    """Ensures tasks are created and retrieved correctly."""
    conv_id = temp_db_sandbox
    task_id = create_scheduled_task(conv_id, "Drink water", "2026-07-28T10:00:00", "daily")
    
    tasks = get_tasks_by_conversation(conv_id)
    assert len(tasks) == 1
    assert tasks[0]["id"] == task_id
    assert tasks[0]["task_prompt"] == "Drink water"
    assert tasks[0]["recurrence"] == "daily"

def test_get_due_tasks(temp_db_sandbox):
    """Ensures only pending tasks that are past their execute_at time are fetched."""
    conv_id = temp_db_sandbox
    # Task 1: Due (Past)
    create_scheduled_task(conv_id, "Past Task", "2026-07-20T10:00:00")
    # Task 2: Not Due (Future)
    create_scheduled_task(conv_id, "Future Task", "2026-07-30T10:00:00")
    
    # Check at a time between the two
    due_tasks = get_due_tasks("2026-07-25T10:00:00")
    
    assert len(due_tasks) == 1
    assert due_tasks[0]["task_prompt"] == "Past Task"

def test_update_task_status_and_validation(temp_db_sandbox):
    """Ensures status updates work and invalid statuses are rejected."""
    conv_id = temp_db_sandbox
    task_id = create_scheduled_task(conv_id, "Test", "2026-07-28T10:00:00")
    
    update_task_status(task_id, "completed")
    
    # Completed tasks should no longer appear in 'pending' lists
    assert len(get_tasks_by_conversation(conv_id)) == 0
    
    # Invalid status should throw ValueError
    with pytest.raises(ValueError, match="Invalid status"):
        update_task_status(task_id, "hacked_status")

def test_reschedule_task(temp_db_sandbox):
    """Ensures rescheduling updates the time and resets status to pending."""
    conv_id = temp_db_sandbox
    task_id = create_scheduled_task(conv_id, "Test", "2026-07-28T10:00:00")
    
    # Simulate worker marking it completed
    update_task_status(task_id, "completed")
    
    # Reschedule it
    reschedule_task(task_id, "2026-07-29T10:00:00")
    
    # Should be pending again and visible
    tasks = get_tasks_by_conversation(conv_id)
    assert len(tasks) == 1
    assert tasks[0]["execute_at"] == "2026-07-29T10:00:00"

def test_cancel_task_security(temp_db_sandbox):
    """Ensures tasks can only be cancelled if the conversation_id matches."""
    conv_id = temp_db_sandbox
    task_id = create_scheduled_task(conv_id, "Test", "2026-07-28T10:00:00")
    
    # Try to cancel with WRONG conversation_id
    rows_affected = cancel_task(task_id, conversation_id=999)
    assert rows_affected == 0
    assert len(get_tasks_by_conversation(conv_id)) == 1 # Still there
    
    # Try to cancel with CORRECT conversation_id
    rows_affected = cancel_task(task_id, conversation_id=conv_id)
    assert rows_affected == 1
    assert len(get_tasks_by_conversation(conv_id)) == 0 # Gone from pending

def test_update_task_schedule_security(temp_db_sandbox):
    """Ensures manual schedule modifications respect conversation_id."""
    conv_id = temp_db_sandbox
    task_id = create_scheduled_task(conv_id, "Test", "2026-07-28T10:00:00", "none")
    
    # Wrong conversation_id
    rows = update_task_schedule(task_id, 999, "2026-07-29T10:00:00", "daily")
    assert rows == 0
    
    # Correct conversation_id
    rows = update_task_schedule(task_id, conv_id, "2026-07-29T10:00:00", "daily")
    assert rows == 1
    
    task = get_tasks_by_conversation(conv_id)[0]
    assert task["execute_at"] == "2026-07-29T10:00:00"
    assert task["recurrence"] == "daily"