from dataclasses import dataclass
from app.repositories.order_repository import OrderRepository
from app.schemas.ai import GenerateResponseRequest
from app.services.response_service import ResponseService


@dataclass(frozen=True)
class GenerateResponseResult:
    # Return both the draft and metadata needed by the API layer.
    draft_response: str
    order_id_used: str | None
    model: str
    input_tokens: int
    output_tokens: int


class GenerateResponseService:
    def __init__(
        self,
        *,
        response_service: ResponseService,
        order_repository: OrderRepository,
    ) -> None:
        self.response_service = response_service
        self.order_repository = order_repository

    async def generate(
        self,
        request: GenerateResponseRequest,
    ) -> GenerateResponseResult:
        order_context = None

        # Retrieve an order only when both identifiers are present.
        if request.order_id and request.customer_id:
            order_context = (
                await self.order_repository
                .get_order_for_customer(
                    request.customer_id,
                    request.order_id,
                )
            )

        # Claude receives only the trusted context the application retrieved.
        claude_result = (
            await self.response_service
            .generate_draft(
                request.customer_message,
                order_context=order_context,
            )
        )

        return GenerateResponseResult(
            draft_response = claude_result.text,
            order_id_used=(
                order_context.order_id
                if order_context
                else None
            ),
            model = claude_result.model,
            input_tokens = claude_result.input_tokens,
            output_tokens = claude_result.output_tokens,
        )
