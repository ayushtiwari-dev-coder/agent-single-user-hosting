# tests/test_stream_processor.py

import pytest
import json
from unittest.mock import MagicMock
from llm.schemas import StreamChunk, ToolCall
from engine.stream_processor import process_llm_stream


def mock_stream_generator(chunks):
    """Helper to simulate a network stream yielding chunks."""
    for chunk in chunks:
        yield chunk


from engine.stream_processor import calculate_fallback_tokens


def test_calculate_fallback_tokens_standard_math():
    """Ensures the 3.7 character heuristic calculates correctly."""
    # 37 chars should equal exactly 10 tokens (37 // 3.7 = 10)
    db_messages = [
        {"role": "user", "content": "A" * 37},
        {"role": "assistant", "content": "B" * 37},
    ]
    # Total prompt chars = 74. 74 // 3.7 = 20 tokens.

    full_text = "C" * 74  # 74 chars // 3.7 = 20 tokens

    p_tokens, c_tokens = calculate_fallback_tokens(db_messages, full_text, [])

    assert p_tokens == 20
    assert c_tokens == 20


def test_calculate_fallback_tokens_with_tools():
    """Ensures hidden JSON tool arguments add the 50-token penalty."""
    db_messages = [{"role": "user", "content": "A" * 37}]  # 10 prompt tokens
    full_text = "B" * 37  # 10 completion tokens

    # Mock 2 tool calls
    mock_tool = MagicMock()
    parsed_tool_calls = [mock_tool, mock_tool]

    p_tokens, c_tokens = calculate_fallback_tokens(
        db_messages, full_text, parsed_tool_calls
    )

    assert p_tokens == 10
    # 10 base tokens + (50 tokens * 2 tools) = 110
    assert c_tokens == 110


def test_calculate_fallback_tokens_empty_state():
    """Edge Case: Ensures empty strings don't crash the math."""
    p_tokens, c_tokens = calculate_fallback_tokens([], "", [])

    assert p_tokens == 0
    assert c_tokens == 0


def test_calculate_fallback_tokens_missing_content_keys():
    """Edge Case: DB messages missing the 'content' key should be handled safely."""
    db_messages = [
        {"role": "user"},  # No content key
        {"role": "assistant", "content": None},  # None content
    ]

    p_tokens, c_tokens = calculate_fallback_tokens(db_messages, "Hello", [])

    assert p_tokens == 0
    assert c_tokens == 1  # "Hello" is 5 chars. 5 // 3.7 = 1


def test_process_stream_pure_text():
    """Happy Path: Ensures text chunks are concatenated and callbacks are fired."""
    chunks = [
        StreamChunk(text="Hello "),
        StreamChunk(text="world! "),
        StreamChunk(
            text="How are you?", is_finished=True, prompt_tokens=10, completion_tokens=5
        ),
    ]

    mock_callback = MagicMock()
    stream = mock_stream_generator(chunks)

    full_text, tool_calls, p_tokens, c_tokens = process_llm_stream(
        stream, mock_callback
    )

    # Assertions
    assert full_text == "Hello world! How are you?"
    assert len(tool_calls) == 0
    assert p_tokens == 10
    assert c_tokens == 5

    # Verify the callback was fired exactly 3 times with the exact text fragments
    assert mock_callback.call_count == 3
    mock_callback.assert_any_call("Hello ")
    mock_callback.assert_any_call("world! ")
    mock_callback.assert_any_call("How are you?")


def test_process_stream_fragmented_tool_call():
    """Edge Case: Ensures broken JSON fragments are glued together silently."""
    chunks = [
        StreamChunk(
            tool_call_deltas=[
                {"id": "call_1", "name": "read_files", "arguments": '{"pa'}
            ]
        ),
        StreamChunk(
            tool_call_deltas=[
                {"id": "call_1", "name": "read_files", "arguments": 'ths": '}
            ]
        ),
        StreamChunk(
            tool_call_deltas=[
                {"id": "call_1", "name": "read_files", "arguments": '["main.py"]}'}
            ]
        ),
        StreamChunk(is_finished=True),
    ]

    mock_callback = MagicMock()
    stream = mock_stream_generator(chunks)

    full_text, tool_calls, _, _ = process_llm_stream(stream, mock_callback)

    # Assertions
    assert full_text == ""  # No text was streamed
    mock_callback.assert_not_called()  # UI should NEVER see tool JSON fragments

    assert len(tool_calls) == 1
    assert isinstance(tool_calls[0], ToolCall)
    assert tool_calls[0].id == "call_1"
    assert tool_calls[0].name == "read_files"

    # Verify the JSON was perfectly glued and parsed
    assert tool_calls[0].args == {"paths": ["main.py"]}


def test_process_stream_parallel_tools():
    """Edge Case: Ensures multiple tools streaming simultaneously are segregated correctly."""
    chunks = [
        # Tool 1 starts
        StreamChunk(
            tool_call_deltas=[{"id": "call_A", "name": "tool_A", "arguments": '{"a": '}]
        ),
        # Tool 2 starts before Tool 1 finishes
        StreamChunk(
            tool_call_deltas=[{"id": "call_B", "name": "tool_B", "arguments": '{"b": '}]
        ),
        # Tool 1 finishes
        StreamChunk(
            tool_call_deltas=[{"id": "call_A", "name": "tool_A", "arguments": "1}"}]
        ),
        # Tool 2 finishes
        StreamChunk(
            tool_call_deltas=[{"id": "call_B", "name": "tool_B", "arguments": "2}"}]
        ),
        StreamChunk(is_finished=True),
    ]

    stream = mock_stream_generator(chunks)
    _, tool_calls, _, _ = process_llm_stream(stream, None)

    assert len(tool_calls) == 2

    # Verify Tool A
    assert tool_calls[0].id == "call_A"
    assert tool_calls[0].name == "tool_A"
    assert tool_calls[0].args == {"a": 1}

    # Verify Tool B
    assert tool_calls[1].id == "call_B"
    assert tool_calls[1].name == "tool_B"
    assert tool_calls[1].args == {"b": 2}


