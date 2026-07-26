# interfaces/telegram_menu.py
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from cli.constants import SUPPORTED_MODELS
import config_configure.in_chat_config as in_chat_config
from queries.conversation_queries import create_conversation


def build_menu_box(layout: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    """
    TEMPLATE BUILDER: Creates a Telegram Inline Keyboard (Box) dynamically.
    'layout' is a list of rows. Each row is a list of (Button Text, Callback Data) tuples.
    """
    markup = InlineKeyboardMarkup()
    for row in layout:
        # Create a list of buttons for this row
        buttons = [InlineKeyboardButton(text, callback_data=cb) for text, cb in row]
        markup.row(*buttons)  # Unpack and add the row to the markup
    return markup


def get_main_menu() -> tuple[str, InlineKeyboardMarkup]:
    """Returns the text and box for the Main Menu."""
    layout = [
        [("🧹 New Chat (/clean)", "tg_cmd_clean")],
        [("🤖 Switch Model", "tg_cmd_model")],
        [("🧠 Thinking Level", "tg_cmd_think")],
    ]
    return "⚙️ *Agent Control Panel*\nChoose an option below:", build_menu_box(layout)


def get_model_menu() -> tuple[str, InlineKeyboardMarkup]:
    """Returns the text and box for the Model Selection Menu."""
    layout = []
    for provider, models in SUPPORTED_MODELS.items():
        for m in models:
            # Add one button per row
            layout.append(
                [
                    (
                        f"{provider.upper()}: {m['model']}",
                        f"tg_set_mod_{provider}_{m['model']}",
                    )
                ]
            )

    # Add a back button at the bottom
    layout.append([("🔙 Back to Menu", "tg_cmd_main")])
    return "🤖 *Select Active Model:*", build_menu_box(layout)


def get_thinking_menu() -> tuple[str, InlineKeyboardMarkup]:
    """Returns the text and box for the Thinking Level Menu."""
    layout = [
        # Two buttons per row
        [("Off", "tg_set_thk_off"), ("Low", "tg_set_thk_low")],
        [("Medium", "tg_set_thk_medium"), ("High", "tg_set_thk_high")],
        [("🔙 Back to Menu", "tg_cmd_main")],
    ]
    return "🧠 *Select Thinking Level:*", build_menu_box(layout)


def process_menu_callback(bot, call, chat_id: int, msg_id: int):
    """Routes the button click to the correct action and updates the UI."""
    cmd = call.data

    if cmd == "tg_cmd_main":
        text, markup = get_main_menu()
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=msg_id,
            reply_markup=markup,
            parse_mode="Markdown",
        )

    elif cmd == "tg_cmd_clean":
        create_conversation(title=f"Telegram Chat {chat_id}")
        bot.edit_message_text(
            "🧹 *Memory cleared!* Started a brand new conversation context.",
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="Markdown",
        )

    elif cmd == "tg_cmd_model":
        text, markup = get_model_menu()
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=msg_id,
            reply_markup=markup,
            parse_mode="Markdown",
        )

    elif cmd == "tg_cmd_think":
        text, markup = get_thinking_menu()
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=msg_id,
            reply_markup=markup,
            parse_mode="Markdown",
        )

    elif cmd.startswith("tg_set_mod_"):
        # Parse: tg_set_mod_gemini_gemini-3.1-flash-lite
        parts = cmd.replace("tg_set_mod_", "").split("_", 1)
        provider, model = parts[0], parts[1]
        res = in_chat_config.switch_active_model(provider, model)
        bot.edit_message_text(
            f"✅ {res['message']}", chat_id=chat_id, message_id=msg_id
        )

    elif cmd.startswith("tg_set_thk_"):
        level = cmd.replace("tg_set_thk_", "")
        res = in_chat_config.update_thinking_level(level)
        bot.edit_message_text(
            f"✅ {res['message']}", chat_id=chat_id, message_id=msg_id
        )
