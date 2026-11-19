"""Every way a call ends: STOPP, a lost connection before and after the founder spoke (a failed
start goes back to Ready), a dropped sideband, the time limit, the startup sweep and the shutdown.
The first final state written wins, and an old call's cleanup never touches the next attempt."""

import asyncio
import logging
from uuid import UUID

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from app import config, db
from app.ai import live
from app.main import create_app
from app.models import Conversation
from app.schemas import ConversationView
from conftest import Call, eventually
from fakes import SUMMARY, written_down


def state(call: Call) -> tuple:
    stored = call.stored()
    return stored["state"], stored["end_reason"]


async def test_a_lost_connection_before_the_founder_spoke_is_a_failed_start(start):
    call = await start()
    await call.say("agent", "Guten Tag!", 0, 900)
    await call.say("founder", "   ", 1000, 1100)  # noise: a speaker change, but no words
    await call.say("agent", "Hören Sie mich?", 1500, 2200)
    await eventually(lambda: call.messages() == [("agent", "Guten Tag!")])  # the greeting was saved

    view = await call.end("connection_lost")

    assert (view["state"], view["transcript"]) == ("ready", [])
    stored = call.stored()
    assert (stored["state"], stored["started_at"], stored["settings"], stored["questionnaire"]) == ("ready", None, None, None)
    assert call.messages() == []
    assert call.session.commands_of("session.close") != []


async def test_stopp_gives_unfinished_and_the_view_has_the_message_in_progress(start):
    call = await start()
    await call.say("agent", "Willkommen beim Gespräch.", 0, 1500)  # in progress: nobody else spoke yet

    view = await call.end("stopped")

    assert (view["state"], view["end_reason"]) == ("unfinished", "stopped")  # also before the founder spoke
    assert [(m["speaker"], m["text"]) for m in view["transcript"]] == [("agent", "Willkommen beim Gespräch.")]
    assert view["ended_at"] is not None and view["summary"] is None
    assert len(call.session.commands_of("session.close")) == 1


async def test_an_old_calls_cleanup_never_touches_the_next_attempt(start, fake, monkeypatch):
    monkeypatch.setattr(config, "END_WAIT_S", 0.1)
    old = await start()
    old_call = live.CALLS[UUID(old.conversation_id)]
    fake.answer_close = False  # the old session stays open: its cleanup is still pending
    await old.say("agent", "Guten Tag!", 0, 800)
    view = await old.end("connection_lost")  # the browser's connection failed before the founder spoke
    assert view["state"] == "ready" and not old_call.sideband.done()

    fake.answer_close = True
    new = await start()
    await old.session.drop()  # now the old call cleans up: flush, end, close
    await asyncio.wait_for(old_call.sideband, timeout=3)

    assert new.stored()["state"] == "in_progress"
    assert new.messages() == []  # the old greeting was not saved into the new attempt
    assert new.session.commands_of("session.close") == []
    assert live.CALLS[UUID(new.conversation_id)].session_id == new.session.id


async def test_session_closed_after_the_founder_spoke_gives_unfinished_without_a_close(start):
    call = await start()
    await call.say("founder", "Hallo.", 0, 500)

    await call.session.send({"type": "session.closed", "reason": "remote_hangup"})

    await eventually(lambda: state(call) == ("unfinished", "connection_lost"))
    await eventually(lambda: not live.CALLS)
    assert call.session.commands_of("session.close") == []


async def test_a_dropped_sideband_ends_the_call_and_closes_the_session_with_a_second_attach(start):
    spoke = await start()
    await spoke.say("founder", "Hallo.", 0, 500)
    await spoke.session.drop()
    await eventually(lambda: state(spoke) == ("unfinished", "connection_lost"))
    await eventually(lambda: spoke.session.attaches == 2 and spoke.session.commands_of("session.close") != [])


async def test_a_dropped_sideband_before_the_founder_spoke_is_a_failed_start_and_closes_too(start):
    call = await start()
    await call.session.drop()
    await eventually(lambda: state(call) == ("ready", None))
    await eventually(lambda: call.session.attaches == 2 and call.session.commands_of("session.close") != [])


async def test_a_failing_second_attach_is_logged_and_changes_nothing_else(start, fake, caplog):
    caplog.set_level(logging.INFO)
    call = await start()
    await call.say("founder", "Hallo.", 0, 500)
    fake.refuse_attach = True

    await call.session.drop()

    await eventually(lambda: "event=close_failed" in caplog.text)
    assert state(call) == ("unfinished", "connection_lost")
    assert call.session.attaches == 1


async def test_a_lost_connection_after_completed_changes_nothing(start, fake):
    call = await start()
    await call.say("founder", "Hallo.", 0, 500)
    fake.responses += [written_down(), {"follow_ups": []}]
    await call.call_tool("submit_initial")

    view = await call.end("connection_lost")

    assert (view["state"], view["end_reason"]) == ("completed", None)
    assert view["summary"] == SUMMARY


async def test_the_time_limit_gives_unfinished_written_before_the_close(start, monkeypatch):
    monkeypatch.setattr(config, "CONVERSATION_TIME_LIMIT_S", 0.3)
    call = await start()
    await call.say("founder", "Hallo.", 0, 500)

    await call.session.next_command("session.close")

    assert state(call) == ("unfinished", "time_limit")  # already stored when the close arrived


async def test_the_startup_sweep_finishes_conversations_a_restart_cut_off(founder, app):
    conversation_id = (await founder.get("/api/my/conversations")).json()[0]["id"]
    with db.session_scope() as session:
        session.execute(update(Conversation).values(state="in_progress"))

    async with LifespanManager(create_app()):  # a restart
        pass

    with db.session_scope() as session:
        row = session.get(Conversation, UUID(conversation_id))
        assert (row.state, row.end_reason) == ("unfinished", "connection_lost")


async def test_the_shutdown_ends_running_calls_and_closes_their_sessions(founder, fake, secrets):
    conversation_id = (await founder.get("/api/my/conversations")).json()[0]["id"]
    restarted = create_app()
    async with LifespanManager(restarted):
        async with AsyncClient(transport=ASGITransport(app=restarted), base_url="http://testserver",
                               cookies=founder.cookies) as client:
            response = await client.post(f"/api/my/conversations/{conversation_id}/start", json={"sdp": "offer-sdp"})
            assert response.status_code == 200
            call = Call(client, conversation_id, fake.session())
            await call.say("founder", "Hallo.", 0, 500)
            await eventually(lambda: live.CALLS[UUID(conversation_id)].founder_spoke)

    assert state(call) == ("unfinished", "connection_lost")
    assert call.session.commands_of("session.close") != []
    assert live.CALLS == {}


async def test_the_founder_view_shows_the_summary_only_when_completed(start, fake):
    call = await start()
    fake.responses += [written_down(),
                       {"follow_ups": [{"question_id": 11, "question": "Noch etwas?", "explanation": "Abschluss."}]}]
    await call.call_tool("submit_initial")

    running = (await call.client.get(f"/api/my/conversations/{call.conversation_id}")).json()
    stopped = await call.end("stopped")

    assert set(running) == set(ConversationView.model_fields)  # never the questionnaire or the settings
    assert (running["state"], running["summary"]) == ("in_progress", None)
    assert (stopped["state"], stopped["summary"]) == ("unfinished", None)
