# tests/test_scheduler_logic.py
import pytest
from unittest.mock import patch, MagicMock
from interfaces.telegram_bot import (
    calculate_next_execution,
    execute_scheduled_task,
    start_scheduler_loop
)

# =====================================================================
# 1. RECURRENCE MATH TESTS
# =====================================================================

def test_calculate_next_execution_daily():
    """Ensures daily adds exactly 24 hours."""
    res = calculate_next_execution("2026-07-27T10:00:00", "daily")
    assert res == "2026-07-28T10:00:00"

def test_calculate_next_execution_twice_daily():
    """Ensures twice_daily adds exactly 12 hours."""
    res = calculate_next_execution("2026-07-27T10:00:00", "twice_daily")
    assert res == "2026-07-27T22:00:00"

def test_calculate_next_execution_weekly():
    """Ensures weekly adds exactly 7 days."""
    res = calculate_next_execution("2026-07-27T10:00:00", "weekly")
    assert res == "2026-08-03T10:00:00"

def test_calculate_next_execution_monthly():
    """Ensures monthly adds exactly 30 days."""
    res = calculate_next_execution("2026-07-27T10:00:00", "monthly")
    assert res == "2026-08-26T10:00:00"

def test_calculate_next_execution_yearly():
    """Ensures yearly adds exactly 365 days."""
    res = calculate_next_execution("2026-07-27T10:00:00", "yearly")
    assert res == "2027-07-27T10:00:00"

def test_calculate_next_execution_custom_days():
    """Ensures Xd regex parses correctly for any number of days."""
    res_3d = calculate_next_execution("2026-07-27T10:00:00", "3d")
    assert res_3d == "2026-07-30T10:00:00"
    
    res_14d = calculate_next_execution("2026-07-27T10:00:00", "14d")
    assert res_14d == "2026-08-10T10:00:00"

def test_calculate_next_execution_invalid():
    """Edge Case: Invalid or corrupted recurrence strings return None."""
    assert calculate_next_execution("2026-07-27T10:00:00", "invalid_format") is None
    assert calculate_next_execution("2026-07-27T10:00:00", "none") is None

# =====================================================================
# 2. TASK EXECUTION TESTS
# =====================================================================

@pytest.fixture
def mock_task():
    return {
        "id": 42,
        "conversation_id": 1,
        "task_prompt": "Send weather",
        "execute_at": "2026-07-27T10:00:00",
        "recurrence": "none"
    }

@patch("interfaces.telegram_bot.get_conversation_by_id")
@patch("interfaces.telegram_bot.bot")
@patch("interfaces.telegram_bot.process_agent_interaction")
@patch("interfaces.telegram_bot.update_task_status")
@patch("interfaces.telegram_bot.reschedule_task")
def test_execute_scheduled_task_one_time(mock_reschedule, mock_update, mock_process, mock_bot, mock_get_conv, mock_task):
    """Happy Path: A one-time task runs and is marked completed."""
    mock_get_conv.return_value = {"title": "Telegram Chat 12345"}
    
    execute_scheduled_task(mock_task)
    
    # Verify it notified the user
    mock_bot.send_message.assert_called_once()
    assert "Scheduled Task Triggered" in mock_bot.send_message.call_args[0][1]
    
    # Verify it triggered the agent
    mock_process.assert_called_once_with(12345, 1, "[SCHEDULED TASK]: Send weather", source="scheduler")
    
    # Verify it marked as completed (since recurrence is 'none')
    mock_update.assert_called_once_with(42, "completed")
    mock_reschedule.assert_not_called()

@patch("interfaces.telegram_bot.get_conversation_by_id")
@patch("interfaces.telegram_bot.bot")
@patch("interfaces.telegram_bot.process_agent_interaction")
@patch("interfaces.telegram_bot.update_task_status")
@patch("interfaces.telegram_bot.reschedule_task")
def test_execute_scheduled_task_recurring(mock_reschedule, mock_update, mock_process, mock_bot, mock_get_conv, mock_task):
    """Happy Path: A recurring task runs and is rescheduled."""
    mock_get_conv.return_value = {"title": "Telegram Chat 12345"}
    mock_task["recurrence"] = "daily"
    
    execute_scheduled_task(mock_task)
    
    # Verify it rescheduled for tomorrow instead of completing
    mock_reschedule.assert_called_once_with(42, "2026-07-28T10:00:00")
    mock_update.assert_not_called()

@patch("interfaces.telegram_bot.get_conversation_by_id")
@patch("interfaces.telegram_bot.update_task_status")
def test_execute_scheduled_task_crash(mock_update, mock_get_conv, mock_task):
    """Edge Case: If the agent crashes, the task is marked as failed."""
    # Force a crash by making get_conversation_by_id throw an error
    mock_get_conv.side_effect = Exception("Database offline")
    
    execute_scheduled_task(mock_task)
    
    # Verify it caught the error and marked the task as failed
    mock_update.assert_called_once_with(42, "failed")

# =====================================================================
# 3. POLLING LOOP TESTS
# =====================================================================

@patch("interfaces.telegram_bot.get_due_tasks")
@patch("interfaces.telegram_bot.update_task_status")
@patch("interfaces.telegram_bot.threading.Thread")
@patch("interfaces.telegram_bot.time.sleep", side_effect=InterruptedError("Break Loop"))
def test_start_scheduler_loop(mock_sleep, mock_thread, mock_update, mock_get_due):
    """Ensures the loop fetches tasks, marks them processing, and spawns threads."""
    # Mock the DB returning 2 due tasks
    mock_get_due.return_value = [{"id": 1}, {"id": 2}]
    
    with pytest.raises(InterruptedError):
        start_scheduler_loop()
    
    # Verify it marked both tasks as processing immediately
    assert mock_update.call_count == 2
    mock_update.assert_any_call(1, "processing")
    mock_update.assert_any_call(2, "processing")
    
    # Verify it spawned 2 background threads to execute them
    assert mock_thread.call_count == 2