# tools/registry.py
import os
import pkgutil
import importlib
import inspect

# O(1) lookup for execution: {"read_files": <func>}
FLAT_REGISTRY = {}

# Categorized by file for future routing:
# {"file_tools": {"description": "...", "tools": {"read_files": <func>}}}
GROUPED_REGISTRY = {}


def _load_all_tools():
    """
    Dynamically scans the tools/ directory.
    Uses the filename as the category key and the module docstring as the description.
    """
    tools_dir = os.path.dirname(__file__)

    for _, module_name, _ in pkgutil.iter_modules([tools_dir]):
        # Skip core, registry, and the new security folder
        if module_name in ["core", "registry"] or module_name.startswith("security"):
            continue

        # Import the file dynamically
        mod = importlib.import_module(f"tools.{module_name}")

        # Extract the module-level docstring (for future categorization)
        mod_doc = inspect.getdoc(mod) or f"Tools related to {module_name}."

        module_tools = {}

        # Scan all functions inside the file
        for name, obj in inspect.getmembers(mod, inspect.isfunction):
            # Check if it has our @agent_tool tag
            if getattr(obj, "__is_agent_tool__", False):
                FLAT_REGISTRY[name] = obj
                module_tools[name] = obj

        # If the file had tools, register the category for future use
        if module_tools:
            GROUPED_REGISTRY[module_name] = {
                "description": mod_doc,
                "tools": module_tools,
            }


# Run the loader once when the app starts
_load_all_tools()


def get_all_tools() -> list:
    """
    Returns a flat list of all callable tool functions.
    The LLM SDKs will automatically extract the name, docstring, and parameters from these.
    """
    return list(FLAT_REGISTRY.values())


def execute_tool(tool_name: str, arguments: dict, conversation_id: int = None) -> str:
    """Executes a tool by name with arguments. Dynamically injects context variables."""
    tool_func = FLAT_REGISTRY.get(tool_name)

    if not tool_func:
        return f"Error: Tool '{tool_name}' is not registered."

    sig = inspect.signature(tool_func)

    # Dynamically inject conversation_id if the tool requires it
    if "conversation_id" in sig.parameters and conversation_id is not None:
        arguments["conversation_id"] = conversation_id

    # Validate that all required arguments are present
    for param_name, param in sig.parameters.items():
        if param.default == inspect.Parameter.empty and param_name not in arguments:
            return f"Error: Missing required parameter '{param_name}' for tool '{tool_name}'."

    try:
        return tool_func(**arguments)
    except Exception as e:
        return f"Error: Failed to execute tool '{tool_name}': {e}"
