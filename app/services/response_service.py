from app.core.prompt_data import serialize_prompt_payload
from app.prompts.response_generation import RESPONSE_GENERATION_SYSTEM_PROMPT
from app.schemas.order import OrderContext
from app.services.claude_service import (
    ClaudeService,
    ClaudeTextResult,
)
from app.schemas.faq import FAQSource


class ResponseService:
    def __init__(self, claude_service: ClaudeService) -> None:
        self.claude_service = claude_service

    async def generate_draft(
        self,
        customer_message: str,
        *,
        order_context: OrderContext | None = None,
        faq_context: list[FAQSource] | None = None,
    ) -> ClaudeTextResult:
        # The caller may omit FAQ context for other existing use cases.
        faq_context = faq_context or []

        # Trusted data comes from repositories, not user claims.
        payload = {
            "customer_message": customer_message,
            "trusted_order_context": (
                order_context.model_dump(mode="json")
                if order_context
                else None
            ),
            "trusted_faq_context": [
                faq.model_dump(mode="json")
                for faq in faq_context
            ],
        }

        user_prompt = (
            "Customer request and application "
            "context:\n"
            + serialize_prompt_payload(payload)
        )

        return await self.claude_service.generate_text(
            user_prompt,
            system=RESPONSE_GENERATION_SYSTEM_PROMPT,
            max_tokens=350,
        )

