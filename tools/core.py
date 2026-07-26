from typing import Callable

def agent_tool(requires_approval: bool = False) -> Callable:
    """
    Decorator that tags a function as an LLM-callable tool.
    If requires_approval is True, the engine will pause and ask the user before executing.
    """
    def decorator(func: Callable) -> Callable:
        func.__is_agent_tool__ = True
        func.requires_approval = requires_approval
        return func
    return decorator