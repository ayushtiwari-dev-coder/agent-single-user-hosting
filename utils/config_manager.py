from utils.config.core import load_config, save_config
from utils.config.models import (
    get_default_provider,
    set_default_provider,
    get_default_embedding_provider,
    set_default_embedding_provider,
    get_active_model,
    set_active_model,
    get_temperature,
    set_temperature,
    get_embedding_model,
    set_embedding_model,
)
from utils.config.settings import (
    get_thinking_level,
    set_thinking_level,
    get_max_turns,
    set_max_turns,
    get_loop_guard,
    set_loop_guard,
    get_max_context_tokens,
    set_max_context_tokens,
    get_summary_trigger_count,
    set_summary_trigger_count,
    get_cli_log_truncation_limit,
    set_cli_log_truncation_limit,
    get_memory_similarity_threshold,
    set_memory_similarity_threshold,
    get_api_retry_settings,
    set_api_retry_settings,
    get_system_instruction,
    set_system_instruction,
    get_workspace_path,
    set_workspace_path,
    get_telegram_config,
    set_telegram_config,
    get_max_concurrent_chats,
    set_max_concurrent_chats,
    # DOCKER RE-ACTIVATION REFERENCE:
    # If Docker sandboxing is enabled, uncomment these imported functions:
    # get_max_active_containers,
    # set_max_active_containers,
    # get_max_total_containers,
    # set_max_total_containers,
    # get_container_idle_timeout,
    # set_container_idle_timeout,
    # get_docker_image,
    # set_docker_image,
    # get_sandbox_settings,
    # set_sandbox_settings,
)
from utils.config.user import (
    get_user_profile,
    set_user_profile,
    get_provider_api_key,
    set_provider_api_key,
)


def is_provider_configured(provider_name: str) -> bool:
    return bool(get_provider_api_key(provider_name))


def has_any_provider_configured() -> bool:
    return is_provider_configured("gemini") or is_provider_configured("groq")
