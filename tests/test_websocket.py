# tests/test_websocket.py
import json
import pytest
import threading
import time
from unittest.mock import patch, MagicMock
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

# Import the router and state managers
from interfaces.websocket import router, active_threads, manager
from managers.approval_manager import active_approvals

app = FastAPI()
app.include_router(router)


@pytest.fixture(autouse=True)
def reset_shared_state():
    """
    Strictly resets shared concurrent states before and after every test
    to prevent test poisoning and zombie threads.
    """
    active_threads.clear()
    active_approvals.clear()
    manager.active_connections.clear()
    yield
    active_threads.clear()
    active_approvals.clear()
    manager.active_connections.clear()




@patch("interfaces.websocket.config_manager")
def test_global_handshake_security(mock_config):
    """Edge Case: Rejects invalid tokens instantly with code 4001."""
    mock_config.get_provider_api_key.return_value = "secure_token_123"
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/main?token=wrong_token"):
            pass

    assert exc.value.code == 4001



@patch("interfaces.websocket.config_manager")
@patch("interfaces.websocket.get_conversations_paginated")
def test_init_session_bootup(mock_get_convs, mock_config):
    """Happy Path: Boot sequence returns session state and recent threads."""
    mock_config.get_provider_api_key.return_value = None
    mock_config.get_default_provider.return_value = "gemini"
    mock_config.get_active_model.return_value = "gemini-3.1"
    mock_config.get_temperature.return_value = 0.5

    mock_get_convs.return_value = [{"id": 1, "title": "Test Chat"}]

    client = TestClient(app)
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json({"type": "init_session"})

        response = ws.receive_json()
        assert response["type"] == "session_state"
        assert response["payload"]["active_provider"] == "gemini"
        assert response["payload"]["temperature"] == 0.5
        assert len(response["payload"]["recent_threads"]) == 1


@patch("interfaces.websocket.config_manager")
@patch("interfaces.websocket.get_messages_paginated")
def test_load_history_pagination(mock_get_msgs, mock_config):
    """Happy Path: Infinite scroll pagination requests return correct chunks."""
    mock_config.get_provider_api_key.return_value = None
    mock_get_msgs.return_value = [{"id": 99, "role": "user", "content": "Old message"}]

    client = TestClient(app)
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json(
            {
                "type": "load_history",
                "payload": {"conversation_id": 42, "before_id": 100},
            }
        )

        response = ws.receive_json()
        assert response["type"] == "history_loaded"
        assert response["conversation_id"] == 42
        assert response["payload"]["messages"][0]["id"] == 99

        mock_get_msgs.assert_called_once_with(42, before_id=100, limit=20)


@patch("interfaces.websocket.config_manager")
@patch("interfaces.websocket.search_conversations")
def test_search_threads(mock_search, mock_config):
    """Happy Path: Live sidebar search returns filtered threads."""
    mock_config.get_provider_api_key.return_value = None
    mock_search.return_value = [{"id": 5, "title": "Quantum Physics"}]

    client = TestClient(app)
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json({"type": "search_threads", "payload": {"query": "Quantum"}})

        response = ws.receive_json()
        assert response["type"] == "search_results"
        assert response["payload"]["results"][0]["title"] == "Quantum Physics"




@patch("interfaces.websocket.config_manager")
def test_concurrency_limit_reached(mock_config):
    """Edge Case: Blocks execution if max_concurrent_chats is reached."""
    mock_config.get_provider_api_key.return_value = None
    mock_config.get_max_concurrent_chats.return_value = 2  # Limit is 2

    # Simulate 2 active chats already running
    active_threads[1] = MagicMock()
    active_threads[2] = MagicMock()

    client = TestClient(app)
    with client.websocket_connect("/ws/main") as ws:
        # Try to start a 3rd chat
        ws.send_json(
            {
                "type": "user_message",
                "payload": {"conversation_id": 3, "content": "Hello"},
            }
        )

        response = ws.receive_json()
        assert response["type"] == "execution_error"
        assert response["conversation_id"] == 3
        assert response["payload"]["error_code"] == "CONCURRENCY_LIMIT_REACHED"


@patch("interfaces.websocket.config_manager")
def test_double_execution_blocked(mock_config):
    """Edge Case: Blocks sending a message to a chat that is already generating."""
    mock_config.get_provider_api_key.return_value = None
    mock_config.get_max_concurrent_chats.return_value = 5

    # Simulate Chat 42 is already running
    active_threads[42] = MagicMock()

    client = TestClient(app)
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json(
            {
                "type": "user_message",
                "payload": {"conversation_id": 42, "content": "Spam click!"},
            }
        )

        response = ws.receive_json()
        assert response["type"] == "execution_error"
        assert response["conversation_id"] == 42
        assert response["payload"]["error_code"] == "CONCURRENT_RUN_BLOCKED"




