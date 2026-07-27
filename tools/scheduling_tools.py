# tools/scheduling_tools.py
import datetime
from tools.core import agent_tool
from queries.scheduler_queries import (
    create_scheduled_task,
    get_all_scheduled_tasks,
    cancel_task_by_id,
    update_task_schedule_by_id
)

@agent_tool()
def schedule_task(
    task_prompt: str, 
    execute_at: str, 
    recurrence: str = "none", 
    conversation_id: int = None
) -> str:
    """
    Schedules a task for the agent to execute autonomously in the future.
    
    CRITICAL RULES:
    - 'task_prompt': Must be a highly detailed instruction of what your future self needs to do. 
        * RESEARCH RULE: If the task involves web research, news gathering, or deep reading, you MUST start the task_prompt with the exact word `/research` (e.g., "/research Find the latest news on OpenAI models and extract key stats").
        * Be extremely specific. Tell your future self exactly what to search for, what tools to use, and how to format the final output (e.g., "Generate a PDF").
    - 'execute_at': MUST be a strict ISO 8601 timestamp (e.g., "2026-07-28T09:00:00"). You must calculate the FIRST time this task should run based on the current time.
    - 'recurrence': How often the task repeats after the first execution. 
        - 'none': Runs exactly once.
        - 'daily': Runs every 24 hours at the exact same time.
        - 'twice_daily': Runs every 12 hours.
        - 'weekly': Runs every 7 days.
        - 'monthly': Runs every 30 days.
        - 'yearly': Runs every 365 days.
        - 'Xd': Custom days (e.g., '3d' for every 3 days).
    """
    if not conversation_id:
        return "Error: conversation_id is missing."

    try:
        datetime.datetime.fromisoformat(execute_at.replace("Z", "+00:00"))
    except ValueError:
        return f"Error: '{execute_at}' is not a valid ISO 8601 timestamp. Please use format YYYY-MM-DDTHH:MM:SS"

    try:
        task_id = create_scheduled_task(conversation_id, task_prompt, execute_at, recurrence.strip().lower())
        return f"Success: Task #{task_id} scheduled for {execute_at} (Recurrence: {recurrence})."
    except Exception as e:
        return f"Error scheduling task: {e}"

@agent_tool()
def list_scheduled_tasks(conversation_id: int = None) -> str | list[dict]:
    """
    Retrieves ALL active or pending scheduled tasks across all past and current sessions.
    Use this to inspect all upcoming tasks and find task_ids before cancelling or modifying duplicates.
    """
    try:
        tasks = get_all_scheduled_tasks()
        if not tasks:
            return "No active scheduled tasks found."
        return tasks
    except Exception as e:
        return f"Error retrieving tasks: {e}"

@agent_tool()
def cancel_scheduled_task(task_id: int, conversation_id: int = None) -> str:
    """
    Cancels a pending scheduled task permanently by its task_id.
    Use list_scheduled_tasks first to find the exact task_id.
    """
    try:
        rows_affected = cancel_task_by_id(task_id)
        if rows_affected == 0:
            return f"Error: Task #{task_id} not found or already cancelled."
        return f"Success: Task #{task_id} has been cancelled."
    except Exception as e:
        return f"Error cancelling task: {e}"

@agent_tool()
def modify_scheduled_task(
    task_id: int, 
    execute_at: str, 
    recurrence: str, 
    conversation_id: int = None
) -> str:
    """
    Changes the execution time or recurrence rule of an existing task by its task_id.
    """
    try:
        datetime.datetime.fromisoformat(execute_at.replace("Z", "+00:00"))
    except ValueError:
        return f"Error: '{execute_at}' is not a valid ISO 8601 timestamp."

    try:
        rows_affected = update_task_schedule_by_id(task_id, execute_at, recurrence.strip().lower())
        if rows_affected == 0:
            return f"Error: Task #{task_id} not found or is no longer pending."
        return f"Success: Task #{task_id} updated to run at {execute_at} (Recurrence: {recurrence})."
    except Exception as e:
        return f"Error modifying task: {e}"