# tests/test_registry.py
import pytest
from unittest.mock import patch, MagicMock
from tools.core import agent_tool
import tools.registry as registry

@pytest.fixture(autouse=True)
def clean_registry():
    """Clears the registry before and after each test to prevent test poisoning."""
    registry.FLAT_REGISTRY.clear()
    registry.GROUPED_REGISTRY.clear()
    yield
    registry.FLAT_REGISTRY.clear()
    registry.GROUPED_REGISTRY.clear()

def test_agent_tool_decorator_default():
    """Ensures the decorator correctly tags a function with default approval."""
    @agent_tool()
    def dummy_func():
        pass

    assert getattr(dummy_func, "__is_agent_tool__") is True
    assert getattr(dummy_func, "requires_approval") is False

def test_agent_tool_decorator_with_approval():
    """Ensures the decorator correctly sets the requires_approval flag."""
    @agent_tool(requires_approval=True)
    def dangerous_func():
        pass

    assert getattr(dangerous_func, "__is_agent_tool__") is True
    assert getattr(dangerous_func, "requires_approval") is True

def test_execute_tool_success():
    """Ensures a registered tool executes correctly."""
    @agent_tool()
    def add_numbers(a: int, b: int):
        return a + b

    registry.FLAT_REGISTRY["add_numbers"] = add_numbers

    result = registry.execute_tool("add_numbers", {"a": 5, "b": 10})
    assert result == 15

def test_execute_tool_missing_param():
    """Ensures the registry catches missing required arguments before crashing."""
    @agent_tool()
    def greet(name: str):
        return f"Hello {name}"

    registry.FLAT_REGISTRY["greet"] = greet

    # Pass empty arguments
    result = registry.execute_tool("greet", {})
    assert "Error: Missing required parameter 'name'" in result

def test_execute_tool_injects_conversation_id():
    """
    Crucial Test: The LLM doesn't know the conversation_id.
    The registry MUST inject it automatically if the function asks for it.
    """
    @agent_tool()
    def check_context(conversation_id: int):
        return f"Context is {conversation_id}"

    registry.FLAT_REGISTRY["check_context"] = check_context

    # We pass empty args (simulating the LLM), but provide conversation_id (from the Engine)
    result = registry.execute_tool("check_context", {}, conversation_id=42)
    assert result == "Context is 42"

def test_execute_tool_not_registered():
    """Ensures calling a hallucinated tool name fails safely."""
    result = registry.execute_tool("ghost_tool", {})
    assert "is not registered" in result

def test_execute_tool_internal_crash():
    """Ensures that if a tool's internal Python code crashes, the registry catches it."""
    @agent_tool()
    def crash_tool():
        raise ValueError("Something broke inside!")

    registry.FLAT_REGISTRY["crash_tool"] = crash_tool

    result = registry.execute_tool("crash_tool", {})
    assert "Failed to execute tool 'crash_tool': Something broke inside!" in result