# tests/test_research_tools.py
import pytest
from unittest.mock import patch, MagicMock
from tools.research_tools import _sanitize_topic, web_researcher

def test_sanitize_topic():
    """Ensures invalid OS characters are stripped for filenames."""
    assert _sanitize_topic("Valid_Topic_123") == "Valid_Topic_123"
    assert _sanitize_topic("Invalid/\\Topic*") == "Invalid__Topic"
    assert _sanitize_topic("") == "general"

@patch("tools.research_tools._search_web")
def test_web_researcher_search(mock_search):
    """Ensures the 'search' action calls DDGS and returns results."""
    mock_search.return_value = [{"title": "Test", "url": "http://test.com", "snippet": "Snippet"}]
    
    result = web_researcher(action="search", topic_name="test", search_query="test query")
    
    mock_search.assert_called_once_with("test query")
    assert isinstance(result, list)
    assert result[0]["title"] == "Test"

@patch("tools.research_tools._read_urls")
def test_web_researcher_read(mock_read):
    """Ensures the 'read' action calls the scraper."""
    mock_read.return_value = "Extracted content from 1 URLs"
    
    result = web_researcher(action="read", topic_name="test", urls_to_read=["http://test.com"])
    
    mock_read.assert_called_once()
    assert "Extracted content" in result

def test_web_researcher_invalid_action():
    """Ensures invalid actions are rejected."""
    result = web_researcher(action="hack")
    assert "Error: Invalid action" in result

@patch("tools.research_tools.DDGS")
def test_web_researcher_search_api_crash(mock_ddgs_class):
    """Edge Case: DuckDuckGo API crashes or rate limits."""
    mock_instance = MagicMock()
    mock_instance.text.side_effect = Exception("Rate Limit Exceeded")
    mock_ddgs_class.return_value.__enter__.return_value = mock_instance
    
    result = web_researcher(action="search", topic_name="test", search_query="query")
    
    assert isinstance(result, list)
    assert "error" in result[0]
    assert "Search failed" in result[0]["error"]

@patch("tools.research_tools.requests.get")
def test_web_researcher_read_jina_crash(mock_get):
    """Edge Case: Jina Reader API fails to scrape the URLs."""
    mock_get.side_effect = Exception("Jina API 500 Internal Server Error")
    
    result = web_researcher(action="read", topic_name="test", urls_to_read=["http://test.com"])
    
    assert "Error: Failed to extract readable content" in result

def test_web_researcher_read_invalid_urls_type():
    """Edge Case: LLM hallucinates urls_to_read as a string instead of a list."""
    result = web_researcher(action="read", topic_name="test", urls_to_read="http://test.com")
    assert "Error: You must provide 'urls_to_read' as a list" in result