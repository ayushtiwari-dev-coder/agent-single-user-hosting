# interfaces/telegram_bot.py
import os
import time
import telebot
import threading
import json
from functools import partial
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import utils.config_manager as config_manager
from engine.agent_engine import AgentEngine
from managers.approval_manager import wait_for_decision, resolve_decision
from queries.conversation_queries import (
    create_conversation,
    get_latest_conversation_by_title,
)
import interfaces.telegram_menu as tg_menu

# 1. Load Config with Environment Variable Fallbacks
tg_config = config_manager.get_telegram_config()
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or tg_config.get("bot_token")

env_users = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
if env_users:
    ALLOWED_USERS = [int(uid.strip()) for uid in env_users.split(",") if uid.strip().isdigit()]
else:
    ALLOWED_USERS = tg_config.get("allowed_user_ids", [])

if not BOT_TOKEN:
    print("[Error] TELEGRAM_BOT_TOKEN is not set in environment or config.json.")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

def is_authorized(update) -> bool:
    """Security check: Only allow whitelisted Telegram User IDs."""
    if not ALLOWED_USERS:
        # If no whitelist specified, allow all requests (or log warning)
        return True
        
    user_id = update.from_user.id
    if user_id not in ALLOWED_USERS:
        chat_id = update.message.chat.id if hasattr(update, "message") else update.chat.id
        print(f"[SECURITY BLOCK] Unauthorized access attempt from User ID: {user_id}")
        bot.send_message(chat_id, f"🚫 Unauthorized. Your User ID is {user_id}.")
        return False
    return True

def get_latest_tg_conversation(chat_id: int) -> dict:
    """Fetches the most recent active conversation for this specific Telegram chat."""
    title = f"Telegram Chat {chat_id}"
    conversation = get_latest_conversation_by_title(title)
    if conversation:
        return conversation
    return create_conversation(title=title)

class TelegramStreamBuffer:
    """Buffers stream chunks and edits a single message in-place without duplicating."""
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.msg_id = None
        self.full_text = ""
        self.last_update_time = 0

    def handle_chunk(self, chunk: str):
        self.full_text += chunk
        now = time.time()
        
        # Create initial message on first chunk
        if self.msg_id is None:
            try:
                sent = bot.send_message(self.chat_id, self.full_text)
                self.msg_id = sent.message_id
                self.last_update_time = now
            except Exception:
                pass
        # Edit the existing message at most once every 1.5 seconds to prevent rate limits
        elif now - self.last_update_time > 1.5:
            try:
                bot.edit_message_text(
                    self.full_text,
                    chat_id=self.chat_id,
                    message_id=self.msg_id
                )
                self.last_update_time = now
            except Exception:
                pass

def agent_worker_thread(chat_id: int, user_text: str):
    """The central orchestrator for processing agent loops in a safe background thread."""
    try:
        conv = get_latest_tg_conversation(chat_id)
        conv_id = conv["id"]

        provider_choice = config_manager.get_default_provider()
        model_choice = config_manager.get_active_model(provider_choice)
        resolved_key = config_manager.get_provider_api_key(provider_choice)

        engine = AgentEngine(
            provider_name=provider_choice,
            model_name=model_choice,
            api_key=resolved_key,
            autonomous=False,
        )

        bot.send_chat_action(chat_id, "typing")
        
        # Instantiate single-message stream buffer
        stream_buffer = TelegramStreamBuffer(chat_id)

        def telegram_approval_callback(tool_name: str, tool_args: dict, c_id: int) -> bool:
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{c_id}"),
                InlineKeyboardButton("🚫 Deny", callback_data=f"deny_{c_id}"),
            )
            prompt_msg = (
                f"🚨 *Action Required*\nApprove execution of `{tool_name}`?\n\n"
                f"Arguments:\n```json\n{json.dumps(tool_args, indent=2)}\n```"
            )
            bot.send_message(chat_id, prompt_msg, reply_markup=markup, parse_mode="Markdown")
            return wait_for_decision(c_id, timeout=300)

        final_response = engine.send_message(
            conversation_id=conv_id,
            user_text=user_text,
            source="telegram",
            send_message_callback=stream_buffer.handle_chunk,
            status_callback=lambda status: print(f"[Telegram Status] {status}"),
            approval_callback=telegram_approval_callback,
        )

        # Final Render: If a streaming message was created, update it to formatted Markdown.
        # Otherwise, send the final response as a single message.
        if stream_buffer.msg_id is not None:
            try:
                bot.edit_message_text(
                    final_response,
                    chat_id=chat_id,
                    message_id=stream_buffer.msg_id,
                    parse_mode="Markdown"
                )
            except Exception:
                # Fallback without Markdown if parsing fails
                bot.edit_message_text(
                    final_response,
                    chat_id=chat_id,
                    message_id=stream_buffer.msg_id
                )
        else:
            try:
                bot.send_message(chat_id, final_response, parse_mode="Markdown")
            except Exception:
                bot.send_message(chat_id, final_response)

    except Exception as e:
        print(f"[Fatal Error in Agent Worker Thread]: {e}")
        try:
            bot.send_message(chat_id, f"🚨 An unexpected error occurred: `{str(e)}`", parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, f"🚨 An unexpected error occurred: {str(e)}")

@bot.message_handler(commands=["start", "help", "menu", "settings"])
def send_menu(message):
    if not is_authorized(message):
        return
    text, markup = tg_menu.get_main_menu()
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=["clean"])
def handle_clean_command(message):
    if not is_authorized(message):
        return
    create_conversation(title=f"Telegram Chat {message.chat.id}")
    bot.reply_to(message, "🧹 *Memory cleared!* Started a brand new conversation context.", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("tg_cmd_") or call.data.startswith("tg_set_"))
def handle_config_queries(call):
    if not is_authorized(call):
        return
    tg_menu.process_menu_callback(bot, call, call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_") or call.data.startswith("deny_"))
def handle_approval_query(call):
    if not is_authorized(call):
        return
    action, conv_id_str = call.data.split("_")
    conv_id = int(conv_id_str)
    approved = (action == "approve")

    success = resolve_decision(conv_id, approved)
    if success:
        bot.answer_callback_query(call.id, "Action registered.")
        status_text = "✅ *Action Approved*" if approved else "🚫 *Action Denied*"
        bot.edit_message_text(
            text=f"{call.message.text}\n\n{status_text}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown",
        )
    else:
        bot.answer_callback_query(call.id, "Error: Approval session expired or not found.")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    if not is_authorized(message):
        return
    threading.Thread(target=agent_worker_thread, args=(message.chat.id, message.text)).start()

def run_telegram_bot():
    print("🚀 Starting Telegram Bot (Long Polling)...")
    bot.infinity_polling()