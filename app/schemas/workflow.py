from enum import Enum

from pydantic import Field

from app.schemas.common import StrictModel
from app.schemas.ticket import TicketResponse
from app.schemas.usage import AIUsage


class WorkflowStep(str, Enum):
    ANALYSIS = "analysis"
    ORDER_LOOKUP = "order_lookup"
    FAQ_LOOKUP = "faq_lookup"
    DATABASE_INSERT = "database_insert"
    RESPONSE_GENERATION = "response_generation"
    DATABASE_UPDATE = "database_update"

class ProcessTicketRequest(StrictModel):
    # min_length=3 matches TicketCreateRequest, so a short ID fails here
    # with a 422 instead of crashing later when the ticket is created.
    customer_id: str =Field(
        min_length=3,
        max_length=50,
    )

    order_id: str | None = Field(
        default=None,
        min_length=1, 
        max_length=50,
    )

    message: str = Field(
        min_length=5, 
        max_length=5000,
    )

class ProcessTicketResponse(StrictModel):
    ticket: TicketResponse 

    # Debugging and understand ing the workflow execution
    executed_steps: list[WorkflowStep] 

    analysis_usage: AIUsage 
    response_usage: AIUsage