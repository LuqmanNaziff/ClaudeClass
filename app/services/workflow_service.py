from app.repositories.faq_repository import FAQRepository
from app.repositories.order_repository import OrderRepository
from app.schemas.workflow import ProcessTicketRequest
from app.services.analysis_service import AnalysisService
from app.services.response_service import ResponseService
from app.services.ticket_service import TicketService


class WorkflowService:
    def __init__(
        self,
        *,
        analysis_service: AnalysisService,
        response_service: ResponseService,
        ticket_service: TicketService,
        order_repository: OrderRepository,
        faq_repository: FAQRepository,
    ) -> None:
        # Inject existing capabilities; the workflow coordinates them.
        self.analysis_service = analysis_service
        self.response_service = response_service
        self.ticket_service = ticket_service
        self.order_repository = order_repository
        self.faq_repository = faq_repository

    async def process(self, request: ProcessTicketRequest,):
        # Exercise 04: you define deterministic ordering/branches.
        raise NotImplementedError
