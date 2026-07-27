# interfaces/telegram_bot.py
import os
import time
import telebot
import threading
import json
from functools import partial
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.apihelper import ApiTelegramException

import utils.config_manager as config_manager
from engine.agent_engine import AgentEngine
from managers.approval_manager import wait_for_decision, resolve_decision
from queries.conversation_queries import (
    create_conversation,
    get_latest_conversation_by_title,
)
import interfaces.telegram_menu as tg_menu
import re
import datetime
try:
    import zoneinfo
    TZ = zoneinfo.ZoneInfo("Asia/Kolkata")
except ImportError:
    from datetime import timezone
    TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

from queries.scheduler_queries import get_due_tasks, update_task_status, reschedule_task
from queries.conversation_queries import get_conversation_by_id


# 1. Load Config with Environment Variable Fallbacks
tg_config = config_manager.get_telegram_config()
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or tg_config.get("bot_token")

env_users = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
if env_users:
    ALLOWED_USERS = [int(uid.strip()) for uid in env_users.split(",") if uid.strip().isdigit()]
else:
    ALLOWED_USERS = tg_config.get("allowed_user_ids", [])

if not BOT_TOKEN:
    print("[Fatal Error] TELEGRAM_BOT_TOKEN is not set in environment or config.json.")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

def is_authorized(update) -> bool:
    """Security check: Only allow whitelisted Telegram User IDs."""
    if not ALLOWED_USERS:
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
    """Buffers stream chunks and edits a single message in-place safely."""
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
        # Edit the existing message at most once every 1.5 seconds
        elif now - self.last_update_time > 1.5:
            try:
                bot.edit_message_text(
                    self.full_text,
                    chat_id=self.chat_id,
                    message_id=self.msg_id
                )
                self.last_update_time = now
            except ApiTelegramException as e:
                # Ignore harmless 'message is not modified' Telegram errors
                if "message is not modified" in str(e).lower():
                    pass
                else:
                    print(f"[Stream Warning] {e}")
            except Exception:
                pass

def telegram_approval_callback(tool_name: str, tool_args: dict, c_id: int, chat_id: int) -> bool:
    """Top-level callback for Telegram UI approvals."""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{c_id}"),
        InlineKeyboardButton("🚫 Deny", callback_data=f"deny_{c_id}"),
    )
    prompt_msg = (
        f"⚠️ *Action Required*\nApprove execution of `{tool_name}`?\n\n"
        f"Arguments:\n```json\n{json.dumps(tool_args, indent=2)}\n```"
    )
    bot.send_message(chat_id, prompt_msg, reply_markup=markup, parse_mode="Markdown")
    return wait_for_decision(c_id, timeout=300)

def process_agent_interaction(chat_id: int, conv_id: int, user_text: str, source: str = "telegram") -> str:
    """Reusable core logic for setting up the engine, streaming, and rendering."""
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
    stream_buffer = TelegramStreamBuffer(chat_id)
    
    # Bind the chat_id to the top-level callback using functools.partial
    bound_approval_callback = partial(telegram_approval_callback, chat_id=chat_id)
    
    final_response = engine.send_message(
        conversation_id=conv_id,
        user_text=user_text,
        source=source,
        send_message_callback=stream_buffer.handle_chunk,
        status_callback=lambda status: print(f"[{source.capitalize()} Status] {status}"),
        approval_callback=bound_approval_callback,
    )
    
    # Final Render Safeguard
    if stream_buffer.msg_id is not None:
        try:
            bot.edit_message_text(
                final_response,
                chat_id=chat_id,
                message_id=stream_buffer.msg_id,
                parse_mode="Markdown"
            )
        except ApiTelegramException as e:
            if "message is not modified" in str(e).lower():
                pass
            else:
                try:
                    bot.edit_message_text(final_response, chat_id=chat_id, message_id=stream_buffer.msg_id)
                except Exception:
                    pass
        except Exception:
            pass
    else:
        try:
            bot.send_message(chat_id, final_response, parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, final_response)
            
    return final_response

