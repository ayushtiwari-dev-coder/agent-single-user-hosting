# tools/memory_tools.py
"""
Long-Term Memory Tools.
Allows the agent to autonomously remember user preferences, facts, and retrieve past context.
"""

from managers.memory_manager import save_semantic_memory, retrieve_semantic_memory
from tools.core import agent_tool


@agent_tool()
def remember_user_preference(content: str, category: str) -> str:
    """
    Autonomously remembers a user preference, setting, configuration, or fact.
    The system automatically clusters it under the best category block.
    """
    try:
        save_semantic_memory(content, category)
        return "Memory successfully stored and clustered."
    except Exception as e:
        return f"Error: Failed to store memory: {e}"


@agent_tool()
def search_user_history(query: str, category: str) -> str:
    """
    Searches user context history inside a specific category block
    to retrieve facts, configurations, or personal preferences.
    """
    try:
        matches = retrieve_semantic_memory(query, category)
        if not matches:
            return "No relevant past history found in this block."
        return "\n".join(f"- {m}" for m in matches)
    except Exception as e:
        return f"Error: Memory search failed: {e}"
