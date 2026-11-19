"""The sideband of a running call: the opening once the session started, transcript deltas turned
into messages on every speaker change, reply times and the note-taker's response times in the logs,
the guard that reminds the note-taker to answer every request with a tool call, and never a
founder's words in the logs."""

import logging

from app import config
from app.ai.transcript import ReplyTimes, TranscriptBuilder
from app.context import text
from app.schemas import TranscriptMessage
from conftest import FOUNDER, eventually
from fakes import written_down

MARKER = "SECRET-MARKER-5c1d"  # stands for something a founder said


def test_a_message_is_a_run_of_deltas_from_one_speaker():
    builder = TranscriptBuilder()

    assert builder.add("agent", " Guten ", 0, 400) is None
    assert builder.add("agent", "Tag! ", 400, 800) is None
    greeting = builder.add("founder", "  ", 900, 950)        # a speaker change finishes the agent's message
    assert builder.add("agent", "Wie ", 1000, 1200) is None  # the founder's blank message is dropped
    last = builder.flush()

    assert greeting == TranscriptMessage(speaker="agent", text="Guten Tag!", start_ms=0, end_ms=800)
    assert last == TranscriptMessage(speaker="agent", text="Wie", start_ms=1000, end_ms=1200)
    assert builder.flush() is None


def test_reply_times_skip_overlaps():
    times = ReplyTimes()

    assert times.record(founder_end_ms=1000, agent_start_ms=1800) == 800
    assert times.record(founder_end_ms=5000, agent_start_ms=4900) is None  # a "mhm" while the agent spoke
    times.record(founder_end_ms=9000, agent_start_ms=10200)

    assert times.summary() == (2, 1000, 1200)


async def test_the_opening_greets_and_starts_the_startup_lookup_once_the_session_started(start):
    call = await start()

    await call.session.send({"type": "session.started", "session": {"id": call.session.id, "expires_at": 1}})

    greeting = await call.session.next_command("session.commentary.append")
    assert greeting["delegation_id"] is None
    assert FOUNDER["name"] in greeting["content"] and FOUNDER["company_name"] in greeting["content"]
    lookup = await call.session.next_command("response.item.create")
    assert FOUNDER["company_name"] in lookup["item"]["content"][0]["text"]
    await call.session.next_command("response.create")  # starts the note-taker
    assert [command["type"] for command in call.session.commands] == [
        "session.commentary.append", "response.item.create", "response.create"]


async def test_deltas_become_messages_saved_in_order_and_reply_times_are_logged(start, caplog):
    caplog.set_level(logging.INFO)
    call = await start()

    await call.say("agent", "Guten Tag, ", 0, 600)
    await call.say("agent", "Frau Muster.", 600, 1100)
    await call.say("founder", "Hallo!", 1500, 1900)
    await call.say("agent", "Schön, ", 2700, 3000)      # reply time 800 ms
    await call.say("agent", "los geht's.", 3000, 3400)
    await call.say("founder", "Gut.", 4000, 4300)
    await call.say("agent", "Erste Frage.", 4900, 5300)  # reply time 600 ms, still in progress at the end
    view = await call.end("stopped")

    expected = [("agent", "Guten Tag, Frau Muster."), ("founder", "Hallo!"), ("agent", "Schön, los geht's."),
                ("founder", "Gut."), ("agent", "Erste Frage.")]
    assert [(m["speaker"], m["text"]) for m in view["transcript"]] == expected
    assert call.messages() == expected
    assert view["transcript"][1] == {"speaker": "founder", "text": "Hallo!", "start_ms": 1500, "end_ms": 1900}
    assert "event=reply_time" in caplog.text and "reply_ms=800" in caplog.text and "reply_ms=600" in caplog.text
    assert "count=2 median_ms=700 max_ms=800 target_ms=1500" in caplog.text


