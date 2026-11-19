"""Access codes: shown once and stored as a hash, their states, single use, email binding,
normalization, and one redemption step for the signup and "Neues Gespräch"."""

import asyncio
import hashlib
import json
import re
from datetime import timedelta

from sqlalchemy import select, update

from app import config
from app.access_codes import CODE_EXPIRED, CODE_NOT_FOUND, CODE_OTHER_EMAIL, CODE_USED
from app.db import session_scope
from app.models import AccessCode, Founder, utcnow
from conftest import FOUNDER


async def test_the_plain_code_is_shown_once_and_only_its_hash_is_stored(team):
    created = (await team.post("/api/team/access-codes", json={"email": "Erika@Example.com"})).json()

    assert re.fullmatch(f"[{config.ACCESS_CODE_ALPHABET}]{{{config.ACCESS_CODE_LENGTH}}}", created["code"])
    assert created["email"] == "erika@example.com"
    listed = (await team.get("/api/team/access-codes")).json()
    assert created["code"] not in json.dumps(listed)
    with session_scope() as session:
        stored = session.scalars(select(AccessCode)).one()
        assert stored.code_hash == hashlib.sha256(created["code"].encode()).hexdigest()
        assert created["code"] not in repr([getattr(stored, column.key) for column in AccessCode.__table__.columns])


async def test_states_unused_used_and_expired(team, create_code, sign_up, client):
    await create_code("unused@example.com")
    expired_code = await create_code("expired@example.com")
    assert (await sign_up(client)).status_code == 200
    with session_scope() as session:
        session.execute(update(AccessCode).where(AccessCode.email == "expired@example.com")
                        .values(expires_at=utcnow() - timedelta(minutes=1)))

    states = {row["email"]: row["state"] for row in (await team.get("/api/team/access-codes")).json()}

    assert states == {"unused@example.com": "unused", "expired@example.com": "expired", FOUNDER["email"]: "used"}
    response = await sign_up(client, email="expired@example.com", code=expired_code)
    assert response.json() == {"detail": CODE_EXPIRED}


async def test_a_code_works_only_once(founder, create_code):
    code = await create_code(FOUNDER["email"])
    assert (await founder.post("/api/my/conversations", json={"code": code})).status_code == 201

    again = await founder.post("/api/my/conversations", json={"code": code})

    assert (again.status_code, again.json()) == (400, {"detail": CODE_USED})


async def test_a_code_works_only_for_its_email(client, create_code, sign_up):
    code = await create_code("someone-else@example.com")

    response = await sign_up(client, code=code)

    assert (response.status_code, response.json()) == (400, {"detail": CODE_OTHER_EMAIL})


async def test_code_and_email_are_normalized(client, create_code, sign_up):
    code = await create_code("ERIKA@example.com")

    response = await sign_up(client, email=" Erika@Example.COM ", code=f"  {code.lower()} ")

    assert response.status_code == 200
    with session_scope() as session:
        assert session.scalars(select(Founder.email)).one() == "erika@example.com"


async def test_new_conversation_uses_the_same_redemption(founder, create_code):
    code = await create_code(FOUNDER["email"])

    unlocked = await founder.post("/api/my/conversations", json={"code": code})

    assert unlocked.status_code == 201
    assert (unlocked.json()["state"], unlocked.json()["started_at"]) == ("ready", None)
    listed = (await founder.get("/api/my/conversations")).json()
    assert len(listed) == 2 and listed[0]["id"] == unlocked.json()["id"]  # newest first
    refusals = {
        CODE_USED: code,
        CODE_OTHER_EMAIL: await create_code("someone-else@example.com"),
        CODE_NOT_FOUND: "NOPE2345",
    }
    for message, refused_code in refusals.items():
        response = await founder.post("/api/my/conversations", json={"code": refused_code})
        assert (response.status_code, response.json()) == (400, {"detail": message})
    assert len((await founder.get("/api/my/conversations")).json()) == 2


async def test_two_simultaneous_redemptions_of_one_code_cannot_both_succeed(founder, create_code):
    code = await create_code(FOUNDER["email"])

    responses = await asyncio.gather(*(founder.post("/api/my/conversations", json={"code": code}) for _ in range(2)))

    assert sorted(response.status_code for response in responses) == [201, 400]

