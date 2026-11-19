"""The central config module: every constant and tunable value of the backend, the default
settings, and the secrets.

Part of every mechanism. Other modules read `config.NAME` and call `config.secrets()` at the moment
they need a value, never `from app.config import NAME`, so the tests can change any value with
`monkeypatch.setattr(config, ...)`. Nothing else in the backend reads environment variables or the
secrets file, and the scripts never parse the file either: they ask `python -m app.cli`.

The database has no password, on purpose: PostgreSQL runs with `trust` authentication inside the
compose network and publishes no port, so only the app's own containers can reach it (see
docker-compose.yml). The connection URL therefore contains no secret and lives here.
"""

from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

# --- Database ---------------------------------------------------------------------------
DATABASE_HOST = "db"        # the compose service of PostgreSQL
DATABASE_USER = "postgres"  # the image's default superuser, allowed in without a password (trust)
DATABASE_NAME = "app"       # must match POSTGRES_DB in docker-compose.yml; the tests use their own


def database_url(name: str | None = None) -> str:
    """SQLAlchemy URL of a database on the app's PostgreSQL server (psycopg 3 driver)."""
    return f"postgresql+psycopg://{DATABASE_USER}@{DATABASE_HOST}/{name or DATABASE_NAME}"


# --- Files ------------------------------------------------------------------------------
SECRETS_PATH = Path("/secrets/secrets.yaml")  # ./secrets is mounted at /secrets (docker-compose.yml)
# The context system's JSON documents (prompts, tool texts, FAQ, default catalog): see app/context.
CONTEXT_DOCUMENTS_DIR = Path(__file__).parent / "context" / "documents"

# --- Access codes -----------------------------------------------------------------------
ACCESS_CODE_VALID_HOURS = 24
ACCESS_CODE_LENGTH = 8
# Capital letters and digits without the look-alikes 0, O, 1 and I, so a code read aloud or typed
# from a message cannot be misread. 32 symbols and 8 places give about 10^12 codes.
ACCESS_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# --- Outside services -------------------------------------------------------------------
# Every call to an outside service has its own timeout below. The tests point these URLs at their
# fake outside world (tests/fakes.py); the backend itself has no test hooks.
OPENAI_API_URL = "https://api.openai.com/v1"
OPENAI_WS_URL = "wss://api.openai.com/v1"  # the sideband WebSocket of a Live session
SERPER_URL = "https://google.serper.dev/search"
KEY_CHECK_TIMEOUT_S = 10  # each request of the preflight checks (internet, OpenAI key, Serper key)

# --- The voice conversation -------------------------------------------------------------
LIVE_MODEL = "gpt-live-1"           # the voice agent; fixed, not a team setting
LIVE_CREATE_TIMEOUT_S = 15          # creating the Live session at START (the founder waits on it)
SIDEBAND_ATTACH_TIMEOUT_S = 5       # opening the sideband, at START and for a last session.close
# Our own limit for one conversation, well below the session limit of the Live API. A conversation
# takes about 10 to 15 minutes; one that reaches this limit ends as Unfinished (time limit).
CONVERSATION_TIME_LIMIT_S = 30 * 60
# After the goodbye, the session is closed once the agent has spoken and then nobody spoke for this
# long: the Live API has no "speech finished" event. It must stay clearly above the pauses between
# the agent's sentences, so the goodbye is never cut off.
GOODBYE_SILENCE_S = 2.5
# Closes at the latest this long after the goodbye message. Without follow-ups the agent still reads
# the summary (up to about a minute) before it says goodbye, so this stays well above that.
GOODBYE_MAX_WAIT_S = 120
END_WAIT_S = 3                      # how long the end route waits for the call's cleanup
# A summary longer than this is sent back to the note-taker to shorten: the voice agent reads the
# first one aloud from one commentary, which the Live API caps at 500 tokens. The final summary of the
# follow-up round replaces it in the success message and keeps the same limit.
SUMMARY_MAX_CHARS = 1200
# The note-taker must answer every request with a tool call; when it answers with text alone, the
# backend reminds it and lets it try again (app/ai/tools.py). At most this often per call, so a
# note-taker that keeps answering with text can never start an endless loop of reminders.
TOOL_REMINDERS_PER_CALL = 3

# --- The backend's AI calls (app/ai/structured.py: the review and the writing down) -----------
STRUCTURED_CALL_ATTEMPTS = 2          # after this many failed attempts the call gives up
STRUCTURED_CALL_TIMEOUT_S = 30        # one attempt; the founder hears the summary or waits meanwhile
STRUCTURED_CALL_RETRY_DELAY_S = 2

# --- Web search ------------------------------------------------------------------------
SEARCH_RESULT_COUNT = 5             # result snippets only: no page is loaded, so it stays fast
SEARCH_TIMEOUT_S = 4                # the founder waits for the answer

# --- Latency ---------------------------------------------------------------------------
# The reply time target (end of the founder's words to the start of the agent's reply), used in the
# log line that sums up a conversation's reply times.
REPLY_TIME_TARGET_MS = 1500

