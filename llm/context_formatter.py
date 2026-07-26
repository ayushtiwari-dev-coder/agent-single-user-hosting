# llm/context_formatter.py
import json
import utils.config_manager as config_manager

DEFAULT_SYSTEM_INSTRUCTION = (
    "You are a highly capable, autonomous AI assistant.\n"
    "You operate in a continuous ReAct (Reason + Act) loop.\n"
    "Use the provided tools to fulfill the user's request accurately and efficiently."
)


def _truncate_single_string(content: str, tool_name: str, filename: str = None) -> str:
    """Generic logic to truncate a single massive string into Head/Tail."""
    lines = content.splitlines()
    total_lines = len(lines)
    
    if total_lines < 10:
        head = content[:500]
        tail = content[-500:]
        return (
            f"[RAW OUTPUT TRUNCATED]\nTool: {tool_name}\nSize: ~{len(content)} chars (Minified)\n"
            f"--- HEAD ---\n{head}\n...\n--- TAIL ---\n{tail}\n"
        )
        
    head_lines = "\n".join(lines[:5])
    tail_lines = "\n".join(lines[-5:])
    
    return (
        f"[RAW OUTPUT TRUNCATED]\nTool: {tool_name}\nSize: {total_lines} lines\n"
        f"--- HEAD (First 5 lines) ---\n{head_lines}\n...\n--- TAIL (Last 5 lines) ---\n{tail_lines}\n"
    )


def smart_truncate_tool_output(
    content: str, tool_name: str, threshold_chars: int = 2000
) -> str:
    """Dynamically truncates tool outputs, handling both raw strings and JSON dicts."""
    if not content or len(content) <= threshold_chars:
        return content

    try:
        parsed_content = json.loads(content)
        if isinstance(parsed_content, dict):
            truncated_dict = {}
            for key, val in parsed_content.items():
                if isinstance(val, str) and len(val) > threshold_chars:
                    truncated_dict[key] = _truncate_single_string(
                        val, tool_name, filename=key
                    )
                else:
                    truncated_dict[key] = val
            return json.dumps(truncated_dict, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        pass

    return _truncate_single_string(content, tool_name)


def format_context(db_messages: list[dict]) -> tuple[str, list[dict]]:
    """
    Extracts base instructions, handles system summaries, and formats the raw database
    messages into a clean, universal standard that any LLM provider can easily map.
    """
    custom_system_instruction = config_manager.get_system_instruction()
    base_instructions = (
        custom_system_instruction
        if custom_system_instruction
        else DEFAULT_SYSTEM_INSTRUCTION
    )

    system_instruction = base_instructions
    standardized_messages = []
    total_msgs = len(db_messages)

    for i, msg in enumerate(db_messages):
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "system":
            system_instruction += f"\n\n[Previous Conversation Summary]\n{content}"
        else:
            # THE ONE-TURN RULE: Truncate old tool outputs
            if role == "tool" and i < total_msgs - 1:
                tool_name = msg.get("tool_name", "unknown")
                content = smart_truncate_tool_output(content, tool_name)

            clean_msg = {"role": role, "content": content}
            if "tool_name" in msg:
                clean_msg["tool_name"] = msg["tool_name"]
            if "tool_calls" in msg:
                clean_msg["tool_calls"] = msg["tool_calls"]

            standardized_messages.append(clean_msg)

    return system_instruction, standardized_messages
