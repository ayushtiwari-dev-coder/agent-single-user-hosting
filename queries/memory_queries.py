import sqlite3
from database.helper import execute_read, execute_write


def get_memory_by_id(memory_id: int) -> dict:
    """
    Retrieves a single memory by its ID.
    """
    query = "SELECT id, content, category, created_at FROM memories WHERE id = ?;"
    memory = execute_read(query, (memory_id,), fetch_one=True)
    if memory is None:
        raise ValueError(f"Memory with ID {memory_id} not found.")
    return memory


def search_memories(search_term: str) -> list[dict]:
    """
    Keyword searches content and categories using wildcards.
    """
    query = "SELECT id, content, category, created_at FROM memories WHERE content LIKE ? OR category LIKE ? ORDER BY created_at DESC;"
    wildcard_term = f"%{search_term}%"
    return execute_read(query, (wildcard_term, wildcard_term))


def create_category_with_embedding(category: str, embedding_str: str) -> None:
    """Saves a new category/block centroid vector."""
    query = "INSERT INTO memory_categories (category, embedding) VALUES (?, ?);"
    execute_write(query, (category, embedding_str))


def get_all_categories() -> list[dict]:
    """Fetches all existing category/block titles and their centroids."""
    query = "SELECT category, embedding FROM memory_categories;"
    # execute_read returns a list of dicts when fetch_one=False
    return execute_read(query)


def create_memory_with_embedding(
    content: str, category: str, embedding_str: str
) -> dict:
    """Saves a new fact along with its serialized content vector."""
    query = "INSERT INTO memories (content, category, embedding) VALUES (?, ?, ?);"
    memory_id = execute_write(query, (content, category, embedding_str))

    # Fetch and return the newly created memory
    fetch_query = "SELECT id, content, category, created_at FROM memories WHERE id = ?;"
    return execute_read(fetch_query, (memory_id,), fetch_one=True)


def get_memories_by_category(category: str) -> list[dict]:
    """Retrieves all stored memories within a specific category block."""
    query = "SELECT id, content, category, embedding FROM memories WHERE category = ?;"
    return execute_read(query, (category,))
