# FILE: llm/generate_with_retry.py
import time
import utils.config_manager as config_manager


def generate_with_retry(
    request_fn,
    is_quota_error_fn,
    status_callback=None,
    max_attempts: int = None,
    base_delay: float = None,
) -> any:
    """
    Generic template to safely handle content generation and API requests for any LLM
    provider. Handles rate-limits (429s), transient exceptions, empty responses, and exponential backoff
    while updating the system console via status callbacks.
    """
    retry_settings = config_manager.get_api_retry_settings()
    if max_attempts is None:
        max_attempts = retry_settings.get("max_attempts", 3)
    if base_delay is None:
        base_delay = retry_settings.get("base_delay", 2.0)

    for attempt in range(max_attempts):
        try:
            # 1. Execute the actual provider request
            response = request_fn()
            if response:
                return response

            # Handle empty responses
            if attempt < max_attempts - 1:
                delay = base_delay * (2**attempt)
                if status_callback:
                    status_callback(
                        f"Encountered empty response. "
                        f"Retrying execution loop in {delay:.1f} seconds (Attempt {attempt + 1}/{max_attempts})..."
                    )
                time.sleep(delay)

        except Exception as e:
            # 2. Check if the error is a 429 rate limit
            is_quota_error = is_quota_error_fn(e)

            if is_quota_error:
                quota_delay = base_delay * 3.0
                if status_callback:
                    status_callback(
                        f"Encountered a rate limit or quota error (429) inside this workflow. "
                        f"Waiting {quota_delay:.1f} seconds before initiating recovery retry..."
                    )
                time.sleep(quota_delay)

                # Attempt generation exactly once more
                try:
                    response = request_fn()
                    if response:
                        return response
                    raise RuntimeError(
                        "Daily quota limit has been reached. Stopping the request at this moment."
                    )
                except Exception as retry_err:
                    # Only report "quota exhausted" if the retry actually failed for
                    # a quota-related reason. Anything else (network blip, transient
                    # server error, etc.) gets its own accurate message instead of
                    # being mislabeled as a quota failure.
                    if is_quota_error_fn(retry_err):
                        raise RuntimeError(
                            "Daily quota limit has been reached. Stopping the request at this moment."
                        ) from retry_err
                    raise RuntimeError(
                        f"Request failed after quota-error retry: {retry_err}"
                    ) from retry_err

            # For other transient exceptions, check if we have reached the limit
            if attempt == max_attempts - 1:
                raise e

            delay = base_delay * (2**attempt)
            exc_str = str(e)
            if status_callback:
                status_callback(
                    f"Encountered an error inside this workflow: '{exc_str}'. "
                    f"Retrying execution loop in {delay:.1f} seconds (Attempt {attempt + 1}/{max_attempts})...."
                )
            time.sleep(delay)

    raise RuntimeError("No response returned after multiple retries.")


def is_quota_error(e: Exception) -> bool:
    """
    Checks if a raised exception represents a 429 rate limit, resource exhaustion,
    or quota exhaustion across any integration provider.
    """
    exc_str = str(e).lower()
    exc_class = type(e).__name__.lower()

    # Common signature flags used across major provider packages
    quota_signals = ["resourceexhausted", "429", "quota", "ratelimit", "limit exceeded"]
    return any(signal in exc_str or signal in exc_class for signal in quota_signals)
