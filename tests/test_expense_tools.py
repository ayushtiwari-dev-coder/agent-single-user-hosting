# tests/test_expense_tools.py

import pytest
import tempfile
import os
import datetime
from unittest.mock import patch, MagicMock

from database.table_generator import create_tables
from queries.expense_queries import (
    create_expense, 
    get_expenses_in_range, 
    get_category_totals_in_range
)
from tools.expense_tools import (
    _get_time_range, 
    log_expense, 
    get_raw_expense_log, 
    get_expense_summary, 
    generate_expense_pdf_report
)


# =====================================================================
# DATABASE SANDBOX FIXTURE
# =====================================================================

@pytest.fixture(autouse=True)
def temp_db_sandbox():
    """
    Creates an isolated, temporary SQLite database for each test 
    to guarantee zero test poisoning or lingering state.
    """
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
# 1. RAW DATABASE QUERY TESTS (queries/expense_queries.py)
# =====================================================================

def test_query_create_expense():
    """Verifies inserting a raw record returns a valid auto-increment ID."""
    exp_id = create_expense(
        amount=250.00,
        item="Subway",
        category="Food",
        reason="Lunch",
        expense_date="2026-07-28",
        created_at="2026-07-28T13:00:00"
    )
    assert exp_id is not None
    assert exp_id > 0


def test_query_get_expenses_in_range_basic():
    """Verifies fetching records strictly within an ISO timestamp window."""
    create_expense(100.0, "Coffee", "Food", "Morning", "2026-07-28", "2026-07-28T09:00:00")
    create_expense(500.0, "Shoes", "Shopping", "Sale", "2026-07-28", "2026-07-28T18:00:00")

    items = get_expenses_in_range("2026-07-28T00:00:00", "2026-07-28T23:59:59")
    assert len(items) == 2
    assert items[0]["item"] == "Shoes"  # Newest first (ORDER BY created_at DESC)
    assert items[1]["item"] == "Coffee"


def test_query_get_expenses_in_range_category_filter():
    """Verifies category filtering works case-insensitively at the database layer."""
    create_expense(100.0, "Coffee", "Food", "Break", "2026-07-28", "2026-07-28T09:00:00")
    create_expense(1200.0, "Power Bill", "Utilities", "Bill", "2026-07-28", "2026-07-28T10:00:00")

    items = get_expenses_in_range("2026-07-28T00:00:00", "2026-07-28T23:59:59", category="food")
    assert len(items) == 1
    assert items[0]["item"] == "Coffee"


def test_query_get_expenses_in_range_keyword_search():
    """Verifies keyword SQL LIKE searches match item names or reasons."""
    create_expense(450.0, "Canvas Board", "Art", "Acrylic painting", "2026-07-28", "2026-07-28T10:00:00")
    create_expense(150.0, "Notebook", "Stationery", "Bought for drawing", "2026-07-28", "2026-07-28T11:00:00")
    create_expense(300.0, "Pizza", "Food", "Dinner", "2026-07-28", "2026-07-28T20:00:00")

    # Search for "drawing" in reason
    res_drawing = get_expenses_in_range("2026-07-28T00:00:00", "2026-07-28T23:59:59", search_query="drawing")
    assert len(res_drawing) == 1
    assert res_drawing[0]["item"] == "Notebook"


def test_query_get_category_totals():
    """Verifies aggregate category GROUP BY queries sum totals correctly."""
    create_expense(100.0, "Coffee", "Food", "A", "2026-07-28", "2026-07-28T09:00:00")
    create_expense(300.0, "Lunch", "Food", "B", "2026-07-28", "2026-07-28T13:00:00")
    create_expense(1000.0, "Cab", "Travel", "C", "2026-07-28", "2026-07-28T15:00:00")

    totals = get_category_totals_in_range("2026-07-28T00:00:00", "2026-07-28T23:59:59")
    assert len(totals) == 2

    food_tot = next(t for t in totals if t["category"] == "Food")
    assert food_tot["total_amount"] == 400.0
    assert food_tot["item_count"] == 2


# =====================================================================
# 2. TIME RANGE HELPER TESTS (_get_time_range)
# =====================================================================

def test_time_range_explicit_dates():
    """Tests specifying custom start and end date strings."""
    start_dt, end_dt, title = _get_time_range(start_date="2026-07-01", end_date="2026-07-15")
    assert start_dt == "2026-07-01T00:00:00"
    assert end_dt == "2026-07-15T23:59:59"
    assert "Custom Range" in title


def test_time_range_named_periods():
    """Tests period keywords: 'today', 'yesterday', 'this_week', 'this_month'."""
    s_today, e_today, _ = _get_time_range(period="today")
    assert s_today.endswith("T00:00:00")
    assert e_today.endswith("T23:59:59")

    _, _, t_week = _get_time_range(period="this_week")
    assert t_week == "Last 7 Days"


def test_time_range_max_30_day_cap():
    """Ensures requesting more than 30 days is safely clamped to 30 days."""
    s_dt, _, title = _get_time_range(days=90, max_days_limit=30)
    assert title == "Last 30 Day(s)"


# =====================================================================
# 3. LOG_EXPENSE TOOL TESTS
# =====================================================================

def test_log_expense_happy_path():
    """Happy Path: Successfully logs an expense and formats the confirmation text."""
    res = log_expense(amount=350.50, item="Swiggy Dinner", category="Food", reason="Late night meal")
    assert "Success: Recorded expense" in res
    assert "₹350.50" in res
    assert "Swiggy Dinner" in res
    assert "Food" in res


