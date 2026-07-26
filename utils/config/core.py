import os
import json
from database.connection import APP_DIR

CONFIG_PATH = os.path.join(APP_DIR, "config.json")

# Default template updated with the new multitasking and resource thresholds
DEFAULT_CONFIG = {
    "user_profile": {
        "name": None,
        "username": None,
        "api_keys": {"gemini": None, "groq": None},
    },
    "models": {
        "default_provider": "gemini",
        "default_embedding_provider": "gemini",
        "active_models": {
            "gemini": "gemini-3.1-flash-lite",
            "groq": "llama-3.3-70b-versatile",
        },
        "embedding_models": {
            "gemini": "gemini-embedding-001",
            "groq": "nomic-embed-text-v1.5",
        },
        "temperature": 0.2,
    },
    "settings": {
        "thinking_level": "high",
        "max_turns": 15,
        "max_context_tokens": 100000,
        "summary_trigger_count": 30,
        "loop_guard": {"max_failed_attempts": 3, "max_success_attempts": 2},
        "system_instruction": None,
        "sandbox": {
            "memory_limit": "512m",
            "cpu_limit": 1000000000,
            "timeout_seconds": 15,
            "docker_image": "python:3.11-slim",
            "workspace_path": "~/.local_workflow_agent/workspace",
            "max_active_containers": 3,
            "max_total_containers": 10,
            "container_idle_timeout_minutes": 30.0,
        },
        "telegram": {
            "bot_token": None,
            "allowed_user_ids": [],
        },
        "cli": {"log_truncation_limit": 500},
        "max_concurrent_chats": 3,
    },
}


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        # Deep merge to guarantee structure compatibility
        merged = DEFAULT_CONFIG.copy()
        for k, v in user_config.items():
            if isinstance(v, dict) and k in merged:
                merged[k].update(v)
            else:
                merged[k] = v
        return merged
    except Exception:
        return DEFAULT_CONFIG


def save_config(config: dict) -> None:
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"\n[Warning] Failed to save local configuration: {e}")
