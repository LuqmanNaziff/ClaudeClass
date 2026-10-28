from datetime import datetime, timezone

from app.repositories.faq_repository import FAQRepository
from app.repositories.order_repository import OrderRepository
from app.schemas.common import TicketStatus
from app.schemas.faq import FAQSource
from app.schemas.order import OrderContext
from app.schemas.ticket import TicketCreateRequest
from app.schemas.usage import AIUsage
from app.schemas.workflow import (
    ProcessTicketRequest,
    ProcessTicketResponse,
    WorkflowStep,
)
from app.services.analysis_service import AnalysisService
from app.services.response_service import ResponseService
from app.services.ticket_service import TicketService


# route -> WorkflowService -> analysis / repositories / tickets / response
# Python code below fixes the order of the steps and every branch. Claude
# performs two tasks inside the workflow (analysis and drafting) but never
# chooses what runs next.

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

    async def process(self, request: ProcessTicketRequest,) -> ProcessTicketResponse:
        # Record each step as it runs, so the response shows what executed.
        executed_steps: list[WorkflowStep] = []
        # Required trusted context that could not be obtained.
        missing_context: list[str] = []

        # 1. Analyse first: until then we do not know which context is needed.
        analysis_result = await self.analysis_service.analyse(request.message)
        analysis = analysis_result.data
        executed_steps.append(WorkflowStep.ANALYSIS)

        # 2. Order lookup only when the analysis says order data is needed,
        #    and always scoped to the customer (Exercise 01).
        order_context: OrderContext | None = None
        if analysis.needs_order_lookup:
            if request.order_id:
                order_context = await self.order_repository.get_order_for_customer(
                    request.customer_id,
                    request.order_id,
                )
                executed_steps.append(WorkflowStep.ORDER_LOOKUP)

            # No order_id, or not this customer's order: never guess the status.
            if order_context is None:
                missing_context.append("verified order information")

        # 3. FAQ retrieval only when the analysis says approved policy is needed.
        faq_context: list[FAQSource] = []
        if analysis.needs_faq_lookup and analysis.faq_query:
            faq_context = await self.faq_repository.search(analysis.faq_query, limit=3)
            executed_steps.append(WorkflowStep.FAQ_LOOKUP)

            # No approved source: Claude must not invent the policy.
            if not faq_context:
                missing_context.append("approved FAQ information")

        # 4. Persist the ticket. TicketService sets the ID, timestamps and the
        #    initial status from the analysis.
        ticket = await self.ticket_service.create(
            TicketCreateRequest(
                customer_id=request.customer_id,
                order_id=request.order_id,
                message=request.message,
            ),
            analysis,
        )
        executed_steps.append(WorkflowStep.DATABASE_INSERT)

        # 5. Draft a reply using ONLY the context retrieved above. Missing
        #    context is passed as None/[], and the prompt tells Claude to say
        #    it cannot be verified rather than invent it.
        response_result = await self.response_service.generate_draft(
            request.message,
            order_context=order_context,
            faq_context=faq_context,
        )
        executed_steps.append(WorkflowStep.RESPONSE_GENERATION)

        # 6. The application, not Claude, decides the final status.
        status = ticket.status
        escalation_reason = ticket.escalation_reason
        if status == TicketStatus.NEEDS_HUMAN_REVIEW:
            # Flagged by the analysis (needs review or urgent priority).
            escalation_reason = analysis.human_review_reason or "Urgent priority"
        elif missing_context:
            status = TicketStatus.NEEDS_HUMAN_REVIEW
            escalation_reason = "Missing required " + " and ".join(missing_context)
        else:
            status = TicketStatus.PROCESSED

        # model_copy keeps the stored ticket immutable; save() replaces it.
        ticket = await self.ticket_service.save(
            ticket.model_copy(
                update={
                    "order_context": order_context,
                    "faq_context": faq_context,
                    "draft_response": response_result.text,
                    "status": status,
                    "escalation_reason": escalation_reason,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
        )
        executed_steps.append(WorkflowStep.DATABASE_UPDATE)

        return ProcessTicketResponse(
            ticket=ticket,
            executed_steps=executed_steps,
            analysis_usage=AIUsage(
                model=analysis_result.model,
                input_tokens=analysis_result.input_tokens,
                output_tokens=analysis_result.output_tokens,
            ),
            response_usage=AIUsage(
                model=response_result.model,
                input_tokens=response_result.input_tokens,
                output_tokens=response_result.output_tokens,
            ),
        )
