"""Commands the developer scripts run in the backend container: `python -m app.cli <command>`.

The scripts never parse the secrets file themselves. Everything that needs its values asks these
commands (through `backend_cli` in scripts/helpers/common.sh), so the config module stays the
file's only reader. Each command exits with 0 when everything is fine, or with 1 and an English
explanation for developers on stderr. No output contains a secret, with two deliberate exceptions
that print one on stdout for `./scripts/test.sh --complete` to capture in a variable (never a file):
`create-access-code` (a new access code, as the team area would show it once) and
`print-openai-key` (for the voice test's text-to-speech).

Synchronous on purpose: these are one-shot commands, not the server; `create-access-code` uses the
app's own database step.
"""

import argparse
import json
import sys
from collections.abc import Callable

import httpx
from pydantic import ValidationError

from app import config
from app.schemas import AccessCodeCreate


def problem(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def check_secrets() -> int:
    """Names every empty value of the secrets file, with the fix from its field description."""
    secrets = config.secrets()
    empty = [name for name in config.Secrets.model_fields if not getattr(secrets, name).strip()]
    for name in empty:
        problem(f"{name} is empty. {config.Secrets.model_fields[name].description}")
    return 1 if empty else 0


def check_internet() -> int:
    """Any HTTP answer from OpenAI's API proves the container is online; the key is not needed."""
    try:
        httpx.get(f"{config.OPENAI_API_URL}/models", timeout=config.KEY_CHECK_TIMEOUT_S)
    except httpx.TransportError:
        return problem("The backend container cannot reach the internet (api.openai.com does not answer). "
                       "Check your connection, VPN or proxy, and Docker's network settings.")
    return 0


def check_key(service: str, field: str, key_url: str, send: Callable[[], httpx.Response]) -> int:
    """One request with the key: tells "unreachable", "key rejected" and other failures apart."""
    try:
        response = send()
    except httpx.TransportError:
        return problem(f"{service} is unreachable from the backend container. "
                       "Check your internet connection, VPN or proxy.")
    if response.status_code in (401, 403):
        return problem(f"{service} rejected {field} (HTTP {response.status_code}). Check the key in "
                       f"secrets/secrets.yaml, or create a new one at {key_url}.")
    if response.is_error:
        return problem(f"{service} answered the key check with HTTP {response.status_code}. "
                       "Try again in a moment; if it persists, check the account (billing, limits).")
    return 0


def check_openai_key() -> int:
    key = config.secrets().openai_api_key
    return check_key("OpenAI", "openai_api_key", "platform.openai.com", lambda: httpx.get(
        f"{config.OPENAI_API_URL}/models", headers={"Authorization": f"Bearer {key}"},
        timeout=config.KEY_CHECK_TIMEOUT_S))


def check_serper_key() -> int:
    key = config.secrets().serper_api_key
    return check_key("Serper", "serper_api_key", "serper.dev", lambda: httpx.post(
        config.SERPER_URL, headers={"X-API-KEY": key}, json={"q": "Venture Capital", "num": 1},
        timeout=config.KEY_CHECK_TIMEOUT_S))


def create_access_code(email: str) -> int:
    """A new access code for an email, through the same step as the team area. Used by the voice test,
    and by developers who want to try the founder's side without the team area."""
    from app.access_codes import create_access_code as create  # here: only this command needs the database
    from app.db import session_scope

    try:
        email = AccessCodeCreate(email=email).email
    except ValidationError:
        return problem(f"{email!r} is not an email address.")
    with session_scope() as session:
        print(create(session, email).code)
    return 0


def print_openai_key() -> int:
    """The OpenAI key, for the voice test's text-to-speech (it plays the founder, not the app)."""
    print(config.secrets().openai_api_key)
    return 0


def openapi() -> int:
    """The OpenAPI schema the frontend types are generated from (scripts/helpers/generate-types.sh)."""
    from app.main import create_app  # here, so the checks above work even when the app cannot be built

    print(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2))
    return 0


COMMANDS: dict[str, Callable[..., int]] = {
    "check-secrets": check_secrets,
    "check-internet": check_internet,
    "check-openai-key": check_openai_key,
    "check-serper-key": check_serper_key,
    "create-access-code": create_access_code,
    "print-openai-key": print_openai_key,
    "openapi": openapi,
}
ARGUMENTS = {"create-access-code": ["email"]}  # every other command takes none


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name, command in COMMANDS.items():
        subparser = commands.add_parser(name, help=(command.__doc__ or "").partition("\n")[0] or None)
        for argument in ARGUMENTS.get(name, []):
            subparser.add_argument(argument)
    arguments = vars(parser.parse_args(argv))
    try:
        return COMMANDS[arguments.pop("command")](**arguments)
    except config.SecretsError as error:
        return problem(str(error))


if __name__ == "__main__":
    sys.exit(main())