@patch("interfaces.websocket.config_manager")
@patch("interfaces.websocket.create_conversation")
@patch("interfaces.websocket.AgentEngine")
def test_new_chat_creation_and_execution(
    mock_engine_class, mock_create_conv, mock_config
):
    """Happy Path: Sending a message with no ID creates a DB record and runs."""
    mock_config.get_provider_api_key.return_value = None
    mock_config.get_max_concurrent_chats.return_value = 5

    # Mock DB creation
    mock_create_conv.return_value = {"id": 99, "title": "Write a python script..."}

    # Mock Engine
    mock_engine = MagicMock()
    mock_engine_class.return_value = mock_engine

    def mock_send_message(*args, **kwargs):
        status_cb = kwargs.get("status_callback")
        if status_cb:
            status_cb("Generating thoughts...")

        # FIX: Simulate streaming by invoking the callback during the test
        stream_cb = kwargs.get("send_message_callback")
        if stream_cb:
            stream_cb("Final Answer")

        return "Final Answer"

    mock_engine.send_message.side_effect = mock_send_message

    client = TestClient(app)
    with client.websocket_connect("/ws/main") as ws:
        # Send message with NO conversation_id
        ws.send_json(
            {"type": "user_message", "payload": {"content": "Write a python script"}}
        )

        # 1. Expect conversation_created event
        creation_event = ws.receive_json()
        assert creation_event["type"] == "conversation_created"
        assert creation_event["conversation_id"] == 99

        # 2. Expect thought_start
        thought_event = ws.receive_json()
        assert thought_event["type"] == "thought_start"
        assert thought_event["conversation_id"] == 99

        # 3. Expect message_chunk
        chunk_event = ws.receive_json()
        assert chunk_event["type"] == "message_chunk"
        assert chunk_event["payload"]["chunk"] == "Final Answer"

        # 4. Expect completion and thread_freed
        assert ws.receive_json()["type"] == "execution_completed"
        assert ws.receive_json()["type"] == "thread_freed"

        # DYNAMIC POLLING: Ensure thread cleans up safely
        cleaned_up = False
        for _ in range(40):
            if 99 not in active_threads:
                cleaned_up = True
                break
            time.sleep(0.05)
        assert (
            cleaned_up is True
        ), "Thread failed to clean up from active_threads dictionary."


@patch("interfaces.websocket.config_manager")
@patch("interfaces.websocket.AgentEngine")
def test_human_in_the_loop_approval_flow(mock_engine_class, mock_config):
    """Rigorous Test: Engine freezes, asks for UI approval, unfreezes, and finishes."""
    mock_config.get_provider_api_key.return_value = None
    mock_config.get_max_concurrent_chats.return_value = 5

    mock_engine = MagicMock()
    mock_engine_class.return_value = mock_engine

    # Locate this mock inside test_human_in_the_loop_approval_flow
    def mock_react_send_message(*args, **kwargs):
        approval_cb = kwargs.get("approval_callback")
        # Trigger the freeze
        is_approved = approval_cb("run_terminal_command", {"cmd": "ls"}, 42)
        if is_approved:
            # FIX: Simulate streaming by invoking the callback during the test
            stream_cb = kwargs.get("send_message_callback")
            if stream_cb:
                stream_cb("Command executed.")
            return "Command executed."
        return "Command denied."

    mock_engine.send_message.side_effect = mock_react_send_message

    client = TestClient(app)
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json(
            {
                "type": "user_message",
                "payload": {"conversation_id": 42, "content": "Run ls"},
            }
        )

        # 1. Expect Approval Request
        approval_req = ws.receive_json()
        assert approval_req["type"] == "approval_required"
        assert approval_req["conversation_id"] == 42
        assert approval_req["payload"]["tool_name"] == "run_terminal_command"

        # -----------------------------------------------------------------
        # ANTI-RACE-CONDITION GUARD
        # The test client is so fast it will reply before the background OS
        # thread finishes setting up the lock dictionary. Wait for the lock!
        # -----------------------------------------------------------------
        lock_ready = False
        for _ in range(40):
            if 42 in active_approvals:
                lock_ready = True
                break
            time.sleep(0.05)
        assert lock_ready is True, "Background thread failed to register lock!"

        # 2. Send Approval Response
        ws.send_json(
            {
                "type": "approval_response",
                "payload": {"conversation_id": 42, "approved": True},
            }
        )

        # 3. Expect Completion
        chunk = ws.receive_json()
        assert chunk["type"] == "message_chunk"
        assert chunk["payload"]["chunk"] == "Command executed."

        assert ws.receive_json()["type"] == "execution_completed"
        assert ws.receive_json()["type"] == "thread_freed"




