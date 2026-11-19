"""Public routes: what the frontend needs before anyone is logged in.

`GET /api/app-config` hands the frontend every value of the config module it uses (the access
code validity, the device check's and the call's timing and thresholds), so the frontend hardcodes
none of them. The device check also calls it to see whether our server is reachable.

Runs on the event loop; nothing here waits.
"""

from fastapi import APIRouter

from app import config
from app.errors import ERROR_RESPONSES
from app.schemas import AppConfig

router = APIRouter(prefix="/api", tags=["public"], responses=ERROR_RESPONSES)


@router.get("/app-config")
async def app_config() -> AppConfig:
    return AppConfig(
        access_code_valid_hours=config.ACCESS_CODE_VALID_HOURS,
        # The endpoint the preflight checks use too; any answer, even "unauthorized", proves that
        # OpenAI is reachable, and the browser's no-cors request never sees the answer itself.
        openai_reachability_url=f"{config.OPENAI_API_URL}/models",
        connection_check_timeout_ms=config.CONNECTION_CHECK_TIMEOUT_MS,
        ice_gathering_timeout_ms=config.ICE_GATHERING_TIMEOUT_MS,
        speaking_level_threshold=config.SPEAKING_LEVEL_THRESHOLD,
        speaking_hold_ms=config.SPEAKING_HOLD_MS,
    )
