from datetime import date, datetime, timezone

from app.core.ids import new_expense_id
from app.prompts.spending import (
    BUDGET_ADVICE_SYSTEM_PROMPT,
    EXPENSE_PARSE_SYSTEM_PROMPT,
)
from app.repositories.spending_repository import SpendingRepository
from app.schemas.spending import (
    CategorySpending,
    ExpenseCategory,
    ExpenseParseResult,
    ParseExpensesRequest,
    SavedExpense,
)
from app.services.claude_service import (
    ClaudeService,
    ClaudeStructuredResult,
    ClaudeTextResult,
)


# route -> SpendingService -> ClaudeService (AI) + SpendingRepository (MongoDB)
# Claude extracts expenses and writes advice text.
# This service (our code) does the maths and decides what is over budget.


# Raised when there is nothing to save or nothing to review, so the route
# can return a controlled 4xx instead of an empty result.
class NoExpensesFoundError(Exception):
    pass


class SpendingService:
    def __init__(
        self,
        claude_service: ClaudeService,
        repository: SpendingRepository,
    ) -> None:
        # Both dependencies are passed in, so the route controls their lifecycle.
        self.claude_service = claude_service
        self.repository = repository

    # POST /expenses/parse: free text -> Claude -> validated expenses -> MongoDB.
    async def parse_and_save(
        self,
        request: ParseExpensesRequest,
    ) -> tuple[list[SavedExpense], ClaudeStructuredResult[ExpenseParseResult]]:
        # Step 1: Claude turns the free text into structured expenses.
        # The user text goes in the user message only; our rules stay in the system prompt.
        # The SDK validates the reply against ExpenseParseResult before we see it.
        result = await self.claude_service.generate_structured(
            "Expense text:\n" + request.text,
            system=EXPENSE_PARSE_SYSTEM_PROMPT,
            output_model=ExpenseParseResult,
            max_tokens=800,
        )

        if not result.data.expenses:
            raise NoExpensesFoundError(
                "No expenses with an amount were found in the text."
            )

        # Step 2: the application (not Claude) adds the IDs, date, month and timestamp.
        spent_on = request.spent_on or date.today()
        created_at = datetime.now(timezone.utc)

        saved = [
            SavedExpense(
                expense_id=new_expense_id(),
                item=parsed.item,
                amount=round(parsed.amount, 2),
                category=parsed.category,
                spent_on=spent_on,
                month=spent_on.strftime("%Y-%m"),
                created_at=created_at,
            )
            for parsed in result.data.expenses
        ]

        # Step 3: store them in MongoDB.
        await self.repository.insert_expenses(saved)

        return saved, result

    # Budget workflow steps 1-3: load trusted data and apply the budget rule. No AI involved.
    async def summarise_month(
        self,
        month: str,
    ) -> list[CategorySpending]:
        totals = await self.repository.totals_by_category(month)

        # Stop here, before any Claude call, when there is nothing to review.
        if not totals:
            raise NoExpensesFoundError(
                f"No expenses recorded for {month}."
            )

        limits = await self.repository.get_budget_limits()

        categories: list[CategorySpending] = []

        for category in ExpenseCategory:
            spent = totals.get(category.value, 0.0)
            limit = limits.get(category.value)

            # Skip categories with no spending and no budget.
            if spent == 0 and limit is None:
                continue

            categories.append(
                CategorySpending(
                    category=category,
                    spent=spent,
                    budget_limit=limit,
                    remaining=(
                        None if limit is None else round(limit - spent, 2)
                    ),
                    # The business rule, decided by code: spent > limit means over budget.
                    over_budget=limit is not None and spent > limit,
                )
            )

        return categories

    # Budget workflow step 4: Claude writes advice from the calculated numbers.
    async def write_advice(
        self,
        month: str,
        categories: list[CategorySpending],
    ) -> ClaudeTextResult:
        # Only code-calculated numbers are sent, never the user's original text,
        # so there is no untrusted input in this prompt.
        lines = [f"Month: {month}"]

        for item in categories:
            limit_text = (
                "no budget set"
                if item.budget_limit is None
                else f"budget RM{item.budget_limit:.2f}"
            )
            status = "OVER BUDGET" if item.over_budget else "within budget"
            lines.append(
                f"- {item.category.value}: spent RM{item.spent:.2f}, {limit_text}, {status}"
            )

        return await self.claude_service.generate_text(
            "\n".join(lines),
            system=BUDGET_ADVICE_SYSTEM_PROMPT,
            max_tokens=300,
        )
