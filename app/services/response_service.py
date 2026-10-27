from app.prompts.response_generation import (
    RESPONSE_GENERATION_SYSTEM_PROMPT,
)
from app.services.claude_service import (
    ClaudeService,
    ClaudeTextResult,
)


# route -> ResponseService -> ClaudeService -> Anthropic SDK
# This service holds the "draft a customer reply" use case: it chooses the
# instructions and limits, and delegates the API call to ClaudeService.

class ResponseService:
    def __init__(self, claude_service: ClaudeService,) -> None:
        # ClaudeService is passed in so the route controls its lifecycle
        # (including close()) and tests can swap in a fake.
        self.claude_service = claude_service

    async def generate(self, customer_message: str,) -> ClaudeTextResult:
        # customer_message is untrusted input and is sent as the user
        # message; the instructions go in the separate system prompt.
        # Returns plain text (ClaudeTextResult), not a structured schema.
        # max_tokens caps the draft length (and therefore the cost).
        return await self.claude_service.generate_text(
            customer_message,
            system=RESPONSE_GENERATION_SYSTEM_PROMPT,
            max_tokens=300,
        )
