"""The founder's routes (`/api/my`): only ever the logged-in founder's own conversations.

START and the end of a call go through the AI module (app/ai/live.py); both check ownership in
their first database step. Another founder's conversation is answered like a missing one (404).

Runs on the event loop; every database step runs in a worker thread through `run_db`, and the calls
to OpenAI at START are awaited while holding no database session.
"""

from uuid import UUID

from fastapi import APIRouter

from app import conversations
from app.ai import live
from app.db import run_db
from app.errors import ERROR_RESPONSES
from app.schemas import CodeRequest, ConversationSummary, ConversationView, EndRequest, StartRequest, StartResponse
from app.security import FounderId

router = APIRouter(prefix="/api/my", tags=["founder"], responses=ERROR_RESPONSES)


@router.get("/conversations")
async def my_conversations(founder_id: FounderId) -> list[ConversationSummary]:
    return await run_db(conversations.list_founder_conversations, founder_id)


@router.post("/conversations", status_code=201)
async def unlock_conversation(body: CodeRequest, founder_id: FounderId) -> ConversationSummary:
    """Unlocks a further conversation ("Neues Gespräch") with a code, redeemed exactly like at signup."""
    return await run_db(conversations.unlock_conversation, founder_id, body.code)


@router.get("/conversations/{conversation_id}")
async def my_conversation(conversation_id: UUID, founder_id: FounderId) -> ConversationView:
    return await run_db(conversations.founder_view, founder_id, conversation_id)


@router.post("/conversations/{conversation_id}/start")
async def start_conversation(conversation_id: UUID, body: StartRequest, founder_id: FounderId) -> StartResponse:
    """START: creates the Live session for the browser's WebRTC offer and returns OpenAI's answer.
    409 if the conversation is not Ready; 502 if OpenAI failed (the conversation stays Ready)."""
    return await live.start_call(founder_id, conversation_id, body.sdp)


@router.post("/conversations/{conversation_id}/end")
async def end_conversation(conversation_id: UUID, body: EndRequest, founder_id: FounderId) -> ConversationView:
    """The browser reports the end of its call, exactly once; the answer is the stored view, with
    every message that was said."""
    await run_db(conversations.check_owner, founder_id, conversation_id)
    await live.end_reported(conversation_id, body.reason)
    return await run_db(conversations.founder_view, founder_id, conversation_id)
