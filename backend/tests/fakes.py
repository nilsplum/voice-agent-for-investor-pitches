"""The fake outside world of the backend tests: OpenAI's Live API (creating a session and its
sideband), its Responses API (the writing down and the review) and Serper, in one small Starlette app that uvicorn
serves on a free local port in the tests' own event loop.

Tests point the config's URLs at it (the `fake` fixture in conftest.py) and script it directly:
queue structured answers and search results, push events into a session's sideband, drop a sideband, and read
the commands the backend sent. The backend has no test hooks; it only sees different URLs.

- A session answers `session.close` with `session.closed` (unless `answer_close` is off) and records
  the commands of every attach, including the short second attach that only closes.
- Like the real note-taker, a session answers a `response.create` that follows a tool's output with
  the note-taker's next response, its reply: `response.created`, then `response.completed`, in the
  delegation of that tool call. Any other `response.create` (the opening's startup lookup, the
  guard's reminder) gets no answer: the real note-taker would call a tool first, so a test scripts
  that itself.
- A structured call or search request with nothing queued is recorded in `problems`, and the `fake`
  fixture fails the test with it, so no test passes by accident on an unplanned call.
"""

import asyncio
import json
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

TIMEOUT = "timeout"  # queued as a structured answer: the fake answers only after the backend gave up
SUMMARY = "Nordlicht baut Roboter für Lager."


def written_down(answers: dict[int, str] | None = None, summary: str = SUMMARY, stop: bool = False) -> dict:
    """An answer of the writing down (app/ai/writer.py) to queue; by default every question of the
    default catalog is answered."""
    answers = {question_id: f"Antwort {question_id}" for question_id in range(1, 12)} if answers is None else answers
    return {"answers": [{"question_id": question_id, "text": said} for question_id, said in answers.items()],
            "summary": summary, "founder_wants_to_stop": stop}


def transcript_event(speaker: str, delta: str, start_ms: int, end_ms: int) -> dict:
    kind = "session.input_transcript.delta" if speaker == "founder" else "session.output_transcript.delta"
    return {"type": kind, "delta": delta, "start_ms": start_ms, "end_ms": end_ms}


def function_call_event(name: str, arguments: Any, call_id: str, delegation_id: str = "delegation_test") -> dict:
    """A finished function call of the note-taker, wrapped as the Live API delivers it."""
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {"type": "response.event", "delegation_id": delegation_id, "event": {
        "type": "response.output_item.done",
        "item": {"type": "function_call", "call_id": call_id, "name": name, "arguments": raw}}}


class FakeSession:
    """One Live session: its create body, its sideband connections and the commands they carried."""

    def __init__(self, session_id: str, body: dict):
        self.id = session_id
        self.body = body
        self.sockets: list[WebSocket] = []
        self.commands: list[dict] = []
        self.responses = 0  # how many responses of the note-taker have started
        self.delegation = "delegation_test"  # of the last tool call pushed: the reply continues it
        self._taken: set[int] = set()
        self._changed = asyncio.Event()

    @property
    def attaches(self) -> int:
        return len(self.sockets)

    async def send(self, event: dict) -> None:
        """Pushes an event to the backend over the latest sideband connection."""
        if (event.get("event") or {}).get("item", {}).get("type") == "function_call":
            self.delegation = event["delegation_id"]
        await self.sockets[-1].send_json(event)

    async def report(self) -> None:
        """The note-taker's next response (its reply after a tool) starts and finishes."""
        self.responses += 1
        for kind in ("response.created", "response.completed"):
            await self.send({"type": "response.event", "delegation_id": self.delegation,
                             "event": {"type": kind, "response": {"id": f"resp_{self.responses}"}}})

    async def drop(self) -> None:
        """Closes the latest sideband connection abnormally, without session.closed."""
        await self.sockets[-1].close(code=1011)

    def after_tool_output(self) -> bool:
        """Whether the last command was a tool's output, which the next `response.create` resumes."""
        last = self.commands[-1] if self.commands else {}
        return last.get("type") == "response.item.create" and last.get("item", {}).get("type") == "function_call_output"

    def commands_of(self, kind: str) -> list[dict]:
        return [command for command in self.commands if command["type"] == kind]

    async def next_command(self, kind: str, timeout: float = 5) -> dict:
        """The next command of this type that no earlier call returned, waiting for it if needed."""
        async with asyncio.timeout(timeout):
            while True:
                for index, command in enumerate(self.commands):
                    if index not in self._taken and command["type"] == kind:
                        self._taken.add(index)
                        return command
                self._changed.clear()
                await self._changed.wait()

    def record(self, command: dict) -> None:
        self.commands.append(command)
        self._changed.set()


