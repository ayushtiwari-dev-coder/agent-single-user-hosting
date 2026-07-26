# tests/test_context_formatter_brutal.py
import pytest
from unittest.mock import patch
from llm.context_formatter import format_context


@patch("llm.context_formatter.config_manager.get_system_instruction", return_value=None)
def test_format_context_empty_messages(mock_get_inst):
    """Brutal Test: Formatting an empty list of messages."""
    system_instruction, standardized_messages = format_context([])

    assert "You are a highly capable, autonomous AI assistant." in system_instruction
    assert standardized_messages == []


@patch("llm.context_formatter.config_manager.get_system_instruction", return_value=None)
def test_format_context_malformed_db_messages(mock_get_inst):
    """Brutal Test: DB returns messages missing 'content' or 'role' keys."""
    raw_db_messages = [
        {"role": "user"},  # Missing content entirely -> gets ""
        {"content": "Who am I?"},  # Missing role -> gets None
        {"role": "assistant", "content": None},  # Content explicitly None -> gets None
    ]

    system_instruction, standardized_messages = format_context(raw_db_messages)

    # Assertions updated to match exact Python .get() behavior
    assert standardized_messages[0] == {"role": "user", "content": ""}
    assert standardized_messages[1] == {"role": None, "content": "Who am I?"}
    assert standardized_messages[2] == {"role": "assistant", "content": None}
