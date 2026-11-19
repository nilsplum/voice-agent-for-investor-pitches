"""The web search behind the `web_search` tool: Google results through Serper.

Built for speed: one search per question, only the result snippets (no page is loaded) and a short
timeout (`config.SEARCH_TIMEOUT_S`), because the founder waits for the answer. A timeout, an HTTP
error or an unexpected body is an `AppError` whose AI message (`search_failed`) the note-taker
passes on, so the agent says it cannot look that up right now. The query is never logged: it can
contain what a founder asked.

Runs on the event loop: one awaited HTTP call through the shared client, holding nothing (no
database session) while it waits.
"""

import logging
import time

import httpx

from app import config, http
from app.context import text
from app.errors import AppError
from app.schemas import SearchResult

logger = logging.getLogger(__name__)


async def search(query: str, language: str) -> list[SearchResult]:
    """At most `config.SEARCH_RESULT_COUNT` results; `language` is the conversation's language code."""
    started = time.monotonic()
    try:
        response = await http.client().post(
            config.SERPER_URL, headers={"X-API-KEY": config.secrets().serper_api_key},
            json={"q": query, "num": config.SEARCH_RESULT_COUNT, "hl": language}, timeout=config.SEARCH_TIMEOUT_S)
        response.raise_for_status()
        organic = response.json().get("organic", [])
        results = [SearchResult.model_validate(item) for item in organic[:config.SEARCH_RESULT_COUNT]]
    except (httpx.HTTPError, ValueError, AttributeError) as error:  # ValueError covers bad JSON and ValidationError
        status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
        raise AppError.for_ai(f"reason=search_failed type={type(error).__name__} status={status}",
                              text("messages.search_failed")) from None
    logger.info("event=search duration_ms=%d results=%d", (time.monotonic() - started) * 1000, len(results))
    return results
