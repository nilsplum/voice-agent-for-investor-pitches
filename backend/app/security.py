"""Passwords, access codes and the session cookie: the building blocks of the one login.

- Founders' passwords are argon2 hashes. Access codes are SHA-256 hashes: a fast hash is enough,
  because a code is random (about 10^12 possibilities) and looked up by its hash.
- Emails and codes are normalized in exactly one place each (`normalize_email`,
  `normalize_access_code`), before anything compares or stores them.
- After a login, Starlette's signed session cookie carries the role (and the founder's ID). Every
  route declares the role it needs through `require_founder` or `require_team`, which read only
  the cookie and never the database.

Security is built the standard way and deliberately no further (no rate limits, password rules or
session revocation), because the app is a local MVP.
Runs on the event loop, except the password functions, which run inside database steps in worker
threads (`db.run_db`), because hashing takes noticeable CPU time.
"""

import hashlib
import secrets
from typing import Annotated
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware

from app import config
from app.errors import AppError
from app.schemas import Role

_password_hasher = PasswordHasher()

LOGIN_REQUIRED = "Bitte melden Sie sich an."
WRONG_ROLE = "Dafür haben Sie keine Berechtigung."


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def normalize_email(email: str) -> str:
    return email.strip().lower()


def generate_access_code() -> str:
    return "".join(secrets.choice(config.ACCESS_CODE_ALPHABET) for _ in range(config.ACCESS_CODE_LENGTH))


def normalize_access_code(code: str) -> str:
    return code.strip().upper()


def hash_access_code(code: str) -> str:
    """The stored form of a code; normalizes first, so letter case and surrounding spaces never matter."""
    return hashlib.sha256(normalize_access_code(code).encode()).hexdigest()


# --- Session cookie ---------------------------------------------------------------------
def install_sessions(app: FastAPI) -> None:
    """Starlette's signed session cookie with its defaults (HTTP-only, SameSite=Lax, 14 days)."""
    app.add_middleware(SessionMiddleware, secret_key=config.secrets().session_secret)


def start_session(request: Request, role: Role, founder_id: UUID | None = None) -> None:
    """After signup and login: a fresh session with the role, and the founder's ID for founders."""
    request.session.clear()
    request.session["role"] = role
    if founder_id is not None:
        request.session["founder_id"] = str(founder_id)


def end_session(request: Request) -> None:
    request.session.clear()


def session_login(request: Request) -> tuple[Role | None, UUID | None]:
    """The role and founder ID of the cookie; (None, None) without a login."""
    founder_id = request.session.get("founder_id")
    return request.session.get("role"), UUID(founder_id) if founder_id else None


async def require_founder(request: Request) -> UUID:
    """Route dependency: the logged-in founder's ID; 401 without a login, 403 for the team."""
    role, founder_id = session_login(request)
    if role is None:
        raise AppError(LOGIN_REQUIRED, "reason=login_required", status_code=401)
    if role != "founder" or founder_id is None:
        raise AppError(WRONG_ROLE, f"reason=wrong_role role={role}", status_code=403)
    return founder_id


async def require_team(request: Request) -> None:
    """Route dependency: passes for the team; 401 without a login, 403 for a founder."""
    role, _ = session_login(request)
    if role is None:
        raise AppError(LOGIN_REQUIRED, "reason=login_required", status_code=401)
    if role != "team":
        raise AppError(WRONG_ROLE, f"reason=wrong_role role={role}", status_code=403)


FounderId = Annotated[UUID, Depends(require_founder)]
