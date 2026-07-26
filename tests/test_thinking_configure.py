# tests/test_thinking_configure.py
import pytest
from unittest.mock import patch, MagicMock
from engine.thinking_configure import supports_thinking, get_thinking_config


def test_supports_thinking_logic():
    # Native support models
    assert supports_thinking("gemini-3.1-flash-lite") is True
    assert supports_thinking("gemma-4-26b-a4b-it") is True
    # Non-support models
    assert supports_thinking("gemini-2.5-flash") is False


def test_get_thinking_config_off():
    # Setting configuration level to off immediately returns None
    config = get_thinking_config("gemini-3.1-flash-lite", level="off")
    assert config is None


@patch("engine.thinking_configure.types")
def test_get_thinking_config_enum_mapping(mock_types):
    mock_types.ThinkingLevel.LOW = "MOCK_LOW_ENUM"
    mock_types.ThinkingConfig = MagicMock(return_value="SUCCESSFUL_CONFIG_OBJECT")

    config = get_thinking_config("gemini-3.1-flash-lite", level="low")
    mock_types.ThinkingConfig.assert_called_with(thinking_level="MOCK_LOW_ENUM")
    assert config == "SUCCESSFUL_CONFIG_OBJECT"


@patch("engine.thinking_configure.types")
def test_get_thinking_config_fallback_string_mapping(mock_types):
    # Simulate missing enums in older client library versions
    del mock_types.ThinkingLevel
    mock_types.ThinkingConfig = MagicMock(return_value="FALLBACK_CONFIG_OBJECT")

    config = get_thinking_config("gemini-3.1-flash-lite", level="high")
    mock_types.ThinkingConfig.assert_called_with(thinking_level="HIGH")
    assert config == "FALLBACK_CONFIG_OBJECT"
