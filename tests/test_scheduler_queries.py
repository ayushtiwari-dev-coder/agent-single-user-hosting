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
    get_all_scheduled_tasks,
    cancel_task_by_id,
    update_task_schedule_by_id,
    reset_orphaned_tasks
)

@pytest.fixture(autouse=True)
def temp_db_sandbox():
    """Sandboxes database connections for scheduler tests."""
    import database.helper
    
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db_path = temp_db.name
    temp_db.close()
    
    db_patcher = patch("database.connection.DATABASE_PATH", temp_db_path)
    db_patcher.start()
    
    if not hasattr(database.helper, "_db_worker") or not database.helper._db_worker.is_alive():
        database.helper._db_worker = database.helper.DatabaseWorker()
        database.helper._db_worker.start()
        
    create_tables()
    
    user = create_user("Test User", "testuser")
    conv = create_conversation(user["id"], "Test Chat")
    
    yield conv["id"]
    
    db_patcher.stop()
    try:
        os.remove(temp_db_path)
    except OSError:
        pass

def test_create_and_get_all_tasks(temp_db_sandbox):
    """Ensures tasks are created and retrieved globally."""
    conv_id = temp_db_sandbox
    task_id = create_scheduled_task(conv_id, "Drink water", "2026-07-28T10:00:00", "daily")
    
    tasks = get_all_scheduled_tasks()
    assert len(tasks) == 1
    assert tasks[0]["id"] == task_id
    assert tasks[0]["task_prompt"] == "Drink water"
    assert tasks[0]["recurrence"] == "daily"

def test_get_due_tasks(temp_db_sandbox):
    """Ensures only pending tasks past their execute_at time are fetched."""
    conv_id = temp_db_sandbox
    create_scheduled_task(conv_id, "Past Task", "2026-07-20T10:00:00")
    create_scheduled_task(conv_id, "Future Task", "2026-07-30T10:00:00")
    
    due_tasks = get_due_tasks("2026-07-25T10:00:00")
    assert len(due_tasks) == 1
    assert due_tasks[0]["task_prompt"] == "Past Task"

def test_update_task_status_and_validation(temp_db_sandbox):
    """Ensures status updates work and invalid statuses raise ValueError."""
    conv_id = temp_db_sandbox
    task_id = create_scheduled_task(conv_id, "Test", "2026-07-28T10:00:00")
    
    update_task_status(task_id, "completed")
    tasks = get_all_scheduled_tasks()
    assert tasks[0]["status"] == "completed"
    
    with pytest.raises(ValueError, match="Invalid status"):
        update_task_status(task_id, "hacked_status")

def test_reschedule_task(temp_db_sandbox):
    """Ensures rescheduling updates the time and resets status to pending."""
    conv_id = temp_db_sandbox
    task_id = create_scheduled_task(conv_id, "Test", "2026-07-28T10:00:00")
    
    update_task_status(task_id, "completed")
    reschedule_task(task_id, "2026-07-29T10:00:00")
    
    tasks = get_all_scheduled_tasks()
    assert len(tasks) == 1
    assert tasks[0]["execute_at"] == "2026-07-29T10:00:00"
    assert tasks[0]["status"] == "pending"

def test_cancel_task_by_id(temp_db_sandbox):
    """Ensures cancelling by task_id marks status as cancelled."""
    conv_id = temp_db_sandbox
    task_id = create_scheduled_task(conv_id, "Test", "2026-07-28T10:00:00")
    
    rows_affected = cancel_task_by_id(task_id)
    assert rows_affected == 1
    # get_all_scheduled_tasks excludes cancelled tasks
    assert len(get_all_scheduled_tasks()) == 0

def test_update_task_schedule_by_id(temp_db_sandbox):
    """Ensures updating schedule by task_id works globally."""
    conv_id = temp_db_sandbox
    task_id = create_scheduled_task(conv_id, "Test", "2026-07-28T10:00:00", "none")
    
    rows = update_task_schedule_by_id(task_id, "2026-07-29T10:00:00", "daily")
    assert rows == 1
    
    task = get_all_scheduled_tasks()[0]
    assert task["execute_at"] == "2026-07-29T10:00:00"
    assert task["recurrence"] == "daily"

def test_reset_orphaned_tasks(temp_db_sandbox):
    """Ensures tasks stuck in 'processing' are reset to 'pending' on boot."""
    conv_id = temp_db_sandbox
    task1 = create_scheduled_task(conv_id, "Task 1", "2026-07-28T10:00:00")
    task2 = create_scheduled_task(conv_id, "Task 2", "2026-07-28T10:00:00")
    
    update_task_status(task1, "processing")
    
    reset_orphaned_tasks()
    
    pending_tasks = get_all_scheduled_tasks()
    assert len(pending_tasks) == 2
    assert pending_tasks[0]["status"] == "pending"
    assert pending_tasks[1]["status"] == "pending"