# =====================================================================
# TELEGRAM WORKER THREAD
# =====================================================================

def agent_worker_thread(chat_id: int, user_text: str):
    """The central orchestrator for processing user messages in a safe background thread."""
    try:
        conv = get_latest_tg_conversation(chat_id)
        conv_id = conv["id"]
        
        # Call the shared core logic
        process_agent_interaction(chat_id, conv_id, user_text, source="telegram")
        
    except Exception as e:
        print(f"[Fatal Error in Agent Worker Thread]: {e}")
        try:
            bot.send_message(chat_id, f"⚠️ An unexpected error occurred: `{str(e)}`", parse_mode="Markdown")
        except Exception:
            bot.send_message(chat_id, f"⚠️ An unexpected error occurred: {str(e)}")

# =====================================================================
# BACKGROUND SCHEDULER LOOP
# =====================================================================

def calculate_next_execution(current_execute_at: str, recurrence: str) -> str:
    """Calculates the next execution time based on the recurrence rule."""
    dt = datetime.datetime.fromisoformat(current_execute_at.replace("Z", "+00:00"))
    rec = recurrence.strip().lower()
    
    if rec == "daily":
        dt += datetime.timedelta(days=1)
    elif rec == "twice_daily":
        dt += datetime.timedelta(hours=12)
    elif rec == "weekly":
        dt += datetime.timedelta(days=7)
    elif rec == "monthly":
        dt += datetime.timedelta(days=30)
    elif rec == "yearly":
        dt += datetime.timedelta(days=365)
    else:
        match = re.match(r"^(\d+)d$", rec)
        if match:
            dt += datetime.timedelta(days=int(match.group(1)))
        else:
            return None
            
    return dt.strftime("%Y-%m-%dT%H:%M:%S")

def execute_scheduled_task(task: dict):
    """Runs the scheduled task autonomously and streams output to Telegram."""
    task_id = task["id"]
    conv_id = task["conversation_id"]
    prompt = task["task_prompt"]
    
    try:
        conv = get_conversation_by_id(conv_id)
        chat_id = int(conv["title"].replace("Telegram Chat ", "").strip())

        active_conv=get_latest_tg_conversation(chat_id)
        current_conv_id=active_conv["id"]
        
        bot.send_message(chat_id, f"⏰ *Scheduled Task Triggered:*\n`{prompt}`", parse_mode="Markdown")
        
        system_prompt = f"[SCHEDULED TASK]: {prompt}"
        
        # Call the shared core logic!
        process_agent_interaction(chat_id, current_conv_id, system_prompt, source="scheduler")
        
        # Handle Recurrence
        recurrence = task.get("recurrence", "none")
        if recurrence == "none":
            update_task_status(task_id, "completed")
        else:
            next_time = calculate_next_execution(task["execute_at"], recurrence)
            if next_time:
                reschedule_task(task_id, next_time)
            else:
                update_task_status(task_id, "completed")
                
    except Exception as e:
        print(f"[Scheduler Error] Task {task_id} failed: {e}")
        update_task_status(task_id, "failed")

def start_scheduler_loop():
    """Background thread that wakes up every 60 seconds to check for due tasks."""
    print("⏰ Scheduler Loop Started...")
    while True:
        try:
            now_str = datetime.datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S")
            due_tasks = get_due_tasks(now_str)
            
            for task in due_tasks:
                update_task_status(task["id"], "processing")
                threading.Thread(target=execute_scheduled_task, args=(task,), daemon=True).start()
                
        except Exception as e:
            print(f"[Scheduler Loop Error]: {e}")
            
        time.sleep(60)


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
        try:
            bot.edit_message_text(
                text=f"{call.message.text}\n\n{status_text}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
            )
        except Exception:
            pass
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