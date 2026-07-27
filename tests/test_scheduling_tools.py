# tests/test_scheduling_tools.py
import pytest
from unittest.mock import patch
from tools.scheduling_tools import (
    schedule_task,
    list_scheduled_tasks,
    cancel_scheduled_task,
    modify_scheduled_task
)

# --- schedule_task Tests ---

@patch("tools.scheduling_tools.create_scheduled_task", return_value=42)
def test_schedule_task_success(mock_create):
    """Happy path: Valid ISO string schedules successfully."""
    res = schedule_task("Drink water", "2026-07-28T10:00:00", "daily", conversation_id=1)
    assert "Success" in res
    assert "42" in res
    mock_create.assert_called_once_with(1, "Drink water", "2026-07-28T10:00:00", "daily")

def test_schedule_task_invalid_iso():
    """Edge Case: LLM hallucinates a human-readable date instead of ISO 8601."""
    res = schedule_task("Drink water", "tomorrow at 5pm", conversation_id=1)
    assert "Error" in res
    assert "not a valid ISO 8601 timestamp" in res

def test_schedule_task_missing_conv_id():
    """Edge Case: Engine fails to inject conversation_id."""
    res = schedule_task("Drink water", "2026-07-28T10:00:00")
    assert "Error: conversation_id is missing" in res

@patch("tools.scheduling_tools.create_scheduled_task", side_effect=Exception("DB Locked"))
def test_schedule_task_db_error(mock_create):
    """Edge Case: Database crash is caught cleanly."""
    res = schedule_task("Drink water", "2026-07-28T10:00:00", conversation_id=1)
    assert "Error scheduling task: DB Locked" in res

# --- list_scheduled_tasks Tests ---

@patch("tools.scheduling_tools.get_tasks_by_conversation")
def test_list_scheduled_tasks_success(mock_get):
    """Happy path: Returns list of dicts."""
    mock_get.return_value = [{"id": 1, "task_prompt": "Test"}]
    res = list_scheduled_tasks(conversation_id=1)
    assert isinstance(res, list)
    assert res[0]["id"] == 1

@patch("tools.scheduling_tools.get_tasks_by_conversation", return_value=[])
def test_list_scheduled_tasks_empty(mock_get):
    """Edge Case: No tasks found returns a clean string."""
    res = list_scheduled_tasks(conversation_id=1)
    assert "No pending scheduled tasks found" in res

# --- cancel_scheduled_task Tests ---

@patch("tools.scheduling_tools.cancel_task", return_value=1)
def test_cancel_scheduled_task_success(mock_cancel):
    """Happy path: Cancels successfully."""
    res = cancel_scheduled_task(42, conversation_id=1)
    assert "Success" in res
    mock_cancel.assert_called_once_with(42, 1)

@patch("tools.scheduling_tools.cancel_task", return_value=0)
def test_cancel_scheduled_task_not_found(mock_cancel):
    """Edge Case: LLM tries to cancel a task that doesn't exist or belongs to someone else."""
    res = cancel_scheduled_task(999, conversation_id=1)
    assert "Error: Task #999 not found" in res

# --- modify_scheduled_task Tests ---

@patch("tools.scheduling_tools.update_task_schedule", return_value=1)
def test_modify_scheduled_task_success(mock_update):
    """Happy path: Modifies successfully."""
    res = modify_scheduled_task(42, "2026-07-28T10:00:00Z", "weekly", conversation_id=1)
    assert "Success" in res
    mock_update.assert_called_once_with(42, 1, "2026-07-28T10:00:00Z", "weekly")

def test_modify_scheduled_task_invalid_iso():
    """Edge Case: Invalid date format blocks modification."""
    res = modify_scheduled_task(42, "2026/07/28", "weekly", conversation_id=1)
    assert "Error" in res
    assert "not a valid ISO 8601 timestamp" in res

@patch("tools.scheduling_tools.update_task_schedule", return_value=0)
def test_modify_scheduled_task_not_found(mock_update):
    """Edge Case: Modifying a non-existent or unauthorized task."""
    res = modify_scheduled_task(999, "2026-07-28T10:00:00", "weekly", conversation_id=1)
    assert "Error: Task #999 not found" in res