@patch("interfaces.websocket.config_manager")
@patch("interfaces.websocket.AgentEngine")
def test_agent_crash_isolation(mock_engine_class, mock_config):
    """Edge Case: If the LLM API crashes, it sends an error but doesn't crash the server."""
    mock_config.get_provider_api_key.return_value = None
    mock_config.get_max_concurrent_chats.return_value = 5

    mock_engine = MagicMock()
    mock_engine_class.return_value = mock_engine
    mock_engine.send_message.side_effect = Exception("Groq API 503 Service Unavailable")

    client = TestClient(app)
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json(
            {
                "type": "user_message",
                "payload": {"conversation_id": 77, "content": "Crash me"},
            }
        )

        # Expect graceful error mapping
        error_event = ws.receive_json()
        assert error_event["type"] == "execution_error"
        assert error_event["conversation_id"] == 77
        assert error_event["payload"]["error_code"] == "AGENT_EXECUTION_FAILED"
        assert "Groq API 503" in error_event["payload"]["message"]

        # Ensure thread is freed even on crash
        assert ws.receive_json()["type"] == "thread_freed"


@patch("interfaces.websocket.config_manager")
@patch("interfaces.websocket.AgentEngine")
def test_disconnect_releases_zombie_approvals(mock_engine_class, mock_config):
    """Edge Case: If user closes browser during an approval freeze, thread is killed."""
    mock_config.get_provider_api_key.return_value = None
    mock_config.get_max_concurrent_chats.return_value = 5

    mock_engine = MagicMock()
    mock_engine_class.return_value = mock_engine

    def mock_react_send_message(*args, **kwargs):
        approval_cb = kwargs.get("approval_callback")
        approval_cb("run_terminal_command", {"cmd": "rm -rf /"}, 88)
        return "Aborted"

    mock_engine.send_message.side_effect = mock_react_send_message

    client = TestClient(app)
    with client.websocket_connect("/ws/main") as ws:
        ws.send_json(
            {
                "type": "user_message",
                "payload": {"conversation_id": 88, "content": "Delete everything"},
            }
        )

        # Wait for approval prompt
        assert ws.receive_json()["type"] == "approval_required"

        # -----------------------------------------------------------------
        # ANTI-RACE-CONDITION GUARD
        # Wait for the lock to be created before simulating the disconnect
        # -----------------------------------------------------------------
        lock_ready = False
        for _ in range(40):
            if 88 in active_approvals:
                lock_ready = True
                break
            time.sleep(0.05)
        assert lock_ready is True, "Background thread failed to register lock!"

        # Simulate user closing the tab
        ws.close()

    # DYNAMIC POLLING: Give the OS time to run the disconnect cleanup
    cleaned_up = False
    for _ in range(40):
        if 88 not in active_approvals and 88 not in active_threads:
            cleaned_up = True
            break
        time.sleep(0.05)

    assert cleaned_up is True, "Disconnect failed to release the zombie thread."



@patch("interfaces.websocket.config_manager")
def test_websocket_concurrent_run_blocked_same_chat(mock_config):
    """
    Edge Case: User spams the 'Send' button. The WebSocket must reject 
    the second message if the first one is still processing in the background thread.
    """
    from interfaces.websocket import active_threads
    mock_config.get_provider_api_key.return_value = None
    mock_config.get_max_concurrent_chats.return_value = 5

    # 1. Simulate that conversation_id 42 is currently locked/running
    active_threads[42] = MagicMock()

    client = TestClient(app)
    with client.websocket_connect("/ws/main") as ws:
        # 2. Try to send another message to conversation 42
        ws.send_json({
            "type": "user_message",
            "payload": {"conversation_id": 42, "content": "Spam message!"}
        })

        # 3. Expect an immediate execution_error rejection
        response = ws.receive_json()
        assert response["type"] == "execution_error"
        assert response["conversation_id"] == 42
        assert response["payload"]["error_code"] == "CONCURRENT_RUN_BLOCKED"
        assert "already running" in response["payload"]["message"]