"""The one error type of the backend, and how errors become responses.

An `AppError` carries three separate messages: the user's (short, plain German; the only text the
browser ever receives), the AI's (what happened, why and what to do next; the only text an AI
receives about it) and the log's (technical details as key=value pairs, never user content).
Anything else that goes wrong is answered with one generic message and logged with its exception
type only, because an exception's text can contain what a founder said.

The note-taker's tools follow the same rule (app/ai/tools.py): when a tool fails, the voice agent is
told the error's AI message, or the context system's `generic_error` text when it has none
(`message_for_ai`), so the agent always knows what happened. An error raised only for the AI
(`AppError.for_ai`) still carries the generic user message, so nothing else ever reaches a browser.

Unexpected exceptions are caught by a small middleware, not by an exception handler: Starlette
re-raises an exception after its 500 handler ran, and the server would then log the full
traceback. `install_error_handlers` runs after the session middleware is installed, so this
middleware is the outermost one and also covers errors in the session handling.

Runs on the event loop; nothing here waits.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.context import text
from app.schemas import ErrorResponse

logger = logging.getLogger(__name__)

INVALID_INPUT = "Bitte prüfen Sie Ihre Eingaben."
UNEXPECTED = "Etwas ist schiefgelaufen. Bitte versuchen Sie es erneut."


class AppError(Exception):
    """A refused request or a failed step, with its message for the user, the AI and the logs."""

    def __init__(self, user_message: str, log_message: str, ai_message: str | None = None,
                 status_code: int = 400):
        super().__init__(log_message)  # str(error) is the log text, never the user's or the AI's
        self.user_message = user_message
        self.log_message = log_message
        self.ai_message = ai_message
        self.status_code = status_code

    @classmethod
    def for_ai(cls, log_message: str, ai_message: str) -> "AppError":
        """A failed tool step: only the voice agent (its AI message) and the logs read it."""
        return cls(UNEXPECTED, log_message, ai_message=ai_message, status_code=500)


def message_for_ai(error: Exception) -> str:
    """What the voice agent is told about a failed tool call."""
    if isinstance(error, AppError) and error.ai_message is not None:
        return error.ai_message
    return text("messages.generic_error")


# Declared on every router, so the OpenAPI schema (and with it the generated frontend types)
# knows that every error body is an ErrorResponse.
ERROR_RESPONSES: dict[int | str, dict] = {
    400: {"model": ErrorResponse, "description": "Refused; `detail` says why in plain German."},
    401: {"model": ErrorResponse, "description": "Not logged in, or the session ended."},
    403: {"model": ErrorResponse, "description": "Logged in, but with the other role."},
    404: {"model": ErrorResponse, "description": "Does not exist, or belongs to someone else."},
    409: {"model": ErrorResponse, "description": "Conflicts with what is stored."},
    422: {"model": ErrorResponse, "description": "The input did not pass validation."},
    500: {"model": ErrorResponse, "description": "Unexpected error."},
    502: {"model": ErrorResponse, "description": "An outside service (OpenAI) failed."},
}


def error_response(user_message: str, status_code: int) -> JSONResponse:
    return JSONResponse(ErrorResponse(detail=user_message).model_dump(), status_code=status_code)


async def handle_app_error(request: Request, error: AppError) -> JSONResponse:
    logger.info("event=request_refused status=%d method=%s path=%s %s",
                error.status_code, request.method, request.url.path, error.log_message)
    return error_response(error.user_message, error.status_code)


async def handle_invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
    # Only the names of the invalid fields: the errors themselves repeat the input.
    fields = sorted({".".join(map(str, e["loc"][1:])) or str(e["loc"][0]) for e in error.errors()})
    logger.info("event=invalid_request method=%s path=%s fields=%s",
                request.method, request.url.path, ",".join(fields))
    return error_response(INVALID_INPUT, 422)


class CatchUnexpectedErrors:
    """Answers every exception that escaped the routes and handlers with the generic message."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            response_started = response_started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as error:
            logger.error("event=unexpected_error method=%s path=%s type=%s",
                         scope["method"], scope["path"], type(error).__name__)
            # Once a response has started, a second one cannot be sent; the server then closes the
            # connection of the incomplete response.
            if not response_started:
                await error_response(UNEXPECTED, 500)(scope, receive, send)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_invalid_request)
    app.add_middleware(CatchUnexpectedErrors)  # added last, so it is the outermost middleware
