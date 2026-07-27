# tests/test_telegram_menu.py
import pytest
from unittest.mock import patch, MagicMock
from interfaces.telegram_menu import build_menu_box, get_main_menu, process_menu_callback

def test_build_menu_box():
    """Ensures the dynamic inline keyboard builder works."""
    layout = [[("Button 1", "cb_1"), ("Button 2", "cb_2")]]
    markup = build_menu_box(layout)
    assert markup is not None
    assert len(markup.keyboard) == 1 # 1 row
    assert len(markup.keyboard[0]) == 2 # 2 buttons

def test_get_main_menu():
    """Ensures the main menu returns text and markup."""
    text, markup = get_main_menu()
    assert "Agent Control Panel" in text
    assert markup is not None

@patch("interfaces.telegram_menu.in_chat_config")
def test_process_menu_callback_model_switch(mock_in_chat):
    """Ensures clicking a model button switches the model."""
    mock_bot = MagicMock()
    mock_call = MagicMock()
    mock_call.data = "tg_set_mod_gemini_gemini-3.1-flash-lite"
    mock_call.message.chat.id = 123
    mock_call.message.message_id = 456
    
    mock_in_chat.switch_active_model.return_value = {"message": "Switched!"}
    
    process_menu_callback(mock_bot, mock_call, 123, 456)
    
    mock_in_chat.switch_active_model.assert_called_once_with("gemini", "gemini-3.1-flash-lite")
    mock_bot.edit_message_text.assert_called_once()


def test_process_menu_callback_unknown_command():
    """Edge Case: User clicks a deprecated or unknown button. Should not crash."""
    mock_bot = MagicMock()
    mock_call = MagicMock()
    mock_call.data = "tg_cmd_hallucinated_button"
    
    # Should safely fall through the if/elif block and do nothing
    process_menu_callback(mock_bot, mock_call, 123, 456)
    
    mock_bot.edit_message_text.assert_not_called()