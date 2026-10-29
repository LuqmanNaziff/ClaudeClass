from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING

from app.schemas.spending import BudgetAdviceResponse, SavedExpense


# The only code that talks to the expenses, budgets and budget_reports collections.
# Services call these methods; Claude never has database access.
class SpendingRepository:
    def __init__(self, database: Any) -> None:
        # MongoDB creates each collection the first time a document is inserted.
        self.expenses = database.expenses
        self.budgets = database.budgets
        self.reports = database.budget_reports

    # Indexes make the monthly totals and budget lookups fast. Running this more than once is safe.
    async def ensure_indexes(self) -> None:
        await self.expenses.create_index(
            "expense_id",
            unique=True,
        )
        await self.expenses.create_index(
            [("month", ASCENDING), ("category", ASCENDING)],
        )
        await self.budgets.create_index(
            "category",
            # unique=True: only one budget limit per category.
            unique=True,
        )
        await self.reports.create_index(
            "report_id",
            unique=True,
        )

    # Stores the validated expenses in one insert_many call.
    async def insert_expenses(
        self,
        expenses: list[SavedExpense],
    ) -> None:
        documents = []

        for expense in expenses:
            # mode="json" turns the date and enum into plain strings MongoDB can store.
            document = expense.model_dump(mode="json")
            # Keep created_at as a real datetime so it sorts correctly.
            document["created_at"] = expense.created_at
            documents.append(document)

        if documents:
            await self.expenses.insert_many(documents)

    # MongoDB adds up the amounts per category for one month.
    # Returns, for example, {"food": 532.0, "transport": 108.0}.
    async def totals_by_category(
        self,
        month: str,
    ) -> dict[str, float]:
        pipeline = [
            {"$match": {"month": month}},
            {
                "$group": {
                    "_id": "$category",
                    "spent": {"$sum": "$amount"},
                }
            },
        ]

        cursor = await self.expenses.aggregate(pipeline)

        totals: dict[str, float] = {}

        async for document in cursor:
            totals[document["_id"]] = round(float(document["spent"]), 2)

        return totals

    # Budget limits are trusted application data, seeded by the developer.
    # Returns, for example, {"food": 500.0, "transport": 200.0}.
    async def get_budget_limits(self) -> dict[str, float]:
        cursor = self.budgets.find(
            {},
            {"_id": 0, "category": 1, "monthly_limit": 1},
        )

        limits: dict[str, float] = {}

        async for document in cursor:
            limits[document["category"]] = float(document["monthly_limit"])

        return limits

    # Keeps a history of every advice report that was generated.
    async def insert_report(
        self,
        report: BudgetAdviceResponse,
    ) -> None:
        document = report.model_dump(mode="json")
        # Store time in UTC to avoid time-zone confusion.
        document["created_at"] = datetime.now(timezone.utc)
        await self.reports.insert_one(document)
