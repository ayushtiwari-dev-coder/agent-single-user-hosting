# tests/test_telegram_bot.py
import pytest
import sys
from unittest.mock import patch, MagicMock


@pytest.fixture(scope="module", autouse=True)
def setup_telegram_mocks():
    """Mocks the config and TeleBot class before the module is imported."""
    with patch("utils.config_manager.get_telegram_config") as mock_config, patch(
        "telebot.TeleBot"
    ) as mock_telebot:

        mock_config.return_value = {
            "bot_token": "123456789:fake_test_token",
            "allowed_user_ids": [12345],
        }

        mock_bot_instance = MagicMock()

        def preserve_func(*args, **kwargs):
            return lambda func: func

        mock_bot_instance.message_handler.side_effect = preserve_func
        mock_bot_instance.callback_query_handler.side_effect = preserve_func
        mock_telebot.return_value = mock_bot_instance

        if "interfaces.telegram_bot" in sys.modules:
            del sys.modules["interfaces.telegram_bot"]

        import interfaces.telegram_bot

        yield interfaces.telegram_bot


@pytest.fixture
def tg_bot_module(setup_telegram_mocks):
    """Provides the telegram_bot module and resets the mock bot for each test."""
    setup_telegram_mocks.bot.reset_mock()
    return setup_telegram_mocks


def test_is_authorized_success(tg_bot_module):
    """Normal Flow: Whitelisted user is allowed."""
    mock_update = MagicMock()
    mock_update.from_user.id = 12345
    assert tg_bot_module.is_authorized(mock_update) is True


def test_is_authorized_failure(tg_bot_module):
    """Security: Non-whitelisted user is blocked and alerted."""
    mock_update = MagicMock()
    mock_update.from_user.id = 99999
    mock_update.message.chat.id = 111

    assert tg_bot_module.is_authorized(mock_update) is False
    tg_bot_module.bot.send_message.assert_called_once_with(
        111, "🚫 Unauthorized. Your User ID is 99999."
    )


@patch("interfaces.telegram_bot.resolve_decision")
def test_handle_approval_query_success(mock_resolve, tg_bot_module):
    """Normal Flow: User clicks 'Approve' button, unfreezing the engine."""
    mock_resolve.return_value = True

    mock_call = MagicMock()
    mock_call.from_user.id = 12345
    mock_call.data = "approve_42"
    mock_call.id = "query_1"
    mock_call.message.chat.id = 111
    mock_call.message.message_id = 222
    mock_call.message.text = "Original message text"

    tg_bot_module.handle_approval_query(mock_call)

    # Verify the Approval Manager was told to unfreeze thread 42 with True
    mock_resolve.assert_called_once_with(42, True)

    # Verify Telegram UI updated
    tg_bot_module.bot.answer_callback_query.assert_called_once_with(
        "query_1", "Action registered."
    )
    kwargs = tg_bot_module.bot.edit_message_text.call_args[1]
    assert "Action Approved" in kwargs["text"]


@patch("interfaces.telegram_bot.resolve_decision")
def test_handle_approval_query_expired(mock_resolve, tg_bot_module):
    """Edge Case: User clicks a button for a session that already timed out."""
    mock_resolve.return_value = False  # Manager says "Too late, event is gone"

    mock_call = MagicMock()
    mock_call.from_user.id = 12345
    mock_call.data = "deny_42"
    mock_call.id = "query_1"

    tg_bot_module.handle_approval_query(mock_call)

    tg_bot_module.bot.answer_callback_query.assert_called_once_with(
        "query_1", "Error: Approval session expired or not found."
    )


@patch(
    "interfaces.telegram_bot.config_manager.get_default_provider", return_value="gemini"
)
@patch(
    "interfaces.telegram_bot.config_manager.get_active_model",
    return_value="gemini-3.1-flash-lite",
)
@patch(
    "interfaces.telegram_bot.config_manager.get_provider_api_key",
    return_value="fake_key",
)
@patch("interfaces.telegram_bot.AgentEngine")
@patch("interfaces.telegram_bot.get_latest_tg_conversation")
@patch("interfaces.telegram_bot.wait_for_decision")
def test_telegram_approval_callback_generation(
    mock_wait,
    mock_get_conv,
    mock_engine_class,
    mock_key,
    mock_model,
    mock_prov,
    tg_bot_module,
):
    """Verifies that the Telegram worker thread correctly generates and passes the UI callback."""
    mock_get_conv.return_value = {"id": 1}
    engine_mock = mock_engine_class.return_value

    # Run the worker thread
    tg_bot_module.agent_worker_thread(chat_id=111, user_text="Hello")

    # Extract the approval_callback that was passed to the engine
    send_msg_kwargs = engine_mock.send_message.call_args[1]
    telegram_callback = send_msg_kwargs["approval_callback"]

    assert telegram_callback is not None

    # Simulate the engine triggering the callback
    mock_wait.return_value = True  # Simulate user clicking approve
    result = telegram_callback("run_terminal_command", {"cmd": "ls"}, 1)

    call_args, call_kwargs = tg_bot_module.bot.send_message.call_args

    assert "reply_markup" in call_kwargs
    assert "Action Required" in call_args[1]  # The text is the 2nd positional argument!

    # Verify it froze the thread
    mock_wait.assert_called_once_with(1, timeout=300)
    assert result is True
