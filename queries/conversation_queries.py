import sqlite3
from database.helper import execute_read, execute_write


def create_conversation(user_id: int = None, title: str = "New Conversation") -> dict:
    """
    Creates a new conversation record.
    """
    query = "INSERT INTO conversations (user_id, title) VALUES (?, ?);"
    conversation_id = execute_write(query, (user_id, title))
    return get_conversation_by_id(conversation_id)


def get_conversation_by_id(conversation_id: int) -> dict:
    """
    Retrieves a single conversation by its ID.
    """
    query = "SELECT id, user_id, title, created_at FROM conversations WHERE id = ?;"
    conversation = execute_read(query, (conversation_id,), fetch_one=True)
    if conversation is None:
        raise ValueError(f"Conversation with ID {conversation_id} not found.")
    return conversation


def get_all_conversations() -> list[dict]:
    """
    Retrieves all conversations (newest first).
    """
    query = "SELECT id, user_id, title, created_at FROM conversations WHERE user_id IS NOT NULL ORDER BY created_at DESC;"
    return execute_read(query)


def update_conversation_title(conversation_id: int, title: str) -> dict:
    """
    Updates the title of a conversation.
    """
    query = "UPDATE conversations SET title = ? WHERE id = ?;"
    rows_affected = execute_write(query, (title, conversation_id))
    if rows_affected == 0:
        raise ValueError(f"Conversation with ID {conversation_id} not found.")
    return get_conversation_by_id(conversation_id)


def delete_conversation(conversation_id: int) -> None:
    """
    Deletes conversation. Linked messages delete automatically via ON DELETE CASCADE.
    """
    query = "DELETE FROM conversations WHERE id = ?;"
    rows_affected = execute_write(query, (conversation_id,))
    if rows_affected == 0:
        raise ValueError(f"Conversation with ID {conversation_id} not found.")


def get_latest_conversation_by_title(title: str) -> dict | None:
    """Retrieves the most recent conversation matching a given title (even if user_id is NULL)."""
    query = """
    SELECT id, user_id, title, created_at 
    FROM conversations 
    WHERE title = ? 
    ORDER BY id DESC 
    LIMIT 1;
    """
    return execute_read(query, (title,), fetch_one=True)


def get_conversations_paginated(limit: int = 20, offset: int = 0) -> list[dict]:
    """Retrieves a chunk of recent conversations for the sidebar."""
    query = "SELECT id, user_id, title, created_at FROM conversations ORDER BY id DESC LIMIT ? OFFSET ?;"
    return execute_read(query, (limit, offset))


def search_conversations(search_term: str, limit: int = 20) -> list[dict]:
    """Live search for conversations by title."""
    query = "SELECT id, user_id, title, created_at FROM conversations WHERE title LIKE ? ORDER BY id DESC LIMIT ?;"
    return execute_read(query, (f"%{search_term}%", limit))
