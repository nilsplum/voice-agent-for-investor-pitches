"""The app factory: lifespan, session cookie, error handling and routers.

There is no module-level app: uvicorn calls `create_app` as a factory (see backend/Dockerfile), so
importing this module has no side effects, and the tests and the CLI's `openapi` command build
their own app. The API documentation is served at /api/docs, which the frontend's dev server
proxies like every other /api path. The OpenAPI schema, which the frontend types are generated
from, also carries `schemas.BROWSER_TYPES`, the types the browser needs although no route has them.

The lifespan's startup stops the app at once, with a clear message, when the context documents
are broken or the database cannot be reached. It seeds the team-editable values on the very first
launch and finishes the conversations a restart cut off (the call registry lives in memory, so no
call survives a restart). Its shutdown ends every running call through its own cleanup (also the
restarts of `--reload`) and then closes the shared HTTP client.

Runs on the event loop; the startup's database work runs in a worker thread through `run_db`.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import TypeAdapter

from app import config, http
from app.ai import live
from app.context import context
from app.conversations import sweep_after_restart
from app.db import run_db
from app.errors import install_error_handlers
from app.logs import configure_logging
from app.routes import auth, founder, public, team
from app.schemas import BROWSER_TYPES
from app.security import install_sessions
from app.team_values import seed_all

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    context()  # loads and validates the context documents before anything uses them
    await run_db(seed_all)  # also the database check: the first query of the app
    await run_db(sweep_after_restart)
    async with http.open_client():
        logger.info("event=startup")
        try:
            yield
        finally:
            await live.end_all_calls()
            logger.info("event=shutdown")


def create_app() -> FastAPI:
    config.secrets()  # first: a missing or broken secrets file stops the app here, with a clear message
    app = FastAPI(title="Voice Agent for Investor Pitches", lifespan=lifespan, openapi_url="/api/openapi.json",
                  docs_url="/api/docs", redoc_url=None)
    install_sessions(app)
    install_error_handlers(app)  # after the sessions, so its middleware is the outermost one
    for router in (public.router, auth.router, founder.router, team.router):
        app.include_router(router)
    _add_browser_types(app)
    return app


def _add_browser_types(app: FastAPI) -> None:
    """Adds `schemas.BROWSER_TYPES` to the OpenAPI schema that FastAPI builds from the routes (once,
    then cached in `app.openapi_schema`), so the generated frontend types name them too."""
    build = app.openapi

    def openapi() -> dict:
        if app.openapi_schema is None:
            schemas = build()["components"]["schemas"]
            for name, browser_type in BROWSER_TYPES.items():
                schemas[name] = TypeAdapter(browser_type).json_schema()
        return app.openapi_schema

    app.openapi = openapi
