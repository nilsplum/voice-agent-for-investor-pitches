"""START: the Live session is created with everything the conversation needs, the sideband is
attached before the route answers, the copies of settings and catalog are taken at START, and a
failed start leaves the conversation Ready."""

from uuid import UUID

import pytest

from app import config, db
from app.ai.live import START_FAILED
from app.context import context, default_catalog
from app.conversations import CANNOT_START, NOT_FOUND
from app.models import Conversation
from conftest import FOUNDER


async def test_the_session_is_created_with_the_conversations_prompts_voice_and_tools(start, fake):
    call = await start()

    body = fake.session().body
    session = body["session"]
    assert body["transport"] == {"type": "webrtc", "sdp": "offer-sdp"}
    assert session["model"] == config.LIVE_MODEL
    assert session["audio"] == {"output": {"voice": config.LANGUAGES["de"].voice}}  # no format for WebRTC
    instructions = session["instructions"]
    for expected in (FOUNDER["name"], FOUNDER["company_name"], "Mira", "Speak German",
                     default_catalog().questions[4].question, context().faq.faq[0].answer):
        assert expected in instructions
    kickoff = session["input"][0]["content"][0]["text"]
    assert FOUNDER["name"] in kickoff and FOUNDER["company_name"] in kickoff

    delegation = session["delegation"]["responses"]
    assert (delegation["model"], delegation["reasoning"]) == (config.DEFAULT_SETTINGS["note_taker_model"],
                                                              {"effort": config.DEFAULT_SETTINGS["note_taker_thinking"]})
    assert delegation["parallel_tool_calls"] is False
    assert [tool["name"] for tool in delegation["tools"]] == ["web_search", "submit_initial"]
    for tool in delegation["tools"]:
        parameters = tool["parameters"]
        assert tool["strict"] is True and parameters["additionalProperties"] is False
        assert sorted(parameters.get("required", [])) == sorted(parameters["properties"])
    # The submit tools take no input: the backend writes the answers from the transcript.
    assert [list(tool["parameters"]["properties"]) for tool in delegation["tools"]] == [["query"], []]
    assert call.stored()["state"] == "in_progress"


async def test_start_answers_with_the_sdp_and_the_agents_name_once_the_sideband_is_attached(founder, fake):
    conversation_id = (await founder.get("/api/my/conversations")).json()[0]["id"]

    response = await founder.post(f"/api/my/conversations/{conversation_id}/start", json={"sdp": "offer-sdp"})

    session = fake.session()
    assert response.json() == {"sdp": f"answer-{session.id}", "agent_name": "Mira"}
    assert session.attaches == 1


async def test_settings_and_questionnaire_are_copied_at_start(start, team):
    call = await start()

    await team.put("/api/team/settings", json={**config.DEFAULT_SETTINGS, "agent_name": "Lena"})
    await team.put("/api/team/catalog", json={"questions": [
        {"id": None, "topic": "Neu", "question": "Neue Frage?", "context": "Neuer Kontext."}]})

    stored = call.stored()
    assert stored["settings"] == config.DEFAULT_SETTINGS
    assert [entry.id for entry in call.questionnaire().entries] == list(range(1, 12))
    assert all(entry.answer is None and entry.follow_up is None for entry in call.questionnaire().entries)
    view = (await call.client.get(f"/api/my/conversations/{call.conversation_id}")).json()
    assert view["agent_name"] == "Mira"


async def test_a_second_start_gets_409_and_another_founders_conversation_404(start, new_client, sign_up):
    call = await start()

    again = await call.client.post(f"/api/my/conversations/{call.conversation_id}/start", json={"sdp": "offer-sdp"})
    assert (again.status_code, again.json()) == (409, {"detail": CANNOT_START})

    other = new_client()
    assert (await sign_up(other, email="other@example.com")).status_code == 200
    for method, path, body in (("POST", "start", {"sdp": "offer-sdp"}), ("POST", "end", {"reason": "stopped"}),
                               ("GET", "", None)):
        response = await other.request(method, f"/api/my/conversations/{call.conversation_id}/{path}".rstrip("/"),
                                       json=body)
        assert (response.status_code, response.json()) == (404, {"detail": NOT_FOUND})
    assert call.stored()["state"] == "in_progress"


@pytest.mark.parametrize("failing", ["create", "attach"])
async def test_a_failing_create_or_attach_leaves_the_conversation_ready(founder, fake, start, failing):
    conversation_id = (await founder.get("/api/my/conversations")).json()[0]["id"]
    if failing == "create":
        fake.create_status = 500
    else:
        fake.refuse_attach = True

    response = await founder.post(f"/api/my/conversations/{conversation_id}/start", json={"sdp": "offer-sdp"})

    assert (response.status_code, response.json()) == (502, {"detail": START_FAILED})
    with db.session_scope() as session:
        row = session.get(Conversation, UUID(conversation_id))
        assert (row.state, row.started_at, row.settings, row.questionnaire) == ("ready", None, None, None)
    fake.create_status, fake.refuse_attach = 201, False
    call = await start()  # the code is not lost: the next START works
    stored = call.stored()
    assert stored["state"] == "in_progress" and stored["settings"] is not None
