"""The one login: founder signup with an access code, login for both roles, logout, and the role
guards of the founder and team routes."""

import uuid

from sqlalchemy import func, select

from app.access_codes import CODE_NOT_FOUND
from app.accounts import EMAIL_TAKEN, WRONG_LOGIN
from app.db import session_scope
from app.models import Conversation, Founder
from app.security import LOGIN_REQUIRED, WRONG_ROLE
from conftest import FOUNDER, TEST_SECRETS


def count(model: type) -> int:
    with session_scope() as session:
        return session.scalar(select(func.count()).select_from(model))


async def test_signup_creates_the_account_and_a_ready_conversation_and_logs_in(client, team, sign_up):
    response = await sign_up(client)

    assert response.status_code == 200
    body = response.json()
    assert body["me"] == {"role": "founder", "name": FOUNDER["name"], "company_name": FOUNDER["company_name"]}
    assert (await client.get("/api/auth/me")).json() == body["me"]
    conversations = (await client.get("/api/my/conversations")).json()
    assert [(c["id"], c["state"], c["started_at"]) for c in conversations] == [(body["conversation_id"], "ready", None)]
    [code] = (await team.get("/api/team/access-codes")).json()
    assert (code["state"], code["conversation_id"]) == ("used", body["conversation_id"])


async def test_a_rejected_code_at_signup_creates_nothing(client, sign_up):
    response = await sign_up(client, code="WRONG234")

    assert (response.status_code, response.json()) == (400, {"detail": CODE_NOT_FOUND})
    assert (count(Founder), count(Conversation)) == (0, 0)
    assert (await client.get("/api/auth/me")).json() is None
    assert (await sign_up(client)).status_code == 200  # the email is still free


async def test_an_existing_email_and_the_team_email_are_refused_alike(new_client, sign_up):
    assert (await sign_up(new_client())).status_code == 200

    existing = await sign_up(new_client(), email=FOUNDER["email"].upper())
    team_email = await sign_up(new_client(), email=TEST_SECRETS.team_email)

    assert existing.status_code == team_email.status_code == 409
    assert existing.json() == team_email.json() == {"detail": EMAIL_TAKEN}
    assert count(Founder) == 1


async def test_login_as_founder_and_as_team(founder, new_client):
    client = new_client()
    founder_login = await client.post("/api/auth/login", json={"email": " Erika@Example.com ", "password": FOUNDER["password"]})
    assert founder_login.json() == {"role": "founder", "name": FOUNDER["name"], "company_name": FOUNDER["company_name"]}
    assert (await client.get("/api/my/conversations")).status_code == 200

    team_login = await client.post("/api/auth/login", json={"email": TEST_SECRETS.team_email.upper(),
                                                            "password": TEST_SECRETS.team_password})
    assert team_login.json() == {"role": "team", "name": TEST_SECRETS.team_email, "company_name": None}
    assert (await client.get("/api/my/conversations")).status_code == 403  # the new login replaced the old one


async def test_a_wrong_password_and_an_unknown_email_give_the_same_message(founder, client):
    attempts = [
        {"email": FOUNDER["email"], "password": "wrong"},
        {"email": "nobody@example.com", "password": FOUNDER["password"]},
        {"email": TEST_SECRETS.team_email, "password": "wrong"},
    ]
    for attempt in attempts:
        response = await client.post("/api/auth/login", json=attempt)
        assert (response.status_code, response.json()) == (400, {"detail": WRONG_LOGIN})
    assert (await client.get("/api/auth/me")).json() is None


async def test_me_is_null_after_logout(founder):
    assert (await founder.get("/api/auth/me")).json()["role"] == "founder"
    assert (await founder.post("/api/auth/logout")).status_code == 204
    assert (await founder.get("/api/auth/me")).json() is None
    assert (await founder.get("/api/my/conversations")).status_code == 401


async def test_role_guards(client, founder, team):
    founder_routes = [("GET", "/api/my/conversations"), ("POST", "/api/my/conversations")]
    team_routes = [("GET", "/api/team/conversations"), ("GET", f"/api/team/conversations/{uuid.uuid4()}"),
                   ("GET", "/api/team/access-codes"), ("POST", "/api/team/access-codes"),
                   ("GET", "/api/team/settings"), ("PUT", "/api/team/settings"), ("POST", "/api/team/settings/reset"),
                   ("GET", "/api/team/catalog"), ("PUT", "/api/team/catalog"), ("POST", "/api/team/catalog/reset")]
    for method, path in founder_routes + team_routes:
        response = await client.request(method, path, json={})
        assert (response.status_code, response.json()) == (401, {"detail": LOGIN_REQUIRED})
    for user, routes in ((founder, team_routes), (team, founder_routes)):
        for method, path in routes:
            response = await user.request(method, path, json={})
            assert (response.status_code, response.json()) == (403, {"detail": WRONG_ROLE})
