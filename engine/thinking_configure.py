# engine/thinking_configure.py
from google.genai import types

THINKING_CAPABLE_PREFIX = "gemini-3"


def supports_thinking(model_name: str) -> bool:
    """Verifies if the model name supports thinking capabilities (Gemini 3.x and Gemma 4)."""
    name_lower = model_name.lower()
    return name_lower.startswith("gemini-3") or name_lower.startswith("gemma-4")


def get_thinking_config(
    model_name: str, level: str = "high"
) -> types.ThinkingConfig | None:
    """
    Returns the appropriate ThinkingConfig for the model.
    Accepts levels: 'low', 'medium', 'high', 'off'.
    Returns None if level is 'off' or if the model does not support thinking.
    """
    if level.lower() == "off":
        return None

    if not supports_thinking(model_name):
        return None

    # Safely extract the Google SDK enum or fall back to native strings
    try:
        level_map = {
            "low": types.ThinkingLevel.LOW,
            "medium": types.ThinkingLevel.MEDIUM,
            "high": types.ThinkingLevel.HIGH,
        }
        thinking_level = level_map.get(level.lower(), types.ThinkingLevel.HIGH)
    except AttributeError:
        # Fallback if specific SDK version has different enum locations
        level_map = {
            "low": "LOW",
            "medium": "MEDIUM",
            "high": "HIGH",
        }
        thinking_level = level_map.get(level.lower(), "HIGH")

    return types.ThinkingConfig(thinking_level=thinking_level)