async def test_a_founders_words_never_reach_the_logs(start, fake, caplog):
    # At the level the app logs at (app/logs.py). The sideband carries what is said by design (the
    # summary and search results go to the voice agent), so the websocket library's DEBUG frame dumps,
    # which the app never turns on, show it.
    caplog.set_level(logging.INFO)
    call = await start()
    fake.searches.append([{"title": MARKER, "link": "https://example.com", "snippet": MARKER}])

    await call.say("founder", f"Unser Geheimnis ist {MARKER}.", 0, 900)
    await call.say("agent", "Danke.", 1500, 1800)
    await call.call_tool("web_search", {"query": f"{MARKER} Markt"})
    fake.responses += [written_down({i: f"Antwort {MARKER}" for i in range(1, 12)}, summary=MARKER),
                       {"follow_ups": [{"question_id": 5, "question": MARKER, "explanation": MARKER}]}]
    await call.call_tool("submit_initial", call_id="call_2")
    await call.end("stopped")

    assert "event=tool_call" in caplog.text
    for record in caplog.records:
        assert MARKER not in record.getMessage()


async def test_the_note_takers_responses_are_logged_with_their_duration_but_never_their_text(start, caplog):
    caplog.set_level(logging.INFO)
    call = await start()
    report = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": f"Gefunden: {MARKER}"}]}

    await call.session.send({"type": "session.delegation.created", "delegation_id": "delegation_a", "target": "responses"})
    for nested in ({"type": "response.created", "response": {"id": "resp_a"}},
                   {"type": "response.output_item.done", "item": report},
                   {"type": "response.completed", "response": {"id": "resp_a"}}):
        await call.session.send({"type": "response.event", "delegation_id": "delegation_a", "event": nested})
    await eventually(lambda: "event=note_taker_finished" in caplog.text)

    assert "event=delegation_created" in caplog.text and "target=responses" in caplog.text
    assert "event=note_taker_started" in caplog.text and "event=note_taker_reported" in caplog.text
    assert "response_id=resp_a outcome=completed duration_ms=" in caplog.text
    assert all(MARKER not in record.getMessage() for record in caplog.records)


# --- The guard of the note-taker's procedure ------------------------------------------------
async def answer_with_text(call, delegation_id: str, response_id: str) -> None:
    """The note-taker answers a request with text alone, as if it had written something down."""
    summary = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Zusammenfassung: ..."}]}
    for nested in ({"type": "response.created", "response": {"id": response_id}},
                   {"type": "response.output_item.done", "item": summary},
                   {"type": "response.completed", "response": {"id": response_id}}):
        await call.session.send({"type": "response.event", "delegation_id": delegation_id, "event": nested})


async def test_a_request_answered_with_text_alone_gets_a_reminder(start, caplog):
    caplog.set_level(logging.INFO)
    call = await start()

    await answer_with_text(call, "delegation_b", "resp_b")

    warning = await call.session.next_command("session.commentary.append")
    assert warning == {"type": "session.commentary.append", "delegation_id": None,
                       "content": text("messages.result_without_tool")}
    reminder = await call.session.next_command("response.item.create")
    assert reminder["item"]["role"] == "developer"
    assert reminder["item"]["content"][0]["text"] == text("messages.tool_required", agent_name="Mira")
    await call.session.next_command("response.create")  # the note-taker tries again
    assert "event=tool_reminder" in caplog.text and "delegation_id=delegation_b count=1" in caplog.text


async def test_a_request_answered_with_a_tool_gets_no_reminder(start, fake):
    call = await start()
    fake.searches.append([{"title": "Nordlicht", "link": "https://nordlicht.example", "snippet": "Roboter."}])

    await call.call_tool("web_search", {"query": "Nordlicht Robotics"})  # the fake note-taker then replies
    await eventually(lambda: call.session.responses == 1)

    assert text("messages.result_without_tool") not in call.told()
    assert [command["type"] for command in call.session.commands] == ["response.item.create", "response.create"]


async def test_the_reminders_stop_after_the_configured_number(start, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(config, "TOOL_REMINDERS_PER_CALL", 2)
    call = await start()

    for number in range(3):
        await answer_with_text(call, "delegation_c", f"resp_c{number}")
    await eventually(lambda: "event=tool_reminders_exhausted" in caplog.text)

    assert len(call.session.commands_of("response.create")) == 2
