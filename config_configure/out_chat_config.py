# config_configure/out_chat_config.py

import utils.config_manager as config_manager


def get_providers_status() -> dict:
    """Headless function to retrieve the configuration status of all providers."""
    gemini_status = (
        "Configured" if config_manager.is_provider_configured("gemini") else "Not Set"
    )
    groq_status = (
        "Configured" if config_manager.is_provider_configured("groq") else "Not Set"
    )
    active_default = config_manager.get_default_provider()

    return {
        "status": "success",
        "data": {
            "gemini": gemini_status,
            "groq": groq_status,
            "active_default": active_default,
            "active_gemini_model": config_manager.get_active_model("gemini"),
            "active_groq_model": config_manager.get_active_model("groq"),
        },
    }


def validate_and_set_api_key(provider: str, key: str, force_save: bool = False) -> dict:
    """Headless function to validate and securely store an API key."""
    is_valid = False
    error_msg = ""

    try:
        if provider == "gemini":
            from google import genai

            client = genai.Client(api_key=key)
            client.models.generate_content(
                model="gemini-3.1-flash-lite", contents="test validation key"
            )
            is_valid = True
        elif provider == "groq":
            from groq import Groq

            client = Groq(api_key=key)
            client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": "test validation key"}],
                max_tokens=1,
            )
            is_valid = True
    except Exception as e:
        error_msg = str(e)

    if is_valid or force_save:
        config_manager.set_provider_api_key(provider, key)
        return {
            "status": "success",
            "message": f"Successfully configured {provider.upper()}!",
        }

    return {
        "status": "error",
        "message": f"Validation failed: {error_msg}",
        "requires_force": True,
    }


def set_active_default_provider(provider: str) -> dict:
    """Headless function to switch the global default provider."""
    config_manager.set_default_provider(provider)
    return {
        "status": "success",
        "message": f"Default provider changed to {provider.upper()}.",
    }


def update_system_instruction(instruction: str | None) -> dict:
    """Headless function to update the base system prompt."""
    if instruction and instruction.strip().upper() == "CLEAR":
        instruction = None

    config_manager.set_system_instruction(instruction)
    msg = (
        "Reverted to default instructions."
        if not instruction
        else "System instructions updated."
    )
    return {"status": "success", "message": msg}


def update_embedding_model(provider: str, model: str) -> dict:
    """Headless function to update the embedding model for a provider."""
    config_manager.set_embedding_model(provider, model)
    return {
        "status": "success",
        "message": f"{provider.capitalize()} embedding model updated to: {model}",
    }


def update_max_turns(turns: int) -> dict:
    """Headless function to update ReAct loop maximum turns."""
    config_manager.set_max_turns(turns)
    return {
        "status": "success",
        "message": f"Max turns successfully updated to {config_manager.get_max_turns()}!",
    }


def update_max_context_tokens(tokens: int) -> dict:
    """Headless function to update the sliding window context size."""
    config_manager.set_max_context_tokens(tokens)
    return {
        "status": "success",
        "message": f"Max tokens successfully updated to {config_manager.get_max_context_tokens()}!",
    }


def update_summary_trigger_count(count: int) -> dict:
    """Headless function to update the background summary threshold."""
    config_manager.set_summary_trigger_count(count)
    return {
        "status": "success",
        "message": f"Trigger count successfully updated to {config_manager.get_summary_trigger_count()}!",
    }


def update_cli_log_truncation(limit: int) -> dict:
    """Headless function to update the CLI log truncation length."""
    config_manager.set_cli_log_truncation_limit(limit)
    return {
        "status": "success",
        "message": f"Truncation limit successfully updated to {config_manager.get_cli_log_truncation_limit()} characters!",
    }


def update_memory_similarity_threshold(score: float) -> dict:
    """Headless function to update the semantic memory clustering threshold."""
    if 0.0 <= score <= 1.0:
        config_manager.set_memory_similarity_threshold(score)
        return {
            "status": "success",
            "message": f"Memory matching threshold successfully updated to {config_manager.get_memory_similarity_threshold()}!",
        }
    return {
        "status": "error",
        "message": "Out of range. Value must be between 0.0 and 1.0.",
    }


def update_api_retry_settings(attempts: int, delay: float) -> dict:
    """Headless function to update network retry bounds."""
    config_manager.set_api_retry_settings(max_attempts=attempts, base_delay=delay)
    return {
        "status": "success",
        "message": "Network API retry bounds successfully updated!",
    }


def update_loop_guard(max_failed: int | None, max_success: int | None) -> dict:
    """Headless function to update infinite loop guard thresholds."""
    config_manager.set_loop_guard(max_failed, max_success)
    return {
        "status": "success",
        "message": "Loop Guard thresholds updated successfully!",
    }


def update_workspace_path(path: str) -> dict:
    """Headless function to update the absolute path for the local workspace."""
    config_manager.set_workspace_path(path)
    return {"status": "success", "message": "Workspace path updated successfully."}


def get_telegram_settings() -> dict:
    """Headless function to retrieve Telegram configuration safely."""
    config = config_manager.get_telegram_config()
    token = config.get("bot_token")

    # Mask the token so it doesn't print the whole secret in the UI
    masked_token = (
        f"{token[:5]}...{token[-4:]}" if token and len(token) > 10 else "Not Set"
    )

    return {
        "status": "success",
        "data": {
            "bot_token_masked": masked_token,
            "has_token": bool(token),
            "allowed_user_ids": config.get("allowed_user_ids", []),
        },
    }


def update_telegram_settings(
    bot_token: str | None = None, allowed_users_str: str | None = None
) -> dict:
    """Headless function to update Telegram bot token and/or whitelist."""
    current = config_manager.get_telegram_config()

    # If None is passed, keep the existing token
    new_token = bot_token if bot_token is not None else current.get("bot_token")

    # If None is passed, keep the existing users
    if allowed_users_str is not None:
        users = []
        if allowed_users_str.strip():
            parts = allowed_users_str.split(",")
            for p in parts:
                p = p.strip()
                if p.isdigit():
                    users.append(int(p))
                else:
                    return {
                        "status": "error",
                        "message": f"Invalid User ID: '{p}'. Must be numbers only.",
                    }
    else:
        users = current.get("allowed_user_ids", [])

    config_manager.set_telegram_config(new_token, users)
    return {
        "status": "success",
        "message": "Telegram configuration updated successfully!",
    }


def set_default_embedding_provider(provider: str) -> dict:
    """Headless function to switch the global default embedding provider."""
    config_manager.set_default_embedding_provider(provider)
    return {
        "status": "success",
        "message": f"Default embedding provider changed to {provider.upper()}.",
    }


def update_max_concurrent_chats(count: int) -> dict:
    """Headless function to update the maximum concurrent chats limit."""
    config_manager.set_max_concurrent_chats(count)
    return {
        "status": "success",
        "message": f"Maximum concurrent chats successfully updated to {config_manager.get_max_concurrent_chats()}!",
    }
