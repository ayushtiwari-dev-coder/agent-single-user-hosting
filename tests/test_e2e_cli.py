import pytest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock
from llm.schemas import StreamChunk
from cli.chat_loop import enter_chat_session
from database.helper import execute_read
from database.table_generator import create_tables

@pytest.fixture(autouse=True)
def temp_db_sandbox():
    """
    Creates an isolated, temporary SQLite database for the E2E tests.
    Ensures the DB worker thread is alive and your real chat history is safe.
    """
    import tempfile
    import os
    from unittest.mock import patch
    from database.table_generator import create_tables
    import database.helper  # Import the helper to check the thread

    # 1. Create a temporary file
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db_path = temp_db.name
    temp_db.close()

    # 2. Patch the database connection to use this temp file
    db_patcher = patch("database.connection.DATABASE_PATH", temp_db_path)
    db_patcher.start()

    # --- THE FIX: Revive the Database Worker if a previous test killed it ---
    if not hasattr(database.helper, "_db_worker") or not database.helper._db_worker.is_alive():
        database.helper._db_worker = database.helper.DatabaseWorker()
        database.helper._db_worker.start()

    # 3. Generate the tables in the temp database
    create_tables()

    yield temp_db_path

    # 4. Cleanup after the test finishes
    db_patcher.stop()
    try:
        os.remove(temp_db_path)
    except OSError:
        pass

from queries.conversation_queries import create_conversation

@patch("cli.chat_loop.PromptSession")
@patch("engine.agent_engine.LLMFactory.get_provider")
@patch("cli.chat_loop.config_manager")
def test_cli_e2e_standard_chat_flow(mock_config, mock_get_provider, mock_prompt_class):
    """
    E2E Flow: User says 'Hello', LLM responds 'Hi there!', User types '/exit'.
    Verifies the CLI loop, Engine, and Database all integrate perfectly.
    """
    # 0. Create a valid conversation in the sandboxed DB first!
    conv = create_conversation(title="E2E Standard Chat")
    conv_id = conv["id"]

    # 1. Bypass config requirements for the test
    mock_config.get_default_provider.return_value = "gemini"
    mock_config.get_active_model.return_value = "gemini-3.1"
    mock_config.get_provider_api_key.return_value = "fake_key"

    # 2. Mock the LLM Network Stream
    mock_provider = MagicMock()
    mock_provider.model_name = "test-model"
    mock_get_provider.return_value = mock_provider
    
    # Simulate the LLM streaming "Hi there!"
    mock_provider.generate_content.return_value = [
        StreamChunk(text="Hi ", is_finished=False),
        StreamChunk(text="there!", is_finished=True, prompt_tokens=10, completion_tokens=5)
    ]

    # 3. Mock the User's Keyboard Input
    mock_session_instance = MagicMock()
    mock_session_instance.prompt.side_effect = ["Hello", "/exit"]
    mock_prompt_class.return_value = mock_session_instance

    # 4. Execute the CLI Loop
    try:
        enter_chat_session(conversation_id=conv_id)
    except SystemExit:
        pass # sys.exit(0) is expected when the user types /exit

    # 5. E2E Assertions: Verify the Database state
    messages = execute_read(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id ASC", 
        (conv_id,)
    )
    
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"
    
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Hi there!"


@patch("cli.chat_loop.PromptSession")
@patch("builtins.input") # FIX: Globally mock Python's input() function
@patch("engine.agent_engine.LLMFactory.get_provider")
@patch("cli.chat_loop.config_manager")
def test_cli_e2e_tool_execution_with_approval(mock_config, mock_get_provider, mock_builtin_input, mock_prompt_class):
    """
    E2E Flow: User asks to run a command -> LLM requests tool -> CLI Security Guard 
    prompts user -> User types 'y' -> Tool executes -> LLM summarizes -> User exits.
    """
    from queries.conversation_queries import create_conversation
    from tools.registry import FLAT_REGISTRY
    from tools.core import agent_tool
    from llm.schemas import StreamChunk

    # 0. Create a valid conversation in the sandboxed DB
    conv = create_conversation(title="E2E Tool Chat")
    conv_id = conv["id"]

    # 1. INJECT A FAKE DANGEROUS TOOL INTO THE REGISTRY FOR THIS TEST
    @agent_tool(requires_approval=True)
    def dummy_dangerous_tool(cmd: str):
        return f"Successfully executed: {cmd}"
    
    FLAT_REGISTRY["dummy_dangerous_tool"] = dummy_dangerous_tool

    # 2. Mock configurations
    mock_config.get_default_provider.return_value = "gemini"
    mock_config.get_active_model.return_value = "gemini-3.1"
    mock_config.get_provider_api_key.return_value = "fake_key"

    mock_provider = MagicMock()
    mock_provider.model_name = "test-model"
    mock_get_provider.return_value = mock_provider

    # Turn 1: LLM requests our fake dangerous tool
    chunk_1 = StreamChunk(
        tool_call_deltas=[{"id": "call_1", "name": "dummy_dangerous_tool", "arguments": '{"cmd": "echo hello"}'}],
        is_finished=True, prompt_tokens=10, completion_tokens=5
    )
    # Turn 2: LLM sees the tool output and gives a final answer
    chunk_2 = StreamChunk(text="I ran the command.", is_finished=True, prompt_tokens=15, completion_tokens=5)
    
    mock_provider.generate_content.side_effect = [[chunk_1], [chunk_2]]

    # Mock the User's Keyboard Input for the main chat (PromptSession)
    mock_session_instance = MagicMock()
    mock_session_instance.prompt.side_effect = ["Run echo hello", "/exit"]
    mock_prompt_class.return_value = mock_session_instance

    # Mock the User typing 'y' when the Security Guard asks "Allow this action? (y/N)"
    mock_builtin_input.return_value = "y"

    # Execute the CLI Loop
    from cli.chat_loop import enter_chat_session
    from database.helper import execute_read
    try:
        enter_chat_session(conversation_id=conv_id)
    except SystemExit:
        pass

    # E2E Assertions
    assert mock_provider.generate_content.call_count == 2
    
    # Verify the Security Guard was triggered!
    mock_builtin_input.assert_called_once()

    messages = execute_read(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id ASC", 
        (conv_id,)
    )
    
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Run echo hello"
    
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "I ran the command."

    tool_logs = execute_read(
        "SELECT tool_name, status, output FROM tool_logs WHERE conversation_id = ? ORDER BY id ASC",
        (conv_id,)
    )
    
    assert len(tool_logs) == 1
    assert tool_logs[0]["tool_name"] == "dummy_dangerous_tool"
    assert tool_logs[0]["status"] == "success"
    assert "Successfully executed: echo hello" in tool_logs[0]["output"]

    # Cleanup the registry
    del FLAT_REGISTRY["dummy_dangerous_tool"]