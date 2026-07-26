# tests/test_config_configure.py

import pytest
from unittest.mock import patch, MagicMock

# Import the modules to test
import config_configure.in_chat_config as in_chat
import config_configure.out_chat_config as out_chat


@patch("config_configure.in_chat_config.config_manager")
def test_switch_active_model_success(mock_cm):
    """Ensures switching models returns the correct success dictionary."""
    mock_cm.get_provider_api_key.return_value = "mock_key_123"
    res = in_chat.switch_active_model("gemini", "gemini-3.1-flash-lite")

    assert res["status"] == "success"
    assert "Assistant is now running" in res["message"]
    assert res["data"]["provider"] == "gemini"
    assert res["data"]["api_key"] == "mock_key_123"
    mock_cm.set_active_model.assert_called_once_with("gemini", "gemini-3.1-flash-lite")


@patch("config_configure.in_chat_config.config_manager")
def test_update_temperature_valid(mock_cm):
    """Ensures valid temperatures are accepted and formatted correctly."""
    res = in_chat.update_temperature(0.7)

    assert res["status"] == "success"
    assert "Temperature updated to 0.7" in res["message"]
    assert res["data"]["temperature"] == 0.7
    mock_cm.set_temperature.assert_called_once_with(0.7)


def test_update_temperature_invalid():
    """Ensures out-of-bounds temperatures are rejected."""
    res = in_chat.update_temperature(2.5)  # Max is 2.0

    assert res["status"] == "error"
    assert "Out of range" in res["message"]


@patch("config_configure.in_chat_config.config_manager")
def test_update_thinking_level_valid(mock_cm):
    """Ensures thinking level updates correctly using string mapping."""
    res = in_chat.update_thinking_level("3")  # "3" maps to "medium"

    assert res["status"] == "success"
    assert "MEDIUM" in res["message"]
    assert res["data"]["thinking_level"] == "medium"
    mock_cm.set_thinking_level.assert_called_once_with("medium")


@patch("config_configure.in_chat_config.search_memories")
def test_search_semantic_memories(mock_search):
    """Ensures memory search returns the correct data payload."""
    mock_search.return_value = [{"id": 1, "content": "User likes Python"}]

    res = in_chat.search_semantic_memories("Python")

    assert res["status"] == "success"
    assert "Found 1 matching memories" in res["message"]
    assert len(res["data"]) == 1


def test_search_semantic_memories_empty():
    """Ensures empty queries are rejected cleanly."""
    res = in_chat.search_semantic_memories("   ")

    assert res["status"] == "error"
    assert "Query cannot be empty" in res["message"]


@patch("config_configure.in_chat_config.delete_conversation")
def test_delete_active_conversation(mock_delete):
    """Ensures conversation deletion returns a success contract."""
    res = in_chat.delete_active_conversation(42)

    assert res["status"] == "success"
    assert "deleted successfully" in res["message"]
    mock_delete.assert_called_once_with(42)


@patch("config_configure.out_chat_config.config_manager")
def test_get_providers_status(mock_cm):
    """Ensures provider status aggregates correctly."""
    mock_cm.is_provider_configured.side_effect = (
        lambda p: p == "gemini"
    )  # Only Gemini configured
    mock_cm.get_default_provider.return_value = "gemini"
    mock_cm.get_active_model.return_value = "gemini-3.1-flash-lite"

    res = out_chat.get_providers_status()

    assert res["status"] == "success"
    assert res["data"]["gemini"] == "Configured"
    assert res["data"]["groq"] == "Not Set"
    assert res["data"]["active_default"] == "gemini"


@patch("config_configure.out_chat_config.config_manager")
def test_update_system_instruction(mock_cm):
    """Ensures system instruction updates and handles 'CLEAR' logic."""
    # Test setting a custom prompt
    res1 = out_chat.update_system_instruction("You are a helpful bot.")
    assert res1["status"] == "success"
    assert "System instructions updated" in res1["message"]
    mock_cm.set_system_instruction.assert_called_with("You are a helpful bot.")

    # Test clearing the prompt
    res2 = out_chat.update_system_instruction("CLEAR")
    assert res2["status"] == "success"
    assert "Reverted to default" in res2["message"]
    mock_cm.set_system_instruction.assert_called_with(None)


@patch("config_configure.out_chat_config.config_manager")
def test_update_loop_guard(mock_cm):
    """Ensures infinite loop guard thresholds update correctly."""
    res = out_chat.update_loop_guard(5, 3)

    assert res["status"] == "success"
    assert "Loop Guard thresholds updated" in res["message"]
    mock_cm.set_loop_guard.assert_called_once_with(5, 3)


@patch("google.genai.Client")
def test_validate_and_set_api_key_gemini_success(mock_genai_client):
    """Ensures Gemini API key validation passes and saves the key."""
    mock_instance = MagicMock()
    mock_genai_client.return_value = mock_instance

    with patch(
        "config_configure.out_chat_config.config_manager.set_provider_api_key"
    ) as mock_set_key:
        res = out_chat.validate_and_set_api_key("gemini", "valid_test_key")

        assert res["status"] == "success"
        assert "Successfully configured GEMINI" in res["message"]
        mock_instance.models.generate_content.assert_called_once()
        mock_set_key.assert_called_once_with("gemini", "valid_test_key")


@patch("groq.Groq")
def test_validate_and_set_api_key_groq_failure(mock_groq_client):
    """Ensures failed Groq API key validation returns an error but allows force_save."""
    mock_instance = MagicMock()
    mock_instance.chat.completions.create.side_effect = Exception("Invalid API Key")
    mock_groq_client.return_value = mock_instance

    # 1. Test standard failure
    res_fail = out_chat.validate_and_set_api_key("groq", "bad_key")
    assert res_fail["status"] == "error"
    assert "Validation failed" in res_fail["message"]
    assert res_fail["requires_force"] is True

    # 2. Test force save bypasses the failure
    with patch(
        "config_configure.out_chat_config.config_manager.set_provider_api_key"
    ) as mock_set_key:
        res_force = out_chat.validate_and_set_api_key(
            "groq", "bad_key", force_save=True
        )
        assert res_force["status"] == "success"
        mock_set_key.assert_called_once_with("groq", "bad_key")


@patch("config_configure.out_chat_config.config_manager")
def test_update_max_concurrent_chats(mock_cm):
    """Ensures max concurrent chats updates correctly."""
    # Mock the getter to return the new value for the success message
    mock_cm.get_max_concurrent_chats.return_value = 4

    res = out_chat.update_max_concurrent_chats(4)

    assert res["status"] == "success"
    assert "updated to 4" in res["message"]
    mock_cm.set_max_concurrent_chats.assert_called_once_with(4)
