import sqlite3
from database.helper import execute_read, execute_write


def create_message(conversation_id: int, role: str, content: str) -> dict:
    """
    Creates a new message. Validates role parameter first.
    """
    valid_roles = {"system", "user", "assistant"}
    if role not in valid_roles:
        raise ValueError(f"Invalid message role '{role}'. Must be one of {valid_roles}")

    query = "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?);"
    try:
        message_id = execute_write(query, (conversation_id, role, content))
        return get_message_by_id(message_id)
    except sqlite3.IntegrityError as e:
        raise ValueError(
            f"Cannot create message. Conversation with ID {conversation_id} does not exist."
        ) from e


def get_message_by_id(message_id: int) -> dict:
    """
    Retrieves a single message by its ID.
    """
    query = "SELECT id, conversation_id, role, content, created_at FROM messages WHERE id = ?;"
    message = execute_read(query, (message_id,), fetch_one=True)
    if message is None:
        raise ValueError(f"Message with ID {message_id} not found.")
    return message


def get_messages_by_conversation(conversation_id: int) -> list[dict]:
    """
    Retrieves all messages for a specific conversation in chronological order.
    """
    query = "SELECT id, conversation_id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC;"
    return execute_read(query, (conversation_id,))


def get_messages_paginated(
    conversation_id: int, before_id: int = None, limit: int = 20
) -> list[dict]:
    """Retrieves a chunk of older messages for infinite scrolling."""
    if before_id:
        query = "SELECT id, conversation_id, role, content, created_at FROM messages WHERE conversation_id = ? AND id < ? ORDER BY id DESC LIMIT ?;"
        rows = execute_read(query, (conversation_id, before_id, limit))
    else:
        query = "SELECT id, conversation_id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?;"
        rows = execute_read(query, (conversation_id, limit))

    # Reverse the rows so they are sent to the UI in chronological order (oldest first in the chunk)
    return list(reversed(rows)) if rows else []
