import os
from dotenv import load_dotenv


def get_project_root() -> str:
    """
    Resolves the absolute path to the root directory of this project.
    This file lives in local_workflow_agent/utils/path_helper.py
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up one level to get to local_workflow_agent/
    return os.path.dirname(current_dir)


def resolve_absolute_path(relative_path: str) -> str:
    """
    Converts any relative project path into a secure, absolute path
    starting from the project root directory.
    """
    root_dir = get_project_root()
    return os.path.abspath(os.path.join(root_dir, relative_path))


def load_env_file() -> None:
    """
    Locates the .env file in the project root and populates os.environ.
    Attempts to use python-dotenv if available, falling back to a robust
    standard-library parser if the dependency is not installed.
    """
    env_path = resolve_absolute_path(".env")
    if not os.path.exists(env_path):
        return

    try:
        # Attempt standard python-dotenv approach with explicit absolute path

        load_dotenv(dotenv_path=env_path)
    except ImportError:
        # Standard library fallback to avoid dependency errors on local machines
        _load_env_fallback(env_path)


def _load_env_fallback(env_path: str) -> None:
    """
    A robust parser that handles inline comments, whitespace, and
    quote stripping without external dependencies.
    """
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Ignore empty lines and direct comment lines
            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()

                # Strip trailing inline comments if present (e.g., KEY=VAL # comment)
                if " #" in val:
                    val = val.split(" #", 1)[0].strip()

                # Remove wrapping double or single quotes
                if (val.startswith('"') and val.endswith('"')) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    val = val[1:-1]

                os.environ[key] = val
