# tests/test_engine_retry.py
import pytest
from unittest.mock import patch, MagicMock
from llm.generate_with_retry import generate_with_retry


@pytest.fixture
def mock_dependencies():
    """Clean initialization of mocks for generating with retry."""
    return {
        "request_fn": MagicMock(),
        "is_quota_error_fn": MagicMock(),
        "callback": MagicMock(),
    }


@patch("llm.generate_with_retry.time.sleep")
def test_success_first_try(mock_sleep, mock_dependencies):
    """Normal scenario: returns immediately on first success."""
    mock_response = MagicMock()
    mock_dependencies["request_fn"].return_value = mock_response

    result = generate_with_retry(
        request_fn=mock_dependencies["request_fn"],
        is_quota_error_fn=mock_dependencies["is_quota_error_fn"],
        status_callback=mock_dependencies["callback"],
        max_attempts=3,
    )

    assert result == mock_response
    assert mock_dependencies["request_fn"].call_count == 1
    mock_sleep.assert_not_called()


@patch("llm.generate_with_retry.time.sleep")
def test_exponential_backoff_transient_errors(mock_sleep, mock_dependencies):
    """Edge Case: Fails twice, succeeds on third try. Checks exact sleep scaling."""
    mock_response = MagicMock()
    mock_dependencies["request_fn"].side_effect = [
        Exception("503 Service Unavailable"),
        Exception("500 Internal Error"),
        mock_response,
    ]
    mock_dependencies["is_quota_error_fn"].return_value = False

    result = generate_with_retry(
        request_fn=mock_dependencies["request_fn"],
        is_quota_error_fn=mock_dependencies["is_quota_error_fn"],
        status_callback=mock_dependencies["callback"],
        max_attempts=3,
    )

    assert result == mock_response
    assert mock_dependencies["request_fn"].call_count == 3
    mock_sleep.assert_any_call(2.0)
    mock_sleep.assert_any_call(4.0)
    assert mock_sleep.call_count == 2


@patch("llm.generate_with_retry.time.sleep")
def test_429_quota_error_recovery(mock_sleep, mock_dependencies):
    """Edge Case: 429 Quota error triggers an immediate 3x base_delay sleep."""
    mock_response = MagicMock()
    mock_dependencies["request_fn"].side_effect = [
        Exception("ResourceExhausted: 429 Quota limit exceeded"),
        mock_response,
    ]
    mock_dependencies["is_quota_error_fn"].return_value = True

    result = generate_with_retry(
        request_fn=mock_dependencies["request_fn"],
        is_quota_error_fn=mock_dependencies["is_quota_error_fn"],
        status_callback=mock_dependencies["callback"],
        max_attempts=3,
    )

    assert result == mock_response
    mock_sleep.assert_called_once_with(6.0)


@patch("llm.generate_with_retry.time.sleep")
def test_429_quota_error_fatal(mock_sleep, mock_dependencies):
    """Edge Case: If 429 Quota fails twice, it crashes safely."""
    mock_dependencies["request_fn"].side_effect = [
        Exception("ResourceExhausted: 429 Quota limit exceeded"),
        Exception("ResourceExhausted: 429 Quota limit exceeded"),
    ]
    mock_dependencies["is_quota_error_fn"].return_value = True

    with pytest.raises(RuntimeError, match="Daily quota limit has been reached"):
        generate_with_retry(
            request_fn=mock_dependencies["request_fn"],
            is_quota_error_fn=mock_dependencies["is_quota_error_fn"],
            status_callback=mock_dependencies["callback"],
            max_attempts=3,
        )
