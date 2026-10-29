from uuid import uuid4


# IDs are created by the application, never by Claude or the client.
# uuid4 is random, so clashes are very unlikely; 8 hex characters keeps the ID readable.
def new_ticket_id() -> str:
    return f"TKT-{uuid4().hex[:8]}"


# Same idea for AI usage logs. 12 characters because there are many more usage logs than tickets.
def new_usage_id() -> str:
    return f"USG-{uuid4().hex[:12]}"


# Spending tracker IDs: one per saved expense and one per advice report.
def new_expense_id() -> str:
    return f"EXP-{uuid4().hex[:8]}"


def new_report_id() -> str:
    return f"RPT-{uuid4().hex[:8]}"
