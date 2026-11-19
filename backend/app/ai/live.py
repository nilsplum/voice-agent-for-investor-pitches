"""The Live session of a conversation: creating it at START, the sideband that runs it, and ending it.

How a call works:
- START (`start_call`) claims the conversation (Ready -> In progress, with its copies of settings
  and questionnaire), renders the prompts from the context system, creates the Live session at
  OpenAI with the browser's SDP offer, the voice of the language and the note-taker's phase 1
  tools (app/ai/tools.py), and attaches the sideband before the browser connects (the attach replays the last 3
  seconds of events, so nothing from the first moments is missed). If OpenAI fails, the
  conversation goes back to Ready and no call exists.
- The sideband (`run_sideband`, one task per call) sends the opening once the session started
  (see `start_call`), saves the transcript on every speaker change, logs the reply times, runs every
  tool call as its own task (app/ai/tools.py), logs each of the note-taker's responses with its
  duration (the "looking it up" and "writing down" waits), enforces the time limit, and on every
  exit leaves the conversation in its final state. It also guards the note-taker's procedure: a
  request it answers with text alone, without any tool call, gets a reminder (tools.py).
- `end_call` is the one way a call ends, used by the end route, the time limit and the sideband's
  exit. A connection lost before the founder said anything is a failed start (back to Ready); every
  other end goes through `finish_conversation`, where the first write wins. Then `close_session`
  ends the session at OpenAI, which also ends the founder's call.

Constraints:
- The voice model hands work to the note-taker (<|SpawnThinking|>) only in its own replies to the
  founder. The greeting is not such a reply but spoken commentary, so a lookup it announces would
  never start: the backend asks the note-taker for the startup lookup itself, in the opening. Its
  result reaches the voice agent like any search's, as the note-taker's reply (tools.py).
- One backend process: the call registry (`CALLS`) lives in memory, so the backend runs one uvicorn
  worker, and the startup sweep finishes the conversations a restart cut off.
- One call, one owner: whatever ends or cleans up a call acts on that call's own `LiveCall` and
  never looks it up again by conversation ID, and its database writes are conditional on its own
  START. After a failed start, the registry may already hold the next call of the same conversation.
- Everything runs on the event loop; database steps run in worker threads through `run_db`, each in
  its own short session. While waiting, the sideband task holds only its socket, a tool task holds
  nothing (it waits on Serper, the writer or the reviewer), and the goodbye watch waits on the call's `spoke`
  event with timeouts, so nothing polls and nothing holds a database session across a wait.
"""

import asyncio
import json
import logging
from collections.abc import Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote
from uuid import UUID

import httpx
from websockets import ConnectionClosed
from websockets.asyncio.client import ClientConnection, connect

from app import config, http
from app.ai.tools import remind_to_use_tools, run_tool, tool_definitions
from app.ai.transcript import ReplyTimes, TranscriptBuilder
from app.context import prompt, render_faq, render_questionnaire
from app.conversations import claim_start, finish_conversation, revert_start, save_message
from app.db import run_db
from app.errors import AppError
from app.schemas import EndReason, Questionnaire, Settings, Speaker, StartResponse, TranscriptMessage

logger = logging.getLogger(__name__)

START_FAILED = "Das Gespräch konnte nicht starten. Bitte versuchen Sie es erneut."
TRANSCRIPT_EVENTS: dict[str, Speaker] = {
    "session.input_transcript.delta": "founder",
    "session.output_transcript.delta": "agent",
}
# How one of the note-taker's responses can end (the Responses API's final lifecycle events).
RESPONSE_FINISHED = {"response.completed", "response.failed", "response.incomplete", "response.cancelled"}


