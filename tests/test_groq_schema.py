# tests/test_groq_schema.py
import pytest
from llm.providers.groq import _function_to_schema


def test_function_to_schema_mapping():
    # 1. Define dummy tool function
    def write_report(filepath: str, lines_count: int, append: bool = False) -> str:
        """Writes lines of content to a specified local file path."""
        pass

    # 2. Convert schema
    schema = _function_to_schema(write_report)

    # 3. Assertions
    assert schema["type"] == "function"
    func_details = schema["function"]
    assert func_details["name"] == "write_report"
    assert (
        func_details["description"]
        == "Writes lines of content to a specified local file path."
    )

    params = func_details["parameters"]
    assert params["type"] == "object"

    properties = params["properties"]
    assert properties["filepath"]["type"] == "string"
    assert properties["lines_count"]["type"] == "integer"
    assert properties["append"]["type"] == "boolean"

    # Required check (append has default and should be excluded)
    required_fields = params["required"]
    assert "filepath" in required_fields
    assert "lines_count" in required_fields
    assert "append" not in required_fields
