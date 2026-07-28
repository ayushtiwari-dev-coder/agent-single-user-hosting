# tests/test_youtube_tools.py

import pytest
from unittest.mock import patch, MagicMock
from tools.youtube_tools import _extract_video_id, read_youtube_transcript

# =====================================================================
# 1. REGEX URL EXTRACTION TESTS
# =====================================================================

def test_extract_video_id_valid_urls():
    """Ensures the regex correctly extracts the 11-character ID from all valid YouTube formats."""
    assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert _extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s") == "dQw4w9WgXcQ"
    assert _extract_video_id("www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

def test_extract_video_id_invalid_urls():
    """Ensures the regex safely returns None for invalid or malformed URLs."""
    assert _extract_video_id("https://google.com") is None
    assert _extract_video_id("https://youtube.com/watch?v=") is None
    assert _extract_video_id("https://youtube.com/watch?v=12345") is None
    assert _extract_video_id("") is None

# =====================================================================
# 2. TOOL EXECUTION & RETRY LOGIC TESTS
# =====================================================================

@patch("tools.youtube_tools.TextFormatter")
@patch("tools.youtube_tools.YouTubeTranscriptApi")
def test_read_youtube_transcript_success(mock_api_class, mock_formatter_class):
    """Happy Path: Successfully fetches and formats the transcript on the first try."""
    # Mock the new API instance and fetch method
    mock_api_instance = mock_api_class.return_value
    mock_api_instance.fetch.return_value = "mock_transcript_object"
    
    # Mock the formatter
    mock_formatter_instance = mock_formatter_class.return_value
    mock_formatter_instance.format_transcript.return_value = "Hello world\nThis is a test"
    
    result = read_youtube_transcript("https://youtu.be/dQw4w9WgXcQ")
    
    assert "Successfully extracted transcript" in result
    assert "Hello world\nThis is a test" in result
    mock_api_instance.fetch.assert_called_once_with("dQw4w9WgXcQ")
    mock_formatter_instance.format_transcript.assert_called_once_with("mock_transcript_object")

def test_read_youtube_transcript_invalid_url():
    """Edge Case: Fails cleanly without calling the API if the URL is garbage."""
    result = read_youtube_transcript("not_a_youtube_link")
    assert "Error: Could not extract a valid 11-character YouTube video ID" in result

@patch("tools.youtube_tools.YouTubeTranscriptApi")
def test_read_youtube_transcript_permanent_error(mock_api_class):
    """Edge Case: If subtitles are disabled, it must fail INSTANTLY without retrying."""
    mock_api_instance = mock_api_class.return_value
    mock_api_instance.fetch.side_effect = Exception("TranscriptsDisabled: Subtitles are disabled for this video.")
    
    result = read_youtube_transcript("https://youtu.be/dQw4w9WgXcQ")
    
    assert "Error: This video does not have any transcripts" in result
    assert mock_api_instance.fetch.call_count == 1  # Proves it didn't retry

@patch("tools.youtube_tools.time.sleep")
@patch("tools.youtube_tools.TextFormatter")
@patch("tools.youtube_tools.YouTubeTranscriptApi")
def test_read_youtube_transcript_transient_recovery(mock_api_class, mock_formatter_class, mock_sleep):
    """Edge Case: Fails on the first try (network blip), but succeeds on the second try."""
    mock_api_instance = mock_api_class.return_value
    mock_api_instance.fetch.side_effect = [
        Exception("Connection reset by peer"),
        "mock_transcript_object"
    ]
    
    mock_formatter_instance = mock_formatter_class.return_value
    mock_formatter_instance.format_transcript.return_value = "Recovered text"
    
    result = read_youtube_transcript("https://youtu.be/dQw4w9WgXcQ")
    
    assert "Successfully extracted transcript" in result
    assert "Recovered text" in result
    assert mock_api_instance.fetch.call_count == 2
    mock_sleep.assert_called_once_with(1.0)

@patch("tools.youtube_tools.time.sleep")
@patch("tools.youtube_tools.YouTubeTranscriptApi")
def test_read_youtube_transcript_transient_fatal(mock_api_class, mock_sleep):
    """Edge Case: Fails on both tries. Must return a clean error message."""
    mock_api_instance = mock_api_class.return_value
    mock_api_instance.fetch.side_effect = Exception("Connection reset by peer")
    
    result = read_youtube_transcript("https://youtu.be/dQw4w9WgXcQ")
    
    assert "Error fetching transcript after retries" in result
    assert "Connection reset by peer" in result
    assert mock_api_instance.fetch.call_count == 2
    mock_sleep.assert_called_once_with(1.0)