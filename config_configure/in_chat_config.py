# config_configure/in_chat_config.py

import utils.config_manager as config_manager
from queries.memory_queries import search_memories
from queries.conversation_queries import delete_conversation


def switch_active_model(provider_choice: str, model_choice: str) -> dict:
    """Headless function to switch the active model and provider mid-chat."""
    try:
        config_manager.set_active_model(provider_choice, model_choice)
        config_manager.set_default_provider(provider_choice)
        resolved_key = config_manager.get_provider_api_key(provider_choice)

        return {
            "status": "success",
            "message": f"Assistant is now running: [{provider_choice.upper()}] - {model_choice}",
            "data": {
                "provider": provider_choice,
                "model": model_choice,
                "api_key": resolved_key,
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def update_temperature(temp_val: float) -> dict:
    """Headless function to update the model temperature."""
    if 0.0 <= temp_val <= 2.0:
        config_manager.set_temperature(temp_val)
        return {
            "status": "success",
            "message": f"Temperature updated to {temp_val}!",
            "data": {"temperature": temp_val},
        }
    return {
        "status": "error",
        "message": "Out of range. Choose a value between 0.0 and 2.0.",
    }


def update_thinking_level(level: str) -> dict:
    """Headless function to update the reasoning/thinking budget."""
    level_map = {"1": "off", "2": "low", "3": "medium", "4": "high"}
    selected_level = (
        level_map.get(str(level).strip().lower()) or str(level).strip().lower()
    )

    if selected_level in ["off", "low", "medium", "high"]:
        config_manager.set_thinking_level(selected_level)
        return {
            "status": "success",
            "message": f"Thinking level updated to {selected_level.upper()}!",
            "data": {"thinking_level": selected_level},
        }
    return {"status": "error", "message": "Invalid selection."}


def search_semantic_memories(query: str) -> dict:
    """Headless function to query the semantic memory database."""
    if not query or not query.strip():
        return {"status": "error", "message": "Query cannot be empty.", "data": []}

    results = search_memories(query.strip())
    return {
        "status": "success",
        "message": f"Found {len(results)} matching memories.",
        "data": results,
    }


def delete_active_conversation(conversation_id: int) -> dict:
    """Headless function to delete a conversation thread."""
    try:
        delete_conversation(conversation_id)
        return {"status": "success", "message": "Conversation deleted successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
