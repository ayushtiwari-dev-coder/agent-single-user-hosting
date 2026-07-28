# tests/test_expense_tools.py

import pytest
import tempfile
import os
import datetime
from unittest.mock import patch, MagicMock
from database.table_generator import create_tables
from queries.expense_queries import create_expense, get_expenses_in_range, get_category_totals_in_range
from tools.expense_tools import _get_time_range, log_expense, query_expenses, generate_expense_pdf_report


# =====================================================================
# DATABASE SANDBOX FIXTURE
# =====================================================================

@pytest.fixture(autouse=True)
def temp_db_sandbox():
    """Sandboxes the database operations using a temporary SQLite database."""
    import database.helper
    temp_db = tempfile.NamedTemporaryFile(delete=False)
    temp_db_path = temp_db.name
    temp_db.close()

    db_patcher = patch("database.connection.DATABASE_PATH", temp_db_path)
    db_patcher.start()

    if not hasattr(database.helper, "_db_worker") or not database.helper._db_worker.is_alive():
        database.helper._db_worker = database.helper.DatabaseWorker()
        database.helper._db_worker.start()

    create_tables()

    yield temp_db_path

    db_patcher.stop()
    try:
        os.remove(temp_db_path)
    except OSError:
        pass


# =====================================================================
# 1. RAW DATABASE QUERY TESTS
# =====================================================================

def test_expense_queries_crud():
    """Tests raw SQL query insertions and range fetches."""
    now_str = "2026-07-28T14:30:00"
    exp_id = create_expense(
        amount=450.00,
        item="Domino's Pizza",
        category="Food",
        reason="Dinner with friends",
        expense_date="2026-07-28",
        created_at=now_str
    )
    assert exp_id is not None
    assert exp_id > 0

    # Fetch in range
    items = get_expenses_in_range("2026-07-28T00:00:00", "2026-07-28T23:59:59")
    assert len(items) == 1
    assert items[0]["item"] == "Domino's Pizza"
    assert items[0]["amount"] == 450.00


def test_expense_queries_category_totals():
    """Verifies aggregate GROUP BY queries calculate category totals correctly."""
    now_str = "2026-07-28T10:00:00"
    create_expense(100.0, "Coffee", "Food", "Morning", "2026-07-28", now_str)
    create_expense(300.0, "Lunch", "Food", "Afternoon", "2026-07-28", now_str)
    create_expense(1200.0, "Power Bill", "Utilities", "Monthly", "2026-07-28", now_str)

    totals = get_category_totals_in_range("2026-07-28T00:00:00", "2026-07-28T23:59:59")
    assert len(totals) == 2  # Food and Utilities

    # Check Food total (100 + 300 = 400, count = 2)
    food_summary = next(c for c in totals if c["category"] == "Food")
    assert food_summary["total_amount"] == 400.0
    assert food_summary["item_count"] == 2


# =====================================================================
# 2. TIME RANGE HELPER TESTS
# =====================================================================

def test_get_time_range_named_periods():
    """Tests _get_time_range helper logic for 'today', 'yesterday', 'this_week', etc."""
    start_today, end_today, title_today = _get_time_range(period="today")
    assert "Today" in title_today
    assert start_today.endswith("T00:00:00")
    assert end_today.endswith("T23:59:59")

    start_week, _, title_week = _get_time_range(period="this_week")
    assert title_week == "Last 7 Days"

    start_month, _, title_month = _get_time_range(period="this_month")
    assert title_month == "Last 30 Days"


def test_get_time_range_custom_days():
    """Tests _get_time_range for specific custom day intervals (3d, 21d)."""
    _, _, title_3d = _get_time_range(days=3)
    assert title_3d == "Last 3 Day(s)"

    _, _, title_21d = _get_time_range(days=21)
    assert title_21d == "Last 21 Day(s)"


# =====================================================================
# 3. TOOL EXECUTION TESTS
# =====================================================================

def test_log_expense_tool_happy_path():
    """Happy Path: Logs an expense and returns a formatted confirmation."""
    res = log_expense(amount=250.0, item="Subway Sandwich", category="Food", reason="Lunch")
    assert "Success: Recorded expense" in res
    assert "₹250.00" in res
    assert "Subway Sandwich" in res
    assert "Food" in res


def test_log_expense_tool_invalid_amount():
    """Edge Case: Blocks zero or negative expense amounts."""
    res = log_expense(amount=-100.0, item="Invalid")
    assert "Error: Expense amount must be greater than zero." in res


def test_query_expenses_tool():
    """Verifies query_expenses calculates total spending and prints the timeline."""
    log_expense(amount=500.0, item="Shirt", category="Shopping", reason="Sale")
    log_expense(amount=200.0, item="Burger", category="Food")

    # Query last 1 day
    res_1d = query_expenses(days=1)
    assert "EXPENSE SUMMARY" in res_1d
    assert "Grand Total Spent:** ₹700.00" in res_1d
    assert "Shopping" in res_1d
    assert "Food" in res_1d
    assert "Shirt" in res_1d

    # Query with category filter
    res_food = query_expenses(days=1, category="Food")
    assert "Burger" in res_food
    assert "Shirt" not in res_food
    assert "Grand Total Spent:** ₹200.00" in res_food


def test_query_expenses_empty():
    """Edge Case: Returns a clean message when no transactions exist."""
    res = query_expenses(days=1, category="Travel")
    assert "No expenses found" in res


@patch("tools.expense_tools.generate_pdf")
def test_generate_expense_pdf_report_tool(mock_generate_pdf):
    """Happy Path: Generates Markdown and delegates directly to generate_pdf in file_tools."""
    mock_generate_pdf.return_value = "Success: PDF delivered via Telegram"
    
    log_expense(amount=1500.0, item="Internet Bill", category="Utilities")

    res = generate_expense_pdf_report(days=7, conversation_id=1)

    assert res == "Success: PDF delivered via Telegram"
    mock_generate_pdf.assert_called_once()
    
    # Verify arguments passed to generate_pdf
    kwargs = mock_generate_pdf.call_args[1]
    assert "# Financial Expense Statement" in kwargs["markdown_content"]
    assert "Internet Bill" in kwargs["markdown_content"]
    assert "Expense_Report_Last_7_Day(s).pdf" in kwargs["filename"]
    assert kwargs["conversation_id"] == 1


def test_generate_expense_pdf_report_no_data():
    """Edge Case: Skips PDF generation if no expenses are logged."""
    res = generate_expense_pdf_report(days=1)
    assert "No expenses logged for Last 1 Day(s). Skipping PDF report generation." in res