from queries.user_queries import (
    create_user,
    get_user_by_id,
    get_user_by_username,
    get_default_user,
)


def get_active_user() -> dict | None:
    """
    Retrieves the default active user profile.
    """
    return get_default_user()


def register_user(name: str, username: str) -> dict:
    """
    Registers a new user in the system after running strict length
    and character validation checks.
    """
    # Define our whitelist of allowed characters (alphanumeric + underscore + dash + semicolon)
    allowed_chars = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-;"
    )

    clean_name = name.strip()
    clean_username = username.strip().lower()

    # 1. Length Checks (Must be between 1 and 25 characters)
    if not (1 <= len(clean_name) <= 25):
        raise ValueError("Name must be between 1 and 25 characters long.")
    if not (1 <= len(clean_username) <= 25):
        raise ValueError("Username must be between 1 and 25 characters long.")

    # 2. Strict Whitelist Check (Also naturally catches spaces, which are not in our whitelist)
    if not all(char in allowed_chars for char in clean_name):
        raise ValueError(
            "Name contains invalid characters. Only letters, numbers, underscores, "
            "dashes, and semicolons are allowed. Spaces are not permitted."
        )

    if not all(char in allowed_chars for char in clean_username):
        raise ValueError(
            "Username contains invalid characters. Only letters, numbers, underscores, "
            "dashes, and semicolons are allowed. Spaces are not permitted."
        )

    return create_user(clean_name, clean_username)


def find_user_by_id(user_id: int) -> dict:
    """
    Retrieves user details by their database ID.
    """
    return get_user_by_id(user_id)


def find_user_by_username(username: str) -> dict | None:
    """
    Retrieves user details by their unique username.
    """
    return get_user_by_username(username)