class FakeWorld:
    def __init__(self) -> None:
        self.base = ""  # host:port, set once the server runs
        self.app = Starlette(routes=[
            Route("/v1/live/sessions", self._create_session, methods=["POST"]),
            WebSocketRoute("/v1/live/sessions/{session_id}/attach", self._attach),
            Route("/v1/responses", self._responses, methods=["POST"]),
            Route("/search", self._search, methods=["POST"]),
        ])
        self.reset()

    def reset(self) -> None:
        self.sessions: dict[str, FakeSession] = {}
        self.create_status = 201          # anything else fails the creation
        self.refuse_attach = False        # refuses every attach (also the second, closing one)
        self.answer_close = True          # answers session.close with session.closed
        # The backend's structured calls (the review, the writing down), answered in the order they arrive.
        self.responses: list[Any] = []    # each: the output as a dict, an HTTP status, TIMEOUT, or a raw body
        self.response_requests: list[dict] = []
        self.searches: list[Any] = []     # each: a list of organic results, or an HTTP status
        self.search_requests: list[dict] = []
        self.search_keys: list[str | None] = []
        self.problems: list[str] = []

    def session(self, index: int = -1) -> FakeSession:
        """A created session, the latest by default."""
        return list(self.sessions.values())[index]

    async def _create_session(self, request: Request) -> JSONResponse:
        body = await request.json()
        if self.create_status != 201:
            return JSONResponse({"error": {"type": "server_error"}}, status_code=self.create_status)
        session_id = f"live_test_{len(self.sessions) + 1}"
        self.sessions[session_id] = FakeSession(session_id, body)
        return JSONResponse({"session": {"id": session_id}, "transport": {"type": "webrtc", "sdp": f"answer-{session_id}"}},
                            status_code=201)

    async def _attach(self, websocket: WebSocket) -> None:
        session = self.sessions.get(websocket.path_params["session_id"])
        if session is None or self.refuse_attach:
            await websocket.close(code=1008)  # before accept: the handshake is refused
            return
        await websocket.accept()
        session.sockets.append(websocket)
        try:
            while True:
                command = await websocket.receive_json()
                if command["type"] == "response.create" and session.after_tool_output():
                    await session.report()  # before the test sees the command, like the real order
                session.record(command)
                if command["type"] == "session.close" and self.answer_close:
                    await websocket.send_json({"type": "session.closed", "reason": "close_requested"})
                    await websocket.close()
                    return
        except (WebSocketDisconnect, RuntimeError):  # the backend or the test closed the connection
            return

    async def _responses(self, request: Request) -> JSONResponse:
        self.response_requests.append(await request.json())
        if not self.responses:
            self.problems.append("a structured call with no answer queued")
            return JSONResponse({}, status_code=500)
        answer = self.responses.pop(0)
        if answer == TIMEOUT:
            await asyncio.sleep(2)
            return JSONResponse({}, status_code=504)
        if isinstance(answer, int):
            return JSONResponse({"error": {"type": "server_error"}}, status_code=answer)
        if "output" in answer:  # a raw body
            return JSONResponse(answer)
        return JSONResponse({"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]}]})

    async def _search(self, request: Request) -> JSONResponse:
        self.search_requests.append(await request.json())
        self.search_keys.append(request.headers.get("x-api-key"))
        if not self.searches:
            self.problems.append("a search request with no result queued")
            return JSONResponse({}, status_code=500)
        answer = self.searches.pop(0)
        if isinstance(answer, int):
            return JSONResponse({"message": "error"}, status_code=answer)
        return JSONResponse({"searchParameters": {}, "organic": answer})
