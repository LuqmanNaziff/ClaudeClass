from pydantic import BaseModel, Field

class SummariseRequest(BaseModel):
    text: str = Field(
        min_length=20,
        max_length=5000,
    )

class SummariseResponse(BaseModel):
    summary: str
    model: str
    input_tokens: int
    output_tokens: int