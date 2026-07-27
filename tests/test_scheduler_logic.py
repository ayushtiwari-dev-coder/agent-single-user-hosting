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
    res = calculate_next_execution("2026-07-27T10:00:00", "daily")
    assert res == "2026-07-28T10:00:00"

def test_calculate_next_execution_twice_daily():
    res = calculate_next_execution("2026-07-27T10:00:00", "twice_daily")
    assert res == "2026-07-27T22:00:00"

def test_calculate_next_execution_weekly():
    res = calculate_next_execution("2026-07-27T10:00:00", "weekly")
    assert res == "2026-08-03T10:00:00"

def test_calculate_next_execution_monthly():
    res = calculate_next_execution("2026-07-27T10:00:00", "monthly")
    assert res == "2026-08-26T10:00:00"

def test_calculate_next_execution_yearly():
    res = calculate_next_execution("2026-07-27T10:00:00", "yearly")
    assert res == "2027-07-27T10:00:00"

def test_calculate_next_execution_custom_days():
    res_3d = calculate_next_execution("2026-07-27T10:00:00", "3d")
    assert res_3d == "2026-07-30T10:00:00"
    
    res_14d = calculate_next_execution("2026-07-27T10:00:00", "14d")
    assert res_14d == "2026-08-10T10:00:00"

def test_calculate_next_execution_invalid():
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

@patch("interfaces.telegram_bot.reschedule_task")
@patch("interfaces.telegram_bot.update_task_status")
@patch("interfaces.telegram_bot.process_agent_interaction")
@patch("interfaces.telegram_bot.bot")
@patch("interfaces.telegram_bot.get_conversation_by_id")
@patch("interfaces.telegram_bot.get_latest_tg_conversation")
def test_execute_scheduled_task_one_time(
    mock_get_latest_conv, mock_get_conv, mock_bot, mock_process, mock_update, mock_reschedule, mock_task
):
    """Happy Path: A one-time task runs and is marked completed."""
    mock_get_conv.return_value = {"title": "Telegram Chat 12345"}
    mock_get_latest_conv.return_value = {"id": 1}
    
    execute_scheduled_task(mock_task)
    
    mock_bot.send_message.assert_called_once()
    mock_process.assert_called_once_with(12345, 1, "[SCHEDULED TASK]: Send weather", source="scheduler")
    mock_update.assert_called_once_with(42, "completed")
    mock_reschedule.assert_not_called()

@patch("interfaces.telegram_bot.reschedule_task")
@patch("interfaces.telegram_bot.update_task_status")
@patch("interfaces.telegram_bot.process_agent_interaction")
@patch("interfaces.telegram_bot.bot")
@patch("interfaces.telegram_bot.get_conversation_by_id")
@patch("interfaces.telegram_bot.get_latest_tg_conversation")
def test_execute_scheduled_task_recurring(
    mock_get_latest_conv, mock_get_conv, mock_bot, mock_process, mock_update, mock_reschedule, mock_task
):
    """Happy Path: A recurring task runs and is rescheduled."""
    mock_get_conv.return_value = {"title": "Telegram Chat 12345"}
    mock_get_latest_conv.return_value = {"id": 1}
    mock_task["recurrence"] = "daily"
    
    execute_scheduled_task(mock_task)
    
    mock_reschedule.assert_called_once_with(42, "2026-07-28T10:00:00")
    mock_update.assert_not_called()

@patch("interfaces.telegram_bot.get_conversation_by_id")
@patch("interfaces.telegram_bot.update_task_status")
def test_execute_scheduled_task_crash(mock_update, mock_get_conv, mock_task):
    """Edge Case: If the agent crashes, the task is marked as failed."""
    mock_get_conv.side_effect = Exception("Database offline")
    
    execute_scheduled_task(mock_task)
    
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
    mock_get_due.return_value = [{"id": 1}, {"id": 2}]
    
    with pytest.raises(InterruptedError):
        start_scheduler_loop()
    
    assert mock_update.call_count == 2
    mock_update.assert_any_call(1, "processing")
    mock_update.assert_any_call(2, "processing")
    assert mock_thread.call_count == 2