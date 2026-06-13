import logging
import anthropic
from .config import settings
from .prompts.extraction import EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

_client = None

_EXTRACTION_TOOL = {
    "name": "extract_listing",
    "description": "Extract structured rental listing data from raw text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "property_type": {
                "type": "string",
                "enum": ["Apartment", "Condo", "Service Apartment", "Borey", "Villa", "Shophouse", "Studio"],
            },
            "property_name":      {"type": ["string", "null"]},
            "unit_code":          {"type": ["string", "null"]},
            "city":               {"type": ["string", "null"]},
            "district":           {"type": ["string", "null"]},
            "landmark":           {"type": ["string", "null"]},
            "room_type":          {"type": ["string", "null"]},
            "floor":              {"type": ["integer", "null"]},
            "furnished_status": {
                "type": ["string", "null"],
                "enum": ["Full", "Partial", "Unfurnished", None],
            },
            "rent_usd":             {"type": ["number", "null"]},
            "management_fee_usd":   {"type": ["number", "null"]},
            "electricity_per_kwh":  {"type": ["number", "null"]},
            "water_per_m3":         {"type": ["number", "null"]},
            "car_parking_usd":      {"type": ["number", "null"]},
            "motor_parking_usd":    {"type": ["number", "null"]},
            "amenities_included":   {"type": ["object", "null"]},
            "amenities_excluded":   {"type": ["object", "null"]},
            "extraction_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "needs_review":          {"type": "boolean"},
        },
        "required": ["extraction_confidence", "needs_review"],
    },
}

# System prompt passed as a structured block so the API can cache it across calls.
# cache_control ephemeral keeps it in the prompt cache for ~5 minutes — sufficient
# for burst ingestion and saves ~80% of input tokens on repeated extractions.
_SYSTEM = [
    {
        "type": "text",
        "text": EXTRACTION_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }
]


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def extract_listing(raw_text):
    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=_SYSTEM,
        tools=[_EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "extract_listing"},
        messages=[
            {"role": "user", "content": f"<listing>\n{raw_text}\n</listing>"}
        ],
    )

    tool_block = next(
        (b for b in message.content if b.type == "tool_use"),
        None,
    )
    if tool_block is None:
        raise ValueError(f"No tool_use block in response: {message.content}")

    data = tool_block.input
    logger.info(
        "Extracted listing — confidence=%.2f needs_review=%s cache_tokens=%s",
        data.get("extraction_confidence", 0),
        data.get("needs_review"),
        getattr(message.usage, "cache_read_input_tokens", 0),
    )
    return data
