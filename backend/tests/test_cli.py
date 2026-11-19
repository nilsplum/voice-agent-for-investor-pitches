"""The commands the scripts run: the secrets template and the `Secrets` model cannot drift apart,
`check-secrets` names what is missing, the key checks tell their failures apart, no check's output
ever contains a secret, and the voice test's two commands print exactly the code or key it needs.

These tests use the real secrets loader on temporary files; the developer's file is never read.
"""

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app import cli, config
from app.db import session_scope
from app.models import AccessCode
from app.security import hash_access_code

TEMPLATE = config.SECRETS_PATH.with_name("secrets.example.yaml")  # ./secrets is mounted in the container
COMPLETE = {"openai_api_key": "sk-SECRET-1", "serper_api_key": "SECRET-2", "session_secret": "SECRET-3",
            "team_email": "team@example.com", "team_password": "SECRET-4"}


@pytest.fixture
def secrets_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    path = tmp_path / "secrets.yaml"
    monkeypatch.setattr(config, "SECRETS_PATH", path)
    config.secrets.cache_clear()
    yield path
    config.secrets.cache_clear()


def write(path: Path, values: dict[str, str]) -> None:
    path.write_text("".join(f'{key}: "{value}"\n' for key, value in values.items()))


def test_the_template_plus_a_session_secret_parses_as_secrets(secrets_file):
    # Exactly what setup.sh writes: the template, then a generated session_secret line.
    secrets_file.write_text(TEMPLATE.read_text() + 'session_secret: "generated"\n')

    secrets = config.secrets()

    assert secrets.session_secret == "generated"
    assert {name for name in config.Secrets.model_fields if not getattr(secrets, name)} == {
        "openai_api_key", "serper_api_key", "team_email", "team_password"}


def test_check_secrets_names_each_empty_value_with_its_fix(secrets_file, capsys):
    write(secrets_file, {**COMPLETE, "serper_api_key": "", "team_password": " "})

    assert cli.main(["check-secrets"]) == 1

    output = capsys.readouterr().err
    assert "serper_api_key is empty. Create a key at serper.dev" in output
    assert "team_password is empty." in output
    assert "openai_api_key" not in output and "SECRET" not in output


def test_check_secrets_passes_silently_when_complete(secrets_file, capsys):
    write(secrets_file, COMPLETE)

    assert cli.main(["check-secrets"]) == 0
    assert capsys.readouterr() == ("", "")


def test_a_broken_file_is_described_without_its_values(secrets_file, capsys):
    secrets_file.write_text('openai_api_key: 1234567\nunknown_key: "SECRET-5"\n')

    assert cli.main(["check-secrets"]) == 1

    output = capsys.readouterr().err
    assert "wrong shape" in output and "unknown_key" in output and "serper_api_key" in output
    assert "1234567" not in output and "SECRET" not in output


def test_a_missing_file_points_to_the_setup(secrets_file, capsys):
    assert cli.main(["check-secrets"]) == 1
    assert "Run ./scripts/setup.sh first." in capsys.readouterr().err


@pytest.mark.parametrize(("answer", "exit_code", "message"), [
    (httpx.Response(200), 0, ""),
    (httpx.ConnectError("no route"), 1, "OpenAI is unreachable"),
    (httpx.Response(401), 1, "OpenAI rejected openai_api_key (HTTP 401)"),
    (httpx.Response(429), 1, "OpenAI answered the key check with HTTP 429"),
])
def test_the_key_check_tells_unreachable_rejected_and_other_failures_apart(
        secrets_file, monkeypatch, capsys, answer, exit_code, message):
    write(secrets_file, COMPLETE)

    def answer_request(*args, **kwargs) -> httpx.Response:
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(httpx, "get", answer_request)

    assert cli.main(["check-openai-key"]) == exit_code
    output = capsys.readouterr().err
    assert message in output and "SECRET" not in output


def test_create_access_code_prints_a_new_code_for_the_email(capsys):
    assert cli.main(["create-access-code", " Erika@Example.com "]) == 0

    code = capsys.readouterr().out.strip()
    with session_scope() as session:
        stored = session.execute(select(AccessCode.email, AccessCode.code_hash, AccessCode.used_at)).one()
    assert tuple(stored) == ("erika@example.com", hash_access_code(code), None)


def test_create_access_code_refuses_what_is_not_an_email(capsys):
    assert cli.main(["create-access-code", "erika"]) == 1
    assert "'erika' is not an email address." in capsys.readouterr().err


def test_print_openai_key_prints_only_the_key(secrets_file, capsys):
    write(secrets_file, COMPLETE)

    assert cli.main(["print-openai-key"]) == 0
    assert capsys.readouterr().out == "sk-SECRET-1\n"
