"""The one error type: the browser only ever receives the user message, and neither a response nor
a log line ever contains an input's value or an unexpected exception's text."""

import logging

from app.access_codes import CODE_NOT_FOUND
from app.errors import INVALID_INPUT, UNEXPECTED

MARKER = "SECRET-MARKER-7f3a"  # stands for something a founder said


async def test_an_app_error_returns_only_its_user_message(client, sign_up, caplog):
    caplog.set_level(logging.INFO)

    response = await sign_up(client, code="WRONG234")

    assert (response.status_code, response.json()) == (400, {"detail": CODE_NOT_FOUND})
    assert "reason=access_code_not_found" in caplog.text  # the log message goes to the logs only


async def test_a_validation_error_returns_the_generic_message_and_logs_only_field_names(client, caplog):
    caplog.set_level(logging.INFO)

    response = await client.post("/api/auth/signup", json={
        "name": " ", "email": f"{MARKER} not an email", "password": "x", "company_name": "Firma", "code": "ABCD2345"})

    assert (response.status_code, response.json()) == (422, {"detail": INVALID_INPUT})
    assert "fields=email,name" in caplog.text
    assert MARKER not in caplog.text


async def test_an_unexpected_exception_is_answered_generically_and_its_text_is_never_logged(app, client, caplog):
    caplog.set_level(logging.DEBUG)

    async def explode() -> None:
        raise RuntimeError(f"the founder said {MARKER}")

    app.add_api_route("/api/test-explode", explode)

    response = await client.get("/api/test-explode")

    assert (response.status_code, response.json()) == (500, {"detail": UNEXPECTED})
    assert "event=unexpected_error" in caplog.text and "type=RuntimeError" in caplog.text
    # Every record of every logger (the server's own error log included), with any traceback.
    for record in caplog.records:
        assert MARKER not in record.getMessage()
        assert record.exc_info is None
