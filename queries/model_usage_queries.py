import sqlite3
from database.helper import execute_read, execute_write


def log_model_usage(
    conversation_id: int | None,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> dict:
    """
    Logs token consumption. Automatically sums total_tokens.
    """
    total_tokens = prompt_tokens + completion_tokens
    query = "INSERT INTO model_usage (conversation_id, model_name, prompt_tokens, completion_tokens, total_tokens) VALUES (?, ?, ?, ?, ?);"
    usage_id = execute_write(
        query,
        (conversation_id, model_name, prompt_tokens, completion_tokens, total_tokens),
    )
    return get_usage_by_id(usage_id)


def get_usage_by_id(usage_id: int) -> dict:
    """
    Retrieves a single usage log record.
    """
    query = "SELECT id, conversation_id, model_name, prompt_tokens, completion_tokens, total_tokens, created_at FROM model_usage WHERE id = ?;"
    usage = execute_read(query, (usage_id,), fetch_one=True)
    if usage is None:
        raise ValueError(f"Usage record with ID {usage_id} not found.")
    return usage


def get_total_usage_stats() -> dict:
    """
    Retrieves aggregate token consumption statistics across the system.
    """
    query = """
    SELECT 
        COALESCE(SUM(prompt_tokens), 0) AS total_prompt_tokens, 
        COALESCE(SUM(completion_tokens), 0) AS total_completion_tokens, 
        COALESCE(SUM(total_tokens), 0) AS grand_total_tokens 
    FROM model_usage;
    """
    return execute_read(query, fetch_one=True)
