from utils.config.core import load_config, save_config


def get_default_provider() -> str:
    config = load_config()
    return config["models"].get("default_provider", "gemini")


def set_default_provider(provider_name: str) -> None:
    config = load_config()
    config["models"]["default_provider"] = provider_name.strip().lower()
    save_config(config)


def get_active_model(provider_name: str) -> str:
    config = load_config()
    models_map = config["models"].get("active_models", {})
    fallback = (
        "gemini-3.1-flash-lite"
        if provider_name.lower() == "gemini"
        else "llama-3.3-70b-versatile"
    )
    return models_map.get(provider_name.lower(), fallback)


def set_active_model(provider_name: str, model_name: str) -> None:
    config = load_config()
    if "active_models" not in config["models"]:
        config["models"]["active_models"] = {}
    config["models"]["active_models"][provider_name.lower()] = model_name
    save_config(config)


def get_temperature() -> float:
    config = load_config()
    return float(config["models"].get("temperature", 0.2))


def set_temperature(temp: float) -> None:
    config = load_config()
    config["models"]["temperature"] = max(0.0, min(float(temp), 2.0))
    save_config(config)


def get_embedding_model(provider_name: str) -> str:
    config = load_config()
    fallback = (
        "gemini-embedding-001"
        if provider_name.lower() == "gemini"
        else "nomic-embed-text-v1_5"
    )
    return (
        config["models"]
        .get("embedding_models", {})
        .get(provider_name.lower(), fallback)
    )


def set_embedding_model(provider_name: str, model_name: str) -> None:
    config = load_config()
    if "embedding_models" not in config["models"]:
        config["models"]["embedding_models"] = {}
    config["models"]["embedding_models"][provider_name.lower()] = model_name
    save_config(config)


def get_default_embedding_provider() -> str:
    config = load_config()
    return config["models"].get("default_embedding_provider", "gemini")


def set_default_embedding_provider(provider_name: str) -> None:
    config = load_config()
    config["models"]["default_embedding_provider"] = provider_name.strip().lower()
    save_config(config)
