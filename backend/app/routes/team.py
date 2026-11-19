"""The team's routes (`/api/team`). The whole router requires the team role.

The conversations are read only from the database, as plain request and response: the list holds
every conversation (the page searches and filters it in the browser), and the detail shows the same
view the founder sees plus the team-only details; „Aktualisieren" simply asks again.
Settings and catalog follow the one rule of app/team_values.py: every save and reset answers with
the full stored value, so the settings page always shows what was stored.

Runs on the event loop; every database step runs in a worker thread through `run_db`.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app import access_codes, conversations, team_values
from app.db import run_db
from app.errors import ERROR_RESPONSES
from app.schemas import (AccessCodeCreate, AccessCodeRow, Catalog, CatalogEdit, CreatedAccessCode, Settings, SettingsPage,
                         TeamConversationDetail, TeamConversationRow)
from app.security import require_team
from app.team_values import TEAM_CATALOG, TEAM_SETTINGS, settings_page

router = APIRouter(prefix="/api/team", tags=["team"], dependencies=[Depends(require_team)],
                   responses=ERROR_RESPONSES)


@router.get("/conversations")
async def list_conversations() -> list[TeamConversationRow]:
    return await run_db(conversations.list_team_conversations)


@router.get("/conversations/{conversation_id}")
async def conversation_detail(conversation_id: UUID) -> TeamConversationDetail:
    return await run_db(conversations.team_detail, conversation_id)


@router.get("/access-codes")
async def list_access_codes() -> list[AccessCodeRow]:
    return await run_db(access_codes.list_access_codes)


@router.post("/access-codes", status_code=201)
async def create_access_code(body: AccessCodeCreate) -> CreatedAccessCode:
    return await run_db(access_codes.create_access_code, body.email)


@router.get("/settings")
async def get_settings() -> SettingsPage:
    return settings_page(await run_db(team_values.read, TEAM_SETTINGS))


@router.put("/settings")
async def save_settings(body: Settings) -> SettingsPage:
    return settings_page(await run_db(team_values.save, TEAM_SETTINGS, body))


@router.post("/settings/reset")
async def reset_settings() -> SettingsPage:
    return settings_page(await run_db(team_values.reset, TEAM_SETTINGS))


@router.get("/catalog")
async def get_catalog() -> Catalog:
    return await run_db(team_values.read, TEAM_CATALOG)


@router.put("/catalog")
async def save_catalog(body: CatalogEdit) -> Catalog:
    return await run_db(team_values.save_catalog, body)


@router.post("/catalog/reset")
async def reset_catalog() -> Catalog:
    return await run_db(team_values.reset, TEAM_CATALOG)
