import json
import utils.config_manager as config_manager


def check_for_infinite_loop(
    tool_call_history: list[dict], tool_name: str, tool_args: dict
) -> tuple[bool, str | None, str]:
    serialized_args = json.dumps(tool_args, sort_keys=True)

    # 1. Exact-arg repeat check (catches identical calls - REAL infinite loops)
    # CHANGED: Now only counts BACK-TO-BACK consecutive identical calls.
    total_identical_calls = 0
    failed_identical_calls = 0
    successful_identical_calls = 0

    for call in reversed(tool_call_history):
        if call["name"] == tool_name and call["args_json"] == serialized_args:
            total_identical_calls += 1
            if call.get("status") == "error":
                failed_identical_calls += 1
            elif call.get("status") == "success":
                successful_identical_calls += 1
        else:
            break
    limits = config_manager.get_loop_guard() or {}
    max_failed = limits.get("max_failed_attempts")
    if max_failed is None or max_failed <= 0:
        max_failed = 3
    max_success = limits.get("max_success_attempts")
    if max_success is None or max_success <= 0:
        max_success = 2

    # Halt if it keeps trying the exact same failed action blindly (back-to-back)
    if failed_identical_calls >= max_failed:
        return (
            True,
            f"Error: Halting. '{tool_name}' already failed consecutively with these exact params: {tool_args}.",
            serialized_args,
        )

    # Halt if it keeps repeating an action that already succeeded (back-to-back) (wasting tokens)
    if successful_identical_calls >= max_success:
        return (
            True,
            f"Error: Halting. '{tool_name}' already succeeded consecutively with these exact params: {tool_args}.",
            serialized_args,
        )

    return False, None, serialized_args