def test_process_stream_malformed_json_hallucination():
    """Edge Case: If the LLM hallucinates broken JSON, it must not crash the engine."""
    chunks = [
        StreamChunk(
            tool_call_deltas=[
                {
                    "id": "call_bad",
                    "name": "write_files",
                    "arguments": '{"broken": "json" -- missing brace',
                }
            ]
        ),
        StreamChunk(is_finished=True),
    ]

    stream = mock_stream_generator(chunks)

    # This should NOT raise a JSONDecodeError. It should catch it and return empty args.
    _, tool_calls, _, _ = process_llm_stream(stream, None)

    assert len(tool_calls) == 1
    assert tool_calls[0].id == "call_bad"
    assert tool_calls[0].name == "write_files"
    assert tool_calls[0].args == {}  # Safely fell back to an empty dictionary


def test_process_stream_mixed_text_and_tools():
    """Happy Path: Ensures text and tools in the same stream are handled correctly."""
    chunks = [
        StreamChunk(text="I will run that for you."),
        StreamChunk(
            tool_call_deltas=[
                {
                    "id": "call_99",
                    "name": "run_terminal_command",
                    "arguments": '{"cmd": "ls"}',
                }
            ]
        ),
        StreamChunk(is_finished=True),
    ]

    mock_callback = MagicMock()
    stream = mock_stream_generator(chunks)

    full_text, tool_calls, _, _ = process_llm_stream(stream, mock_callback)

    assert full_text == "I will run that for you."
    mock_callback.assert_called_once_with("I will run that for you.")

    assert len(tool_calls) == 1
    assert tool_calls[0].args == {"cmd": "ls"}


def test_process_stream_massive_json_payload():
    """
    Stress Test: Simulates the LLM streaming a massive 1MB+ JSON argument
    to ensure the string buffer and JSON parser don't hit recursion limits or memory crash.
    """
    # Create a massive 100,000 character string chunk
    massive_string = "A" * 100000

    chunks = [
        StreamChunk(
            tool_call_deltas=[
                {"id": "call_1", "name": "write_files", "arguments": '{"content": "'}
            ]
        ),
        StreamChunk(
            tool_call_deltas=[
                {"id": "call_1", "name": "write_files", "arguments": massive_string}
            ]
        ),
        StreamChunk(
            tool_call_deltas=[
                {"id": "call_1", "name": "write_files", "arguments": '"}'}
            ]
        ),
        StreamChunk(is_finished=True),
    ]

    stream = mock_stream_generator(chunks)
    full_text, tool_calls, _, _ = process_llm_stream(stream, None)

    assert len(tool_calls) == 1
    assert tool_calls[0].name == "write_files"
    # Ensure the massive string was parsed successfully
    assert len(tool_calls[0].args["content"]) == 100000


def test_stream_processor_schizophrenic_tools():
    """
    Edge Case: LLM requests 3 tools simultaneously. 
    Tool 1 is perfect. Tool 2 is missing a name. Tool 3 has garbage JSON.
    """
    chunks = [
        StreamChunk(
            tool_call_deltas=[
                {"id": "call_1", "name": "good_tool", "arguments": '{"val": 1}'},
                {"id": "call_2", "name": None, "arguments": '{"val": 2}'}, # Missing name
                {"id": "call_3", "name": "bad_tool", "arguments": 'NOT JSON'} # Garbage args
            ],
            is_finished=True
        )
    ]

    def mock_stream():
        for c in chunks: yield c

    full_text, tool_calls, p_tokens, c_tokens = process_llm_stream(mock_stream(), None)

    # We expect exactly 3 tool calls to be parsed
    assert len(tool_calls) == 3

    # Tool 1: Perfect
    assert tool_calls[0].id == "call_1"
    assert tool_calls[0].name == "good_tool"
    assert tool_calls[0].args == {"val": 1}

    # Tool 2: Missing name (Should safely be None)
    assert tool_calls[1].id == "call_2"
    assert tool_calls[1].name is None
    assert tool_calls[1].args == {"val": 2}

    # Tool 3: Garbage JSON (Should fallback to empty dict {})
    assert tool_calls[2].id == "call_3"
    assert tool_calls[2].name == "bad_tool"
    assert tool_calls[2].args == {}

def test_process_stream_missing_arguments_key():
    """Edge Case: LLM requests a tool but omits the arguments payload entirely."""
    chunks = [
        StreamChunk(
            tool_call_deltas=[
                {
                    "id": "call_no_args", 
                    "name": "get_all_scheduled_tasks", 
                    # Notice "arguments" is completely missing or empty
                    "arguments": "" 
                }
            ]
        ),
        StreamChunk(is_finished=True),
    ]
    
    stream = mock_stream_generator(chunks)
    _, tool_calls, _, _ = process_llm_stream(stream, None)
    
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "get_all_scheduled_tasks"
    # Must safely default to an empty dictionary without crashing
    assert tool_calls[0].args == {}