"""Access codes: how the team invites a founder to exactly one conversation.

A code is random, bound to one email, valid for `config.ACCESS_CODE_VALID_HOURS` and usable once.
Only its SHA-256 hash is stored; the plain code exists once, in the response to the team.

`redeem_access_code` is the only place where a code's state changes. It checks the code, marks it
as used and creates the Ready conversation in one step, inside the caller's transaction. Signup and
"Neues Gespräch" both call it, so they cannot behave differently, and a rejected code creates
nothing (at signup not even the account, because the whole signup step rolls back).

Every function is a database step for `db.run_db` (or runs inside one) and runs in a worker thread.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.errors import AppError
from app.models import AccessCode, Conversation, Founder, utcnow
from app.schemas import AccessCodeRow, AccessCodeState, CreatedAccessCode
from app.security import generate_access_code, hash_access_code, normalize_email

logger = logging.getLogger(__name__)

CODE_NOT_FOUND = "Diesen Zugangscode gibt es nicht. Bitte prüfen Sie ihn auf Tippfehler."
CODE_OTHER_EMAIL = "Dieser Zugangscode wurde für eine andere E-Mail-Adresse erstellt."
CODE_USED = "Dieser Zugangscode wurde schon benutzt."
CODE_EXPIRED = "Dieser Zugangscode ist abgelaufen. Bitte fragen Sie das Team nach einem neuen."


def access_code_state(code: AccessCode, now: datetime) -> AccessCodeState:
    """The one place that computes a code's state from its stored times."""
    if code.used_at is not None:
        return "used"
    if code.expires_at <= now:
        return "expired"
    return "unused"


def create_access_code(session: Session, email: str) -> CreatedAccessCode:
    plain_code = generate_access_code()
    now = utcnow()
    code = AccessCode(email=normalize_email(email), code_hash=hash_access_code(plain_code), created_at=now,
                      expires_at=now + timedelta(hours=config.ACCESS_CODE_VALID_HOURS))
    session.add(code)
    session.flush()
    logger.info("event=access_code_created access_code_id=%s", code.id)
    return CreatedAccessCode(code=plain_code, email=code.email, expires_at=code.expires_at)


def list_access_codes(session: Session) -> list[AccessCodeRow]:
    """All codes, newest first, with their computed state."""
    now = utcnow()
    codes = session.scalars(select(AccessCode).order_by(AccessCode.created_at.desc()))
    return [AccessCodeRow(id=c.id, email=c.email, created_at=c.created_at, expires_at=c.expires_at,
                          state=access_code_state(c, now), conversation_id=c.conversation_id) for c in codes]


def redeem_access_code(session: Session, code: str, founder: Founder) -> Conversation:
    """Check the code for this founder, mark it as used and create the Ready conversation it unlocks.

    The row is locked (`FOR UPDATE`) until the caller's transaction ends, so two simultaneous
    redemptions of one code wait for each other and the second one finds it used.
    """
    row = session.scalar(select(AccessCode).where(AccessCode.code_hash == hash_access_code(code)).with_for_update())
    if row is None:
        raise AppError(CODE_NOT_FOUND, "reason=access_code_not_found")
    if row.email != founder.email:
        raise AppError(CODE_OTHER_EMAIL, f"reason=access_code_other_email access_code_id={row.id}")
    now = utcnow()
    state = access_code_state(row, now)
    if state == "used":
        raise AppError(CODE_USED, f"reason=access_code_used access_code_id={row.id}")
    if state == "expired":
        raise AppError(CODE_EXPIRED, f"reason=access_code_expired access_code_id={row.id}")
    conversation = Conversation(founder_id=founder.id, state="ready", created_at=now)
    session.add(conversation)
    session.flush()
    row.used_at = now
    row.conversation_id = conversation.id
    logger.info("event=access_code_redeemed access_code_id=%s conversation_id=%s", row.id, conversation.id)
    return conversation
