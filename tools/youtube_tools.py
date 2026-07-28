# tools/youtube_tools.py

import re
import time
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from tools.core import agent_tool

def _extract_video_id(url: str) -> str:
    """Extracts the 11-character YouTube video ID from various URL formats."""
    match = re.search(r"(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?|shorts)\/|.*[?&]v=)|youtu\.be\/)([^\"&?\/\s]{11})", url)
    if match:
        return match.group(1)
    return None

@agent_tool()
def read_youtube_transcript(video_url: str) -> str:
    """
    Fetches the full text transcript of a YouTube video given its URL.
    Use this to read, summarize, or extract information from YouTube videos.
    """
    video_id = _extract_video_id(video_url)
    if not video_id:
        return "Error: Could not extract a valid 11-character YouTube video ID from the URL."

    # Simple 2-attempt retry loop
    for attempt in range(2):
        try:

            ytt_api = YouTubeTranscriptApi()
            transcript = ytt_api.fetch(video_id)
            
            formatter = TextFormatter()
            full_text = formatter.format_transcript(transcript)
            
            return f"Successfully extracted transcript ({len(full_text)} characters):\n\n{full_text}"
            
        except Exception as e:
            error_msg = str(e)
            
            # If the error is permanent (no subtitles exist), do NOT retry. Fail instantly.
            if "Subtitles are disabled" in error_msg or "No transcripts were found" in error_msg or "TranscriptsDisabled" in error_msg:
                return f"Error: This video does not have any transcripts or subtitles available. ({error_msg})"
            
            # If it's a random network blip, wait 1 second and try exactly one more time
            if attempt == 0:
                time.sleep(1.0)
                continue
            
            return f"Error fetching transcript after retries: {error_msg}"