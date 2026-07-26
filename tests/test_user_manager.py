# tests/test_user_manager.py
import pytest
from unittest.mock import patch
from managers.user_manager import register_user


@patch("managers.user_manager.create_user")
def test_register_user_success(mock_create):
    """Verifies valid names and usernames pass constraints and are normalized."""
    mock_create.return_value = {"id": 1, "name": "John_Doe", "username": "johndoe"}
    user = register_user(" John_Doe ", "JohnDoe")

    mock_create.assert_called_once_with("John_Doe", "johndoe")
    assert user["username"] == "johndoe"


def test_register_user_length_limits():
    """Edge Case: Fails if the display name or username is empty or exceeds length boundaries."""
    with pytest.raises(ValueError, match="must be between 1 and 25"):
        register_user("", "valid_user")

    with pytest.raises(ValueError, match="must be between 1 and 25"):
        register_user("valid_name", "")

    with pytest.raises(ValueError, match="must be between 1 and 25"):
        register_user("A" * 26, "valid_user")


def test_register_user_invalid_characters():
    """Edge Case: Characters that violate formatting limits inside inputs are blocked."""
    invalid_names = ["Ayush@123", "Ayush!", "Ayush#"]
    for name in invalid_names:
        with pytest.raises(ValueError, match="Name contains invalid characters"):
            register_user(name, "valid_user")

    invalid_usernames = ["ayush tiwari", "ayush@tiwari", "ayush/tiwari"]
    for uname in invalid_usernames:
        with pytest.raises(ValueError, match="Username contains invalid characters"):
            # Ensure name has no spaces so execution reaches username checks
            register_user("Valid_Name", uname)
