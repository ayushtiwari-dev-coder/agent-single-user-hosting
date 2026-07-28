# tools/expense_tools.py

import datetime
import logging
from tools.core import agent_tool
from queries.expense_queries import create_expense, get_expenses_in_range, get_category_totals_in_range
from tools.file_tools import generate_pdf

logger = logging.getLogger("tools.expense_tools")

# Indian Standard Time (IST: UTC +05:30)
try:
    import zoneinfo
    TZ_IST = zoneinfo.ZoneInfo("Asia/Kolkata")
except ImportError:
    TZ_IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _get_time_range(
    days: int = None, 
    period: str = None, 
    start_date: str = None, 
    end_date: str = None,
    max_days_limit: int = 30
) -> tuple[str, str, str]:
    """Calculates IST start/end ISO datetimes capped strictly to max_days_limit."""
    now = datetime.datetime.now(TZ_IST)
    
    # Enforce 30-day maximum safety limit to protect context window
    if days and days > max_days_limit:
        days = max_days_limit

    # 1. Explicit Custom Date Range (e.g. "2026-07-01" to "2026-07-15")
    if start_date:
        try:
            s_dt = datetime.datetime.fromisoformat(start_date.strip())
            start_dt = s_dt.strftime("%Y-%m-%dT00:00:00")
        except ValueError:
            start_dt = (now - datetime.timedelta(days=max_days_limit)).strftime("%Y-%m-%dT00:00:00")
        
        if end_date:
            try:
                e_dt = datetime.datetime.fromisoformat(end_date.strip())
                end_dt = e_dt.strftime("%Y-%m-%dT23:59:59")
            except ValueError:
                end_dt = now.strftime("%Y-%m-%dT23:59:59")
        else:
            end_dt = now.strftime("%Y-%m-%dT23:59:59")
            
        title = f"Custom Range ({start_date} to {end_date or 'Today'})"
        return start_dt, end_dt, title

    # 2. Named Periods or Relative Days
    end_dt = now.strftime("%Y-%m-%dT23:59:59")
    if period:
        period_clean = str(period).strip().lower()
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
            start_dt = (now - datetime.timedelta(days=max_days_limit)).strftime("%Y-%m-%dT00:00:00")
            title = f"Last {max_days_limit} Days"
        else:
            start_dt = (now - datetime.timedelta(days=max_days_limit)).strftime("%Y-%m-%dT00:00:00")
            title = f"Last {max_days_limit} Days"
    elif days is not None and days > 0:
        start_dt = (now - datetime.timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
        title = f"Last {days} Day(s)"
    else:
        start_dt = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%dT00:00:00")
        title = "Last 7 Days"

    return start_dt, end_dt, title


@agent_tool()
def log_expense(
    amount: float, 
    item: str, 
    category: str = "General", 
    reason: str = "", 
    date_str: str = None
) -> str:
    """
    Logs a new personal expense transaction into the database.
    
    Args:
        amount: Exact numerical amount spent (e.g. 250.0, 1200.50).
        item: Specific item purchased (e.g. "Canvas Paint", "Subway").
        category: Broad category ("Food", "Art/Hobbies", "Travel", "Utilities", etc.).
        reason: (Optional) Context, justification, or notes about why it was purchased.
        date_str: (Optional) Custom date string if backdating a past expense 
                  (e.g., "2026-07-25" or "2026-07-25T14:30:00"). Defaults to current time in IST.
    """
    if amount <= 0:
        return "Error: Expense amount must be greater than zero."

    now = datetime.datetime.now(TZ_IST)

    if date_str:
        try:
            custom_dt = datetime.datetime.fromisoformat(date_str.strip())
            if "T" not in date_str:
                custom_dt = custom_dt.replace(hour=now.hour, minute=now.minute, second=now.second)
            expense_date = custom_dt.strftime("%Y-%m-%d")
            created_at = custom_dt.strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            expense_date = now.strftime("%Y-%m-%d")
            created_at = now.strftime("%Y-%m-%dT%H:%M:%S")
    else:
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
        dt_obj = datetime.datetime.fromisoformat(created_at)
        time_str = dt_obj.strftime("%d %b %Y at %I:%M:%S %p IST")
        return (
            f"Success: Recorded expense #{expense_id}!\n"
            f"• Amount: ₹{amount:,.2f}\n"
            f"• Item: {item}\n"
            f"• Category: {category.title()}\n"
            f"• Reason: {reason if reason else 'N/A'}\n"
            f"• Timestamp: {time_str}"
        )
    except Exception as e:
        logger.exception(f"Failed to log expense: {e}")
        return f"Error logging expense: {e}"


@agent_tool()
def get_raw_expense_log(
    days: int = 7, 
    start_date: str = None, 
    end_date: str = None, 
    category: str = None, 
    search_query: str = None
) -> str:
    """
    Fetches the unsummarized, itemized transaction log with full reasons and exact timestamps.
    Use this tool when the user asks specific questions like "What art stuff did I buy?", 
    "Show me my exact transactions for last week", or wants to analyze specific reasons for spending.
    
    Args:
        days: Past number of days to fetch (Default: 7 days, Maximum: 30 days).
        start_date: (Optional) Explicit start date "YYYY-MM-DD".
        end_date: (Optional) Explicit end date "YYYY-MM-DD".
        category: (Optional) Filter strictly to one category (e.g., "Art/Hobbies").
        search_query: (Optional) Keyword to search inside item names or reasons (e.g. "paint", "amazon", "pizza").
    """
    try:
        start_dt, end_dt, range_title = _get_time_range(
            days=days, start_date=start_date, end_date=end_date, max_days_limit=30
        )
        items = get_expenses_in_range(
            start_dt, end_dt, category=category, search_query=search_query, limit=100
        )

        if not items:
            cat_info = f" in category '{category}'" if category else ""
            search_info = f" matching '{search_query}'" if search_query else ""
            return f"No individual transactions found for {range_title}{cat_info}{search_info}."

        output = [f"📜 **ITEMIZED TRANSACTION LOG ({range_title.upper()})**"]
        if search_query:
            output.append(f"🔍 Search Keyword: '{search_query}'")
        output.append(f"Showing {len(items)} transactions:\n")

        for idx, row in enumerate(items, start=1):
            dt_obj = datetime.datetime.fromisoformat(row["created_at"])
            time_formatted = dt_obj.strftime("%d %b %Y at %I:%M:%S %p IST")
            reason_str = f"\n   ↳ Notes/Reason: {row['reason']}" if row['reason'] and row['reason'] != "None provided" else ""
            output.append(
                f"{idx}. **₹{row['amount']:,.2f}** — {row['item']} [{row['category']}]\n"
                f"   📅 Time: {time_formatted}{reason_str}"
            )

        return "\n\n".join(output)

    except Exception as e:
        logger.exception(f"Error fetching raw expense log: {e}")
        return f"Error fetching itemized expense log: {e}"


@agent_tool()
def get_expense_summary(
    days: int = None, 
    period: str = None, 
    start_date: str = None, 
    end_date: str = None, 
    category: str = None, 
    daily_budget: float = None
) -> str:
    """
    Calculates aggregated financial metrics, total spending, category totals, and budget status.
    Use this when the user wants high-level numbers, totals, or budget performance rather than itemized details.
    """
    try:
        start_dt, end_dt, range_title = _get_time_range(
            days=days, period=period, start_date=start_date, end_date=end_date, max_days_limit=30
        )
        items = get_expenses_in_range(start_dt, end_dt, category=category)
        cat_summaries = get_category_totals_in_range(start_dt, end_dt)

        if not items:
            cat_msg = f" for category '{category}'" if category else ""
            return f"No expense data found for {range_title}{cat_msg}."

        grand_total = sum(row["amount"] for row in items)

        output = [f"📊 **FINANCIAL SUMMARY: {range_title.upper()}**"]
        output.append(f"💰 **Total Spent:** ₹{grand_total:,.2f}")
        output.append(f"🧾 **Total Items Purchased:** {len(items)}")

        if daily_budget and daily_budget > 0:
            num_days = days if (days and days > 0) else 30
            if period and period.strip().lower() in ["today", "yesterday"]:
                num_days = 1
            elif period and period.strip().lower() in ["this_week", "weekly", "7d"]:
                num_days = 7

            target_total = daily_budget * num_days
            variance = grand_total - target_total
            daily_avg = grand_total / num_days

            output.append(f"🎯 **Target Budget:** ₹{daily_budget:,.2f}/day (Allowed: ₹{target_total:,.2f} for {num_days} days)")
            output.append(f"📈 **Actual Average:** ₹{daily_avg:,.2f}/day")

            if variance <= 0:
                output.append(f"🟢 **STATUS: UNDER BUDGET by ₹{abs(variance):,.2f}!** Good job! 🎉\n")
            else:
                output.append(f"🔴 **STATUS: OVER BUDGET by ₹{variance:,.2f}!** Watch out! ⚠️\n")
        else:
            output.append("")

        if cat_summaries and not category:
            output.append("🏷️ **Breakdown by Category:**")
            for cat in cat_summaries:
                pct = (cat["total_amount"] / grand_total) * 100 if grand_total > 0 else 0
                output.append(f"• **{cat['category']}**: ₹{cat['total_amount']:,.2f} ({pct:.1f}% | {cat['item_count']} items)")

        return "\n".join(output)

    except Exception as e:
        logger.exception(f"Error calculating expense summary: {e}")
        return f"Error fetching expense summary: {e}"


@agent_tool()
def generate_expense_pdf_report(
    days: int = None, 
    period: str = None, 
    start_date: str = None, 
    end_date: str = None, 
    conversation_id: int = None
) -> str:
    """Generates a financial statement PDF for expenses and delivers it directly via Telegram."""
    try:
        start_dt, end_dt, range_title = _get_time_range(
            days=days, period=period, start_date=start_date, end_date=end_date, max_days_limit=30
        )
        items = get_expenses_in_range(start_dt, end_dt)
        cat_summaries = get_category_totals_in_range(start_dt, end_dt)

        if not items:
            return f"No expenses logged for {range_title}. Skipping PDF report generation."

        grand_total = sum(row["amount"] for row in items)

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

        return generate_pdf(markdown_content=markdown_report, filename=filename, conversation_id=conversation_id)

    except Exception as e:
        logger.exception(f"Error generating expense PDF: {e}")
        return f"Error generating PDF report: {e}"