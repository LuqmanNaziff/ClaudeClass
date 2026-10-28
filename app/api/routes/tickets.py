from fastapi import APIRouter, HTTPException, Query, status

from app.database import get_database
from app.repositories.ticket_repository import TicketRepository
from app.schemas.ticket import (
    TicketCreateRequest,
    TicketListResponse,
    TicketResponse,
)
from app.services.analysis_service import AnalysisService
from app.services.claude_service import ClaudeService
from app.services.ticket_service import TicketService

# Routes only accept the request and shape the response. Pydantic validates
# the body; TicketService and the repository do the work.
router = APIRouter(prefix="/tickets", tags=["tickets"])


def get_ticket_service() -> TicketService:
    # Routes obtain application dependencies; they do not query Mongo directly.
    return TicketService(TicketRepository(get_database()))


# POST /tickets: analyse a support message with Claude, then store the ticket.
@router.post(
    "",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket(
    request: TicketCreateRequest,
) -> TicketResponse:
    database = get_database()
    ticket_service = TicketService(TicketRepository(database))
    claude_service = ClaudeService()
    analysis_service = AnalysisService(claude_service)

    try:
        # Claude's output is validated as a TicketAnalysis before it is used.
        analysis_result = await analysis_service.analyse(request.message)
    finally:
        # Close the per-request Claude client even if the analysis fails.
        await claude_service.close()

    # The application, not Claude, sets the ticket ID, status and timestamps.
    return await ticket_service.create(request, analysis_result.data)


# GET /tickets: list tickets, newest first, with simple pagination.
# Declared before /{ticket_id} so the two paths are easy to tell apart.
@router.get(
    "",
    response_model=TicketListResponse,
)
async def list_tickets(
    customer_id: str | None = Query(default=None, min_length=3, max_length=50),
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
) -> TicketListResponse:
    service = TicketService(TicketRepository(get_database()))

    return await service.list(
        customer_id=customer_id,
        limit=limit,
        skip=skip,
    )


# GET /tickets/{ticket_id}: fetch one ticket.
@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
)
async def get_ticket(
    ticket_id: str,
) -> TicketResponse:
    service = TicketService(TicketRepository(get_database()))

    ticket = await service.get(ticket_id)

    # The service returns None for "not found"; the route turns it into a 404.
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    return ticket
