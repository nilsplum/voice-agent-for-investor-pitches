"""What the frontend gets from the backend besides the routes' data: the config values of
`GET /api/app-config`, and the types the browser needs although no route carries them."""

from typing import get_args

from app import config
from app.schemas import ToolName


async def test_the_app_config_hands_the_frontend_its_config_values(client):
    response = await client.get("/api/app-config")

    assert response.json() == {
        "access_code_valid_hours": config.ACCESS_CODE_VALID_HOURS,
        "openai_reachability_url": f"{config.OPENAI_API_URL}/models",
        "connection_check_timeout_ms": config.CONNECTION_CHECK_TIMEOUT_MS,
        "ice_gathering_timeout_ms": config.ICE_GATHERING_TIMEOUT_MS,
        "speaking_level_threshold": config.SPEAKING_LEVEL_THRESHOLD,
        "speaking_hold_ms": config.SPEAKING_HOLD_MS,
    }


async def test_the_api_schema_names_every_tool_for_the_browsers_status(client):
    schema = (await client.get("/api/openapi.json")).json()

    assert schema["components"]["schemas"]["ToolName"]["enum"] == list(get_args(ToolName))
