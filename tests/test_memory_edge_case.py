# tests/test_memory_edge_case.py
import pytest
from unittest.mock import patch, MagicMock
from engine.handle_permissions import determine_and_execute_tool
from llm.providers.gemini import GeminiProvider
from tools.memory_tools import remember_user_preference


@patch("engine.handle_permissions.execute_and_format_tool")
def test_memory_tool_is_safe_by_default(mock_execute):
    """Edge Case: Memory tools are safe and MUST NOT trigger REQUIRES_APPROVAL."""
    mock_execute.return_value = ("Memory saved", "success")
    output, status = determine_and_execute_tool(
        "remember_user_preference",
        {"content": "User likes dark mode", "category": "UI"},
        conversation_id=1,
        autonomous=False,
    )
    assert status == "success"
    mock_execute.assert_called_once()


def test_gemini_embedding_api_failure():
    """Edge Case: If the Gemini API goes down, it must raise a clean RuntimeError."""
    provider = GeminiProvider(api_key="fake_key", model_name="gemini-3.1-flash-lite")
    provider.client.models.embed_content = MagicMock(
        side_effect=Exception("500 Internal Server Error")
    )

    with pytest.raises(
        RuntimeError, match="Gemini Embedding API failed: 500 Internal Server Error"
    ):
        provider.embed_text(["Test string"])


@patch("tools.memory_tools.save_semantic_memory")
def test_memory_tool_returns_error_to_llm(mock_save):
    """Edge Case: If the manager fails, the tool returns error string to LLM without crashing."""
    mock_save.side_effect = RuntimeError("Gemini Embedding API failed: Quota Exceeded")
    
    result = remember_user_preference("User likes dark mode", "UI Preferences")
    
    assert isinstance(result, str)
    assert result.startswith("Error: Failed to store memory")
    assert "Quota Exceeded" in result