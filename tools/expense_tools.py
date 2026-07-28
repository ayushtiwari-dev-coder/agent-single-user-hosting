# tools/expense_tools.py

import datetime
import logging
from tools.core import agent_tool
from queries.expense_queries import create_expense, get_expenses_in_range, get_category_totals_in_range
from tools.file_tools import generate_pdf  

logger = logging.getLogger("tools.expense_tools")

# Always use Indian Standard Time (IST: UTC +05:30)
try:
    import zoneinfo
    TZ_IST = zoneinfo.ZoneInfo("Asia/Kolkata")
except ImportError:
    TZ_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _get_time_range(days: int = None, period: str = None) -> tuple[str, str, str]:
    """Calculates IST start/end datetimes and a descriptive range title."""
    now = datetime.datetime.now(TZ_IST)
    end_dt = now.strftime("%Y-%m-%dT23:59:59")
    
    if period:
        period_clean = period.strip().lower()
        if period_clean in ["today", "1d"]:
            start_dt = now.strftime("%Y-%m-%dT00:00:00")
            title = f"Today ({now.strftime('%d %b %Y')})"
        elif period_clean in ["yesterday"]:
            yest = now - datetime.timedelta(days=1)
            start_dt = yest.strftime("%Y-%m-%dT00:00:00")
            end_dt = yest.strftime("%Y-%m-%dT23:59:59")
            title = f"Yesterday ({yest.strftime('%d %b %Y')})"
        elif period_clean in ["this_week", "weekly", "7d"]:
            start_dt = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%dT00:00:00")
            title = "Last 7 Days"
        elif period_clean in ["this_month", "monthly", "30d"]:
            start_dt = (now - datetime.timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
            title = "Last 30 Days"
        else:
            start_dt = (now - datetime.timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
            title = "Last 30 Days"
    elif days is not None and days > 0:
        start_dt = (now - datetime.timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
        title = f"Last {days} Day(s)"
    else:
        start_dt = (now - datetime.timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
        title = "Last 30 Days"

    return start_dt, end_dt, title


@agent_tool()
def log_expense(amount: float, item: str, category: str = "General", reason: str = "") -> str:
    """
    Logs a new personal expense transaction into the database.
    Captures exact timestamp in Indian Standard Time (IST).
    """
    if amount <= 0:
        return "Error: Expense amount must be greater than zero."

    now = datetime.datetime.now(TZ_IST)
    expense_date = now.strftime("%Y-%m-%d")
    created_at = now.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        expense_id = create_expense(
            amount=round(amount, 2),
            item=item.strip(),
            category=category.strip().title(),
            reason=reason.strip() if reason else "None provided",
            expense_date=expense_date,
            created_at=created_at
        )
        time_str = now.strftime("%I:%M:%S %p IST")
        return (
            f"Success: Recorded expense #{expense_id}!\n"
            f"• Amount: ₹{amount:,.2f}\n"
            f"• Item: {item}\n"
            f"• Category: {category.title()}\n"
            f"• Reason: {reason if reason else 'N/A'}\n"
            f"• Exact Time: {expense_date} at {time_str}"
        )
    except Exception as e:
        logger.exception(f"Failed to log expense: {e}")
        return f"Error logging expense: {e}"


@agent_tool()
def query_expenses(days: int = None, period: str = None, category: str = None) -> str:
    """
    Queries expenses and calculates financial summaries over any flexible time frame
    (e.g., last 1 day, last 3 days, last 21 days, last 30 days, or by specific category).
    """
    try:
        start_dt, end_dt, range_title = _get_time_range(days=days, period=period)
        items = get_expenses_in_range(start_dt, end_dt, category=category)
        cat_summaries = get_category_totals_in_range(start_dt, end_dt)

        if not items:
            cat_msg = f" for category '{category}'" if category else ""
            return f"No expenses found for {range_title}{cat_msg}."

        grand_total = sum(row["amount"] for row in items)

        output = [f"📊 **EXPENSE SUMMARY: {range_title.upper()}**"]
        output.append(f"💰 **Grand Total Spent:** ₹{grand_total:,.2f}")
        output.append(f"🧾 **Total Transactions:** {len(items)}\n")

        if cat_summaries and not category:
            output.append("🏷️ **Breakdown by Category:**")
            for cat in cat_summaries:
                pct = (cat["total_amount"] / grand_total) * 100 if grand_total > 0 else 0
                output.append(f"• **{cat['category']}**: ₹{cat['total_amount']:,.2f} ({pct:.1f}% | {cat['item_count']} items)")
            output.append("")

        output.append("📜 **Detailed Transaction Timeline:**")
        for idx, row in enumerate(items, start=1):
            dt_obj = datetime.datetime.fromisoformat(row["created_at"])
            time_formatted = dt_obj.strftime("%d %b at %I:%M %p")
            reason_str = f" | Note: {row['reason']}" if row['reason'] and row['reason'] != "None provided" else ""
            output.append(f"{idx}. ₹{row['amount']:,.2f} - **{row['item']}** ({row['category']}) [{time_formatted}]{reason_str}")

        return "\n".join(output)

    except Exception as e:
        logger.exception(f"Error querying expenses: {e}")
        return f"Error fetching expense summary: {e}"


@agent_tool()
def generate_expense_pdf_report(days: int = None, period: str = None, conversation_id: int = None) -> str:
    """
    Generates a financial statement PDF for expenses over a specified time frame
    and delivers it directly to your Telegram chat.
    """
    try:
        start_dt, end_dt, range_title = _get_time_range(days=days, period=period)
        items = get_expenses_in_range(start_dt, end_dt)
        cat_summaries = get_category_totals_in_range(start_dt, end_dt)

        if not items:
            return f"No expenses logged for {range_title}. Skipping PDF report generation."

        grand_total = sum(row["amount"] for row in items)

        # Build clean Markdown content
        md = [
            f"# Financial Expense Statement",
            f"**Report Period:** {range_title}\n",
            f"**Total Expenditure:** ₹{grand_total:,.2f} | **Total Transactions:** {len(items)}\n",
            f"### Category Breakdown\n",
            f"| Category | Total Amount | Count |",
            f"| :--- | :--- | :--- |",
        ]
        for c in cat_summaries:
            md.append(f"| **{c['category']}** | ₹{c['total_amount']:,.2f} | {c['item_count']} |")

        md.extend([
            f"\n### Chronological Transaction Log\n",
            f"| Date & Time (IST) | Item | Category | Amount | Notes |",
            f"| :--- | :--- | :--- | :--- | :--- |"
        ])
        for r in items:
            time_formatted = datetime.datetime.fromisoformat(r['created_at']).strftime('%d %b %Y %I:%M %p')
            md.append(f"| {time_formatted} | **{r['item']}** | {r['category']} | ₹{r['amount']:,.2f} | {r['reason']} |")

        markdown_report = "\n".join(md)
        filename = f"Expense_Report_{range_title.replace(' ', '_')}.pdf"

        # Delegate PDF creation and Telegram delivery to pdf_tools!
        return generate_pdf(markdown_content=markdown_report, filename=filename, conversation_id=conversation_id)

    except Exception as e:
        logger.exception(f"Error generating expense PDF: {e}")
        return f"Error generating PDF report: {e}"