@dataclass(eq=False)
class LiveCall:
    """The state of one running call, owned by its sideband task."""

    conversation_id: UUID
    started_at: datetime            # the attempt's token: every database write of the call carries it
    session_id: str                 # OpenAI's session ID, opaque
    settings: Settings
    questionnaire: Questionnaire    # the conversation's copy, updated by the store steps of the tools
    opening: list[dict]             # the commands sent once the session started (see start_call)
    socket: ClientConnection        # the sideband
    transcript: TranscriptBuilder = field(default_factory=TranscriptBuilder)
    reply_times: ReplyTimes = field(default_factory=ReplyTimes)
    founder_spoke: bool = False     # a lost connection before this is a failed start
    # How many messages were saved when the follow-up round began: the round is written down from
    # the messages after them.
    round_starts_at: int = 0
    closing: bool = False           # session.close sent, or session.closed received
    ending: bool = False            # the sideband stopped reading and is cleaning up
    spoke: asyncio.Event = field(default_factory=asyncio.Event)  # set by every transcript delta
    agent_spoke_at: float = 0.0     # loop time of the agent's latest transcript delta
    # The note-taker's running responses by ID, with their start time, for the log of their duration.
    running_responses: dict[str, float] = field(default_factory=dict)
    # The delegations (the note-taker's tasks) in which it called a tool. Its procedure answers every
    # request with a tool call first, so a response that ends a delegation without one is a request
    # answered with text alone; `tool_reminders` counts the reminders the guard sent for that.
    delegations_with_tools: set[str] = field(default_factory=set)
    tool_reminders: int = 0
    tasks: set[asyncio.Task] = field(default_factory=set)        # tool calls, reminders and the goodbye watch
    sideband: asyncio.Task | None = None

    async def send(self, event: dict) -> bool:
        """Sends a command over the sideband and logs only its type. False if the sideband dropped."""
        try:
            await self.socket.send(json.dumps(event))
        except ConnectionClosed:
            logger.info("event=send_failed conversation_id=%s type=%s", self.conversation_id, event["type"])
            return False
        logger.info("event=sent conversation_id=%s type=%s", self.conversation_id, event["type"])
        return True

    async def tell(self, content: str) -> None:
        """A backend message to the voice agent: what it says or does next. Commentary, because the
        voice agent speaks it right away, also while the note-taker's request still runs."""
        await self.send({"type": "session.commentary.append", "delegation_id": None, "content": content})

    def start_task(self, work: Coroutine) -> None:
        task = asyncio.create_task(work)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def start_goodbye_watch(self) -> None:
        """Right before the goodbye message goes out: only what the agent says from now on counts."""
        self.start_task(goodbye_watch(self, asyncio.get_running_loop().time()))


CALLS: dict[UUID, LiveCall] = {}  # conversation ID -> its running call


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {config.secrets().openai_api_key}"}


