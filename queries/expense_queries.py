# queries/expense_queries.py

from database.helper import execute_read, execute_write

def create_expense(amount: float, item: str, category: str, reason: str, expense_date: str, created_at: str) -> int:
    """Inserts a new expense row into the database."""
    query = """
    INSERT INTO expenses (amount, item, category, reason, expense_date, created_at)
    VALUES (?, ?, ?, ?, ?, ?);
    """
    return execute_write(query, (amount, item, category, reason, expense_date, created_at))

def get_expenses_in_range(
    start_datetime: str, 
    end_datetime: str, 
    category: str = None, 
    search_query: str = None,
    limit: int = 100
) -> list[dict]:
    """Fetches detailed expense rows filtered by date range, optional category, or keyword search."""
    params = [start_datetime, end_datetime]
    conditions = ["created_at >= ?", "created_at <= ?"]

    if category:
        conditions.append("LOWER(category) = LOWER(?)")
        params.append(category)

    if search_query:
        conditions.append("(LOWER(item) LIKE LOWER(?) OR LOWER(reason) LIKE LOWER(?))")
        search_term = f"%{search_query.strip()}%"
        params.extend([search_term, search_term])

    where_clause = " AND ".join(conditions)
    query = f"""
    SELECT id, amount, item, category, reason, expense_date, created_at
    FROM expenses
    WHERE {where_clause}
    ORDER BY created_at DESC
    LIMIT {int(limit)};
    """
    return execute_read(query, tuple(params))

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