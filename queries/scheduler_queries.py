# queries/scheduler_queries.py
import sqlite3
from database.helper import execute_read, execute_write

def create_scheduled_task(conversation_id: int, task_prompt: str, execute_at: str, recurrence: str = "none") -> int:
    """Inserts a new scheduled task into the database."""
    query = """
        INSERT INTO scheduled_tasks (conversation_id, task_prompt, execute_at, recurrence, status)
        VALUES (?, ?, ?, ?, 'pending');
    """
    return execute_write(query, (conversation_id, task_prompt, execute_at, recurrence))

def get_due_tasks(current_time_iso: str) -> list[dict]:
    """Retrieves all 'pending' tasks where execute_at is <= now."""
    query = """
        SELECT id, conversation_id, task_prompt, execute_at, recurrence 
        FROM scheduled_tasks 
        WHERE status = 'pending' AND execute_at <= ?
        ORDER BY execute_at ASC;
    """
    return execute_read(query, (current_time_iso,))

def get_all_scheduled_tasks() -> list[dict]:
    """Retrieves ALL non-cancelled scheduled tasks across all conversations."""
    query = """
        SELECT id, conversation_id, task_prompt, execute_at, recurrence, status 
        FROM scheduled_tasks 
        WHERE status != 'cancelled'
        ORDER BY execute_at ASC;
    """
    return execute_read(query)

def update_task_status(task_id: int, status: str) -> None:
    """Updates the status to 'processing', 'completed', or 'failed'."""
    valid_statuses = {"pending", "processing", "completed", "failed"}
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of {valid_statuses}")
    query = "UPDATE scheduled_tasks SET status = ? WHERE id = ?;"
    execute_write(query, (status, task_id))

def reschedule_task(task_id: int, next_execute_at: str) -> None:
    """Rolls a recurring task forward to its next time and sets it back to 'pending'."""
    query = "UPDATE scheduled_tasks SET execute_at = ?, status = 'pending' WHERE id = ?;"
    execute_write(query, (next_execute_at, task_id))

def cancel_task_by_id(task_id: int) -> int:
    """Cancels a task permanently by its ID, regardless of conversation."""
    query = "UPDATE scheduled_tasks SET status = 'cancelled' WHERE id = ?;"
    return execute_write(query, (task_id,))

def update_task_schedule_by_id(task_id: int, execute_at: str, recurrence: str) -> int:
    """Updates a task's schedule by its ID, regardless of conversation."""
    query = """
        UPDATE scheduled_tasks 
        SET execute_at = ?, recurrence = ? 
        WHERE id = ? AND status = 'pending';
    """
    return execute_write(query, (execute_at, recurrence, task_id))

def reset_orphaned_tasks() -> None:
    """Resets tasks stuck in 'processing' back to 'pending' on boot."""
    query = "UPDATE scheduled_tasks SET status = 'pending' WHERE status = 'processing';"
    execute_write(query)