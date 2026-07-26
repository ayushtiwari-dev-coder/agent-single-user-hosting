import os
from utils.config.core import load_config, save_config


def get_user_profile() -> tuple[str | None, str | None]:
    """Returns (display_name, username) of the active user."""
    config = load_config()
    profile = config.get("user_profile", {})
    return profile.get("name"), profile.get("username")


def set_user_profile(name: str, username: str) -> None:
    config = load_config()
    config["user_profile"]["name"] = name.strip()
    config["user_profile"]["username"] = username.strip().lower()
    save_config(config)


def get_provider_api_key(provider_name: str) -> str | None:
    """Gets the API key, falling back safely to OS environment variables."""
    config = load_config()
    provider_name = provider_name.strip().lower()
    key = config["user_profile"].get("api_keys", {}).get(provider_name)
    if key:
        return key

    env_var_map = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY"}
    return os.environ.get(env_var_map.get(provider_name, ""))


def set_provider_api_key(provider_name: str, api_key: str | None) -> None:
    config = load_config()
    provider_name = provider_name.strip().lower()
    if "api_keys" not in config["user_profile"]:
        config["user_profile"]["api_keys"] = {}
    config["user_profile"]["api_keys"][provider_name] = api_key
    save_config(config)
