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

def test_schedule_task_invalid_iso():
    """Edge Case: Invalid date string is caught."""
    res = schedule_task("Drink water", "tomorrow at 5pm", conversation_id=1)
    assert "Error" in res

def test_schedule_task_missing_conv_id():
    """Edge Case: Missing conversation_id."""
    res = schedule_task("Drink water", "2026-07-28T10:00:00")
    assert "Error: conversation_id is missing" in res

# --- list_scheduled_tasks Tests ---

@patch("tools.scheduling_tools.get_all_scheduled_tasks")
def test_list_scheduled_tasks_success(mock_get):
    """Happy path: Returns global task list."""
    mock_get.return_value = [{"id": 1, "task_prompt": "Test"}]
    res = list_scheduled_tasks(conversation_id=1)
    assert isinstance(res, list)
    assert res[0]["id"] == 1

@patch("tools.scheduling_tools.get_all_scheduled_tasks", return_value=[])
def test_list_scheduled_tasks_empty(mock_get):
    """Edge Case: Empty task list."""
    res = list_scheduled_tasks(conversation_id=1)
    assert "No active scheduled tasks found" in res

# --- cancel_scheduled_task Tests ---

@patch("tools.scheduling_tools.cancel_task_by_id", return_value=1)
def test_cancel_scheduled_task_success(mock_cancel):
    """Happy path: Cancels globally by ID."""
    res = cancel_scheduled_task(42, conversation_id=1)
    assert "Success" in res

@patch("tools.scheduling_tools.cancel_task_by_id", return_value=0)
def test_cancel_scheduled_task_not_found(mock_cancel):
    """Edge Case: Task ID not found."""
    res = cancel_scheduled_task(999, conversation_id=1)
    assert "Error: Task #999 not found" in res

# --- modify_scheduled_task Tests ---

@patch("tools.scheduling_tools.update_task_schedule_by_id", return_value=1)
def test_modify_scheduled_task_success(mock_update):
    """Happy path: Modifies globally by ID."""
    res = modify_scheduled_task(42, "2026-07-28T10:00:00Z", "weekly", conversation_id=1)
    assert "Success" in res

@patch("tools.scheduling_tools.update_task_schedule_by_id", return_value=0)
def test_modify_scheduled_task_not_found(mock_update):
    """Edge Case: Modifying non-existent task."""
    res = modify_scheduled_task(999, "2026-07-28T10:00:00", "weekly", conversation_id=1)
    assert "Error: Task #999 not found" in res