# --- The browser -----------------------------------------------------------------------
# Values the frontend needs, sent to it by GET /api/app-config, so the frontend hardcodes none.
CONNECTION_CHECK_TIMEOUT_MS = 5000  # each request of the device check (our server, OpenAI)
# START sends the browser's offer once it lists all of its network addresses (OpenAI takes no later
# ones). Without STUN servers this takes milliseconds; the limit only bounds a stuck browser.
ICE_GATHERING_TIMEOUT_MS = 3000
# The status shows „Spricht" while the agent's audio level (RMS of its samples, 0 to 1) is above
# this threshold, and for SPEAKING_HOLD_MS after it dropped below, so it does not flicker between
# words. The Live API has no events for speech starting or stopping.
SPEAKING_LEVEL_THRESHOLD = 0.02
SPEAKING_HOLD_MS = 600


# --- Languages, models and thinking levels ----------------------------------------------
# The values the team can choose on the settings page. schemas.py builds its Literal types from
# these keys, so validation, the API schema, the generated frontend types and the settings page's
# options all follow this one place. Every conversation stores the values it ran with, and the
# team's settings are stored too; both are checked against these options whenever they are read.
# So an option can only be removed while no stored conversation and no team setting uses it.
class LanguageConfig(BaseModel):
    """One conversation language. The interface itself is always German."""

    label: str  # what the settings page shows (German)
    name: str   # what the English prompts say ("Speak German.")
    voice: str  # the gpt-live-1 voice for this language; one matching voice per language


LANGUAGES = {
    "de": LanguageConfig(label="Deutsch", name="German", voice="juni"),
    "en": LanguageConfig(label="Englisch", name="English", voice="marin"),
}

# The note-taker and reviewer models, with their German labels. gpt-6-luna is OpenAI's recommended
# model for Responses delegation and the fastest; gpt-6.1-terra, OpenAI's fast and efficient model
# between Luna and Sol, thinks more thoroughly. Both accept every level of THINKING_LEVELS.
MODELS = {
    "gpt-6-luna": "GPT-6 Luna (schnell)",
    "gpt-6.1-terra": "GPT-6.1 Terra (gründlicher)",
}

# The reasoning efforts every offered model accepts, both in delegation and in the Responses API,
# lowest first. OpenAI's model pages and its SDK's delegation type disagree at the edges ("none",
# "minimal" and "max" are not accepted everywhere), so only the common ones are offered.
THINKING_LEVELS = {
    "low": "Niedrig",
    "medium": "Mittel",
    "high": "Hoch",
    "xhigh": "Sehr hoch",
}

# The shipped default settings, validated as `schemas.Settings` when they are seeded
# (app/team_values.py). Fast by default: the note-taker decides how quickly a founder's question is
# answered and how long the "writing down" waits take, so the fastest model at the lowest level.
DEFAULT_SETTINGS = {
    "language": "de",
    "agent_name": "Mira",
    "note_taker_model": "gpt-6-luna",
    "note_taker_thinking": "low",
    "reviewer_model": "gpt-6-luna",
    "reviewer_thinking": "low",
}


# --- Secrets ----------------------------------------------------------------------------
class SecretsError(RuntimeError):
    """secrets/secrets.yaml is missing or has the wrong shape. The message names the problem and its
    fix, and never contains a value from the file."""


class Secrets(BaseModel):
    """The shape of secrets/secrets.yaml; secrets/secrets.example.yaml is its committed template.

    Empty values load fine, because `python -m app.cli check-secrets` has to load an incomplete
    file to name what is missing. Each description is the fix that check prints for an empty value.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    openai_api_key: str = Field(description=(
        "Create a key at platform.openai.com (it needs access to gpt-live-1) and add it in secrets/secrets.yaml."))
    serper_api_key: str = Field(description="Create a key at serper.dev and add it in secrets/secrets.yaml.")
    session_secret: str = Field(description=(
        "Add a random value in secrets/secrets.yaml, for example the output of `openssl rand -hex 32`."))
    team_email: str = Field(description=(
        "Add the email the team logs in with (for example admin@example.com) in secrets/secrets.yaml."))
    team_password: str = Field(description="Add the team's password in secrets/secrets.yaml.")


@cache
def secrets() -> Secrets:
    """Load secrets/secrets.yaml once per process; a changed file takes effect after a restart.

    A function rather than an import-time load, so importing a module never reads the file: the CLI
    reports a broken file itself, and the tests replace this loader before any app exists.
    """
    try:
        raw = yaml.safe_load(SECRETS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SecretsError("secrets/secrets.yaml is missing. Run ./scripts/setup.sh first.") from None
    except yaml.YAMLError:
        raise SecretsError(
            "secrets/secrets.yaml is not valid YAML. Compare it with secrets/secrets.example.yaml.") from None
    try:
        return Secrets.model_validate(raw or {})
    except ValidationError as error:
        # Built from the field names and error types only: Pydantic's own message would repeat the
        # offending input, which can be a secret.
        problems = ", ".join(f"{'.'.join(map(str, e['loc'])) or 'file'} ({e['type']})" for e in error.errors())
        raise SecretsError(f"secrets/secrets.yaml has the wrong shape: {problems}. "
                           "Compare it with secrets/secrets.example.yaml.") from None
