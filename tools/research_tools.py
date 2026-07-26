# tools/research_tools.py
import os
import re
import requests
import logging
from ddgs import DDGS

from tools.core import agent_tool
from database.connection import APP_DIR
import utils.config_manager as config_manager

logger = logging.getLogger("tools.research_tools")

# Define sandboxed workspace directory
WORKSPACE_DIR = os.path.join(APP_DIR, "workspace")

def _get_workspace_path() -> str:
    """Ensures workspace directory exists and returns its absolute path."""
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    return WORKSPACE_DIR

def _sanitize_topic(topic: str) -> str:
    """Strips invalid OS filename characters and prevents path traversal."""
    if not topic:
        return "general"
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', str(topic))
    return clean.strip('_') or "general"

def _search_web(query: str, max_results: int = 5) -> list[dict]:
    """Internal function to handle web searches using DDGS."""
    try:
        results = []
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=max_results))
            for r in raw_results:
                results.append({
                    "title": r.get("title"),
                    "url": r.get("href"),
                    "snippet": r.get("body")
                })
        return results
    except Exception as e:
        logger.error(f"Web search failed for query '{query}': {e}")
        return [{"error": f"Search failed: {str(e)}"}]

def _read_urls(urls: list[str], filepath: str) -> str:
    """Internal function to fetch, clean, and save webpage content to a scratchpad file."""
    urls_to_process = urls[:3]
    warning = (
        " (Note: Scraped first 3 URLs to prevent timeouts.)"
        if len(urls) > 3
        else ""
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # Check all possible case variations for Jina API key in Render environment
    jina_key = (
        os.environ.get("JINA_API_KEY") 
        or os.environ.get("jina_api_key") 
        or os.environ.get("JINA_KEY")
    )
    if not jina_key and hasattr(config_manager, "get_tool_api_key"):
        try:
            jina_key = config_manager.get_tool_api_key("jina")
        except Exception:
            jina_key = None

    if jina_key:
        headers["Authorization"] = f"Bearer {jina_key}"

    success_count = 0

    for url in urls_to_process:
        try:
            # Use Jina Reader API to convert raw web pages to clean Markdown
            jina_url = f"https://r.jina.ai/{url}"
            response = requests.get(jina_url, headers=headers, timeout=15)
            response.raise_for_status()

            clean_text = response.text

            if clean_text:
                # Append scraped content to the topic scratchpad file
                with open(filepath, "a", encoding="utf-8") as f:
                    f.write(f"\n\n### Source: {url}\n\n")
                    f.write(clean_text[:15000])  # Cap at 15k chars per URL
                success_count += 1

        except Exception as e:
            logger.error(f"Failed to read URL '{url}': {e}")

    if success_count > 0:
        filename = os.path.basename(filepath)
        return (
            f"Success: Extracted content from {success_count} URLs and appended to "
            f"'{filename}'.{warning} "
            f"Use the `read_file` tool to inspect '{filename}' after completing research."
        )
    else:
        return "Error: Failed to extract readable content from the provided URLs."

@agent_tool()
def web_researcher(
    action: str,
    topic_name: str = "general",
    search_query: str = "",
    urls_to_read: list[str] = None,
    conversation_id: int = None,
) -> str | list[dict]:
    """
    The ultimate tool for internet research. MUST be used in two steps:

    Step 1: action="search" with 'topic_name' and 'search_query'. Returns top links and snippets.
    Step 2: action="read" with 'topic_name' and 'urls_to_read' (a list of URLs).

    CRITICAL RULES:
    - 'topic_name' MUST be a short, 1-2 word description of the current task (e.g., "mumbai_lakes").
    - For simple factual questions, DO NOT use action="read". Search snippets are enough!
    - The "read" action saves page content into a markdown file. You must use `read_file` on the generated filename to view it.
    """
    safe_topic = _sanitize_topic(topic_name)
    
    # Dynamic filename tied to conversation_id and topic
    filename = (
        f"research_{conversation_id}_{safe_topic}.md"
        if conversation_id
        else f"research_{safe_topic}.md"
    )
    filepath = os.path.join(_get_workspace_path(), filename)

    if action == "search":
        if not search_query:
            return "Error: You must provide a 'search_query' when action is 'search'."
        return _search_web(search_query)

    elif action == "read":
        if not urls_to_read or not isinstance(urls_to_read, list):
            return "Error: You must provide 'urls_to_read' as a list of URL strings when action is 'read'."
        return _read_urls(urls_to_read, filepath)

    else:
        return f"Error: Invalid action '{action}'. Must be 'search' or 'read'."