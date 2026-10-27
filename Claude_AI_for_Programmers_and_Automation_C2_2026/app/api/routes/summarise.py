from fastapi import APIRouter, HTTPException

from app.schemas.summarise import SummariseRequest, SummariseResponse
from app.services.claude_service import ClaudeService

router = APIRouter(tags=["summaries"])


@router.post("/summarise", response_model=SummariseResponse)
async def summarise_support_message(payload: SummariseRequest) -> SummariseResponse:
    try:
        service = ClaudeService()
        prompt = (
            "You are a customer support assistant. "
            "Summarise the complaint in 2 to 4 clear sentences. "
            "Keep it factual, neutral, and brief.\n\n"
            f"Customer message:\n{payload.message}"
        )

        result = await service.generate_text(
            user_message=prompt,
            max_tokens=200,
            system="Summarise customer support complaints clearly and concisely.",
        )

        return SummariseResponse(
            summary=result.text,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
    except Exception as exc:  # pragma: no cover - route-level error handling
        raise HTTPException(status_code=500, detail=str(exc)) from exc
