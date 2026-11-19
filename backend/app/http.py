"""The one shared outbound HTTP client, for OpenAI's REST endpoints (creating Live sessions, the
reviewer) and for Serper.

One `httpx.AsyncClient` for the whole process reuses its connections, so a call to OpenAI or
Serper skips the TCP and TLS setup. The app's lifespan opens it (`open_client`) and closes it on
shutdown. It has no default timeout: every call passes its own from the config module, because
each wait has its own reason (see config.py).

Runs on the event loop; the calls are awaited, so nothing blocks it while OpenAI or Serper answer.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def open_client() -> AsyncIterator[None]:
    global _client
    previous = _client  # only the tests ever nest two apps' lifespans
    async with httpx.AsyncClient(timeout=None) as client:
        _client = client
        try:
            yield
        finally:
            _client = previous


def client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("The HTTP client is opened by the app's lifespan (app.http.open_client).")
    return _client
