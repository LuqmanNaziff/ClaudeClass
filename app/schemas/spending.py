from datetime import date, datetime
from enum import Enum

from pydantic import Field, field_validator

from app.schemas.common import StrictModel
from app.schemas.usage import AIUsage


# Request/response shapes for the Personal Spending Tracker.
# Pydantic validates what the user sends AND what Claude returns.


# Enum limits the category to a fixed set of values, so Claude cannot invent new ones.
class ExpenseCategory(str, Enum):
    FOOD = "food"
    TRANSPORT = "transport"
    SHOPPING = "shopping"
    BILLS = "bills"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"


# Body of POST /expenses/parse: free text such as "lunch nasi lemak RM12 and grab RM18".
class ParseExpensesRequest(StrictModel):
    text: str = Field(
        min_length=3,
        max_length=1000,
    )
    # Optional date the money was spent. The service uses today when it is missing.
    spent_on: date | None = None

    # The user cannot log spending in the future.
    @field_validator("spent_on")
    @classmethod
    def not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("spent_on cannot be in the future.")
        return value


# One expense as Claude must return it. Claude's output is untrusted,
# so these limits are checked before anything is saved.
class ParsedExpense(StrictModel):
    item: str = Field(
        min_length=1,
        max_length=100,
    )
    # gt=0 rejects zero or negative amounts; le=100_000 rejects absurd values.
    amount: float = Field(
        gt=0,
        le=100_000,
    )
    category: ExpenseCategory


# The full structured result Claude must return.
class ExpenseParseResult(StrictModel):
    expenses: list[ParsedExpense] = Field(
        max_length=20,
    )


# An expense after the application accepted and stored it.
# The application (not Claude) sets expense_id, spent_on, month and created_at.
class SavedExpense(StrictModel):
    expense_id: str
    item: str
    amount: float
    category: ExpenseCategory
    spent_on: date
    # "YYYY-MM", used to group spending per month.
    month: str
    created_at: datetime


# Reply of POST /expenses/parse.
class ParseExpensesResponse(StrictModel):
    expenses: list[SavedExpense]
    total_amount: float
    usage: AIUsage


# Body of POST /budget/advice: which month to review, for example "2026-10".
class BudgetAdviceRequest(StrictModel):
    month: str = Field(
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    )


# Spending vs. budget for one category. Calculated by code, never by Claude.
class CategorySpending(StrictModel):
    category: ExpenseCategory
    spent: float
    # None when no budget is set for the category.
    budget_limit: float | None
    remaining: float | None
    over_budget: bool


# Reply of POST /budget/advice. The same shape is stored in budget_reports.
class BudgetAdviceResponse(StrictModel):
    report_id: str
    month: str
    total_spent: float
    categories: list[CategorySpending]
    over_budget_categories: list[ExpenseCategory]
    advice: str = Field(
        min_length=1,
        max_length=2000,
    )
    usage: AIUsage