# --- START ----------------------------------------------------------------------------------
async def start_call(founder_id: UUID, conversation_id: UUID, sdp: str) -> StartResponse:
    """Claims the conversation, creates the Live session and attaches the sideband; returns
    OpenAI's SDP answer for the browser. Any failure after the claim puts the conversation back to
    Ready (502), so the access code is not lost."""
    start = await run_db(claim_start, founder_id, conversation_id)
    step = "prepare"
    try:
        settings = start.settings
        language = config.LANGUAGES[settings.language]
        values = {"agent_name": settings.agent_name, "founder_name": start.founder_name,
                  "company_name": start.company_name, "language": language.name}
        kickoff = prompt("voice_kickoff", **values)
        # The opening, sent once the session started (OpenAI's greeting recipe sends the kickoff both
        # here as a developer message and then as commentary): the greeting, as words for the agent
        # to say, and the startup lookup, which the backend asks the note-taker for directly.
        opening = [
            {"type": "session.commentary.append", "delegation_id": None, "content": kickoff},
            {"type": "response.item.create", "item": {"type": "message", "role": "developer", "content": [
                {"type": "input_text", "text": prompt("note_taker_kickoff", **values)}]}},
            {"type": "response.create"},
        ]
        body = {
            "session": {
                "model": config.LIVE_MODEL,
                "instructions": prompt("voice_instructions", **values, faq=render_faq(),
                                       questionnaire=render_questionnaire(start.questionnaire.entries)),
                "input": [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": kickoff}]}],
                # No audio format: WebRTC negotiates it on the media connection.
                "audio": {"output": {"voice": language.voice}},
                "delegation": {"type": "responses", "responses": {
                    "model": settings.note_taker_model,
                    "instructions": prompt("note_taker_instructions", **values),
                    "tools": tool_definitions(1),
                    "tool_choice": "auto",
                    "parallel_tool_calls": False,  # keeps the note-taker's work in a simple order
                    "reasoning": {"effort": settings.note_taker_thinking},
                }},
            },
            "transport": {"type": "webrtc", "sdp": sdp},
        }
        step = "create"
        session_id, answer_sdp = await create_session(body)
        step = "attach"
        socket = await attach(session_id)
    except Exception as error:
        status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
        logger.warning("event=start_failed conversation_id=%s step=%s type=%s status=%s", conversation_id, step,
                       type(error).__name__, status)
        await run_db(revert_start, conversation_id, start.started_at)
        raise AppError(START_FAILED, f"reason=start_failed step={step}", status_code=502) from None
    call = LiveCall(conversation_id=conversation_id, started_at=start.started_at, session_id=session_id,
                    settings=settings, questionnaire=start.questionnaire, opening=opening, socket=socket)
    CALLS[conversation_id] = call
    call.sideband = asyncio.create_task(run_sideband(call))
    logger.info("event=call_started conversation_id=%s session_id=%s", conversation_id, session_id)
    return StartResponse(sdp=answer_sdp, agent_name=settings.agent_name)


async def create_session(body: dict) -> tuple[str, str]:
    """`POST /live/sessions` with the browser's offer; returns the session ID and the SDP answer."""
    response = await http.client().post(f"{config.OPENAI_API_URL}/live/sessions", headers=_auth(), json=body,
                                        timeout=config.LIVE_CREATE_TIMEOUT_S)
    response.raise_for_status()
    created = response.json()
    return created["session"]["id"], created["transport"]["sdp"]


async def attach(session_id: str) -> ClientConnection:
    """Opens a sideband connection to a running session: at START, and for a last session.close."""
    return await connect(f"{config.OPENAI_WS_URL}/live/sessions/{quote(session_id, safe='')}/attach",
                         additional_headers=_auth(), open_timeout=config.SIDEBAND_ATTACH_TIMEOUT_S,
                         max_size=None, compression=None)


# --- The sideband -----------------------------------------------------------------------------
async def run_sideband(call: LiveCall) -> None:
    """Reads the call's events until the session closes, the socket drops or the time limit is
    reached; every exit ends the call (`finally`). Never resumes reading after a drop."""
    limit = asyncio.timeout(config.CONVERSATION_TIME_LIMIT_S)
    try:
        try:
            async with limit:
                await _read_events(call)
        except TimeoutError:
            if not limit.expired():
                raise
            logger.info("event=time_limit conversation_id=%s", call.conversation_id)
            await end_call(call.conversation_id, "time_limit", call)
    except ConnectionClosed:
        logger.info("event=sideband_dropped conversation_id=%s", call.conversation_id)
    except Exception as error:
        logger.error("event=sideband_failed conversation_id=%s type=%s", call.conversation_id, type(error).__name__)
    finally:
        call.ending = True
        await _clean_up(call)


async def _read_events(call: LiveCall) -> None:
    async for raw in call.socket:
        if await handle_event(call, json.loads(raw)):
            return
    logger.info("event=sideband_dropped conversation_id=%s", call.conversation_id)


async def handle_event(call: LiveCall, event: dict) -> bool:
    """Handles one event of the sideband; True once the session has closed."""
    kind = event.get("type")
    if kind in TRANSCRIPT_EVENTS:
        await _on_transcript(call, TRANSCRIPT_EVENTS[kind], event)
    elif kind == "response.event":
        _on_note_taker(call, event)
    elif kind == "session.delegation.created":
        # The voice agent handed work over (<|SpawnThinking|>), or the opening asked for the lookup.
        delegation = event.get("delegation") or {}
        logger.info("event=delegation_created conversation_id=%s delegation_id=%s target=%s", call.conversation_id,
                    event.get("delegation_id") or delegation.get("id"), event.get("target") or delegation.get("target"))
    elif kind == "session.started":
        for command in call.opening:
            await call.send(command)
    elif kind == "error":
        error = event.get("error") or {}
        logger.warning("event=openai_error conversation_id=%s type=%s code=%s", call.conversation_id,
                       error.get("type"), error.get("code"))
    elif kind == "session.closed":
        call.closing = True
        logger.info("event=session_closed conversation_id=%s reason=%s", call.conversation_id, event.get("reason"))
        return True
    return False


def _on_note_taker(call: LiveCall, event: dict) -> None:
    """The note-taker's events, which arrive wrapped with their delegation. A finished function call
    is a tool call, run as its own task. The start and end of each response are logged with IDs,
    kind and duration only, never its text, which repeats what the founder said. A response that
    completes a delegation without any tool call breaks the note-taker's procedure (its text then
    reached the voice agent instead of a tool's result), so the guard reminds it."""
    nested = event.get("event") or {}
    kind = nested.get("type")
    item = nested.get("item") or {}
    response_id = (nested.get("response") or {}).get("id")
    delegation_id = event.get("delegation_id")
    now = asyncio.get_running_loop().time()
    if kind == "response.output_item.done" and item.get("type") == "function_call":
        if delegation_id:
            call.delegations_with_tools.add(delegation_id)
        call.start_task(run_tool(call, item))
    elif kind == "response.output_item.done" and item.get("type") == "message":
        logger.info("event=note_taker_reported conversation_id=%s delegation_id=%s", call.conversation_id,
                    event.get("delegation_id"))
    elif kind == "response.created" and response_id:
        call.running_responses[response_id] = now
        logger.info("event=note_taker_started conversation_id=%s delegation_id=%s response_id=%s",
                    call.conversation_id, event.get("delegation_id"), response_id)
    elif kind in RESPONSE_FINISHED and response_id:
        started = call.running_responses.pop(response_id, now)
        logger.info("event=note_taker_finished conversation_id=%s delegation_id=%s response_id=%s outcome=%s "
                    "duration_ms=%d", call.conversation_id, event.get("delegation_id"), response_id,
                    kind.removeprefix("response."), (now - started) * 1000)
        if kind == "response.completed" and delegation_id and delegation_id not in call.delegations_with_tools:
            call.start_task(remind_to_use_tools(call, delegation_id))


async def _on_transcript(call: LiveCall, speaker: Speaker, event: dict) -> None:
    delta = event.get("delta") or ""
    start_ms, end_ms = int(event.get("start_ms") or 0), int(event.get("end_ms") or 0)
    if speaker == "founder" and delta.strip():
        call.founder_spoke = True
    if speaker == "agent":
        call.agent_spoke_at = asyncio.get_running_loop().time()
    finished = call.transcript.add(speaker, delta, start_ms, end_ms)
    call.spoke.set()
    if finished is None:
        return
    await _save(call, finished)
    if finished.speaker == "founder":  # the agent starts answering now
        if (reply_ms := call.reply_times.record(finished.end_ms, start_ms)) is not None:
            logger.info("event=reply_time conversation_id=%s reply_ms=%d", call.conversation_id, reply_ms)


async def _save(call: LiveCall, message: TranscriptMessage) -> None:
    """A failed save loses one message but never ends the conversation."""
    try:
        await run_db(save_message, call.conversation_id, call.started_at, message)
    except Exception as error:
        logger.error("event=save_failed conversation_id=%s type=%s", call.conversation_id, type(error).__name__)


async def _clean_up(call: LiveCall) -> None:
    """Every exit of the sideband: save the message in progress, end the call (it changes nothing if
    the conversation already has its final state, and closes the session if that has not happened
    yet), stop the call's tasks and log its reply times."""
    if message := call.transcript.flush():
        await _save(call, message)
    try:
        await end_call(call.conversation_id, "connection_lost", call)
    except Exception as error:
        logger.error("event=end_failed conversation_id=%s type=%s", call.conversation_id, type(error).__name__)
    for task in list(call.tasks):
        task.cancel()
    count, median_ms, max_ms = call.reply_times.summary()
    logger.info("event=reply_times conversation_id=%s count=%d median_ms=%d max_ms=%d target_ms=%d",
                call.conversation_id, count, median_ms, max_ms, config.REPLY_TIME_TARGET_MS)
    if CALLS.get(call.conversation_id) is call:
        del CALLS[call.conversation_id]
    await call.socket.close()
    logger.info("event=call_ended conversation_id=%s", call.conversation_id)


# --- Ending -----------------------------------------------------------------------------------
async def end_call(conversation_id: UUID, reason: EndReason, call: LiveCall | None) -> None:
    """The one way a call ends. The database is written first, then the session closed, so the
    stored state never lags behind what the founder sees."""
    if call is not None and reason == "connection_lost" and not call.founder_spoke:
        await run_db(revert_start, conversation_id, call.started_at)
    else:
        await run_db(finish_conversation, conversation_id, reason, call.started_at if call else None)
    if call is not None:
        await close_session(call)


async def end_reported(conversation_id: UUID, reason: EndReason) -> None:
    """The browser reported the end of its call: end it, then wait (bounded, without cancelling)
    until its cleanup has saved the last message, so the view the route returns is complete and no
    old call is still cleaning up when the founder presses START again."""
    call = CALLS.get(conversation_id)
    await end_call(conversation_id, reason, call)
    if call is not None and call.sideband is not None:
        await asyncio.wait({call.sideband}, timeout=config.END_WAIT_S)


async def close_session(call: LiveCall) -> None:
    """The one place that ends a session at OpenAI, which also ends the founder's call. Calling it
    twice is harmless."""
    if call.closing:
        return
    call.closing = True
    if await call.send({"type": "session.close"}):
        return
    # The sideband dropped without session.closed. Attach once more, only to send session.close,
    # so the founder does not keep talking to an agent whose tools no longer work.
    try:
        socket = await attach(call.session_id)
        try:
            await socket.send(json.dumps({"type": "session.close"}))
        finally:
            await socket.close()
        logger.info("event=closed_by_second_attach conversation_id=%s", call.conversation_id)
    except Exception as error:
        # The database is already correct; the founder sees the outcome when they press STOPP.
        logger.warning("event=close_failed conversation_id=%s type=%s", call.conversation_id, type(error).__name__)


async def goodbye_watch(call: LiveCall, sent_at: float) -> None:
    """After the completion: closes the session once the agent has said goodbye, at the latest after
    GOODBYE_MAX_WAIT_S. Started by the tool that completed the conversation, as it sends the goodbye
    message (`sent_at`).

    It closes once the agent has spoken after that moment and then nobody (agent or founder) spoke
    for GOODBYE_SILENCE_S. What the agent said before (its handover, "one moment, I'm writing
    everything down") never counts as the goodbye. Counting the founder too means a founder who
    still says something after the goodbye is never cut off. It waits on the call's events with
    timeouts, so nothing polls."""
    loop = asyncio.get_running_loop()
    try:
        try:
            async with asyncio.timeout(config.GOODBYE_MAX_WAIT_S):
                # Speech counts by its time, so a delta handled before this task resumed counts too.
                while True:
                    call.spoke.clear()
                    try:
                        async with asyncio.timeout(config.GOODBYE_SILENCE_S):
                            await call.spoke.wait()
                    except TimeoutError:
                        if call.agent_spoke_at > sent_at:
                            break
        except TimeoutError:
            pass  # the cap: close anyway
        logger.info("event=goodbye_close conversation_id=%s waited_ms=%d", call.conversation_id,
                    (loop.time() - sent_at) * 1000)
        await close_session(call)
    except Exception as error:
        logger.error("event=goodbye_watch_failed conversation_id=%s type=%s", call.conversation_id, type(error).__name__)


async def end_all_calls() -> None:
    """Shutdown (also the restarts of `--reload`): every call ends through its sideband's cleanup,
    so its conversation gets its final state and the founder's call is closed. A call that is
    already cleaning up is only waited for: cancelling it again would cut its cleanup short."""
    calls = [call for call in CALLS.values() if call.sideband is not None]
    for call in calls:
        if not call.ending:
            call.sideband.cancel()
    await asyncio.gather(*(call.sideband for call in calls), return_exceptions=True)
