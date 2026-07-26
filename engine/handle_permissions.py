# engine/handle_permissions.py
import json
from tools.registry import execute_tool,FLAT_REGISTRY
from managers.conversation_manager import log_tool_run



def _detect_tool_error(tool_name: str, tool_output: any) -> bool:
    """
    Determines if a tool execution failed using generic contracts.
    1. Structured dict with 'status' or 'error' keys.
    2. Flat string starting with 'Error:'.
    """
    if isinstance(tool_output, dict):
        if tool_output.get("status") in ("success", "error"):
            return tool_output["status"] == "error"
        if "error" in tool_output:
            return True
            
    if isinstance(tool_output, str):
        return tool_output.strip().startswith("Error:")
        
    return False


def _extract_display_output(tool_output: any) -> any:
    """
    Produces a clean, LLM-facing representation of a tool's output.
    Tools using the structured {"status": ..., "output": ...} contract get
    unwrapped to just their output text, so the model sees readable content
    instead of a raw Python dict repr. All other output shapes (read_files/
    write_files dicts, plain strings) pass through unchanged.
    """
    if isinstance(tool_output, dict) and set(tool_output.keys()) == {
        "status",
        "output",
    }:
        return tool_output["output"]
    return tool_output


def execute_and_format_tool(
    tool_name: str, tool_args: dict, conversation_id: int
) -> tuple[str, str]:
    """
    UNIFIED EXECUTION LAYER:
    Runs the tool, checks for errors, logs to the database, and formats the output.
    Does not care who calls it.
    """
    # 1. Execute the Tool
    tool_output = execute_tool(tool_name, tool_args, conversation_id)

    # 2. Check for Errors
    has_error = _detect_tool_error(tool_name, tool_output)
    status = "error" if has_error else "success"

    # 3. Log the Execution Details
    log_tool_run(
        conversation_id, tool_name, json.dumps(tool_args), status, output=tool_output
    )

    # 4. Return clean display value
    display_output = _extract_display_output(tool_output)
    return display_output, status


def determine_and_execute_tool(
    tool_name: str,
    tool_args: dict,
    conversation_id: int,
    autonomous: bool,
    approval_callback=None,
) -> tuple[str, str]:
    """
    Checks if a tool needs approval.
    If safe, executes directly.
    If unsafe, runs the security guard, then asks for user approval via the UI callback.
    """
    if not autonomous:
        tool_func = FLAT_REGISTRY.get(tool_name)
        needs_approval = getattr(tool_func, "requires_approval", False) if tool_func else False
        
        if needs_approval:
            # Ask for User Approval via the UI's Callback
            if approval_callback is None:
                error_msg = f"Error: Tool '{tool_name}' requires approval, but no UI callback was provided."
                log_tool_run(
                    conversation_id, 
                    tool_name, 
                    json.dumps(tool_args), 
                    "error", 
                    output=error_msg
                )
                return error_msg, "error"
                
            # The engine pauses here and waits for the UI to return True/False
            is_approved = approval_callback(tool_name, tool_args, conversation_id)
            
            if not is_approved:
                error_msg = f"Error: Permission Denied. User refused execution of '{tool_name}'."
                log_tool_run(
                    conversation_id, 
                    tool_name, 
                    json.dumps(tool_args), 
                    "error", 
                    output=error_msg
                )
                return error_msg, "error"

    # 3. Safe to run directly (or approved) -> Pass to Unified Execution Layer
    return execute_and_format_tool(tool_name, tool_args, conversation_id)
