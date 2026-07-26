# tests/test_approval_manager.py
import pytest
import threading
import time
from managers.approval_manager import (
    wait_for_decision,
    resolve_decision,
    active_approvals,
)


@pytest.fixture(autouse=True)
def cleanup_approvals():
    """Ensure the global active_approvals dict is clean before each test."""
    active_approvals.clear()
    yield
    active_approvals.clear()


def test_wait_for_decision_timeout():
    """Edge Case: If the user ignores the prompt, it should safely timeout and return False."""
    # Set a tiny timeout of 0.1 seconds for the test
    result = wait_for_decision(conversation_id=99, timeout=0.1)

    assert result is False
    assert 99 not in active_approvals  # Ensure it cleaned up after itself


def test_wait_for_decision_approved():
    """Normal Flow: User clicks 'Approve', thread unfreezes and returns True."""

    # Simulate the UI (Telegram/React) resolving the decision in the background after 0.1s
    def delayed_resolve():
        time.sleep(0.1)
        resolve_decision(conversation_id=42, approved=True)

    threading.Thread(target=delayed_resolve).start()

    # This will freeze until the background thread calls resolve_decision
    result = wait_for_decision(conversation_id=42, timeout=2.0)

    assert result is True
    assert 42 not in active_approvals


def test_wait_for_decision_denied():
    """Normal Flow: User clicks 'Deny', thread unfreezes and returns False."""

    def delayed_resolve():
        time.sleep(0.1)
        resolve_decision(conversation_id=42, approved=False)

    threading.Thread(target=delayed_resolve).start()

    result = wait_for_decision(conversation_id=42, timeout=2.0)

    assert result is False


def test_resolve_decision_invalid_id():
    """Edge Case: Webhook receives an approval for an expired or invalid conversation ID."""
    result = resolve_decision(conversation_id=999, approved=True)
    assert result is False
