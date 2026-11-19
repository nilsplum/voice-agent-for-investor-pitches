"""The note-taker's tools: their definitions, their handlers, and the guard of the note-taker's procedure.

The note-taker (the text model attached to the Live session through Responses delegation) is the
only AI that calls tools, and it only triggers them: the backend does the work.
- Phase 1 offers `web_search` and `submit_initial`; phase 2, the follow-up round, `web_search` and
  `submit_follow_up`. `submit_initial` swaps the set with `session.update`, so the note-taker can only
  call the write tool of its phase, and the browser sees the round begin. The tools are the same for
  every conversation: the submit tools take no input, because the backend writes the answers from
  the saved transcript (app/ai/writer.py).
- Every tool's arguments are a Pydantic model (`argument_model`): its JSON schema is the tool's
  strict `parameters`, and the same model parses the call, so schema and parser cannot disagree.
- Every tool's output tells the note-taker what to reply, and that reply always reaches the voice
  agent as the result of the hand-over: the API delivers it, and the browser needs it to end the
  tool's status. So there are two kinds of output:
  - Writing down drives the conversation, so the backend tells the voice agent every result and
    next step itself (`LiveCall.tell`): the summary, the missing questions, the follow-up round, the
    goodbye, the AI message of what failed. The note-taker gets `tool_done` and replies only „OK",
    so its own words never carry a script, a summary or a question.
  - A search's result is the reply itself: the output carries the results (or that nothing was
    found, or that the search failed), and the note-taker passes them on as plain information. The
    same holds for the startup lookup, which the backend's kickoff asks for when the session starts
    (the voice agent hands work over only in reply to the founder): its reply reaches the voice
    agent while it greets, where a bare „OK" made it say „OK" and greet twice, while background
    about the company fits into the greeting.
- `remind_to_use_tools` is the guard of the note-taker's procedure (every request is done with a
  tool call). The sideband calls it when a request ended with text alone, which then reached the
  voice agent as if it were a result. The OpenAI API can neither force a tool call per response nor
  cancel that text, so the guard tells the voice agent to ignore it and has the note-taker do the
  request with its tool, at most `TOOL_REMINDERS_PER_CALL` times per call.

Each tool call runs as its own task of the call (LiveCall.tasks) on the event loop, so the sideband
keeps saving the transcript while, for example, the writing down or the review runs. Database steps
run in worker threads through `run_db`, each in its own short session; Serper, the writer and the
reviewer are awaited while holding no database session.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from app import config, conversations
from app.ai.reviewer import review
from app.ai.writer import write_down
from app.context import context, render_follow_ups, render_question_references, render_search_results, text
from app.db import run_db
from app.errors import AppError, message_for_ai
from app.schemas import QuestionnaireEntry, ToolName, TranscriptMessage, WrittenDown
from app.search import search

if TYPE_CHECKING:
    from app.ai.live import LiveCall

logger = logging.getLogger(__name__)

PHASE_TOOLS: dict[int, tuple[ToolName, ...]] = {
    1: ("web_search", "submit_initial"),
    2: ("web_search", "submit_follow_up"),
}


def argument_model(name: ToolName) -> type[BaseModel]:
    """The arguments of a tool, described by the context system: every field a required string and
    no other field allowed, as OpenAI's strict function calling requires."""
    fields = context().tools.tools[name].fields
    return create_model(name, __config__=ConfigDict(extra="forbid"),
                        **{field: (str, Field(description=description)) for field, description in fields.items()})


def tool_definitions(phase: int) -> list[dict]:
    """The tools of a phase as the Live session's delegation offers them to the note-taker."""
    tools = context().tools.tools
    return [{"type": "function", "name": name, "description": tools[name].description, "strict": True,
             "parameters": argument_model(name).model_json_schema()} for name in PHASE_TOOLS[phase]]


class Result(NamedTuple):
    """What a tool did: its outcome (and details) for the log line, and its output for the
    note-taker, which says what it replies; None stands for `tool_done` („OK")."""

    outcome: str
    output: str | None = None
    details: str = ""


