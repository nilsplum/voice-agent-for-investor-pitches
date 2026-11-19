"""Shared fixtures of the backend tests: a real PostgreSQL test database, test secrets, the fake
outside world (tests/fakes.py), the app running in-process, and helpers that act as the team, as a
founder, and as a founder in a running call.

The tests run in the backend container (./scripts/test.sh) against the app's database server, in
their own database `app_test`. It is dropped, recreated and migrated with Alembic at the start of
every test session, so the migrations are always tested from scratch, and every table is emptied
before each test. The developer's secrets file is never read: the `secrets` fixture replaces the
loader before the app is built. Every app runs against the fake outside world, whose server runs
in the session's event loop; tests marked `real` call the real OpenAI and Serper APIs instead and
run only with `--complete`.
"""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import create_engine, select, text

from app import config, db
from app.ai import live
from app.main import create_app
from app.models import Base, Conversation, TranscriptMessageRow
from app.schemas import Questionnaire
from fakes import FakeSession, FakeWorld, function_call_event, transcript_event

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DATABASE = "app_test"
TEST_SECRETS = config.Secrets(openai_api_key="sk-test", serper_api_key="serper-test",
                              session_secret="test-session-secret", team_email="team@example.com",
                              team_password="team-password")
FOUNDER = {"name": "Erika Muster", "email": "erika@example.com", "password": "founder-password",
           "company_name": "Nordlicht Robotics"}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--complete", action="store_true",
                     help="also run the tests against the real OpenAI and Serper APIs (marker `real`)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--complete"):
        return
    skip = pytest.mark.skip(reason="calls the real APIs: run ./scripts/test.sh --complete")
    for item in items:
        if "real" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    """Points the config at a fresh, migrated test database for the whole session."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(config, "DATABASE_NAME", TEST_DATABASE)
        server = create_engine(config.database_url("postgres"), isolation_level="AUTOCOMMIT")
        with server.connect() as connection:
            connection.execute(text(f"DROP DATABASE IF EXISTS {TEST_DATABASE} WITH (FORCE)"))
            connection.execute(text(f"CREATE DATABASE {TEST_DATABASE}"))
        server.dispose()
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
        db.get_engine.cache_clear()
        yield
        db.get_engine().dispose()
        db.get_engine.cache_clear()


@pytest.fixture(autouse=True)
def empty_tables() -> None:
    with db.session_scope() as session:
        session.execute(text(f"TRUNCATE {', '.join(t.name for t in Base.metadata.sorted_tables)} CASCADE"))


@pytest.fixture
def secrets(monkeypatch: pytest.MonkeyPatch) -> config.Secrets:
    monkeypatch.setattr(config, "secrets", lambda: TEST_SECRETS)
    return TEST_SECRETS


@pytest.fixture(scope="session")
async def fake_server() -> AsyncIterator[FakeWorld]:
    """The fake outside world, served once for the whole session on a free local port."""
    world = FakeWorld()
    server = uvicorn.Server(uvicorn.Config(world.app, host="127.0.0.1", port=0, lifespan="off", log_config=None,
                                           access_log=False))
    serving = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    world.base = "127.0.0.1:%d" % server.servers[0].sockets[0].getsockname()[1]
    yield world
    server.should_exit = True
    await serving


@pytest.fixture
def fake(fake_server: FakeWorld, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeWorld]:
    """Points OpenAI and Serper at the fake world, emptied for this test, and shortens the waits a
    test would otherwise sit through. Fails the test if the fake got a request it had nothing for."""
    fake_server.reset()
    monkeypatch.setattr(config, "OPENAI_API_URL", f"http://{fake_server.base}/v1")
    monkeypatch.setattr(config, "OPENAI_WS_URL", f"ws://{fake_server.base}/v1")
    monkeypatch.setattr(config, "SERPER_URL", f"http://{fake_server.base}/search")
    monkeypatch.setattr(config, "STRUCTURED_CALL_RETRY_DELAY_S", 0.01)
    monkeypatch.setattr(config, "GOODBYE_SILENCE_S", 0.2)
    monkeypatch.setattr(config, "GOODBYE_MAX_WAIT_S", 3)
    yield fake_server
    assert fake_server.problems == []


@pytest.fixture
async def app(secrets: config.Secrets, fake: FakeWorld) -> AsyncIterator[FastAPI]:
    """The app, built after the test secrets are in place, with its lifespan running. Its shutdown
    must end every call it started."""
    app = create_app()
    async with LifespanManager(app):
        yield app
    assert live.CALLS == {}


@pytest.fixture
async def new_client(app: FastAPI) -> AsyncIterator[Callable[[], AsyncClient]]:
    """Makes HTTP clients for the running app; each keeps its own session cookie (one user each)."""
    clients: list[AsyncClient] = []

    def make() -> AsyncClient:
        clients.append(AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver"))
        return clients[-1]

    yield make
    for client in clients:
        await client.aclose()


@pytest.fixture
def client(new_client: Callable[[], AsyncClient]) -> AsyncClient:
    """A client without a login."""
    return new_client()


@pytest.fixture
async def team(new_client: Callable[[], AsyncClient]) -> AsyncClient:
    """A client logged in with the team's login."""
    client = new_client()
    response = await client.post("/api/auth/login", json={"email": TEST_SECRETS.team_email,
                                                          "password": TEST_SECRETS.team_password})
    assert response.status_code == 200
    return client


