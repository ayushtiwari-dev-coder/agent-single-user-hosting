# tools/file_tools.py
import os
from tools.core import agent_tool
from database.connection import APP_DIR

WORKSPACE_DIR = os.path.join(APP_DIR, "workspace")

def _get_safe_path(filename: str) -> str:
    """Ensures file path cannot escape the sandboxed workspace directory."""
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    safe_path = os.path.abspath(os.path.join(WORKSPACE_DIR, filename))
    if not safe_path.startswith(WORKSPACE_DIR):
        raise ValueError("Permission denied: Cannot access files outside the workspace directory.")
    return safe_path

@agent_tool()
def write_file(filename: str, content: str) -> str:
    """Writes text content to a specified file inside the workspace storage."""
    try:
        target_path = _get_safe_path(filename)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to '{filename}'."
    except Exception as e:
        return f"Error writing file '{filename}': {e}"

@agent_tool()
def read_file(filename: str) -> str:
    """Reads and returns text content from a specified file inside workspace storage."""
    try:
        target_path = _get_safe_path(filename)
        if not os.path.exists(target_path):
            return f"Error: File '{filename}' does not exist."
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file '{filename}': {e}"