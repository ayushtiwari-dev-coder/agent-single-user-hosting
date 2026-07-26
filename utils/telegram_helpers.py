# utils/telegram_helpers.py
import logging
from queries.conversation_queries import get_conversation_by_id

logger = logging.getLogger("utils.telegram_helpers")

def send_telegram_document(
    conversation_id: int,
    document_obj,  # Accepts io.BytesIO RAM buffer OR a local file path string
    filename: str,
    caption: str = ""
) -> bool:
    """
    Generic reusable helper to deliver any file or in-memory stream 
    directly to the Telegram chat linked to the conversation_id.
    """
    if not conversation_id:
        logger.error("send_telegram_document failed: missing conversation_id.")
        return False

    try:
        conv = get_conversation_by_id(conversation_id)
        conv_title = conv.get("title", "") if conv else ""

        if "Telegram Chat " not in conv_title:
            logger.error(f"Conversation {conversation_id} is not linked to a Telegram chat.")
            return False

        chat_id = int(conv_title.replace("Telegram Chat ", "").strip())


        from interfaces.telegram_bot import bot

        bot.send_document(
            chat_id=chat_id,
            document=document_obj,
            visible_file_name=filename,
            caption=caption,
            parse_mode="Markdown"
        )
        return True

    except Exception as e:
        logger.exception(f"Failed to deliver document '{filename}' to Telegram: {e}")
        return False