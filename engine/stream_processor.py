# engine/stream_processor.py

import json
import logging
from typing import Generator, Callable, Tuple, List
from llm.schemas import StreamChunk, ToolCall

logger = logging.getLogger("engine.stream_processor")


def process_llm_stream(
    stream: Generator[StreamChunk, None, None],
    send_message_callback: Callable[[str], None] = None,
) -> Tuple[str, List[ToolCall], int, int]:
    """
    Consumes the LLM stream, routes text to the UI callback, and buffers tool calls.
    Returns the fully compiled text, parsed tool calls, and token usage.
    """
    full_text = ""
    tool_buffer = {}  # { "call_id": {"name": "...", "arguments": "..."} }
    final_prompt_tokens = 0
    final_comp_tokens = 0

    # 1. Route the traffic as it arrives
    for chunk in stream:
        # STATE A: Normal Text State
        if chunk.text:
            full_text += chunk.text
            # Instantly stream text to the UI!
            if send_message_callback:
                send_message_callback(chunk.text)

        # STATE B: Tool Generation State (Silent buffering)
        if chunk.tool_call_deltas:
            for delta in chunk.tool_call_deltas:
                tc_id = delta["id"]
                if tc_id not in tool_buffer:
                    tool_buffer[tc_id] = {
                        "name": delta["name"],
                        "arguments": "",
                        "metadata": delta.get("metadata", {}),  # <-- 1. CAPTURE IT HERE
                    }

                if delta.get("arguments"):
                    tool_buffer[tc_id]["arguments"] += delta["arguments"]
        # STATE C: Token Extraction (ADD THIS BLOCK)
        if chunk.prompt_tokens:
            final_prompt_tokens = chunk.prompt_tokens
        if chunk.completion_tokens:
            final_comp_tokens = chunk.completion_tokens

    # 2. Parse the Tool Buffer into standard ToolCall objects
    parsed_tool_calls = []
    for tc_id, tc_data in tool_buffer.items():
        try:
            # Parse the glued-together JSON string
            args_dict = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
        except json.JSONDecodeError as e:
            logger.warning(
                f"LLM hallucinated invalid JSON for tool '{tc_data['name']}': {e}"
            )
            args_dict = (
                {}
            )  # Fallback to empty dict to let the tool execution handle the missing args

        parsed_tool_calls.append(
            ToolCall(
                name=tc_data["name"],
                args=args_dict,
                id=tc_id,
                metadata=tc_data.get("metadata", {}),
            )
        )

    return full_text, parsed_tool_calls, final_prompt_tokens, final_comp_tokens


def calculate_fallback_tokens(
    db_messages: List[dict], full_text: str, parsed_tool_calls: List[ToolCall]
) -> Tuple[int, int]:
    """
    Fallback token calculator using the O(1) character math heuristic (chars / 3.7).
    Used when the LLM API drops the usage metadata in the stream (e.g., Gemini, Groq).
    """

    total_prompt_chars = sum(len(str(msg.get("content") or "")) for msg in db_messages)

    prompt_tokens = int(total_prompt_chars / 3.7)

    # 2. Calculate completion tokens based on what was just generated
    comp_tokens = int(len(full_text) / 3.7)

    if parsed_tool_calls:
        # Add a flat buffer for the hidden JSON tool arguments
        comp_tokens += 50 * len(parsed_tool_calls)

    return prompt_tokens, comp_tokens
