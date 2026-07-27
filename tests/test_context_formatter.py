# tests/test_context_formatter.py
import pytest
import json
from unittest.mock import patch
from llm.context_formatter import format_context, smart_truncate_tool_output


def test_smart_truncate_raw_string():
    """Ensures raw strings (like terminal logs) are truncated without crashing."""
    massive_log = "Starting process...\n" + "Log entry\n" * 1000 + "Process finished."
    res = smart_truncate_tool_output(
        massive_log, "run_terminal_command", threshold_chars=500
    )

    assert "[RAW OUTPUT TRUNCATED]" in res
    assert "Starting process..." in res
    assert "Process finished." in res


def test_smart_truncate_json_dict():
    """Ensures dictionary outputs (like read_files) truncate values and inject skeletons."""
    massive_code = "def main():\n" + "    pass\n" * 1000
    mock_db_output = json.dumps(
        {"script.py": massive_code, "small.txt": "Hello"}  # Should not be truncated
    )

    res = smart_truncate_tool_output(mock_db_output, "read_files", threshold_chars=500)
    parsed_res = json.loads(res)

    assert parsed_res["small.txt"] == "Hello"

    truncated_py = parsed_res["script.py"]
    assert "[RAW OUTPUT TRUNCATED]" in truncated_py


def test_smart_truncate_ignores_small_outputs():
    """Efficiency: Small outputs should not be truncated."""
    small_content = "Just a small terminal output."
    res = smart_truncate_tool_output(
        small_content, "run_terminal_command", threshold_chars=2000
    )
    assert res == small_content




@patch("llm.context_formatter.config_manager.get_system_instruction", return_value=None)
def test_format_context_one_turn_rule(mock_get_inst):
    """Architecture: Ensures the LAST message is kept intact, but OLDER messages are truncated."""
    massive_log = "A\n" * 5000

    raw_db_messages = [
        {"role": "user", "content": "Run command"},
        {
            "role": "tool",
            "tool_name": "run_terminal_command",
            "content": massive_log,
        },  # OLD (Index 1)
        {"role": "user", "content": "Run again"},
        {
            "role": "tool",
            "tool_name": "run_terminal_command",
            "content": massive_log,
        },  # NEW (Index 3)
    ]

    _, standardized_messages = format_context(raw_db_messages)

    # Index 1 must be truncated
    assert "[RAW OUTPUT TRUNCATED]" in standardized_messages[1]["content"]
    assert len(standardized_messages[1]["content"]) < 2000

    # Index 3 must be exactly the original massive log
    assert standardized_messages[3]["content"] == massive_log


@patch("llm.context_formatter.config_manager.get_system_instruction", return_value=None)
def test_format_context_standard_message_flow(mock_get_inst):
    """Ensures standard user-assistant-tool alternation formats correctly."""
    raw_db_messages = [
        {"role": "user", "content": "Verify directories."},
        {
            "role": "assistant",
            "content": "Running task.",
            "tool_calls": [{"name": "read_files", "args": {}}],
        },
    ]
    system_instruction, standardized_messages = format_context(raw_db_messages)

    assert "You are a highly capable, autonomous AI assistant." in system_instruction
    assert len(standardized_messages) == 2
    assert standardized_messages[0]["role"] == "user"
    assert standardized_messages[1]["role"] == "assistant"
    assert "tool_calls" in standardized_messages[1]


@patch(
    "llm.context_formatter.config_manager.get_system_instruction",
    return_value="CUSTOM INSTRUCTION ACTIVE.",
)
def test_format_context_custom_instruction(mock_get_inst):
    """Ensures custom system instructions override the default."""
    raw_db_messages = [{"role": "user", "content": "Hi"}]
    system_instruction, _ = format_context(raw_db_messages)

    assert "CUSTOM INSTRUCTION ACTIVE." in system_instruction
    assert "You are a highly efficient" not in system_instruction


@patch("llm.context_formatter.config_manager.get_system_instruction", return_value=None)
def test_format_context_extracts_previous_summaries(mock_get_inst):
    """Ensures previous summaries are appended to the system prompt and removed from messages."""
    raw_db_messages = [
        {"role": "system", "content": "Workspace project directories initialized."},
        {"role": "user", "content": "List files."},
    ]
    system_instruction, standardized_messages = format_context(raw_db_messages)

    assert (
        "[Previous Conversation Summary]\nWorkspace project directories initialized."
        in system_instruction
    )
    assert len(standardized_messages) == 1
    assert standardized_messages[0]["role"] == "user"


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
    _, standardized_messages = format_context(raw_db_messages)

    assert standardized_messages[0] == {"role": "user", "content": ""}
    assert standardized_messages[1] == {"role": None, "content": "Who am I?"}
    assert standardized_messages[2] == {"role": "assistant", "content": None}


def test_smart_truncate_no_newlines():
    """
    Edge Case: Ensures the truncator doesn't crash or fail to compress
    massive strings that contain absolutely zero newline characters.
    """
    # 20,000 characters, no newlines
    massive_minified_string = "A" * 20000

    res = smart_truncate_tool_output(
        massive_minified_string, "read_files", threshold_chars=500
    )

    assert "[RAW OUTPUT TRUNCATED]" in res
    # Ensure the string was actually compressed
    assert len(res) < 2000
    # Ensure it grabbed the head and tail safely
    assert "AAAAA" in res

from unittest.mock import MagicMock

@patch("llm.context_formatter.datetime")
def test_get_dynamic_system_instruction(mock_datetime):
    """Ensures the dynamic time injection correctly formats and replaces the placeholder."""
    from llm.context_formatter import _get_dynamic_system_instruction
    
    # Mock the datetime to a fixed point so the test is deterministic
    mock_now = MagicMock()
    mock_now.strftime.return_value = "Monday, July 27, 2026 at 08:50 PM IST"
    mock_datetime.datetime.now.return_value = mock_now
    
    # 1. Test with the {current_time} placeholder
    base_with_placeholder = "The time is {current_time}. Hello."
    res1 = _get_dynamic_system_instruction(base_with_placeholder)
    assert res1 == "The time is Monday, July 27, 2026 at 08:50 PM IST. Hello."
    
    # 2. Test without the placeholder (Fallback logic)
    base_without = "Just a normal prompt."
    res2 = _get_dynamic_system_instruction(base_without)
    assert "CURRENT DATE AND TIME: Monday, July 27, 2026 at 08:50 PM IST" in res2
    assert "Just a normal prompt." in res2