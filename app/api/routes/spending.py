from time import perf_counter

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    status as http_status,
)

from app.core.ids import new_report_id
from app.database import get_database
from app.repositories.spending_repository import SpendingRepository
from app.repositories.usage_repository import UsageRepository
from app.schemas.spending import (
    BudgetAdviceRequest,
    BudgetAdviceResponse,
    ParseExpensesRequest,
    ParseExpensesResponse,
)
from app.schemas.usage import AIOperation, AIUsage
from app.services.claude_service import ClaudeResponseError, ClaudeService
from app.services.spending_service import NoExpensesFoundError, SpendingService
from app.services.usage_service import UsageService


# Personal Spending Tracker endpoints.
# tags=["spending"] groups these endpoints together in the /docs page.
router = APIRouter(tags=["spending"])


# POST /expenses/parse: free text in, validated expenses saved to MongoDB.
@router.post(
    "/expenses/parse",
    response_model=ParseExpensesResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def parse_expenses(
    request: ParseExpensesRequest,
    http_request: Request,
) -> ParseExpensesResponse:
    # Routes only wire things together; the services do the real work.
    database = get_database()
    claude_service = ClaudeService()
    spending_service = SpendingService(
        claude_service,
        SpendingRepository(database),
    )
    usage_service = UsageService(
        UsageRepository(database)
    )

    # Time the Claude call so the usage log can record its latency.
    started = perf_counter()

    try:
        saved, result = await spending_service.parse_and_save(request)
    except NoExpensesFoundError as exc:
        # The request was valid, but Claude found nothing usable in it.
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )
    finally:
        # Close the per-request Claude client even if parsing fails.
        await claude_service.close()

    usage = AIUsage(
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=int((perf_counter() - started) * 1000),
    )

    # Save the usage log; safe_record never fails the request.
    await usage_service.safe_record(
        request_id=http_request.state.request_id,
        operation=AIOperation.EXPENSE_PARSE,
        usage=usage,
    )

    return ParseExpensesResponse(
        expenses=saved,
        total_amount=round(sum(expense.amount for expense in saved), 2),
        usage=usage,
    )


# POST /budget/advice: the multi-step workflow.
# MongoDB totals -> budget limits -> code decides over budget
# -> Claude writes advice -> report saved -> response.
@router.post(
    "/budget/advice",
    response_model=BudgetAdviceResponse,
)
async def budget_advice(
    request: BudgetAdviceRequest,
    http_request: Request,
) -> BudgetAdviceResponse:
    database = get_database()
    spending_repository = SpendingRepository(database)
    claude_service = ClaudeService()
    spending_service = SpendingService(
        claude_service,
        spending_repository,
    )
    usage_service = UsageService(
        UsageRepository(database)
    )

    try:
        # Steps 1-3: totals, budget limits and the over-budget rule. No AI involved,
        # so a month with no data stops here without paying for a Claude call.
        try:
            categories = await spending_service.summarise_month(request.month)
        except NoExpensesFoundError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            )

        # Step 4: Claude writes the advice text from the calculated numbers.
        started = perf_counter()
        result = await spending_service.write_advice(request.month, categories)
    finally:
        await claude_service.close()

    # Step 5: don't trust AI output blindly; an empty reply is not usable advice.
    if not result.text:
        raise ClaudeResponseError("Claude returned empty advice.")

    usage = AIUsage(
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=int((perf_counter() - started) * 1000),
    )

    # The application builds the report: ID, totals and flags come from code.
    report = BudgetAdviceResponse(
        report_id=new_report_id(),
        month=request.month,
        total_spent=round(sum(item.spent for item in categories), 2),
        categories=categories,
        over_budget_categories=[
            item.category for item in categories if item.over_budget
        ],
        advice=result.text[:2000],
        usage=usage,
    )

    # Step 6: store the report and the usage log, then return the report.
    await spending_repository.insert_report(report)
    await usage_service.safe_record(
        request_id=http_request.state.request_id,
        operation=AIOperation.BUDGET_ADVICE,
        usage=usage,
    )

    return report
