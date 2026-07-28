# queries/expense_queries.py

from database.helper import execute_read, execute_write

def create_expense(amount: float, item: str, category: str, reason: str, expense_date: str, created_at: str) -> int:
    """Inserts a new expense row into the database."""
    query = """
    INSERT INTO expenses (amount, item, category, reason, expense_date, created_at)
    VALUES (?, ?, ?, ?, ?, ?);
    """
    return execute_write(query, (amount, item, category, reason, expense_date, created_at))

def get_expenses_in_range(start_datetime: str, end_datetime: str, category: str = None) -> list[dict]:
    """Fetches all detailed expense rows between two ISO timestamps."""
    if category:
        query = """
        SELECT id, amount, item, category, reason, expense_date, created_at
        FROM expenses
        WHERE created_at >= ? AND created_at <= ? AND LOWER(category) = LOWER(?)
        ORDER BY created_at DESC;
        """
        return execute_read(query, (start_datetime, end_datetime, category))
    else:
        query = """
        SELECT id, amount, item, category, reason, expense_date, created_at
        FROM expenses
        WHERE created_at >= ? AND created_at <= ?
        ORDER BY created_at DESC;
        """
        return execute_read(query, (start_datetime, end_datetime))

def get_category_totals_in_range(start_datetime: str, end_datetime: str) -> list[dict]:
    """Calculates aggregate spending broken down by category for a time range."""
    query = """
    SELECT category, SUM(amount) as total_amount, COUNT(*) as item_count
    FROM expenses
    WHERE created_at >= ? AND created_at <= ?
    GROUP BY category
    ORDER BY total_amount DESC;
    """
    return execute_read(query, (start_datetime, end_datetime))