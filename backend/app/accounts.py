"""Signup, the one login for both roles, and who is logged in.

The team has one shared login in the secrets file (`team_email`, `team_password`). Its password is
kept there in plain text on purpose: one login for a local MVP, with no team table and no hashing
for the team. Founders are rows with argon2 password hashes. One login function tells them apart
by the email alone: the team's email (normalized like every email) is checked against the team's
password, every other email is looked up among the founders, and every failure gives the same
message. Signup refuses the team's email, so the two can never collide.

Every function is a database step for `db.run_db` and runs in a worker thread, password hashing
included. The routes write the session cookie afterwards (`security.start_session`).
"""

import hmac
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.access_codes import redeem_access_code
from app.errors import AppError
from app.models import Founder
from app.schemas import LoginRequest, Me, Role, SignupRequest, SignupResponse
from app.security import hash_password, normalize_email, verify_password

logger = logging.getLogger(__name__)

EMAIL_TAKEN = "Zu dieser E-Mail-Adresse gibt es schon ein Konto. Bitte melden Sie sich an."
WRONG_LOGIN = "Die Anmeldedaten sind falsch."


def team_email() -> str:
    return normalize_email(config.secrets().team_email)


def founder_me(founder: Founder) -> Me:
    return Me(role="founder", name=founder.name, company_name=founder.company_name)


def signup(session: Session, request: SignupRequest) -> tuple[SignupResponse, UUID]:
    """Create the founder and redeem the code in one transaction: a rejected code rolls the account back."""
    email = normalize_email(request.email)
    if email == team_email() or session.scalar(select(Founder.id).where(Founder.email == email)):
        raise AppError(EMAIL_TAKEN, "reason=signup_email_taken", status_code=409)
    founder = Founder(name=request.name, email=email, password_hash=hash_password(request.password),
                      company_name=request.company_name)
    session.add(founder)
    session.flush()
    conversation = redeem_access_code(session, request.code, founder)
    logger.info("event=signup founder_id=%s conversation_id=%s", founder.id, conversation.id)
    return SignupResponse(me=founder_me(founder), conversation_id=conversation.id), founder.id


def login(session: Session, request: LoginRequest) -> tuple[Me, UUID | None]:
    """The logged-in user and, for founders, the ID the session cookie carries."""
    email = normalize_email(request.email)
    if email == team_email():
        if hmac.compare_digest(request.password.encode(), config.secrets().team_password.encode()):
            logger.info("event=login role=team")
            return Me(role="team", name=email, company_name=None), None
        raise AppError(WRONG_LOGIN, "reason=login_failed account=team")
    founder = session.scalar(select(Founder).where(Founder.email == email))
    if founder is None or not verify_password(founder.password_hash, request.password):
        raise AppError(WRONG_LOGIN, f"reason=login_failed account={'founder' if founder else 'unknown'}")
    logger.info("event=login role=founder founder_id=%s", founder.id)
    return founder_me(founder), founder.id


def me(session: Session, role: Role, founder_id: UUID | None) -> Me | None:
    """The user of a session cookie, or None if its founder no longer exists (a reset database)."""
    if role == "team":
        return Me(role="team", name=team_email(), company_name=None)
    founder = session.get(Founder, founder_id) if founder_id else None
    return founder_me(founder) if founder else None
