from pydantic import ValidationError
from app.schemas.ai import TicketAnalysis

invalid_analysis = {
  "summary": "Customer is angry.",
  "category": "delivery",
  "sentiment": "super_angry",
  "priority": "ASAP",
  "needs_order_lookup": True,
  "needs_faq_lookup": False,
  "needs_human_review": False
}

try:
    TicketAnalysis.model_validate(invalid_analysis)
except ValidationError as exc:
    print("Validation failed as expected:")
    print(exc)