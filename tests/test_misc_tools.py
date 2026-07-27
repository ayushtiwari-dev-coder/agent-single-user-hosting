# tests/test_misc_tools.py
import pytest
from unittest.mock import patch
from tools.memory_tools import remember_user_preference, search_user_history

@patch("tools.memory_tools.save_semantic_memory")
def test_remember_user_preference(mock_save):
    """Ensures memory saving tool calls the manager."""
    result = remember_user_preference("User likes Python", "Coding")
    assert "successfully stored" in result
    mock_save.assert_called_once_with("User likes Python", "Coding")

@patch("tools.memory_tools.retrieve_semantic_memory")
def test_search_user_history(mock_retrieve):
    """Ensures memory searching formats the list correctly."""
    mock_retrieve.return_value = ["User likes Python", "User uses VSCode"]
    result = search_user_history("What does user like?", "Coding")
    assert "- User likes Python" in result
    assert "- User uses VSCode" in result