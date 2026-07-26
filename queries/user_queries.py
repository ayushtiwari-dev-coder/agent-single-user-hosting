import sqlite3
from database.helper import execute_read, execute_write


def create_user(name: str, username: str) -> dict:
    """
    Inserts a new user into the users table.
    """
    query = "INSERT INTO users (name, username) VALUES (?, ?);"
    try:
        user_id = execute_write(query, (name, username))
        return get_user_by_id(user_id)
    except sqlite3.IntegrityError as e:
        raise ValueError(f"Username '{username}' is already taken.") from e


def get_user_by_id(user_id: int) -> dict:
    """
    Retrieves a user by their unique database ID.
    """
    query = "SELECT id, name, username, created_at FROM users WHERE id = ?;"
    user = execute_read(query, (user_id,), fetch_one=True)
    if user is None:
        raise ValueError(f"User with ID {user_id} not found.")
    return user


def get_user_by_username(username: str) -> dict | None:
    """
    Retrieves a user by their unique username.
    """
    query = "SELECT id, name, username, created_at FROM users WHERE username = ?;"
    return execute_read(query, (username,), fetch_one=True)


def get_default_user() -> dict | None:
    """
    Retrieves the first user in the database.
    """
    query = "SELECT id, name, username, created_at FROM users ORDER BY id ASC LIMIT 1;"
    return execute_read(query, fetch_one=True)