def test_log_expense_invalid_amount():
    """Edge Case: Rejects zero or negative amounts cleanly."""
    res_zero = log_expense(amount=0.0, item="Test")
    assert "Error: Expense amount must be greater than zero." in res_zero

    res_neg = log_expense(amount=-50.0, item="Test")
    assert "Error: Expense amount must be greater than zero." in res_neg


def test_log_expense_backdating_past_date():
    """Crucial Feature: Verifies user can backdate expenses for past dates (e.g. 2026-07-25)."""
    res = log_expense(
        amount=600.0, 
        item="Paint Set", 
        category="Art", 
        reason="Bought 3 days ago", 
        date_str="2026-07-25"
    )
    assert "Success: Recorded expense" in res
    assert "25 Jul 2026" in res

    # Verify query for July 25th returns it
    raw_log = get_raw_expense_log(start_date="2026-07-25", end_date="2026-07-25")
    assert "Paint Set" in raw_log
    assert "₹600.00" in raw_log


# =====================================================================
# 4. GET_RAW_EXPENSE_LOG TOOL TESTS
# =====================================================================

def test_get_raw_expense_log_itemized_output():
    """Verifies raw log returns full unsummarized details with reasons and timestamps."""
    log_expense(amount=450.0, item="Canvas Board", category="Art", reason="For oil painting")
    
    res = get_raw_expense_log(days=1)
    assert "ITEMIZED TRANSACTION LOG" in res
    assert "Canvas Board" in res
    assert "For oil painting" in res
    assert "₹450.00" in res


def test_get_raw_expense_log_keyword_search():
    """Verifies LLM can search specifically for items like 'art' or 'pizza'."""
    log_expense(amount=450.0, item="Canvas Board", category="Art", reason="Painting project")
    log_expense(amount=1200.0, item="Power Bill", category="Utilities", reason="Electricity")

    # Search for "canvas"
    search_res = get_raw_expense_log(days=7, search_query="canvas")
    assert "Canvas Board" in search_res
    assert "Power Bill" not in search_res


def test_get_raw_expense_log_specific_day():
    """Tests asking 'What did I spend on the 27th?'."""
    log_expense(amount=200.0, item="Snacks", category="Food", date_str="2026-07-27")

    res_27 = get_raw_expense_log(start_date="2026-07-27", end_date="2026-07-27")
    assert "Snacks" in res_27
    assert "27 Jul 2026" in res_27


def test_get_raw_expense_log_empty():
    """Edge Case: Handles empty results cleanly."""
    res = get_raw_expense_log(days=1, category="NonExistentCategory")
    assert "No individual transactions found" in res


# =====================================================================
# 5. GET_EXPENSE_SUMMARY TOOL TESTS
# =====================================================================

def test_get_expense_summary_totals():
    """Verifies aggregated metrics calculation."""
    log_expense(amount=500.0, item="Shirt", category="Shopping")
    log_expense(amount=300.0, item="Lunch", category="Food")

    res = get_expense_summary(days=1)
    assert "FINANCIAL SUMMARY" in res
    assert "Total Spent:** ₹800.00" in res
    assert "Shopping" in res
    assert "Food" in res


def test_get_expense_summary_budget_target_under():
    """Verifies Budget Target comparison when UNDER budget (🟢)."""
    log_expense(amount=300.0, item="Lunch", category="Food")

    # ₹500/day budget for 1 day = ₹500 allowed. Spent ₹300. Under by ₹200.
    res = get_expense_summary(days=1, daily_budget=500.0)
    assert "Target Budget:** ₹500.00/day" in res
    assert "🟢 **STATUS: UNDER BUDGET by ₹200.00!" in res


def test_get_expense_summary_budget_target_over():
    """Verifies Budget Target comparison when OVER budget (🔴)."""
    log_expense(amount=800.0, item="Dinner", category="Food")

    # ₹500/day budget for 1 day = ₹500 allowed. Spent ₹800. Over by ₹300.
    res = get_expense_summary(days=1, daily_budget=500.0)
    assert "🔴 **STATUS: OVER BUDGET by ₹300.00!" in res


# =====================================================================
# 6. GENERATE_EXPENSE_PDF_REPORT TOOL TESTS
# =====================================================================

@patch("tools.expense_tools.generate_pdf")
def test_generate_expense_pdf_report_delegation(mock_generate_pdf):
    """Happy Path: Verifies Markdown construction and delegation to generate_pdf in file_tools."""
    mock_generate_pdf.return_value = "Success: PDF delivered to Telegram"
    
    log_expense(amount=1500.0, item="Internet Bill", category="Utilities")

    res = generate_expense_pdf_report(days=7, conversation_id=42)

    assert res == "Success: PDF delivered to Telegram"
    mock_generate_pdf.assert_called_once()
    
    # Assert correct parameters passed to file_tools.generate_pdf
    kwargs = mock_generate_pdf.call_args[1]
    assert "# Financial Expense Statement" in kwargs["markdown_content"]
    assert "Internet Bill" in kwargs["markdown_content"]
    assert "Expense_Report_Last_7_Day(s).pdf" in kwargs["filename"]
    assert kwargs["conversation_id"] == 42


def test_generate_expense_pdf_report_no_data():
    """Edge Case: Safely skips PDF generation if database has no transactions in range."""
    res = generate_expense_pdf_report(days=1)
    assert "No expenses logged for Last 1 Day(s). Skipping PDF report generation." in res