# --- Handlers ---------------------------------------------------------------------------------
async def web_search(call: "LiveCall", arguments: Any) -> Result:
    """The startup lookup and a founder's question alike: the results go back to the note-taker,
    whose reply is the voice agent's result. Nothing found and a failed search go back the same way,
    so that reply is never a bare „OK" (see above)."""
    try:
        results = await search(arguments.query, call.settings.language)
    except AppError as error:
        return Result("unavailable", message_for_ai(error), error.log_message)
    if not results:
        return Result("empty", text("messages.search_empty"))
    return Result("results", text("messages.search_results", results=render_search_results(results)))


async def submit_initial(call: "LiveCall", arguments: Any) -> Result:
    """Writes the answers down from the saved transcript. Then exactly one of: the missing questions
    to ask (nothing is stored); the early end (stored as it is, no review, the goodbye); or stored,
    the summary read aloud while the review runs, then the follow-up round or the goodbye. The
    transcript is read once, for the writing down and the review."""
    # The founder's last answer is saved already: the agent's handover ("I'm writing everything
    # down") started a new message, and a speaker change saves the finished one.
    transcript = await run_db(conversations.read_transcript, call.conversation_id)
    written = await _written_down(call, transcript, follow_up_round=False)
    answers = {answer.question_id: answer.text for answer in written.answers}
    stop = written.founder_wants_to_stop
    if not stop:
        _refuse_missing([entry for entry in call.questionnaire.entries if not answers[entry.id]])
    stored = await run_db(conversations.store_initial, call.conversation_id, call.started_at, answers,
                          written.summary, stop)
    if stored is None:
        # An earlier call wrote everything down and tells the voice agent what comes next.
        return Result("already_written_down")
    call.questionnaire = stored
    if stop:
        await _say_goodbye(call)
        return Result("stopped")
    await call.tell(text("messages.summary", summary=written.summary))
    follow_ups, reviewed = await review(call.questionnaire, transcript, call.settings)
    call.questionnaire = await run_db(conversations.store_review, call.conversation_id, call.started_at, follow_ups,
                                      reviewed)
    if not follow_ups:
        await _say_goodbye(call)
        return Result("completed")
    call.round_starts_at = len(transcript)
    await call.send({"type": "session.update", "session": {"delegation": {
        "type": "responses", "responses": {"tools": tool_definitions(2)}}}})
    await call.tell(text("messages.follow_up_round", follow_ups=render_follow_ups(call.questionnaire.entries)))
    return Result("follow_up_round")


async def submit_follow_up(call: "LiveCall", arguments: Any) -> Result:
    """Writes the follow-up round down from the transcript since it began, so what the founder said
    in the round lands in the round and never repeats the first answers. Then the missing follow-ups
    to ask (nothing is stored), or the round's answers and the final summary stored, the
    conversation complete and the goodbye; when the founder wants to stop, what is there is stored."""
    transcript = await run_db(conversations.read_transcript, call.conversation_id)
    written = await _written_down(call, transcript[call.round_starts_at:], follow_up_round=True)
    answers = {answer.question_id: answer.text for answer in written.answers}
    if not written.founder_wants_to_stop:
        _refuse_missing([entry for entry in call.questionnaire.entries if entry.follow_up and not answers[entry.id]])
    call.questionnaire = await run_db(conversations.store_follow_up_answers, call.conversation_id, call.started_at,
                                      answers, written.summary)
    await _say_goodbye(call)
    return Result("stopped" if written.founder_wants_to_stop else "completed")


async def _written_down(call: "LiveCall", transcript: list[TranscriptMessage], follow_up_round: bool) -> WrittenDown:
    written = await write_down(call.questionnaire, transcript, call.settings, follow_up_round)
    if written is None:
        raise AppError.for_ai("reason=write_down_failed", text("messages.write_down_failed"))
    return written


