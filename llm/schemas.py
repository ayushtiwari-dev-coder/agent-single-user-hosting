# llm/schemas.py

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ToolCall:
    """Standardized representation of a tool/function call requested by the LLM."""

    name: str
    args: Dict[str, Any]
    id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Standardized output returned by any LLM Provider."""

    text: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_output: Any = None


@dataclass
class StreamChunk:
    """Standardized chunk yielded during a streaming LLM response."""

    text: str = ""
    tool_call_deltas: list = field(default_factory=list)  # Holds JSON fragments
    is_finished: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
