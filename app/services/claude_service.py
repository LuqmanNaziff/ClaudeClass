from dataclasses import dataclass
from typing import Generic, TypeVar
from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError
from app.config import get_settings

# route/service -> ClaudeService -> Anthropic SDK (anthropic.AsyncAnthropic)
# Routes never talk to the Anthropic SDK directly. They call this service,
# which keeps all Claude API access behind one clear boundary.

# Claude -> structured response parsing -> TicketAnalysis -> Pydantic validation

class ClaudeConfigurationError(RuntimeError):
    # Raised when a required setting (API key, model) is missing or empty,
    # so callers can tell a setup problem apart from an API failure.
    pass

class ClaudeErrorResponse(RuntimeError):
    # Raised when the Claude API returns an error response, so callers can
    # tell an API failure apart from a setup problem.
    pass


@dataclass(frozen=True)
class ClaudeTextResult:
    # Immutable (frozen) result object: callers get only the data they need,
    # not the raw SDK response object.
    text: str           # The generated text, with text blocks joined together
    model: str          # The model that actually answered
    input_tokens: int   # Tokens in the prompt (useful for cost tracking)
    output_tokens: int  # Tokens in the response (useful for cost tracking)

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)

@dataclass(frozen=True)
class ClaudeStructuredResult(Generic[StructuredModel]):
    # Immutable (frozen) result object: callers get only the data they need,
    # not the raw SDK response object.
    data: StructuredModel   # The parsed structured data
    model: str              # The model that actually answered
    input_tokens: int       # Tokens in the prompt (useful for cost tracking)
    output_tokens: int      # Tokens in the response (useful for cost tracking)


class ClaudeService:
    def __init__(self) -> None:
        # Read settings (loaded from environment / .env) once at construction.
        settings = get_settings()

        # Fail early with a clear message if the key was never provided.
        if settings.anthropic_api_key is None:
            raise ClaudeConfigurationError(
                "ANTHROPIC_API_KEY is not configured."
            )

        # The key is stored as a Pydantic SecretStr so it is hidden in logs
        # and reprs; get_secret_value() reveals it only here, where it is used.
        api_key = (
            settings.anthropic_api_key
            .get_secret_value()
            .strip()
        )

        # A key that is only whitespace passes the None check above, so
        # guard against it separately.
        if not api_key:
            raise ClaudeConfigurationError(
                "ANTHROPIC_API_KEY is empty."
            )

        if not settings.claude_model:
            raise ClaudeConfigurationError(
                "CLAUDE_MODEL is not configured."
            )

        self.model = settings.claude_model

        # Async client so FastAPI's event loop is not blocked while waiting
        # for Claude. Timeout and retry behaviour come from settings.
        self.client = AsyncAnthropic(
            api_key=api_key,
            timeout=settings.claude_timeout_seconds,
            max_retries=settings.claude_max_retries,
        )

    async def generate_text(
        self,
        user_message: str,
        *,
        max_tokens: int = 300,
        system: str | None = None,
    ) -> ClaudeTextResult:
        # user_message is the untrusted user input; system (optional) holds
        # the application's own instructions. They are sent in separate
        # fields so user input cannot overwrite the app's instructions.
        # max_tokens caps the response length (and therefore the cost).

        # Build the request as a dict so optional fields can be added below.
        request = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": user_message,
                }
            ],
        }

        # Only include "system" when one was given; the API does not want
        # an empty or None value for it.
        if system:
            request["system"] = system

        # Send the request to Claude and wait for the full response.
        message = await self.client.messages.create(
            **request
        )

        # message.content is a list of blocks (text, tool use, etc.).
        # Keep only the text blocks, then join them into a single string.
        text_parts = [
            block.text
            for block in message.content
            if block.type == "text"
        ]

        text = "\n".join(text_parts).strip()

        # Return only the fields the rest of the app needs.
        return ClaudeTextResult(
            text=text,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )

    async def generate_structured(
        self,
        user_message: str,
        *,
        output_model: type[StructuredModel],
        max_tokens: int = 500,
        system: str | None = None,
    ) -> ClaudeStructuredResult[StructuredModel]:
        # Generate text from Claude, then parse it into a Pydantic model.
        # structured_model is the Pydantic model class to parse into.

        request = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": user_message,
                }
            ],
            "output_format": output_model,
        }

        if system:
            request["system"] = system

        try:
            message = await self.client.messages.parse(
                **request
            )
        except ValidationError as exc:
            raise ClaudeErrorResponse(
                "Claude structured output failed application validatioon"
            ) from exc

        if message.parsed_output is None:
            raise ClaudeErrorResponse(
                "Claude returned no structured output"
            )

        return ClaudeStructuredResult[StructuredModel](
            data=message.parsed_output,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )

    async def close(self) -> None:
        # Releases the HTTP connections held by the client. Meant to be
        # called once when the application shuts down.
        await self.client.close()