def _refuse_missing(missing: list[QuestionnaireEntry]) -> None:
    """Nothing is stored while a question the founder must answer has no answer: the voice agent
    asks the missing ones and writes everything down again."""
    if missing:
        raise AppError.for_ai(f"reason=missing_answers count={len(missing)}",
                              text("messages.missing_answers", questions=render_question_references(missing)))


async def _say_goodbye(call: "LiveCall") -> None:
    """The conversation is complete: the voice agent says goodbye, and the watch, started as the
    message goes out, closes the session once it has."""
    call.start_goodbye_watch()
    await call.tell(text("messages.goodbye"))


HANDLERS: dict[ToolName, Callable[["LiveCall", Any], Awaitable[Result]]] = {
    "web_search": web_search,
    "submit_initial": submit_initial,
    "submit_follow_up": submit_follow_up,
}


# --- The guard of the note-taker's procedure ------------------------------------------------
async def remind_to_use_tools(call: "LiveCall", delegation_id: str) -> None:
    """A request of the voice agent ended with the note-taker's text and no tool call. The voice
    agent is told to ignore that text; the note-taker gets the request's tools named and a new
    response to do it. Sends only commands and holds nothing while it does."""
    if call.closing:
        return
    if call.tool_reminders >= config.TOOL_REMINDERS_PER_CALL:
        logger.warning("event=tool_reminders_exhausted conversation_id=%s delegation_id=%s", call.conversation_id,
                       delegation_id)
        return
    call.tool_reminders += 1
    logger.info("event=tool_reminder conversation_id=%s delegation_id=%s count=%d", call.conversation_id,
                delegation_id, call.tool_reminders)
    await call.tell(text("messages.result_without_tool"))
    await call.send({"type": "response.item.create", "item": {"type": "message", "role": "developer", "content": [
        {"type": "input_text", "text": text("messages.tool_required", agent_name=call.settings.agent_name)}]}})
    await call.send({"type": "response.create"})


# --- The one runner -----------------------------------------------------------------------
async def run_tool(call: "LiveCall", item: dict) -> None:
    """Runs one function call of the note-taker and sends back the handler's output, or, when the
    handler failed, tells the voice agent the AI message of what failed and gives the note-taker
    `tool_done`. Every exception becomes such a message, so neither model waits for nothing; the log
    gets the tool, the outcome and the duration, never the arguments or what was said."""
    name = item.get("name")
    started = time.monotonic()
    try:
        result = await _handle(call, name, item.get("arguments") or "{}")
    except Exception as error:
        result = (Result("refused", details=error.log_message) if isinstance(error, AppError)
                  else Result("failed", details=f"type={type(error).__name__}"))
        await call.tell(message_for_ai(error))
    logger.info("event=tool_call conversation_id=%s tool=%s outcome=%s duration_ms=%d %s", call.conversation_id,
                name, result.outcome, (time.monotonic() - started) * 1000, result.details)
    await call.send({"type": "response.item.create", "item": {
        "type": "function_call_output", "call_id": item.get("call_id"),
        "output": result.output or text("messages.tool_done")}})
    # Appending the output alone does not resume the note-taker. Its next response, its reply, is
    # also the browser's signal that the tool is done (conversation/status.ts): the tag and the
    # status end.
    await call.send({"type": "response.create"})


async def _handle(call: "LiveCall", name: str | None, raw_arguments: str) -> Result:
    if name not in HANDLERS:  # not a tool this backend offers
        raise AppError.for_ai("reason=tool_not_available", text("messages.generic_error"))
    model = argument_model(name)
    try:
        arguments = model.model_validate_json(raw_arguments)
    except ValidationError as error:
        # Only the field names: the errors themselves would repeat what the founder said. Strict
        # function calling makes this rare, so the voice agent hears the generic message.
        fields = sorted({str(e["loc"][0]) for e in error.errors() if e["loc"]}) or list(model.model_fields)
        raise AppError.for_ai(f"reason=invalid_arguments fields={','.join(fields)}",
                              text("messages.generic_error")) from None
    return await HANDLERS[name](call, arguments)
