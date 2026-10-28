import json
from typing import Any


def serialize_prompt_payload(payload: dict[str, Any]) -> str:
    """Serialize application-created prompt data in a visible, stable shape."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )
