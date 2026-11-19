"""The team's review: the list of every conversation, newest first, and the detail with the same view
the founder sees plus the team-only details (questionnaire, settings), read from the database."""

import uuid

from conftest import FOUNDER


async def test_the_list_shows_every_conversation_with_its_founder_newest_first(team, founder, new_client, sign_up):
    other = new_client()
    assert (await sign_up(other, name="Max Beispiel", email="max@example.com", company_name="Feldweg AI")).status_code == 200

    rows = (await team.get("/api/team/conversations")).json()

    assert [(row["founder_name"], row["founder_email"], row["company_name"], row["state"]) for row in rows] == [
        ("Max Beispiel", "max@example.com", "Feldweg AI", "ready"),
        (FOUNDER["name"], FOUNDER["email"], FOUNDER["company_name"], "ready"),
    ]
    assert rows[0]["started_at"] is None


async def test_a_ready_conversation_has_no_details_yet(team, founder):
    conversation_id = (await founder.get("/api/my/conversations")).json()[0]["id"]

    detail = (await team.get(f"/api/team/conversations/{conversation_id}")).json()

    assert detail["view"] == (await founder.get(f"/api/my/conversations/{conversation_id}")).json()
    assert (detail["founder_name"], detail["founder_email"], detail["company_name"]) == (
        FOUNDER["name"], FOUNDER["email"], FOUNDER["company_name"])
    assert (detail["settings"], detail["questionnaire"]) == (None, None)


async def test_the_detail_shows_what_the_founder_sees_plus_questionnaire_and_settings(team, start):
    call = await start()
    await call.say("agent", "Willkommen.", 0, 800)
    await call.say("founder", "Danke.", 1200, 1600)
    await call.end("stopped")

    detail = (await team.get(f"/api/team/conversations/{call.conversation_id}")).json()

    assert detail["view"] == (await call.client.get(f"/api/my/conversations/{call.conversation_id}")).json()
    assert detail["view"]["state"] == "unfinished"
    assert [message["text"] for message in detail["view"]["transcript"]] == ["Willkommen.", "Danke."]
    assert detail["settings"]["agent_name"] == "Mira"
    assert len(detail["questionnaire"]["entries"]) == 11
    assert detail["questionnaire"]["entries"][0]["answer"] is None


async def test_an_unknown_conversation_is_not_found(team):
    response = await team.get(f"/api/team/conversations/{uuid.uuid4()}")

    assert response.status_code == 404
