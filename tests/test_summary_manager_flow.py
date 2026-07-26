import pytest
from unittest.mock import patch, MagicMock
from managers.summary_manager import _run_summary_workflow


@patch(
    "managers.summary_manager.config_manager.get_summary_trigger_count", return_value=5
)
@patch("managers.summary_manager.get_summary_by_conversation", return_value=None)
@patch("managers.summary_manager.execute_read")
@patch("managers.summary_manager.LLMFactory.get_provider")
@patch("managers.summary_manager.create_or_update_summary")
@patch("managers.summary_manager.logger")
def test_summary_workflow_llm_empty_response(
    mock_logger,
    mock_create_summary,
    mock_get_provider,
    mock_execute_read,
    mock_get_summary,
    mock_trigger,
):
    """Brutal Test: LLM returns an empty string. Ensure we don't overwrite the DB with nothing."""
    mock_execute_read.return_value = [
        {"id": i, "role": "user", "content": f"Msg {i}"} for i in range(6)
    ]

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.text = ""  # LLM Hallucinates an empty response
    mock_llm.generate_content.return_value = mock_response
    mock_get_provider.return_value = mock_llm

    _run_summary_workflow("gemini", "fake", "gemini", 1)

    # Ensure we DID NOT save an empty summary to the database
    mock_create_summary.assert_not_called()


@patch(
    "managers.summary_manager.config_manager.get_summary_trigger_count", return_value=5
)
@patch("managers.summary_manager.get_summary_by_conversation", return_value=None)
@patch("managers.summary_manager.execute_read")
@patch("managers.summary_manager.LLMFactory.get_provider")
@patch("managers.summary_manager.logger")
def test_summary_workflow_llm_exception(
    mock_logger, mock_get_provider, mock_execute_read, mock_get_summary, mock_trigger
):
    """Brutal Test: LLM throws an exception. Ensure the background thread catches it and doesn't crash the app."""
    mock_execute_read.return_value = [
        {"id": i, "role": "user", "content": f"Msg {i}"} for i in range(6)
    ]

    mock_llm = MagicMock()
    mock_llm.generate_content.side_effect = Exception("API Timeout")
    mock_get_provider.return_value = mock_llm

    # This should execute silently and log the exception, NOT crash.
    _run_summary_workflow("gemini", "fake", "gemini", 1)

    mock_logger.exception.assert_called_once()
    assert (
        "Background summary generation failed" in mock_logger.exception.call_args[0][0]
    )


@patch("managers.summary_manager.get_summary_by_conversation")  # <-- ADDED THIS PATCH
@patch("managers.summary_manager.execute_read")
def test_summary_workflow_db_locked(mock_execute_read, mock_get_summary):
    """Brutal Test: Database is locked/fails during read. Thread should exit safely."""
    mock_get_summary.return_value = None
    mock_execute_read.side_effect = Exception("database is locked")

    # Should safely return without crashing
    _run_summary_workflow("gemini", "fake", "gemini", 1)
