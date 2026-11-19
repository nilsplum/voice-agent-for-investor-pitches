"""The backend's own AI calls: one OpenAI Responses API request whose answer is a strict structured
output, shared by the writing down (app/ai/writer.py) and the review (app/ai/reviewer.py).

- The caller names the model and thinking level (from the conversation's settings), the
  instructions (from the context system), the input (one JSON object) and the output model. The
  output model's JSON schema is the response format, so the answer always has that shape, and the
  same model parses it. Output models forbid extra fields and have no defaults, as OpenAI's strict
  mode requires.
- Some models occasionally add a second message item to a structured output, so every output text
  is tried and the first valid one counts.
- `accept` lets a caller refuse a valid but unusable answer (for example a summary too long to read
  aloud); it counts as a failed attempt.
- Every attempt has `STRUCTURED_CALL_TIMEOUT_S`, and a failed attempt is retried after
  `STRUCTURED_CALL_RETRY_DELAY_S`, at most `STRUCTURED_CALL_ATTEMPTS` times; then the result is
  `None` and the caller decides what that means. Logs carry the call's name, the attempt, the
  duration, and for a failure its type and HTTP status, never the input or the answer, which repeat
  what the founder said.

Runs on the event loop: awaited HTTP calls through the shared client, holding no database session.
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable

import httpx
from pydantic import BaseModel, ValidationError

from app import config, http

logger = logging.getLogger(__name__)


async def call[Output: BaseModel](name: str, model: str, thinking: str, instructions: str, payload: dict,
                                  output: type[Output],
                                  accept: Callable[[Output], bool] | None = None) -> Output | None:
    """The parsed structured answer, or None once every attempt failed."""
    body = {
        "model": model,
        "reasoning": {"effort": thinking},
        "instructions": instructions,
        "input": json.dumps(payload, ensure_ascii=False),
        "text": {"format": {"type": "json_schema", "name": name, "strict": True,
                            "schema": output.model_json_schema()}},
    }
    headers = {"Authorization": f"Bearer {config.secrets().openai_api_key}"}
    for attempt in range(1, config.STRUCTURED_CALL_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            response = await http.client().post(f"{config.OPENAI_API_URL}/responses", headers=headers, json=body,
                                                timeout=config.STRUCTURED_CALL_TIMEOUT_S)
            response.raise_for_status()
            result = _parsed(response.json(), output)
            if accept is not None and not accept(result):
                raise ValueError("the answer was not accepted")
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as error:
            status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
            logger.warning("event=structured_call_failed name=%s attempt=%d type=%s status=%s duration_ms=%d", name,
                           attempt, type(error).__name__, status, (time.monotonic() - started) * 1000)
            if attempt < config.STRUCTURED_CALL_ATTEMPTS:
                await asyncio.sleep(config.STRUCTURED_CALL_RETRY_DELAY_S)
            continue
        logger.info("event=structured_call name=%s attempt=%d duration_ms=%d", name, attempt,
                    (time.monotonic() - started) * 1000)
        return result
    return None


def _parsed[Output: BaseModel](body: dict, output: type[Output]) -> Output:
    """The first valid structured output among the response's message texts."""
    texts = [part["text"] for item in body.get("output", []) if item.get("type") == "message"
             for part in item.get("content", []) if part.get("type") == "output_text"]
    for candidate in texts:
        try:
            return output.model_validate_json(candidate)
        except ValidationError:
            continue
    raise ValueError("the response contains no valid structured output")
