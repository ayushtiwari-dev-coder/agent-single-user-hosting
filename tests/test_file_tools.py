# tests/test_file_tools.py
import pytest
import os
from unittest.mock import patch, mock_open
from tools.file_tools import _get_safe_path, write_file, read_file, WORKSPACE_DIR

def test_get_safe_path_valid():
    """Ensures valid filenames are mapped inside the workspace."""
    path = _get_safe_path("test.txt")
    assert path.startswith(WORKSPACE_DIR)
    assert path.endswith("test.txt")

def test_get_safe_path_directory_traversal():
    """Ensures malicious path traversal is blocked."""
    with pytest.raises(ValueError, match="Permission denied"):
        _get_safe_path("../../../etc/passwd")

@patch("tools.file_tools.open", new_callable=mock_open)
def test_write_file_success(mock_file):
    """Ensures writing to a file works and returns a success string."""
    result = write_file("hello.txt", "world")
    assert "Successfully wrote" in result
    mock_file().write.assert_called_once_with("world")

@patch("tools.file_tools.os.path.exists", return_value=True)
@patch("tools.file_tools.open", new_callable=mock_open, read_data="File content here")
def test_read_file_success(mock_file, mock_exists):
    """Ensures reading a file returns its content."""
    result = read_file("hello.txt")
    assert result == "File content here"

@patch("tools.file_tools.os.path.exists", return_value=False)
def test_read_file_not_found(mock_exists):
    """Ensures reading a missing file returns a clean error."""
    result = read_file("missing.txt")
    assert "does not exist" in result

@patch("tools.file_tools.open", side_effect=PermissionError("Access Denied"))
def test_write_file_os_error(mock_file):
    """Edge Case: OS-level write failures (e.g., permissions, disk full) are caught cleanly."""
    result = write_file("test.txt", "data")
    assert "Error writing file" in result
    assert "Access Denied" in result

@patch("tools.file_tools.os.path.exists", return_value=True)
@patch("tools.file_tools.open", side_effect=IsADirectoryError("Is a directory"))
def test_read_file_is_directory_error(mock_file, mock_exists):
    """Edge Case: LLM tries to read a folder instead of a file."""
    result = read_file("some_folder")
    assert "Error reading file" in result
    assert "Is a directory" in result