@pytest.fixture
def create_code(team: AsyncClient) -> Callable[[str], Awaitable[str]]:
    """Creates an access code for an email through the team's API and returns the plain code."""

    async def create(email: str) -> str:
        response = await team.post("/api/team/access-codes", json={"email": email})
        assert response.status_code == 201
        return response.json()["code"]

    return create


@pytest.fixture
def sign_up(create_code: Callable[[str], Awaitable[str]]) -> Callable[..., Awaitable[Response]]:
    """Signs a client up as FOUNDER (fields can be overridden), with a fresh code for its email
    unless a `code` is given."""

    async def sign_up(client: AsyncClient, **overrides: str) -> Response:
        founder = {**FOUNDER, **overrides}
        founder.setdefault("code", await create_code(founder["email"]))
        return await client.post("/api/auth/signup", json=founder)

    return sign_up


@pytest.fixture
async def founder(new_client: Callable[[], AsyncClient], sign_up: Callable[..., Awaitable[Response]]) -> AsyncClient:
    """A client signed up (and so logged in) as FOUNDER, with one Ready conversation."""
    client = new_client()
    response = await sign_up(client)
    assert response.status_code == 200
    return client


# --- A founder in a running call ------------------------------------------------------------
@dataclass
class Call:
    """A founder's running call: the founder's client, the conversation and its fake Live session."""

    client: AsyncClient
    conversation_id: str
    session: FakeSession

    async def say(self, speaker: str, delta: str, start_ms: int, end_ms: int) -> None:
        await self.session.send(transcript_event(speaker, delta, start_ms, end_ms))

    async def call_tool(self, name: str, arguments: Any = None, call_id: str = "call_1") -> str:
        """Sends a function call of the note-taker (no arguments by default, like the submit tools)
        and returns the output the backend sent back once the tool is done."""
        await self.session.send(function_call_event(name, arguments or {}, call_id))
        output = await self.session.next_command("response.item.create")
        await self.session.next_command("response.create")
        assert output["item"]["call_id"] == call_id
        return output["item"]["output"]

    def told(self) -> list[str]:
        """What the backend told the voice agent so far (its commentary), in order."""
        return [command["content"] for command in self.session.commands_of("session.commentary.append")]

    async def end(self, reason: str) -> dict:
        response = await self.client.post(f"/api/my/conversations/{self.conversation_id}/end", json={"reason": reason})
        assert response.status_code == 200
        return response.json()

    def stored(self) -> dict:
        """The conversation's row as stored right now."""
        with db.session_scope() as session:
            row = session.get(Conversation, UUID(self.conversation_id))
            return {column.key: getattr(row, column.key) for column in Conversation.__table__.columns}

    def questionnaire(self) -> Questionnaire:
        return Questionnaire.model_validate(self.stored()["questionnaire"])

    def messages(self) -> list[tuple[str, str]]:
        with db.session_scope() as session:
            rows = session.scalars(select(TranscriptMessageRow)
                                   .where(TranscriptMessageRow.conversation_id == UUID(self.conversation_id))
                                   .order_by(TranscriptMessageRow.id))
            return [(row.speaker, row.text) for row in rows]


@pytest.fixture
def start(founder: AsyncClient, fake: FakeWorld) -> Callable[[], Awaitable[Call]]:
    """Presses START on the founder's newest conversation; the call is running when it returns."""

    async def start_call() -> Call:
        conversation_id = (await founder.get("/api/my/conversations")).json()[0]["id"]
        response = await founder.post(f"/api/my/conversations/{conversation_id}/start", json={"sdp": "offer-sdp"})
        assert response.status_code == 200, response.json()
        return Call(founder, conversation_id, fake.session())

    return start_call


async def eventually(check: Callable[[], bool], timeout: float = 3) -> None:
    """Waits until `check()` holds: for effects the backend applies on its own task."""
    async with asyncio.timeout(timeout):
        while not check():
            await asyncio.sleep(0.02)
