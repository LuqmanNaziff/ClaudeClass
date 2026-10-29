from time import perf_counter

from fastapi import APIRouter, Request

from app.database import get_database
from app.repositories.faq_repository import FAQRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.usage_repository import UsageRepository
from app.schemas.ai import (
    AnalyseRequest,
    AnalyseResponse,
    GenerateResponseRequest,
    GenerateResponseResponse,
    ResponseContextUsed,
)
from app.schemas.usage import AIOperation, AIUsage
from app.services.analysis_service import AnalysisService
from app.services.claude_service import ClaudeService
from app.services.generate_response_service import (
    GenerateResponseService,
)
from app.services.response_service import ResponseService
from app.services.usage_service import UsageService


# Routes only accept the request and shape the response. FastAPI/Pydantic
# validate the incoming body; the Claude work happens in the services.
# tags=["ai"] groups these endpoints together in the /docs page.
router = APIRouter(tags=["ai"])


# POST /analyse: send a support message, get a structured TicketAnalysis
# plus token usage back.
@router.post("/analyse", response_model=AnalyseResponse)
async def analyse_ticket(
    request: AnalyseRequest,
    http_request: Request,
) -> AnalyseResponse:
    # Routes only wire things together; the services do the real work.
    database = get_database()
    claude_service = ClaudeService()
    analysis_service = AnalysisService(claude_service)
    usage_service = UsageService(
        UsageRepository(database)
    )

    # Time the Claude call so the usage log can record its latency.
    started = perf_counter()

    try:
        # Close the per-request Claude client even if the analysis fails (see finally).
        result = await analysis_service.analyse(request.message)
    finally:
        await claude_service.close()

    # result.data is the validated TicketAnalysis; usage is grouped in
    # its own AIUsage object so token counts stay separate from the answer.
    latency_ms = int((perf_counter() - started) * 1000)

    usage = AIUsage(
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=latency_ms,
    )

    # Save the usage log; safe_record never fails the request.
    await usage_service.safe_record(
        request_id=http_request.state.request_id,
        operation=AIOperation.TICKET_ANALYSIS,
        usage=usage,
    )

    return AnalyseResponse(
        analysis=result.data,
        usage=usage,
    )


# POST /generate-response: send a customer message, get a draft reply back.
# The draft is plain text for a human to review, not a final answer.
@router.post(
    "/generate-response",
    response_model=GenerateResponseResponse,
)
async def generate_response(
    request: GenerateResponseRequest,
    http_request: Request,
) -> GenerateResponseResponse:
    database = get_database()
    claude_service = ClaudeService()
    usage_service = UsageService(
        UsageRepository(database)
    )

    service = GenerateResponseService(
        response_service=ResponseService(claude_service),
        order_repository=OrderRepository(database),
        faq_repository=FAQRepository(database),
    )

    try:
        # Application service coordinates trusted retrieval and generation.
        result = await service.generate(request)
    finally:
        await claude_service.close()

    # The service measured the latency itself, so reuse that number.
    usage = AIUsage(
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
    )

    await usage_service.safe_record(
        request_id=http_request.state.request_id,
        operation=AIOperation.RESPONSE_GENERATION,
        usage=usage,
    )

    # Return both the draft and which trusted order context was actually used.
    return GenerateResponseResponse(
        draft_response=result.draft_response,
        context_used=ResponseContextUsed(
            order_id=result.order_id_used,
            faq_ids=result.faq_ids_used,
        ),
        usage=usage,
    )
