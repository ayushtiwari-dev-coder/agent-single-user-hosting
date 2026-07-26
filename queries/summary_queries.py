import sqlite3
from database.helper import execute_read, execute_write


def create_or_update_summary(
    conversation_id: int, summary_text: str, last_message_id: int
) -> dict:
    """
    Saves or updates the running summary of a conversation (Context Compression).
    """
    existing_summary = get_summary_by_conversation(conversation_id)

    if existing_summary:
        query = "UPDATE summaries SET summary_text = ?, last_summarized_message_id = ? WHERE conversation_id = ?;"
        params = (summary_text, last_message_id, conversation_id)
    else:
        query = "INSERT INTO summaries (summary_text, last_summarized_message_id, conversation_id) VALUES (?, ?, ?);"
        params = (summary_text, last_message_id, conversation_id)

    execute_write(query, params)
    return get_summary_by_conversation(conversation_id)


def get_summary_by_conversation(conversation_id: int) -> dict | None:
    """
    Retrieves the running summary for a specific conversation.
    """
    query = "SELECT id, conversation_id, summary_text, last_summarized_message_id, created_at FROM summaries WHERE conversation_id = ?;"
    return execute_read(query, (conversation_id,), fetch_one=True)
