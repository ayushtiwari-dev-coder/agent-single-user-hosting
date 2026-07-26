# managers/approval_manager.py
import threading

# Global dictionary to hold events for async approvals
# Maps: conversation_id -> {"event": threading.Event, "approved": bool}
active_approvals = {}


def wait_for_decision(conversation_id: int, timeout: int = 300) -> bool:
    """
    Freezes the current thread until the UI resolves the approval.
    Used by asynchronous UIs like Telegram or React WebSockets.
    """
    event = threading.Event()
    active_approvals[conversation_id] = {"event": event, "approved": False}

    # Freeze the thread here
    event_triggered = event.wait(timeout=timeout)

    # Retrieve the user's decision
    decision = active_approvals.pop(conversation_id, {})

    if not event_triggered:
        return False  # Timed out

    return decision.get("approved", False)


def resolve_decision(conversation_id: int, approved: bool) -> bool:
    """
    Called by the UI (Telegram callback or React WebSocket) to unfreeze the thread.
    Returns True if a thread was successfully unfrozen, False otherwise.
    """
    if conversation_id in active_approvals:
        active_approvals[conversation_id]["approved"] = approved
        active_approvals[conversation_id]["event"].set()  # Unfreezes the thread!
        return True
    return False
