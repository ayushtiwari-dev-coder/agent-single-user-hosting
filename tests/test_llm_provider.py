# tests/test_llm_providers.py
import pytest
from llm.providers.gemini import GeminiProvider
from llm.providers.groq import GroqProvider


def test_gemini_message_formatting():
    """Ensures universal messages translate to Gemini's specific Part/Content schema."""
    provider = GeminiProvider(api_key="fake", model_name="gemini-3.1-flash-lite")

    # FIX: Removed the 'system' role, as the engine extracts it before this step
    standard_msgs = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]

    gemini_msgs = provider.format_messages(standard_msgs)

    # Gemini maps 'assistant' to 'model'
    assert gemini_msgs[0]["role"] == "user"
    assert gemini_msgs[0]["parts"][0]["text"] == "Hello"
    assert gemini_msgs[1]["role"] == "model"
    assert gemini_msgs[1]["parts"][0]["text"] == "Hi there"


def test_groq_message_formatting():
    """Ensures universal messages translate to Groq/OpenAI standard schema."""
    provider = GroqProvider(api_key="fake", model_name="llama-3.3-70b-versatile")

    # Groq/OpenAI DOES accept system roles in the messages array
    standard_msgs = [
        {"role": "system", "content": "You are an AI."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]

    groq_msgs = provider.format_messages(standard_msgs)

    assert groq_msgs[0]["role"] == "system"
    assert groq_msgs[0]["content"] == "You are an AI."
    assert groq_msgs[1]["role"] == "user"
    assert groq_msgs[1]["content"] == "Hello"
    assert groq_msgs[2]["role"] == "assistant"
    assert groq_msgs[2]["content"] == "Hi there"


def test_groq_parallel_tool_message_formatting():
    """Ensures executing the same tool in parallel maps strict sequential FIFO IDs to prevent 400 Bad Requests."""
    from llm.providers.groq import GroqProvider
    from llm.schemas import ToolCall

    # Initialize mock provider settings
    provider = GroqProvider(api_key="fake", model_name="llama-3.3-70b-versatile")

    # Setup conversation containing parallel requests to 'read_files' with independent IDs
    standard_msgs = [
        {"role": "user", "content": "Process target files"},
        {
            "role": "assistant",
            "content": "Executing standard read tools...",
            "tool_calls": [
                ToolCall(name="read_files", args={"paths": ["first.txt"]}, id="call_A"),
                ToolCall(
                    name="read_files", args={"paths": ["second.txt"]}, id="call_B"
                ),
            ],
        },
        {
            "role": "tool",
            "tool_name": "read_files",
            "content": "Content of the first file",
        },
        {
            "role": "tool",
            "tool_name": "read_files",
            "content": "Content of the second file",
        },
    ]

    # Process conversion schema through refactored formatting logic
    groq_msgs = provider.format_messages(standard_msgs)

    # Assert both tool calls in assistant turn are parsed correctly
    assert len(groq_msgs) == 4
    assert "tool_calls" in groq_msgs[1]
    assert groq_msgs[1]["tool_calls"][0]["id"] == "call_A"
    assert groq_msgs[1]["tool_calls"][1]["id"] == "call_B"

    # Verify sequential mapping adheres strictly to requested queue positions
    assert groq_msgs[2]["role"] == "tool"
    assert (
        groq_msgs[2]["tool_call_id"] == "call_A"
    )  # Successfully mapped to the first execution call
    assert groq_msgs[2]["content"] == "Content of the first file"

    assert groq_msgs[3]["role"] == "tool"
    assert (
        groq_msgs[3]["tool_call_id"] == "call_B"
    )  # Successfully mapped to the second execution call
    assert groq_msgs[3]["content"] == "Content of the second file"


from llm.schemas import ToolCall


def test_gemini_parallel_tool_message_formatting():
    """Ensures executing multiple tools in parallel groups them into a single 'function' role."""
    provider = GeminiProvider(api_key="fake", model_name="gemini-3.1-flash-lite")

    standard_msgs = [
        {"role": "user", "content": "Process files"},
        {
            "role": "assistant",
            "content": "Reading...",
            "tool_calls": [
                ToolCall(name="read_files", args={"paths": ["a.txt"]}, id="call_A"),
                ToolCall(name="read_files", args={"paths": ["b.txt"]}, id="call_B"),
            ],
        },
        {"role": "tool", "tool_name": "read_files", "content": "A content"},
        {"role": "tool", "tool_name": "read_files", "content": "B content"},
    ]

    gemini_msgs = provider.format_messages(standard_msgs)

    # Should be exactly 3 messages: user -> model -> function (grouped)
    assert len(gemini_msgs) == 3
    assert gemini_msgs[0]["role"] == "user"
    assert gemini_msgs[1]["role"] == "model"
    assert len(gemini_msgs[1]["parts"]) == 3  # 1 text part, 2 function_call parts

    # Verify the tool responses were grouped!
    assert gemini_msgs[2]["role"] == "user"
    assert len(gemini_msgs[2]["parts"]) == 2  # 2 function_response parts


# Add these to the bottom of tests/test_llm_provider.py

from unittest.mock import patch, MagicMock
from llm.schemas import StreamChunk

# --- GROQ STREAMING TESTS ---


def test_groq_generate_content_stream():
    """Verifies Groq correctly parses a network stream into StreamChunks."""
    provider = GroqProvider(api_key="fake", model_name="llama-3.3-70b-versatile")

    # 1. Create Mock Network Chunks
    class MockDelta:
        def __init__(self, content=None, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls

    class MockChoice:
        def __init__(self, delta, finish_reason=None):
            self.delta = delta
            self.finish_reason = finish_reason

    class MockUsage:
        def __init__(self):
            self.prompt_tokens = 15
            self.completion_tokens = 25

    class MockChunk:
        def __init__(
            self, content=None, tool_calls=None, finish_reason=None, has_usage=False
        ):
            self.choices = [MockChoice(MockDelta(content, tool_calls), finish_reason)]
            self.usage = MockUsage() if has_usage else None
            self.x_groq = None

    # Simulate a stream: Text -> Text -> Finish with Usage
    mock_stream = [
        MockChunk(content="Hello "),
        MockChunk(content="World!"),
        MockChunk(finish_reason="stop", has_usage=True),
    ]

    # 2. Mock the request function to return our fake stream
    with patch.object(provider, "_make_groq_request", return_value=mock_stream):
        generator = provider.generate_content(messages=[], tools=[])

        # 3. Consume the generator and verify
        chunks = list(generator)

        assert len(chunks) == 3
        assert isinstance(chunks[0], StreamChunk)

        # Verify Text Extraction
        assert chunks[0].text == "Hello "
        assert chunks[1].text == "World!"

        # Verify Finish Reason & Tokens on the last chunk
        assert chunks[2].is_finished is True
        assert chunks[2].prompt_tokens == 15
        assert chunks[2].completion_tokens == 25


# --- GEMINI STREAMING TESTS ---


def test_gemini_generate_content_stream():
    """Verifies Gemini correctly parses a network stream into StreamChunks."""
    provider = GeminiProvider(api_key="fake", model_name="gemini-3.1-flash-lite")

    # 1. Create Mock Network Chunks
    class MockPart:
        def __init__(self, text=None, function_call=None):
            self.text = text
            self.function_call = function_call

    class MockContent:
        def __init__(self, parts):
            self.parts = parts

    class MockCandidate:
        def __init__(self, parts):
            self.content = MockContent(parts)

    class MockUsageMetadata:
        def __init__(self):
            self.prompt_token_count = 10
            self.candidates_token_count = 20

    class MockChunk:
        def __init__(self, parts=None, has_usage=False):
            self.candidates = [MockCandidate(parts)] if parts else []
            self.usage_metadata = MockUsageMetadata() if has_usage else None

    class MockFunctionCall:
        def __init__(self):
            self.name = "read_files"
            self.args = {"paths": ["test.txt"]}
            self.id = "call_123"

    # Simulate a stream: Text -> Tool Call + Usage
    mock_stream = [
        MockChunk(parts=[MockPart(text="I will read that.")]),
        MockChunk(parts=[MockPart(function_call=MockFunctionCall())], has_usage=True),
    ]

    # 2. Mock the request function
    # We patch the client's generate_content_stream method
    provider.client.models.generate_content_stream = MagicMock(return_value=mock_stream)

    # 3. Consume the generator and verify
    generator = provider.generate_content(messages=[], tools=[])
    chunks = list(generator)

    assert len(chunks) == 2

    # Verify Text Extraction
    assert chunks[0].text == "I will read that."
    assert chunks[0].is_finished is False

    # Verify Tool Call Extraction & Usage
    assert len(chunks[1].tool_call_deltas) == 1
    assert chunks[1].tool_call_deltas[0]["name"] == "read_files"
    assert "test.txt" in chunks[1].tool_call_deltas[0]["arguments"]
    assert chunks[1].is_finished is True
    assert chunks[1].prompt_tokens == 10
    assert chunks[1].completion_tokens == 20
