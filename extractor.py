import json
import logging
import anthropic
from prompts.extraction import EXTRACTION_PROMPT

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def extract_listing(raw_text):
    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=EXTRACTION_PROMPT,
        messages=[
            {"role": "user", "content": f"<listing>\n{raw_text}\n</listing>"}
        ],
    )
    response_text = message.content[0].text.strip()
    logger.info("Raw extraction response: %s", response_text)

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error("JSON parse failed: %s | response: %s", e, response_text)
        raise

    return data
