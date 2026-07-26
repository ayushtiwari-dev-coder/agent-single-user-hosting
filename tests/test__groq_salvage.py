# tests/test__groq_salvage.py

import pytest
from llm.providers.groq import salvage_groq_failed_generation_stream


def test_salvage_xml_wrapped_json():
    """Tests if the regex correctly extracts tool parameters from Llama's raw XML tags."""
    broken_llama_output = """
I will write the file for you now.
<function=write_files>{"files_json": "[{\\"path\\": \\"test.py\\", \\"content\\": \\"print(1)\\"}]"}</function>
"""
    stream = salvage_groq_failed_generation_stream(broken_llama_output)
    assert stream is not None

    # Extract from the first chunk's delta
    tool_call = stream[0].choices[0].delta.tool_calls[0]
    assert tool_call.function.name == "write_files"
    assert "test.py" in tool_call.function.arguments


def test_salvage_unescaped_newlines():
    """Edge Case: Resolves raw newlines found in unescaped tool parameters."""
    broken_llama_output = """
<function=run_terminal_command>{"cmd": "echo 'line1
line2'"}</function>
"""
    stream = salvage_groq_failed_generation_stream(broken_llama_output)
    assert stream is not None

    tool_call = stream[0].choices[0].delta.tool_calls[0]
    assert "\\n" in tool_call.function.arguments



def test_salvage_hallucinated_list():
    """Edge Case: Restructures raw list data into a generic arguments dictionary container."""
    broken_llama_output = """ <function=write_files>[{"path": "test.py", "content": "print(1)"}]</function> """
    stream = salvage_groq_failed_generation_stream(broken_llama_output)
    assert stream is not None

    tool_call = stream[0].choices[0].delta.tool_calls[0]
    
    assert '"arguments":' in tool_call.function.arguments

def test_salvage_complete_garbage():
    """If the LLM outputs garbage, the salvager should gracefully return it as a text chunk."""
    garbage_output = "I don't know how to do that."
    stream = salvage_groq_failed_generation_stream(garbage_output)
    assert stream is not None

    # It should fallback to a text chunk, NOT a tool call
    text_content = stream[0].choices[0].delta.content
    assert "[Groq API Intercepted a Broken Tool Call]" in text_content
    assert garbage_output in text_content
    assert stream[0].choices[0].delta.tool_calls is None


def test_salvage_broken_json():
    """If the LLM outputs a valid function tag but completely destroyed JSON, fallback to text."""
    broken_output = "<function=read_files>{broken json -- missing brace</function>"
    stream = salvage_groq_failed_generation_stream(broken_output)
    assert stream is not None

    # It should fallback to a text chunk showing the broken args
    text_content = stream[0].choices[0].delta.content
    assert "[Groq API Intercepted a Broken Tool Call]" in text_content
    assert "Tool: read_files" in text_content
    assert "{broken json" in text_content
    assert stream[0].choices[0].delta.tool_calls is None
