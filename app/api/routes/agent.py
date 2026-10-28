from fastapi import (
    APIRouter,
    status,
)

from app.database import get_database
from app.repositories.faq_repository import FAQRepository
from app.repositories.order_repository import OrderRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.agent import (
    AgentSupportRequest,
    AgentSupportResponse,
)
from app.services.agent_service import AgentService
from app.services.analysis_service import AnalysisService
from app.services.claude_service import ClaudeService
from app.services.ticket_service import TicketService


# route -> AgentService -> ClaudeService (decides which tool to call)
#                       -> ToolRegistry  (validates and runs the tool)
#                       -> repositories / TicketService -> MongoDB
# Unlike /workflows/process-ticket, Claude chooses the next step here. The
# application still controls which tools exist and what each one may do.
# prefix="/agent" is added to every path in this file.
router = APIRouter(
    prefix="/agent",
    tags=["agent"],
)


# POST /agent/support: send a customer message and get back the final reply,
# the stored ticket, and an audit list of every tool Claude asked to use.
# 201 Created because a ticket is created for every request.
@router.post(
    "/support",
    response_model = AgentSupportResponse,
    status_code = status.HTTP_201_CREATED,
)
async def agent_support(request: AgentSupportRequest,) -> AgentSupportResponse:
    # request is already validated by AgentSupportRequest at this point.
    # Routes obtain application dependencies; they do not query Mongo directly.
    database = get_database()

    # Shared by the analysis step and the agent loop, closed once below.
    claude_service = ClaudeService()

    # The route composes existing application capabilities into AgentService.
    ticket_service = TicketService(
        TicketRepository(database)
    )

    service = AgentService(
        claude_service = claude_service,
        analysis_service = AnalysisService(claude_service),
        ticket_service = ticket_service,
        order_repository = OrderRepository(database),
        faq_repository = FAQRepository(database),
    )

    try:
        # Runs the bounded agent loop (see AgentService.support).
        result = await service.support(request)
    finally:
        # Close the per-request Claude client even if the agent fails.
        await claude_service.close()

    # Expose both the final answer and the application audit of executed tools.
    return AgentSupportResponse(
        ticket=result.ticket,
        final_response=result.final_response,
        tool_calls=result.tool_calls,
        iterations=result.iterations,
        analysis_usage=result.analysis_usage,
        agent_usage=result.agent_usage,
    )
