import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import targets (FIXED: Importing router instead of app)
from interfaces.websocket import router, WS_EVENT_ROUTER
from engine.stream_processor import process_llm_stream
from llm.schemas import StreamChunk
from managers.conversation_manager import compile_llm_context

# Setup a dummy FastAPI app for the TestClient
app = FastAPI()
app.include_router(router)

# =====================================================================
# 1. WEBSOCKET EXTREME EDGE CASES
# =====================================================================

def test_websocket_unknown_event_routing():
    """Edge Case: Ensures the O(1) Dictionary Dispatcher safely catches unregistered events."""
    client = TestClient(app)
    with client.websocket_connect("/ws/main") as ws:
        # Send an event type that does NOT exist in WS_EVENT_ROUTER
        ws.send_json({
            "type": "hack_the_mainframe",
            "payload": {"data": "malicious"}
        })
        
        response = ws.receive_json()
        assert response["type"] == "error"
        assert "Unknown event type: hack_the_mainframe" in response["payload"]["message"]

@patch("interfaces.websocket.search_conversations")
def test_websocket_missing_payload_keys(mock_search):
    """Edge Case: Ensures handlers don't crash with KeyError if payload is completely empty."""
    # Fake the database response so we don't need the background DB thread
    mock_search.return_value = [{"id": 1, "title": "Mocked Search Result"}]
    
    client = TestClient(app)
    with client.websocket_connect("/ws/main") as ws:
        # Send a valid event type, but completely omit the payload and conversation_id
        ws.send_json({
            "type": "user_message"
            # Missing payload entirely
        })
        
        # The handler should safely catch the missing 'content' and return early without crashing
        # We send a follow-up ping to ensure the connection is still alive
        ws.send_json({"type": "search_threads", "payload": {"query": "test"}})
        response = ws.receive_json()
        
        assert response["type"] == "search_results" # Proves the socket didn't crash!

# =====================================================================
# 2. STREAM PROCESSOR EXTREME HALLUCINATIONS
# =====================================================================

def mock_stream_generator(chunks):
    for chunk in chunks:
        yield chunk

def test_stream_processor_micro_fragmentation():
    """
    Brutal Test: The LLM network stream is incredibly slow and fragmented.
    It sends a JSON tool call exactly ONE character at a time across 30 chunks.
    Ensures the tool_buffer concatenation doesn't drop a single character.
    """
    json_payload = '{"cmd": "echo hello", "path": "/test"}'
    chunks = []
    
    # Create a stream chunk for EVERY SINGLE CHARACTER
    for char in json_payload:
        chunks.append(StreamChunk(
            tool_call_deltas=[{"id": "call_micro", "name": "run_terminal_command", "arguments": char}]
        ))
    
    chunks.append(StreamChunk(is_finished=True))
    
    stream = mock_stream_generator(chunks)
    _, tool_calls, _, _ = process_llm_stream(stream, MagicMock())
    
    assert len(tool_calls) == 1
    assert tool_calls[0].id == "call_micro"
    # If it parsed successfully into a dict, the concatenation was flawless
    assert tool_calls[0].args["cmd"] == "echo hello"
    assert tool_calls[0].args["path"] == "/test"

def test_stream_processor_mixed_valid_and_broken_tools():
    """
    Edge Case: The LLM calls TWO tools in parallel. 
    Tool A is perfect JSON. Tool B is completely destroyed JSON.
    Ensures Tool A survives and executes, while Tool B safely falls back to {}.
    """
    chunks = [
        StreamChunk(tool_call_deltas=[
            {"id": "call_good", "name": "read_files", "arguments": '{"paths": ["test.txt"]}'},
            {"id": "call_bad", "name": "write_files", "arguments": '{"content": "missing bracket'}
        ]),
        StreamChunk(is_finished=True)
    ]
    
    stream = mock_stream_generator(chunks)
    _, tool_calls, _, _ = process_llm_stream(stream, MagicMock())
    
    assert len(tool_calls) == 2
    
    # Verify Good Tool
    good_tool = next(t for t in tool_calls if t.id == "call_good")
    assert good_tool.args == {"paths": ["test.txt"]}
    
    # Verify Bad Tool (Should be caught by JSONDecodeError and fallback to {})
    bad_tool = next(t for t in tool_calls if t.id == "call_bad")
    assert bad_tool.args == {}

# =====================================================================
# 3. CONTEXT MANAGER EXTREME LIMITS
# =====================================================================

@patch("managers.conversation_manager.get_connection")
@patch("managers.conversation_manager._estimate_tokens")
def test_compile_llm_context_massive_single_message(mock_estimate, mock_conn):
    """
    Safety Check: What happens if a SINGLE message is larger than the max_context_tokens?
    Ensures the while loop breaks safely and doesn't infinite-loop trying to trim an untrimmable array.
    """
    mock_cursor = mock_conn.return_value.execute.return_value
    mock_cursor.fetchone.return_value = None # No summary
    
    # DB returns exactly ONE message, but it's massive
    mock_cursor.fetchall.return_value = [
        {"role": "user", "content": "Massive text..."}
    ]
    
    # Token estimator says this 1 message is 200,000 tokens (Limit is 100,000)
    mock_estimate.return_value = 200000 
    
    # If the safety break `len(context_messages) > 1` fails, this will infinite loop and crash the test.
    result = compile_llm_context(conversation_id=1, max_tokens=100000)
    
    # It should safely return the 1 message, accepting the API will likely reject it, 
    # rather than crashing the local backend loop.
    assert len(result) == 1
    assert result[0]["role"] == "user"

