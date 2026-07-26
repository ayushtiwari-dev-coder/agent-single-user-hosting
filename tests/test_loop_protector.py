# tests/test_loop_protector.py
import pytest
import json
from unittest.mock import patch
from llm.loop_protector import check_for_infinite_loop


@pytest.fixture
def mock_tool_details():
    """Initializes sample tool configurations."""
    args = {"files_json": '[{"path": "test.py", "content": "print(1)"}]'}
    return {
        "name": "write_files",
        "args": args,
        "serialized_args": json.dumps(args, sort_keys=True),
    }


def test_allow_initial_tool_call(mock_tool_details):
    """Ensures a tool call is allowed to run on its first attempt."""
    tool_call_history = []
    is_looping, loop_error, _ = check_for_infinite_loop(
        tool_call_history, mock_tool_details["name"], mock_tool_details["args"]
    )
    assert is_looping is False
    assert loop_error is None


def test_block_identical_failed_call(mock_tool_details):
    """Safety: Halts execution if a tool already failed 3 times consecutively."""
    tool_call_history = [
        {
            "name": mock_tool_details["name"],
            "args_json": mock_tool_details["serialized_args"],
            "status": "error",
        }
    ] * 3

    is_looping, loop_error, _ = check_for_infinite_loop(
        tool_call_history, mock_tool_details["name"], mock_tool_details["args"]
    )
    assert is_looping is True
    assert "already failed" in loop_error


def test_block_identical_successful_call(mock_tool_details):
    """Safety: Halts execution if an agent repeatedly requests an already completed successful action."""
    tool_call_history = [
        {
            "name": mock_tool_details["name"],
            "args_json": mock_tool_details["serialized_args"],
            "status": "success",
        }
    ] * 2

    is_looping, loop_error, _ = check_for_infinite_loop(
        tool_call_history, mock_tool_details["name"], mock_tool_details["args"]
    )
    assert is_looping is True
    assert "already succeeded" in loop_error


def test_allow_different_arguments(mock_tool_details):
    """Verification: Allows identical tools to run if the arguments are different."""
    tool_call_history = [
        {
            "name": mock_tool_details["name"],
            "args_json": mock_tool_details["serialized_args"],
            "status": "success",
        }
    ]
    new_args = {"files_json": '[{"path": "test.py", "content": "print(2)"}]'}

    is_looping, loop_error, _ = check_for_infinite_loop(
        tool_call_history, mock_tool_details["name"], new_args
    )
    assert is_looping is False
    assert loop_error is None


@patch("utils.config_manager.get_loop_guard")
def test_loop_guard_dynamic_fallback(mock_get_loop_guard, mock_tool_details):
    """Ensures fallback to standard defaults if LoopGuard is zero or invalid in config."""
    mock_get_loop_guard.return_value = {
        "max_failed_attempts": None,
        "max_success_attempts": 0,
    }

    # 1. Fallback for Failures: 2 failures should not loop yet (Default is 3)
    history_2_fails = [
        {
            "name": mock_tool_details["name"],
            "args_json": mock_tool_details["serialized_args"],
            "status": "error",
        }
    ] * 2

    is_looping, _, _ = check_for_infinite_loop(
        history_2_fails, mock_tool_details["name"], mock_tool_details["args"]
    )
    assert is_looping is False

    # 2. 3 failures must trigger fallback guard
    history_3_fails = [
        {
            "name": mock_tool_details["name"],
            "args_json": mock_tool_details["serialized_args"],
            "status": "error",
        }
    ] * 3
    is_looping, loop_error, _ = check_for_infinite_loop(
        history_3_fails, mock_tool_details["name"], mock_tool_details["args"]
    )
    assert is_looping is True
    assert "already failed consecutively" in loop_error

    # 3. Fallback for Successes: 1 success should not loop yet (Default is 2)
    history_1_success = [
        {
            "name": mock_tool_details["name"],
            "args_json": mock_tool_details["serialized_args"],
            "status": "success",
        }
    ]
    is_looping, _, _ = check_for_infinite_loop(
        history_1_success, mock_tool_details["name"], mock_tool_details["args"]
    )
    assert is_looping is False

    # 4. 2 successes must trigger fallback
    history_2_successes = [
        {
            "name": mock_tool_details["name"],
            "args_json": mock_tool_details["serialized_args"],
            "status": "success",
        }
    ] * 2
    is_looping, loop_error, _ = check_for_infinite_loop(
        history_2_successes, mock_tool_details["name"], mock_tool_details["args"]
    )
    assert is_looping is True
    assert "already succeeded consecutively" in loop_error
