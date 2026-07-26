# tests/test_agent_engine_react_loop.py

import pytest
from unittest.mock import patch, MagicMock
from engine.agent_engine import AgentEngine
from llm.schemas import StreamChunk  # CHANGED: Imported StreamChunk


@pytest.fixture
def mock_engine_dependencies():
    with patch(
        "engine.agent_engine.LLMFactory.get_provider"
    ) as mock_get_provider, patch(
        "engine.agent_engine.save_user_message"
    ) as mock_save_user, patch(
        "engine.agent_engine.save_assistant_message"
    ) as mock_save_ast, patch(
        "engine.agent_engine.compile_llm_context", return_value=[]
    ) as mock_compile, patch(
        "engine.agent_engine.log_api_usage"
    ) as mock_log_api, patch(
        "engine.agent_engine.get_all_tools", return_value=[]
    ) as mock_get_tools, patch(
        "engine.agent_engine.determine_and_execute_tool"
    ) as mock_execute_tool, patch(
        "engine.agent_engine.config_manager.get_max_turns", return_value=5
    ):

        mock_provider = MagicMock()
        mock_provider.model_name = "test-model"
        mock_get_provider.return_value = mock_provider

        yield {
            "provider": mock_provider,
            "execute_tool": mock_execute_tool,
            "save_ast": mock_save_ast,
        }


def test_successful_react_loop(mock_engine_dependencies):
    """Brutal Test: Simulates a full 2-turn ReAct loop (Tool Call -> Final Answer)."""
    provider = mock_engine_dependencies["provider"]
    execute_tool = mock_engine_dependencies["execute_tool"]

    # Turn 1: LLM requests a tool call (Simulated as a stream chunk)
    chunk_turn_1 = StreamChunk(
        text="",
        tool_call_deltas=[
            {
                "id": "call_A",
                "name": "read_files",
                "arguments": '{"paths": ["test.txt"]}',
            }
        ],
        is_finished=True,
        prompt_tokens=10,
        completion_tokens=5,
    )

    # Turn 2: LLM gives the final text answer
    chunk_turn_2 = StreamChunk(
        text="The file says hello world.",
        tool_call_deltas=[],
        is_finished=True,
        prompt_tokens=20,
        completion_tokens=10,
    )

    # Mock the provider to return Turn 1's stream, then Turn 2's stream
    provider.generate_content.side_effect = [[chunk_turn_1], [chunk_turn_2]]

    # Mock the tool execution returning success
    execute_tool.return_value = ("File contents: hello world", "success")

    engine = AgentEngine(provider_name="gemini", api_key="fake_key")

    # Execute
    final_output = engine.send_message(conversation_id=1, user_text="Read test.txt")

    # Assertions
    assert final_output == "The file says hello world."
    assert provider.generate_content.call_count == 2
    execute_tool.assert_called_once_with(
        "read_files", {"paths": ["test.txt"]}, 1, False, approval_callback=None
    )


def test_react_loop_tool_failure_recovery(mock_engine_dependencies):
    """Brutal Test: Tool fails, engine feeds error back to LLM, LLM recovers and answers."""
    provider = mock_engine_dependencies["provider"]
    execute_tool = mock_engine_dependencies["execute_tool"]

    # Turn 1: LLM requests a bad tool call
    chunk_turn_1 = StreamChunk(
        text="",
        tool_call_deltas=[
            {
                "id": "call_bad",
                "name": "run_terminal_command",
                "arguments": '{"cmd": "rm -rf /"}',
            }
        ],
        is_finished=True,
    )

    # Turn 2: LLM apologizes after seeing the error
    chunk_turn_2 = StreamChunk(
        text="I cannot do that.", tool_call_deltas=[], is_finished=True
    )

    provider.generate_content.side_effect = [[chunk_turn_1], [chunk_turn_2]]

    # Mock the tool execution returning an ERROR
    execute_tool.return_value = ("Security Guard blocked this command", "error")

    engine = AgentEngine(provider_name="gemini", api_key="fake_key")
    final_output = engine.send_message(conversation_id=1, user_text="Delete everything")

    assert final_output == "I cannot do that."
    assert provider.generate_content.call_count == 2


def test_engine_api_crash_handling(mock_engine_dependencies):
    """Brutal Test: If the LLM API throws a fatal exception, the engine must raise a clean RuntimeError."""
    provider = mock_engine_dependencies["provider"]

    # This remains an Exception because we are testing the try/except block
    provider.generate_content.side_effect = Exception("500 Internal Server Error")

    engine = AgentEngine(provider_name="gemini", api_key="fake_key")

    import pytest

    with pytest.raises(
        RuntimeError, match="LLM API execution failed: 500 Internal Server Error"
    ):
        engine.send_message(conversation_id=1, user_text="Hello")
