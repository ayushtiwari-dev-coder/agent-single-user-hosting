# tests/test_summary_manager.py
import pytest
from unittest.mock import patch, MagicMock
from managers.summary_manager import _run_summary_workflow


@patch(
    "managers.summary_manager.config_manager.get_summary_trigger_count", return_value=5
)
@patch("managers.summary_manager.get_summary_by_conversation")
@patch("managers.summary_manager.execute_read")
@patch("managers.summary_manager.LLMFactory.get_provider")
@patch("managers.summary_manager.create_or_update_summary")
def test_summary_workflow_triggers_and_saves(
    mock_create_summary,
    mock_get_provider,
    mock_execute_read,
    mock_get_summary,
    mock_trigger,
):
    """Ensures the background summarizer compiles text and saves it to the DB."""
    # Mock DB returning no previous summary
    mock_get_summary.return_value = None

    # Mock DB returning 6 raw messages (which is > the trigger count of 5)
    mock_execute_read.return_value = [
        {"id": i, "role": "user", "content": f"Message {i}"} for i in range(6)
    ]

    # Mock LLM Provider
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "This is the new compressed summary."
    mock_llm.generate_content.return_value = mock_response
    mock_get_provider.return_value = mock_llm

    # Run workflow
    _run_summary_workflow(
        provider_name="gemini", api_key="fake", model_name="gemini", conversation_id=1
    )

    # Assert LLM was called to generate the summary
    mock_llm.generate_content.assert_called_once()

    # Assert the new summary was saved to the database (linked to the last message ID: 5)
    mock_create_summary.assert_called_once_with(
        1, "This is the new compressed summary.", 5
    )


@patch(
    "managers.summary_manager.config_manager.get_summary_trigger_count", return_value=10
)
@patch(
    "managers.summary_manager.get_summary_by_conversation"
)  # FIX: Added missing DB mock
@patch("managers.summary_manager.execute_read")
@patch("managers.summary_manager.LLMFactory.get_provider")
def test_summary_workflow_skips_if_under_threshold(
    mock_get_provider, mock_execute_read, mock_get_summary, mock_trigger
):
    """Ensures it does NOT waste API calls if there aren't enough messages yet."""
    mock_get_summary.return_value = None

    # Mock DB returning only 2 messages (Threshold is 10)
    mock_execute_read.return_value = [
        {"id": 1, "role": "user", "content": "Hi"},
        {"id": 2, "role": "assistant", "content": "Hello"},
    ]

    _run_summary_workflow(
        provider_name="gemini", api_key="fake", model_name="gemini", conversation_id=1
    )

    # Assert LLM was NEVER called
    mock_get_provider.assert_not_called()
