"""The one login for both roles: signup (founders only, with an access code), login, logout, me.

Signup and login replace the whole session cookie (`security.start_session`), so a new login never
inherits anything from an earlier one. Signup logs the founder in at once.

Runs on the event loop; every database step (password hashing included) runs in a worker thread
through `run_db`.
"""

from fastapi import APIRouter, Request

from app import accounts
from app.db import run_db
from app.errors import ERROR_RESPONSES
from app.schemas import LoginRequest, Me, SignupRequest, SignupResponse
from app.security import end_session, session_login, start_session

router = APIRouter(prefix="/api/auth", tags=["auth"], responses=ERROR_RESPONSES)


@router.post("/signup")
async def signup(body: SignupRequest, request: Request) -> SignupResponse:
    response, founder_id = await run_db(accounts.signup, body)
    start_session(request, "founder", founder_id)
    return response


@router.post("/login")
async def login(body: LoginRequest, request: Request) -> Me:
    me, founder_id = await run_db(accounts.login, body)
    start_session(request, me.role, founder_id)
    return me


@router.post("/logout", status_code=204)
async def logout(request: Request) -> None:
    end_session(request)


@router.get("/me")
async def me(request: Request) -> Me | None:
    """Who is logged in, or null. A cookie whose founder no longer exists is cleared."""
    role, founder_id = session_login(request)
    if role is None:
        return None
    user = await run_db(accounts.me, role, founder_id)
    if user is None:
        end_session(request)
    return user
