# tests/test_agent_engine_limits.py

import pytest
from unittest.mock import patch, MagicMock
from engine.agent_engine import AgentEngine
from llm.schemas import StreamChunk  # CHANGED: Imported StreamChunk


@patch("engine.agent_engine.config_manager.get_max_turns", return_value=3)
@patch("engine.agent_engine.LLMFactory.get_provider")
@patch("engine.agent_engine.save_user_message")
@patch("engine.agent_engine.save_assistant_message")
@patch("engine.agent_engine.compile_llm_context", return_value=[])
@patch("engine.agent_engine.log_api_usage")
@patch("engine.agent_engine.check_for_infinite_loop")  # Bypass loop protector
def test_max_turns_exceeded(
    mock_loop_check,
    mock_log_api,
    mock_compile,
    mock_save_ast,
    mock_save_usr,
    mock_get_provider,
    mock_max_turns,
):
    """Ensures the AgentEngine forcefully stops if MAX_TURNS is reached."""
    # Tell the loop protector to never trigger during this test
    mock_loop_check.return_value = (False, None, '{"cmd": "ls"}')

    # 1. Setup a mock provider
    mock_provider = MagicMock()
    mock_provider.model_name = "fake-test-model"
    mock_get_provider.return_value = mock_provider

    # 2. Create a fake LLM stream chunk that ALWAYS requests a tool call
    # CHANGED: Now using StreamChunk in a list to simulate a stream
    fake_chunk = StreamChunk(
        text="",
        tool_call_deltas=[
            {
                "id": "call_123",
                "name": "run_terminal_command",
                "arguments": '{"cmd": "ls"}',
            }
        ],
        is_finished=True,
        prompt_tokens=10,
        completion_tokens=10,
    )

    # Return a list containing the chunk (lists are iterable, satisfying the stream loop)
    mock_provider.generate_content.return_value = [fake_chunk]

    # 3. Initialize the engine
    engine = AgentEngine(provider_name="gemini", api_key="fake_key")

    # 4. Mock the tool executor so it doesn't actually run terminal commands
    with patch(
        "engine.agent_engine.determine_and_execute_tool",
        return_value=("Success", "success"),
    ):
        # 5. Run the engine
        final_output = engine.send_message(
            conversation_id=1, user_text="Do something forever"
        )

    # 6. Assertions
    assert "Maximum tool execution limit (3 turns) reached" in final_output
    assert mock_provider.generate_content.call_count == 3

@patch("engine.agent_engine.config_manager.get_max_turns", return_value=5)
@patch("engine.agent_engine.LLMFactory.get_provider")
@patch("engine.agent_engine.save_user_message")
@patch("engine.agent_engine.save_assistant_message")
@patch("engine.agent_engine.compile_llm_context", return_value=[])
@patch("engine.agent_engine.log_api_usage")
@patch("engine.agent_engine.determine_and_execute_tool")
def test_engine_mid_loop_api_crash(
    mock_execute_tool, mock_log_api, mock_compile, mock_save_ast, 
    mock_save_usr, mock_get_provider, mock_max_turns
):
    """
    Edge Case: Turn 1 works. Turn 2 throws a fatal API error.
    Ensures the engine raises the error cleanly for the UI to catch.
    """
    mock_provider = MagicMock()
    mock_provider.model_name = "test-model"
    mock_get_provider.return_value = mock_provider

    # Turn 1: Valid tool call chunk
    from llm.schemas import StreamChunk
    chunk_turn_1 = StreamChunk(
        tool_call_deltas=[{"id": "call_1", "name": "test_tool", "arguments": "{}"}],
        is_finished=True
    )
    
    # Turn 2: The API throws a hard exception
    mock_provider.generate_content.side_effect = [
        [chunk_turn_1], # Turn 1 succeeds
        Exception("502 Bad Gateway: Provider is down") # Turn 2 fails
    ]

    mock_execute_tool.return_value = ("Tool success", "success")

    from engine.agent_engine import AgentEngine
    engine = AgentEngine(provider_name="gemini", api_key="fake")
    
    # Expect the engine to raise the RuntimeError so the UI can catch it
    import pytest
    with pytest.raises(RuntimeError, match="LLM API execution failed"):
        engine.send_message(conversation_id=1, user_text="Do task")

    # Verify the tool was executed during Turn 1 before the crash
    mock_execute_tool.assert_called_once()
    
