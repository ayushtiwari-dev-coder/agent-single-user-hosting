# tests/test_telegram_worker_flow.py
import pytest
import sys
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def clean_telegram_module():
    """Forces a clean import of the telegram module so tests don't poison each other."""
    with patch("utils.config_manager.get_telegram_config") as mock_tg_config, patch(
        "telebot.TeleBot"
    ) as mock_telebot:

        # Provide fake config so the module doesn't exit(1) during import
        mock_tg_config.return_value = {
            "bot_token": "fake_token",
            "allowed_user_ids": [12345],
        }

        # Force Python to reload the module completely fresh
        if "interfaces.telegram_bot" in sys.modules:
            del sys.modules["interfaces.telegram_bot"]

        import interfaces.telegram_bot as tg_bot

        yield tg_bot


@patch("interfaces.telegram_bot.get_latest_tg_conversation")
@patch("interfaces.telegram_bot.config_manager")
@patch("interfaces.telegram_bot.AgentEngine")
def test_agent_worker_thread_success(
    mock_engine_class, mock_config, mock_get_conv, clean_telegram_module
):
    tg_bot = clean_telegram_module

    mock_get_conv.return_value = {"id": 99}
    mock_config.get_default_provider.return_value = "gemini"
    mock_config.get_active_model.return_value = "gemini-3.1"
    mock_config.get_provider_api_key.return_value = "fake_key"

    mock_engine_instance = MagicMock()
    mock_engine_instance.send_message.return_value = "This is the final answer."
    mock_engine_class.return_value = mock_engine_instance

    tg_bot.bot.reset_mock()
    tg_bot.agent_worker_thread(chat_id=12345, user_text="Hello bot")

    # Debugging assertion: If it fails, print the actual error the bot tried to send!
    actual_calls = tg_bot.bot.send_message.call_args_list
    assert (
        tg_bot.bot.send_chat_action.call_count == 1
    ), f"Failed early! Bot caught this hidden error: {actual_calls}"

    tg_bot.bot.send_chat_action.assert_called_once_with(12345, "typing")
    tg_bot.bot.send_message.assert_called_with(
        12345, "This is the final answer.", parse_mode="Markdown"
    )


@patch("interfaces.telegram_bot.get_latest_tg_conversation")
@patch("interfaces.telegram_bot.config_manager")
@patch("interfaces.telegram_bot.AgentEngine")
def test_agent_worker_thread_engine_crash(
    mock_engine_class, mock_config, mock_get_conv, clean_telegram_module
):
    tg_bot = clean_telegram_module
    mock_get_conv.return_value = {"id": 99}

    mock_engine_instance = MagicMock()
    mock_engine_instance.send_message.side_effect = Exception("LLM Provider is down")
    mock_engine_class.return_value = mock_engine_instance

    tg_bot.bot.reset_mock()
    tg_bot.agent_worker_thread(chat_id=12345, user_text="Hello bot")

    # 1. Verify send_message was called exactly once
    assert tg_bot.bot.send_message.call_count == 1

    # 2. Extract the arguments it was called with
    args, kwargs = tg_bot.bot.send_message.call_args

    # args[0] is the chat_id, args[1] is the text message
    assert args[0] == 12345

    # 3. Check that the message CONTAINS our error, ignoring exact emojis/newlines
    assert "unexpected execution error" in args[1]
    assert "LLM Provider is down" in args[1]
    assert kwargs.get("parse_mode") == "Markdown"
