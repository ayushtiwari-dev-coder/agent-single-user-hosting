# tests/test_handle_permissions.py
import pytest
import json
from unittest.mock import patch, MagicMock
from engine.handle_permissions import determine_and_execute_tool

@patch("engine.handle_permissions.FLAT_REGISTRY")
@patch("engine.handle_permissions.execute_and_format_tool")
@patch("engine.handle_permissions.log_tool_run")
def test_tool_executes_directly_no_approval_needed(mock_log, mock_execute, mock_registry):
    """Tools without the requires_approval flag execute instantly."""
    mock_execute.return_value = ("File contents", "success")
    
    # Mock a safe tool in the registry
    mock_tool = MagicMock()
    mock_tool.requires_approval = False
    mock_registry.get.return_value = mock_tool
    
    mock_callback = MagicMock()
    
    output, status = determine_and_execute_tool(
        "safe_tool",
        {"arg": "value"},
        conversation_id=1,
        autonomous=False,
        approval_callback=mock_callback,
    )
    
    assert status == "success"
    assert output == "File contents"
    mock_execute.assert_called_once()
    mock_callback.assert_not_called()  # Callback should NOT be triggered

@patch("engine.handle_permissions.FLAT_REGISTRY")
@patch("engine.handle_permissions.execute_and_format_tool")
@patch("engine.handle_permissions.log_tool_run")
def test_tool_requires_approval_missing_callback(mock_log, mock_execute, mock_registry):
    """If an unsafe tool is called but no UI callback is provided, it must fail safely."""
    # Mock a dangerous tool in the registry
    mock_tool = MagicMock()
    mock_tool.requires_approval = True
    mock_registry.get.return_value = mock_tool
    
    output, status = determine_and_execute_tool(
        "dangerous_tool",
        {"arg": "value"},
        conversation_id=1,
        autonomous=False,
        approval_callback=None,
    )
    
    assert status == "error"
    assert "no UI callback was provided" in output
    mock_execute.assert_not_called()
    mock_log.assert_called_once()

@patch("engine.handle_permissions.FLAT_REGISTRY")
@patch("engine.handle_permissions.execute_and_format_tool")
@patch("engine.handle_permissions.log_tool_run")
def test_tool_requires_approval_user_approves(mock_log, mock_execute, mock_registry):
    """Normal Flow: User approves via callback, tool executes."""
    mock_execute.return_value = ("Action done", "success")
    
    mock_tool = MagicMock()
    mock_tool.requires_approval = True
    mock_registry.get.return_value = mock_tool
    
    mock_callback = MagicMock(return_value=True)  # User clicks 'Yes'
    
    output, status = determine_and_execute_tool(
        "dangerous_tool",
        {"arg": "value"},
        conversation_id=1,
        autonomous=False,
        approval_callback=mock_callback,
    )
    
    assert status == "success"
    assert output == "Action done"
    mock_callback.assert_called_once_with("dangerous_tool", {"arg": "value"}, 1)
    mock_execute.assert_called_once()

@patch("engine.handle_permissions.FLAT_REGISTRY")
@patch("engine.handle_permissions.execute_and_format_tool")
@patch("engine.handle_permissions.log_tool_run")
def test_tool_requires_approval_user_denies(mock_log, mock_execute, mock_registry):
    """Normal Flow: User denies via callback, execution halts."""
    mock_tool = MagicMock()
    mock_tool.requires_approval = True
    mock_registry.get.return_value = mock_tool
    
    mock_callback = MagicMock(return_value=False)  # User clicks 'No'
    
    output, status = determine_and_execute_tool(
        "dangerous_tool",
        {"arg": "value"},
        conversation_id=1,
        autonomous=False,
        approval_callback=mock_callback,
    )
    
    assert status == "error"
    assert "Permission Denied" in output
    mock_callback.assert_called_once()
    mock_execute.assert_not_called()
    mock_log.assert_called_once()

@patch("engine.handle_permissions.FLAT_REGISTRY")
@patch("engine.handle_permissions.execute_and_format_tool")
def test_autonomous_mode_bypasses_approval(mock_execute, mock_registry):
    """If autonomous mode is True, even unsafe tools execute immediately."""
    mock_execute.return_value = ("Executed", "success")
    
    mock_tool = MagicMock()
    mock_tool.requires_approval = True
    mock_registry.get.return_value = mock_tool
    
    mock_callback = MagicMock()
    
    output, status = determine_and_execute_tool(
        "dangerous_tool",
        {"arg": "value"},
        conversation_id=1,
        autonomous=True,
        approval_callback=mock_callback,
    )
    
    assert status == "success"
    mock_execute.assert_called_once()
    mock_callback.assert_not_called()

@patch("engine.handle_permissions.FLAT_REGISTRY")
@patch("engine.handle_permissions.execute_tool") # FIX: Explicitly mock the executor
@patch("engine.handle_permissions.log_tool_run")
def test_tool_execution_os_level_crash(mock_log, mock_execute_tool, mock_registry):
    """
    Edge Case: The tool is safe/approved, but the actual Python execution 
    throws a hard OS error (e.g., MemoryError, PermissionError).
    """
    from engine.handle_permissions import determine_and_execute_tool
    
    # 1. Mock the registry so the permission handler thinks the tool is safe
    mock_tool = MagicMock()
    mock_tool.requires_approval = False
    mock_registry.get.return_value = mock_tool
    
    # 2. Simulate tools.registry.execute_tool catching an OS error
    # Your registry automatically wraps crashes in this specific "Error:" string format
    mock_execute_tool.return_value = "Error: Failed to execute tool 'read_secure_file': Permission denied: '/root/secret.txt'"

    # 3. Execute
    output, status = determine_and_execute_tool(
        tool_name="read_secure_file",
        tool_args={"path": "/root/secret.txt"},
        conversation_id=1,
        autonomous=True
    )

    # 4. Assertions
    assert status == "error"
    assert "Failed to execute tool" in output
    assert "Permission denied" in output
    
    # Ensure it was logged to the database as an error, not a success
    mock_log.assert_called_once()
    assert mock_log.call_args[0][3] == "error" # The 4th argument is 'status'