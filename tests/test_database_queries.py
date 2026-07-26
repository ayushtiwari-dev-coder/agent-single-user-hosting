# tests/test_database_queries.py
import pytest
import tempfile
import os
from unittest.mock import patch

from database.table_generator import create_tables
from queries.user_queries import create_user, get_user_by_id
from queries.conversation_queries import create_conversation, get_conversation_by_id
from queries.message_queries import create_message
from queries.memory_queries import (
    create_category_with_embedding,
    create_memory_with_embedding,
    get_all_categories,
    get_memories_by_category,
)


@pytest.fixture(autouse=True)
def temp_db_sandbox():
    """Sandboxes database connections by creating a temporary file and redirecting DB operations."""
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db_path = temp_db.name
    temp_db.close()

    # Patch the global DATABASE_PATH constant
    db_patcher = patch("database.connection.DATABASE_PATH", temp_db_path)
    db_patcher.start()

    # Initialize schema
    create_tables()

    yield temp_db_path

    db_patcher.stop()
    try:
        os.remove(temp_db_path)
    except OSError:
        pass


def test_create_and_fetch_user():
    """Tests standard creation and retrieval queries."""
    user = create_user("Test User", "testuser")
    assert user["username"] == "testuser"
    assert user["id"] is not None

    fetched = get_user_by_id(user["id"])
    assert fetched["name"] == "Test User"


def test_user_unique_constraint():
    """Edge Case: Cannot create two users with identical usernames."""
    create_user("User One", "unique_name")
    with pytest.raises(ValueError, match="is already taken"):
        create_user("User Two", "unique_name")


def test_message_role_constraint():
    """Edge Case: SQLite message insertion throws ValueError if role is invalid."""
    user = create_user("A", "A")
    conv = create_conversation(user["id"], "Test Title")

    with pytest.raises(ValueError, match="Invalid message role"):
        create_message(conv["id"], role="hacker", content="Malicious code")

    # Valid roles should pass
    msg = create_message(conv["id"], role="user", content="Good payload")
    assert msg["role"] == "user"


def test_missing_data_exceptions():
    """Ensures get_*_by_id functions raise clean ValueErrors when IDs don't exist."""
    with pytest.raises(ValueError):
        get_conversation_by_id(9999)


def test_semantic_memory_queries():
    """Verifies that memory categories and embedded memories are stored and retrieved correctly."""
    # 1. Write mock category and memory (using stringified JSON lists to mock vectors)
    mock_cat_embedding = "[0.1, 0.2, 0.3]"
    mock_mem_embedding = "[0.4, 0.5, 0.6]"

    create_category_with_embedding("Python Settings", mock_cat_embedding)
    create_memory_with_embedding(
        "User prefers Python 3.11", "Python Settings", mock_mem_embedding
    )

    # 2. Verify Category Retrieval
    categories = get_all_categories()
    assert len(categories) == 1
    assert categories[0]["category"] == "Python Settings"
    assert categories[0]["embedding"] == mock_cat_embedding

    # 3. Verify Memory Retrieval by Category
    memories = get_memories_by_category("Python Settings")
    assert len(memories) == 1
    assert memories[0]["content"] == "User prefers Python 3.11"
    assert memories[0]["category"] == "Python Settings"
    assert memories[0]["embedding"] == mock_mem_embedding

    # 4. Verify Empty Category Retrieval (No matches)
    empty_memories = get_memories_by_category("Non-existent Category")
    assert len(empty_memories) == 0
