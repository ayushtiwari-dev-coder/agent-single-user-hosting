# tools/scheduling_tools.py
import datetime
from tools.core import agent_tool
from queries.scheduler_queries import (
    create_scheduled_task, 
    get_tasks_by_conversation, 
    cancel_task, 
    update_task_schedule
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
    - 'task_prompt': Must be a highly detailed instruction of what you need to do when the time comes (e.g., "Research the weather in Mumbai and send a summary").
    - 'execute_at': MUST be a strict ISO 8601 timestamp (e.g., "2026-07-28T09:00:00"). You must calculate the FIRST time this task should run based on the current time.
    - 'recurrence': How often the task repeats after the first execution. 
        - 'none': Runs exactly once.
        - 'daily': Runs every 24 hours at the exact same time.
        - 'twice_daily': Runs every 12 hours (e.g., if scheduled at 9 AM, it will run again at 9 PM).
        - 'weekly': Runs every 7 days.
        - 'monthly': Runs every 30 days.
        - 'yearly': Runs every 365 days.
        - 'Xd': Custom days, where X is a number (e.g., '3d' for every 3 days, '14d' for every 14 days).
    """
    if not conversation_id:
        return "Error: conversation_id is missing."

    try:
        datetime.datetime.fromisoformat(execute_at.replace("Z", "+00:00"))
    except ValueError:
        return f"Error: '{execute_at}' is not a valid ISO 8601 timestamp."

    try:
        task_id = create_scheduled_task(conversation_id, task_prompt, execute_at, recurrence.strip().lower())
        return f"Success: Task #{task_id} scheduled for {execute_at} (Recurrence: {recurrence})."
    except Exception as e:
        return f"Error scheduling task: {e}"

@agent_tool()
def list_scheduled_tasks(conversation_id: int = None) -> str | list[dict]:
    """
    Retrieves all currently pending scheduled tasks for this conversation.
    Use this to find the 'id' (task_id), 'execute_at' time, and 'recurrence' rule of active tasks before cancelling or modifying them
    """
    if not conversation_id:
        return "Error: conversation_id is missing."
    
    try:
        tasks = get_tasks_by_conversation(conversation_id)
        if not tasks:
            return "No pending scheduled tasks found."
        return tasks
    except Exception as e:
        return f"Error retrieving tasks: {e}"

@agent_tool()
def cancel_scheduled_task(task_id: int, conversation_id: int = None) -> str:
    """
    Cancels a pending scheduled task permanently. 
    You MUST provide the correct integer 'task_id'. If you don't know the exact task_id, use list_scheduled_tasks first to find it.
    """
    if not conversation_id:
        return "Error: conversation_id is missing."
        
    try:
        rows_affected = cancel_task(task_id, conversation_id)
        if rows_affected == 0:
            return f"Error: Task #{task_id} not found or already processed/cancelled."
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
    Changes the execution time or recurrence rule of an existing pending task.
    - 'task_id': The integer ID of the task (use list_scheduled_tasks to find this).
    - 'execute_at': The new valid ISO 8601 timestamp for the next execution.
    - 'recurrence': The new recurrence rule ('none', 'daily', 'twice_daily', 'weekly', 'monthly', 'yearly', or 'Xd').
    """
    if not conversation_id:
        return "Error: conversation_id is missing."

    try:
        datetime.datetime.fromisoformat(execute_at.replace("Z", "+00:00"))
    except ValueError:
        return f"Error: '{execute_at}' is not a valid ISO 8601 timestamp."

    try:
        rows_affected = update_task_schedule(task_id, conversation_id, execute_at, recurrence.strip().lower())
        if rows_affected == 0:
            return f"Error: Task #{task_id} not found or is no longer pending."
        return f"Success: Task #{task_id} updated to run at {execute_at} (Recurrence: {recurrence})."
    except Exception as e:
        return f"Error modifying task: {e}"