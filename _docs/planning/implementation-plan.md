# Voice Agent for Investor Pitches: Implementation Plan

This plan turns `_docs/planning/high-level-plan.md` into six commits that are implemented one after another. The order of authority is fixed: the requirements (`_docs/_requirements.md`) define what the app must do, the high-level plan says what we build and why, and this plan says how, in which order and in which files. If this plan ever seems to disagree with the high-level plan, the high-level plan wins and this plan is corrected.

**How to work with this plan**
- Implement one commit at a time, in order. Before each commit, read `AGENTS.md`, the README, the high-level plan, the whole section of the current commit, and "Target Architecture" below, which every commit builds on.
- Each commit section has four parts: **Summary**, **How it works**, **What users notice**, and **Implementation** (files, behaviour, UI, edge cases, tests, docs and cleanup). Implement exactly what the commit describes, nothing from later commits.
- Every commit ends green: `./scripts/test.sh` passes, the README and the high-level plan describe what exists, and every touched file has a correct docstring or header comment (AGENTS.md section 2: purpose, mechanisms, constraints, interactions; short, never repeating what the code says).
- Code comments, docstrings and published descriptions never cite this plan (no "Commit 4", no user story IDs like `F3`). They state the reason itself.
- Package versions and model names are never taken from this plan: pin the latest stable version of every dependency and check the current models at implementation time (AGENTS.md section 4).
- Every text a user reads is German and is given here word for word. Everything else in the repo (code, comments, prompts, docs, script output) is English. The README's team part is the one German document.
- The user story IDs (T1 to T3, F1 to F5, D1) refer to section 15 of the high-level plan.

---

## Decisions

The high-level plan already contains every decision that changes behaviour. This list explains them together with the implementation decisions behind this plan, so nobody adds back what was left out on purpose.

1. **The team has one shared login in the secrets file.** `team_email` and `team_password` sit in `secrets/secrets.yaml` in plain text, filled in by the developer (the committed template leaves both empty). There is no list of team members, no password hashing for the team and no script to add members. One login page and one login function serve everyone: the team's email opens the Team area, every other email is looked up among the founders. Signup refuses the team's email, so the two never collide. Founders keep their passwords as hashes in the database.
2. **The database has no password.** PostgreSQL runs with `trust` authentication inside the compose network and publishes no port, so only the app's containers reach it. The connection URL contains no secret and lives in the config module. No script ever reads or passes a database password.
3. **"Anything else?" is an ordinary catalog question.** No code knows it. The reviewer's instructions say to always select a question of this kind for a follow-up and to word it as a closing round. Phase 2 exists only when there are follow-ups: if the reviewer selects none, or the review fails, `submit_initial` completes the conversation itself and the agent says goodbye. One rule covers both cases, and no follow-up is ever added by code.
4. **Security is what the high-level plan asks for, built the standard way, and nothing more** (AGENTS.md: the structure matters, security does not). Built: founders' passwords as argon2 hashes; access codes as SHA-256 hashes, shown once, bound to an email, single use, valid for 24 hours; a signed session cookie that carries the role; founders reach only their own conversations; no secrets in logs. Deliberately not built: equal timing for unknown accounts, revoking sessions, CSRF measures beyond the cookie defaults, file permissions, read-only mounts, locking the browser's data channel, password rules, rate limits. Do not add them.
5. **How a conversation ends is decided by who ended it**, never by translating OpenAI's close reasons. There are three reasons: `stopped` (STOPP), `time_limit` (our own limit) and `connection_lost` (every end we did not cause). The backend writes the final state before it closes a session itself, and the first write wins. A connection lost before the founder's first words is a failed start: the conversation goes back to Ready, so the access code is not lost. The browser always reports the end of its call and shows the view the backend returns, so it never shows an outdated outcome.
6. **"Spricht" and "Hört zu" (speaking, listening) come from the agent's audio level in the browser.** The Live API has no events for speech starting or stopping. The same audio level hook drives the microphone meter of the device check. "Schlägt nach ..." and "Schreibt Ihre Antworten auf ..." come from the note-taker's tool events on the data channel.
7. **One transcript message is a run of consecutive transcript deltas from the same speaker.** The Live API has no turn IDs. A speaker change starts a new message. The backend saves each message when the speaker changes and at the end, and the browser builds the same messages live.
8. **The session ends after the goodbye once the agent has been silent for a short, configured time**, because the Live API has no "speech finished" event.
9. **Frontend types are generated from FastAPI's OpenAPI schema** (`openapi-typescript`), and the one API client is built on `openapi-fetch`, so a wrong path or body fails the type check. `start.sh` and `test.sh` regenerate the types, `test.sh` type-checks the frontend against them, and the regenerated file is committed with the change. Commit 2 corrects the matching sentence in AGENTS.md section 6, which still says the tests fail if the committed types are out of date (they cannot be, because `test.sh` regenerates them first).
10. **The database is reached one way everywhere.** Every route is `async def`, and every database step is a plain function `step(session, ...)` that runs in a worker thread through `run_db`. Nothing touches the database on the event loop, and nothing else blocks it: password hashing runs inside these steps too. The schema is managed with Alembic migrations.
11. **Languages.** The interface is German and addresses users formally ("Sie"). Prompts, tool texts and AI messages are English, because only the AI reads them. The language setting (German by default, or English) is the language the agent speaks, and it chooses the voice. Texts written for the team are German: the catalog and the reviewer's follow-up questions and explanations (the agent asks them in the conversation language). Records of what was said (transcript, answers, summary) are in the conversation language.

---

## Target Architecture

This is the end state after commit 6. Each commit creates its part of it.

### Repository layout

```
AGENTS.md, README.md, docker-compose.yml, .gitignore
_docs/                              the requirements and the plans
drafts/                             experiments (d1, d2) and the Live API spike (d3)
secrets/secrets.example.yaml        committed template of the secrets file, all values empty
secrets/secrets.yaml                git-ignored, created by setup.sh, filled in by the developer
scripts/setup.sh, start.sh, test.sh
scripts/helpers/common.sh           output helpers, the compose wrapper, backend commands
scripts/helpers/preflight.sh        every preflight check as its own function, one bundle per script
scripts/helpers/generate-types.sh   OpenAPI schema -> frontend/src/api/types.ts
backend/Dockerfile, pyproject.toml, alembic.ini
backend/migrations/                 Alembic environment and versions
backend/app/
  main.py            app factory: lifespan, routers, error handlers
  config.py          central config module (constants, defaults, secrets loader)
  cli.py             commands the scripts run in the backend container
  errors.py          AppError, the one error type, and its handlers
  logs.py            logging setup (one format for the whole backend)
  db.py              engine, session scope, run_db
  models.py          SQLAlchemy tables
  schemas.py         Pydantic models shared by API, database JSON, tools and reviewer
  security.py        password and code hashing, session cookie, role dependencies
  http.py            the one shared outbound HTTP client
  accounts.py        signup, login, who is logged in
  access_codes.py    create, list, redeem (the one redemption step)
  team_values.py     settings and catalog: seed, read, save, reset
  conversations.py   conversation states, questionnaire, transcript, views and lists
  search.py          Serper web search
  context/__init__.py            loads and validates the context system, renders prompts and texts
  context/documents/*.json       prompts, voice_agent, note_taker, reviewer, messages, tools, faq, catalog
  ai/live.py         Live session creation, the sideband, the call registry, ending a call
  ai/tools.py        tool definitions (argument models) and handlers
  ai/reviewer.py     the reviewer call
  ai/transcript.py   transcript messages and reply times from transcript deltas
  routes/public.py, routes/auth.py, routes/founder.py, routes/team.py
backend/tests/       pytest suite, fakes.py (the fake outside world), data/ (prepared questionnaires)
e2e/                 Playwright voice conversation test (only with --complete)
frontend/Dockerfile, package.json, vite.config.ts, tsconfig.json, index.html
frontend/src/
  main.tsx, App.tsx              router, route guards, AppProvider
  api/client.ts, api/types.ts    the one API client, generated types
  styles/tokens.css, base.css    colour tokens and base styles
  notifications/                 the one toast and confirmation module
  layout/                        page shell (header, area name, navigation, log out)
  labels.ts                      German labels of the backend's enum values (states, end reasons)
  audio/useAudioLevel.ts         audio level of any MediaStream (mic meter and agent speaking)
  call/useCall.ts                the WebRTC call to OpenAI and its events
  conversation/                  ConversationView, OutcomeMessage, StatusPill, transcript.ts, status.ts
  pages/                         Welcome, Signup, Login, NotFound, founder/*, team/*
```

### Containers
- `db`: PostgreSQL (latest stable major) with `POSTGRES_DB: app` and `POSTGRES_HOST_AUTH_METHOD: trust` (decision 2), data in the named volume `db-data`, a `pg_isready` healthcheck, no published port.
- `backend`: Python (latest stable), FastAPI with uvicorn and **one worker**, because the call registry lives in memory. On start it runs `alembic upgrade head`, then uvicorn with `--reload`. It mounts `./backend` at `/app` (development) and `./secrets` at `/secrets` (the secrets file and its template), and depends on a healthy `db`. Its healthcheck calls `GET /api/app-config` with Python's `urllib` (the slim image has no `curl`), so `compose up --wait` really waits until the app answers.
- `frontend`: Node (latest LTS), the Vite dev server on port 5173, the only published port. Vite proxies `/api` to `http://backend:8000`, so the browser sees one origin: the session cookie works without CORS, and `http://localhost:5173` is a secure context for the microphone.
- `e2e` (compose profile `e2e`, used only by `test.sh --complete`): built from `e2e/Dockerfile` on the official Playwright Python image, which installs the test's pinned packages. It shares the frontend container's network (`network_mode: "service:frontend"`), so Chrome opens `http://localhost:5173` like a developer's browser: a secure context for the microphone and accepted by Vite's host check, without special flags or settings.

### Backend conventions
- **Config module (`config.py`)**: typed module-level constants, grouped and commented: the database location, the URLs of OpenAI and Serper, timeouts, the access code validity and format, the conversation time limit, the goodbye silence, the review attempts, the search result count, the browser's audio thresholds, the models, the thinking levels, the languages with their voices, and the default settings. It also defines `Secrets` (Pydantic: `openai_api_key`, `serper_api_key`, `session_secret`, `team_email`, `team_password`) and `secrets()`, a cached loader for `/secrets/secrets.yaml`. It is a function, not an import-time load, so importing a module never reads the file: the CLI's `check-secrets` can report a broken or incomplete file itself, and the tests replace the loader before any app exists. `create_app()` calls it first (the session cookie needs the session secret), so a broken file stops the app with a clear message. A changed secrets file takes effect after a restart. Nothing else reads environment variables or the secrets file. Other modules read `config.NAME` and call `config.secrets()` at the moment they need them (no `from config import ...` of values), so tests can change them with `monkeypatch.setattr(config, ...)`.
- **Errors (`errors.py`)**: `AppError(user_message, log_message, ai_message=None, status_code=400)`. One handler logs `log_message` and returns `{"detail": user_message}` (the `ErrorResponse` model). FastAPI's request validation errors return „Bitte prüfen Sie Ihre Eingaben." with status 422, and the log gets only the names of the invalid fields. Any other exception is caught by one small HTTP middleware, logged with its type only (its text can contain founders' words) and answered with „Etwas ist schiefgelaufen. Bitte versuchen Sie es erneut." and status 500. It is a middleware and not an exception handler because Starlette re-raises an exception after its handler ran, and the server would then log the full traceback. The background work of a call follows the same rule (see Tools): an `AppError` gives the AI its `ai_message`, or the `generic_error` text from the context system if it has none, and anything else gives `generic_error` and a log line with the type only.
- **Database (`db.py`)**: synchronous SQLAlchemy 2 with psycopg 3. `session_scope()` is a context manager that commits or rolls back. `run_db(step, *args)` runs `step(session, *args)` inside its own `session_scope()` in a worker thread (`asyncio.to_thread`) and returns the result. Steps return plain values or Pydantic models, never ORM objects, because the session is closed once `run_db` returns. Every route and the whole conversation engine reach the database only through `run_db` (decision 10).
- **Logging (`logs.py`)**: `configure_logging()` runs once in the lifespan and sets one `key=value` line format (`event=... conversation_id=... duration_ms=...`). Modules use `logging.getLogger(__name__)`. Only IDs, states, counts, lengths and durations are logged, never founders' words, transcripts, prompts, search queries, secrets (including access codes and passwords) or exception texts.
- **Outbound HTTP (`http.py`)**: one `httpx.AsyncClient`, opened and closed in the lifespan, used for OpenAI's REST endpoints and Serper. Every call passes its own timeout from the config module.

### Data model (all tables created by Alembic migrations)

| Table | Columns | Notes |
|---|---|---|
| `founders` | `id` (UUID), `name`, `email` (unique, stored trimmed and lowercased), `password_hash`, `company_name`, `created_at` | The team is not stored here: its login is in the secrets file. |
| `access_codes` | `id`, `email` (normalized like founders' emails), `code_hash` (unique), `created_at`, `expires_at`, `used_at` (nullable), `conversation_id` (nullable FK) | The state (unused, used, expired) is computed from the columns, never stored. |
| `conversations` | `id` (UUID), `founder_id` (FK), `state` (`ready`, `in_progress`, `completed`, `unfinished`), `created_at`, `started_at`, `ended_at`, `end_reason` (`stopped`, `time_limit`, `connection_lost`, nullable), `settings` (JSONB, nullable), `questionnaire` (JSONB, nullable) | `settings` and `questionnaire` are the copies made at START, `null` while Ready. `ended_at` is set when the conversation becomes Completed or Unfinished. |
| `transcript_messages` | `id` (identity), `conversation_id` (FK, indexed), `speaker` (`founder`, `agent`), `text`, `start_ms`, `end_ms` | One row per finished message, in conversation order (`id`). A Ready conversation never has messages. |
| `team_values` | `key` (`settings`, `catalog`), `value` (JSONB), `updated_at` | The team-editable values, one row each. |

The JSONB columns are always read and written through their Pydantic models (`Settings`, `Questionnaire`, `Catalog`), never as loose dicts.

### Pydantic models (`schemas.py`), the one home of every shape
- `Literal` types: `Role` (`founder`, `team`), `ConversationState`, `EndReason`, `Speaker`, `AccessCodeState`, `ToolName`, and `Language`, `ModelName`, `ThinkingLevel`, which are built from the config module's lists, so the config module stays their only source.
- `Settings`: `language`, `agent_name`, `note_taker_model`, `note_taker_thinking`, `reviewer_model`, `reviewer_thinking`.
- `CatalogQuestion` (`id`, `topic`, `question`, `context`), `Catalog` (`questions`, `next_id`), and for saving `CatalogQuestionEdit` (`id: int | None`, `None` for a new question) and `CatalogEdit` (`questions`).
- `FollowUp` (`question`, `explanation`: what the reviewer selected), `QuestionnaireEntry` (`id`, `topic`, `question`, `context`, `answer: str | None`, `follow_up: FollowUp | None`, `follow_up_answer: str | None`: what the founder said about this question in the follow-up round, for any entry, with or without a selected follow-up), `Questionnaire` (`entries`, `summary: str | None`, `reviewed: bool | None`).
- `TranscriptMessage` (`speaker`, `text`, `start_ms`, `end_ms`). Its docstring holds the one definition of a message (decision 7).
- API models: `AppConfig`, `SignupRequest`, `SignupResponse` (`me`, `conversation_id`), `LoginRequest` (`email`, `password`), `Me` (`role`, `name`, `company_name: str | None`), `CodeRequest`, `ConversationSummary` (a row of "Meine Gespräche"), `ConversationView` (what the conversation view shows: `id`, `state`, `agent_name: str | None`, `created_at`, `started_at`, `ended_at`, `end_reason`, `transcript`, `summary`, with `summary` only when Completed), `StartRequest` (`sdp`), `StartResponse` (`sdp`, `agent_name`), `EndRequest` (`reason: Literal["stopped", "connection_lost"]`), `TeamConversationRow`, `TeamConversationDetail` (`view`, `founder_name`, `founder_email`, `company_name`, `settings`, `questionnaire`), `AccessCodeCreate`, `AccessCodeRow`, `CreatedAccessCode`, `Option` (`value`, `label`), `SettingsPage`, `ErrorResponse`.
- AI models: `ReviewFollowUp` (`question_id`, `question`, `explanation`), `ReviewOutput` (`follow_ups`), `SearchResult` (`title`, `link`, `snippet`), and the context system's document models (in `context/`).
- Every model and field that crosses into the frontend has a `description`, because the descriptions become the comments of the generated TypeScript types.

### API (all under `/api`; founder routes require the founder role, team routes the team role)

| Method and path | Purpose |
|---|---|
| `GET /app-config` | Public. Values the frontend needs from the config module. A success also proves the server is reachable. |
| `POST /auth/signup` | Founder signup with an access code: creates the account and its first conversation in one transaction and logs the founder in. |
| `POST /auth/login`, `POST /auth/logout` | The one login for both roles; logout. |
| `GET /auth/me` | Who is logged in, or `null`. |
| `GET /my/conversations`, `POST /my/conversations` | The founder's list; "Neues Gespräch" with a code. |
| `GET /my/conversations/{id}` | The founder's conversation view. |
| `POST /my/conversations/{id}/start`, `POST /my/conversations/{id}/end` | Start the call (SDP offer in, SDP answer out); report the end of the call. |
| `GET /team/conversations`, `GET /team/conversations/{id}` | All conversations, newest first; one conversation with the team-only details. |
| `GET /team/access-codes`, `POST /team/access-codes` | List; create for an email. |
| `GET /team/settings`, `PUT /team/settings`, `POST /team/settings/reset` | Agent settings. |
| `GET /team/catalog`, `PUT /team/catalog`, `POST /team/catalog/reset` | Question catalog. |

### Frontend conventions
- **API client (`api/client.ts`)**: one `openapi-fetch` client typed with the generated `paths`, `credentials: "same-origin"`, and one `unwrap` that every method uses: it returns the data or throws `ApiError` with the backend's `detail`. On 401 (the session ended) it sends the browser to `/login`. Components call only the named methods exported from this file.
- **Notifications (`notifications/`)**: one provider with `notify(text, kind)` for toasts and `confirm({title, text, confirmLabel, danger})`, which returns a promise and renders a native `<dialog>`. Nothing else shows transient feedback.
- **Colour tokens (`styles/tokens.css`)**: every colour is a CSS variable (`--color-bg`, `--color-surface`, `--color-text`, `--color-muted`, `--color-border`, `--color-primary` (blue, START), `--color-danger` (red, STOPP), `--color-success`, `--color-warning`, `--color-founder-bubble`, `--color-agent-bubble`). Components use only these variables.
- **Text**: German, formal ("Sie"), plain and short; no long dashes, no short dashes as a pause, ranges written as "10 bis 15". Longer explanations sit behind an info button. The German labels of the backend's enum values (conversation states, access code states, end reasons) live once in `labels.ts`, typed with the generated types, so a new value fails the type check until it has a label.
- **Icons**: `lucide-react` for the few icons (tutorial slides, device check rows, status, info, outcome, catalog buttons).

### The conversation at runtime

This is the mechanism commit 4 builds and commit 5 connects to the browser. It is described here once, and both commits refer to it.

**Start (`POST /my/conversations/{id}/start`)**
1. `run_db(claim_start, founder_id, id)`: one conditional update `ready -> in_progress` of this founder's conversation that writes `started_at`, the copy of the current settings and the new questionnaire (the current catalog questions, all answers empty). It returns what the next steps need (settings, questionnaire, founder name, company name). Not this founder's conversation: 404 „Dieses Gespräch gibt es nicht." Not Ready (another tab started it, or it already ended): 409 „Dieses Gespräch kann nicht mehr gestartet werden."
2. Render the prompts from the context system and build the phase 1 tools (see Tools). Nothing in this step waits.
3. `create_session(...)`: `POST {OPENAI_API_URL}/live/sessions` with the body below and `LIVE_CREATE_TIMEOUT_S`.
4. `attach(session_id)`: opens the sideband WebSocket `{OPENAI_WS_URL}/live/sessions/{id}/attach` with the API key and `SIDEBAND_ATTACH_TIMEOUT_S`.
5. Register a `LiveCall` in the in-memory registry (`conversation_id -> LiveCall`), start the sideband task with the open socket, and return the SDP answer and the agent's name.

If step 3 or 4 fails, `run_db(revert_start, id)` puts the conversation back to Ready, and the route answers 502 „Das Gespräch konnte nicht starten. Bitte versuchen Sie es erneut." The browser never receives an SDP answer, so no call exists. Attaching before the browser connects is how the API is meant to be used: the attach replays the last 3 seconds of events, so nothing from the first moments is missed.

```json
{
  "session": {
    "model": "gpt-live-1",
    "instructions": "<voice prompt>",
    "input": [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "<kickoff>"}]}],
    "audio": {"output": {"voice": "<voice of the language>"}},
    "delegation": {"type": "responses", "responses": {
      "model": "<settings.note_taker_model>",
      "instructions": "<note-taker prompt>",
      "tools": ["<get_questionnaire>", "<web_search>", "<submit_initial>"],
      "tool_choice": "auto",
      "parallel_tool_calls": false,
      "reasoning": {"effort": "<settings.note_taker_thinking>"}
    }}
  },
  "transport": {"type": "webrtc", "sdp": "<browser SDP offer>"}
}
```
The response carries `session.id` (opaque, kept unchanged) and `transport.sdp` (the answer). `parallel_tool_calls: false` keeps the note-taker's work in a simple order.

**The sideband task (`ai/live.py`, one asyncio task per call)**
- Reads events with `async for` under `asyncio.timeout(CONVERSATION_TIME_LIMIT_S)`.
- `session.started`: sends the kickoff as `session.commentary.append` with `delegation_id: null`, unless the spike showed that the `input` message alone makes the agent speak first.
- `session.input_transcript.delta` and `session.output_transcript.delta`: added to the call's `TranscriptBuilder` (`ai/transcript.py`). When the speaker changes, the finished message is saved with `run_db(save_message)`, and a founder message followed by an agent message gives one reply time, which is logged. The first founder delta sets `LiveCall.founder_spoke`. Every delta, from either speaker, sets the call's `spoke` event, which the goodbye watch waits on.
- `response.event` whose nested event is `response.output_item.done` with an item of type `function_call`: `run_tool` (see Tools) runs it as its own task (kept in `LiveCall.tasks`), so transcripts keep being saved while, for example, the review runs.
- `error`: logs its `type` and `code` only.
- `session.closed`: sets `LiveCall.closing` and ends the loop.
- Time limit reached: `end_call(id, "time_limit", call)`, and the loop ends.
- An unexpected exception in the loop is logged with its type only and ends the loop like a dropped socket.
- `finally` (every exit: `session.closed`, a dropped socket, the time limit, an unexpected exception, cancellation at shutdown): save the unfinished last message, `end_call(id, "connection_lost", call)` (it changes nothing if the conversation already has its final state, and it closes the session at OpenAI if that has not happened yet), cancel the call's running tasks, log the reply time count, median and maximum, remove the registry entry if it still points to this call, and close the socket.

The sideband reads events from one connection per call and never resumes reading after a drop. The only second connection is the short one `close_session` opens after a drop, and it reads nothing, so no deduplication is needed.

**One call, one owner**
Everything that ends or cleans up a call acts on that call's own `LiveCall` object and never looks it up again by conversation ID. After a failed start, the founder can press START again while the old call is still cleaning up, and the registry then already holds the new call for the same conversation. The old cleanup must never reset or close that new call.

**Ending a call (`end_call(conversation_id, reason, call)` in `ai/live.py`)**
The one way a call ends. The end route (with the call registered for the conversation, or none), the time limit and the sideband's `finally` (each with its own call) all use it:
1. If there is a call, the reason is `connection_lost` and the founder has not spoken yet, the start failed: `run_db(revert_start)`. In every other case: `run_db(finish_conversation, reason)`.
2. If there is a call, `close_session(call)`, so the founder's call ends together with the conversation.

**Closing the session (`close_session(call)` in `ai/live.py`)**
The one place that ends the session at OpenAI, used by `end_call` and the goodbye watch. Ending the session there also ends the founder's call: the browser receives `session.closed`, reports the end and shows the outcome message.
- It does nothing once `LiveCall.closing` is set (the backend already sent `session.close`, or OpenAI already reported `session.closed`), so calling it twice is harmless. Otherwise it sets `closing` first.
- While the sideband is open, it sends `session.close` over it.
- If the sideband has dropped (the socket closed without `session.closed`), it attaches once more (one try, `SIDEBAND_ATTACH_TIMEOUT_S`) only to send `session.close`, and closes that connection without reading from it. Without this, the founder would keep talking to an agent whose tools no longer work, while the conversation is already Unfinished.
- If that attach fails too, it logs the failure and gives up. The database is already correct, and the founder sees the outcome when they press STOPP.

`finish_conversation` turns an In progress conversation into Unfinished with the reason and `ended_at`, and leaves every other state alone. `revert_start` turns an In progress conversation back into Ready (clears `started_at`, `settings` and `questionnaire`, deletes its transcript messages such as a saved greeting) and leaves every other state alone. `save_message` never writes for a Ready conversation, so a message flushed after a revert is dropped. Because every write is conditional on In progress, the first one wins, and the backend always writes before it sends `session.close` itself.

**Ending from the browser (`POST /my/conversations/{id}/end`)**
The browser calls it exactly once whenever its call ends: with `stopped` after the founder confirmed STOPP, and with `connection_lost` when the call ended by itself (`session.closed` on the data channel, the data channel closed, or the peer connection `failed` or `closed`). The route checks ownership, takes the call registered for the conversation and runs `end_call`. It then waits for that call's sideband task to finish (at most `END_WAIT_S`, without cancelling it) before it reads and returns the `ConversationView`. The sideband's `finally` saves the message that was still in progress, so the returned view contains everything that was said, and no old call is still cleaning up when the founder presses START again. If no call is registered (for example after a restart), `end_call` only runs `finish_conversation`. After a goodbye the conversation is already Completed, so the reported `connection_lost` changes nothing.

**Restarts**
On every start, the lifespan marks all In progress conversations as Unfinished (`connection_lost`) with `sweep_after_restart`, because the registry is in memory and no call survives a restart. On shutdown (also the restarts of `--reload` and `docker compose stop`, which shut down gracefully), the lifespan cancels all sideband tasks and waits for them, so every call ends through its `finally` and the founder's call is closed. Only a hard crash skips this: the sweep still corrects the database, and the founder sees the outcome when they press STOPP. The README notes that `--reload` restarts during development end running conversations.

**Completion and goodbye**
A conversation becomes Completed in the same step that stores its last answers: `store_follow_up_answers` in phase 2, or `store_review` when the review selected no follow-ups. The tool then returns the `completed` text ("everything is written down: thank the founder and say goodbye"), and the call starts its goodbye watch: once the agent has spoken after the completion and then nobody (neither agent nor founder) has spoken for `GOODBYE_SILENCE_S`, the backend ends the session with `close_session`. Counting the founder's speech too means a founder who still says something after the goodbye is never cut off. `GOODBYE_MAX_WAIT_S` caps the whole wait. The watch is one of the call's tasks (`LiveCall.tasks`) and waits on the `spoke` event with timeouts, so nothing polls; whether the agent spoke is the transcript builder's current speaker.

**Tools (`ai/tools.py`)**
- Every tool call runs through one runner, `run_tool(call, item)`. It calls the tool's handler and catches every exception, so the note-taker always gets an answer: the handler's result, an `AppError`'s `ai_message` (or `generic_error`), or, for any other exception, `generic_error` plus a log line with the exception's type only. It logs the tool name and duration, then sends the output as `response.item.create` (`function_call_output` with the `call_id`) followed by `response.create`, because appending an item alone does not resume the note-taker. The goodbye watch catches unexpected exceptions the same way.
- All tools are built the same way, once per phase: `tool_model(name, fields)` creates a Pydantic model with `create_model(..., __config__=ConfigDict(extra="forbid"))`, where every field is a `str` (or `list[int]`) with a description. Its `model_json_schema()` is the tool's `parameters` (`"strict": true`), and the same model parses the arguments, so schema and parser cannot disagree.
- Field descriptions come from the context system (`tools.json`) for the fixed fields (`ids`, `query`, `summary`) and, for the answer fields, from the questionnaire filled into one of the three field templates of `tools.json` (an answer in phase 1; a follow-up or an addition in phase 2). The answer field of question `id` is named by one function, `answer_field(id)` (`question_{id}`), used both to build and to read the fields.
- `get_questionnaire(ids)` (both phases): the requested entries (all if `ids` is empty) as JSON: `id`, `topic`, `question`, `context` and, if present, the follow-up question with its explanation. Unknown IDs return an AI message with the valid IDs.
- `web_search(query)` (both phases): `search(query, language)` returns at most `SEARCH_RESULT_COUNT` results (`title`, `link`, `snippet`) as JSON. No results and failures return AI messages ("say you can't look that up right now").
- `submit_initial(question_{id}..., summary)` (phase 1):
  1. Parse. Invalid arguments return an AI message that names only the field names.
  2. Empty check: every answer and the summary must be non-blank after trimming. Otherwise the AI message lists the missing questions by ID and topic, for example "Questions 5 (Traktion) and 8 (Finanzierungsbedarf) have no answer yet. Ask the founder, then submit again." Nothing is stored.
  3. `run_db(store_initial)`: the answers and the summary go into the questionnaire, only if no answers were stored before. A second `submit_initial` (for example when the founder adds something while the answers are being written down) gets the `already_submitted` AI message ("everything is already written down; corrections come in the closing round") and changes nothing, so the summary is never read twice and two reviews never race.
  4. `session.commentary.append` with the `summary_commentary` text, which contains the stored summary, so the agent reads it aloud while the review runs.
  5. The review (`ai/reviewer.py`).
  6. `run_db(store_review, follow_ups, reviewed)`: stores the follow-ups and `reviewed`. Without follow-ups, the same step completes the conversation (decision 3).
  7. With follow-ups: `session.update` replaces `delegation.responses.tools` with the phase 2 set (`get_questionnaire`, `web_search`, and `submit_follow_up` with one field per questionnaire entry), and the tool returns the `follow_ups` text (the follow-ups in questionnaire order). Without: the goodbye watch starts, and the tool returns the `completed` text.
- `submit_follow_up(question_{id}...)` (phase 2) has a field for every entry, in questionnaire order. The field of an entry with a follow-up is described as that follow-up and must be answered; every other field is described as an optional addition to its question and may be empty. This lets the note-taker put anything the founder adds or corrects about another question into that question, instead of squeezing it into whichever follow-up was being asked. The handler parses, runs the empty check only on the entries with a follow-up, then `run_db(store_follow_up_answers)` (stores every non-empty field as its entry's `follow_up_answer` and completes), starts the goodbye watch and returns the `completed` text.
- The store steps are conditional on In progress; otherwise they raise an `AppError` with the `conversation_ended` AI message.

**Reviewer (`ai/reviewer.py`)**
One `POST {OPENAI_API_URL}/responses` with the reviewer model and thinking level from the conversation's settings, the `reviewer_instructions` prompt, the questionnaire (IDs, topics, questions, contexts, answers) as JSON input, and `text.format` set to the strict JSON schema of `ReviewOutput` (`ReviewOutput` and `ReviewFollowUp` forbid extra fields and have no defaults, as OpenAI's strict mode requires). The code keeps only follow-ups whose `question_id` is in the questionnaire, and only the first one per question, so "at most one per question" holds whatever the model returns. Every attempt has `REVIEW_TIMEOUT_S`, and a failed attempt is retried after `REVIEW_RETRY_DELAY_S`. After `REVIEW_ATTEMPTS` failed attempts, the result is "no follow-ups, `reviewed = false`".

**Web search (`search.py`)**
`POST {SERPER_URL}` with the `X-API-KEY` header, the body `{"q": query, "num": SEARCH_RESULT_COUNT, "hl": language}` and `SEARCH_TIMEOUT_S`. Only the organic results' `title`, `link` and `snippet` are returned (no page loading). The query is never logged.

**The browser side (`call/useCall.ts`)**
1. Create the `RTCPeerConnection`, add the track of the page's microphone stream (opened in the device check), create the data channel `oai-events` (before the offer, so it is part of it), create the offer and set it locally.
2. `api.startConversation(id, offer.sdp)`, then `setRemoteDescription({type: "answer", sdp})`. The remote track plays in an `<audio autoplay>` element whose output device is the speaker chosen in the device check (`setSinkId` where supported). If the start request fails (any error, including 409), no call exists: the page shows the error as a toast, reloads the view and renders it by its state.
3. The status is „Verbinde ..." until the data channel opens.
4. Data channel events go to two pure functions: `transcript.ts` (`appendDelta`, the same message rule as the backend) and `status.ts` (the tool activity). A nested `response.output_item.done` with a `function_call` sets the activity from the tool name. The next nested `response.created` of the same `delegation_id` clears it, because the note-taker's next response only starts after the backend returned the tool's output (the spike confirms this order).
5. The status shown is the activity if there is one, else „Spricht" while the agent's audio level (`useAudioLevel` on the remote stream) is above `speaking_level_threshold` (held for `speaking_hold_ms`, so it does not flicker between words), else „Hört zu".
6. Any end runs `handleEnd(reason)` exactly once: it mutes the agent's audio at once, reports the end with `api.endConversation` and waits for the returned view, and only then closes the peer connection (also if the report failed). Reporting first matters: closing first would make OpenAI end the session as lost, and the backend could record `connection_lost` before the browser's `stopped` arrives. The microphone stream is not touched: it belongs to the page (see commit 5), so a retry after a failed start uses the same working microphone.
7. No call outlives its page: leaving the page while a call runs (for example with the browser's Back button) runs `handleEnd("connection_lost")`.

### Testing approach
- **Backend (`backend/tests/`)**: pytest with pytest-asyncio (one session-wide event loop) against a real PostgreSQL database `app_test`, which the session fixture creates and migrates with Alembic. Tables are emptied before each test. `config.secrets` is replaced by a fixture with test values (team login, session secret, dummy keys), so the tests never read the developer's file. Each test builds the app with `create_app()` after that replacement and runs it in-process (`httpx.AsyncClient` with `ASGITransport` and its lifespan), so its sideband tasks run on the test's event loop.
- **The fake outside world (`tests/fakes.py`)**: one small Starlette app served by uvicorn on a free local port in the same event loop. It implements `POST /v1/live/sessions`, the WebSocket `/v1/live/sessions/{id}/attach`, `POST /v1/responses` and Serper's search endpoint. Tests point the config URLs at it and script it directly, for example `fake.reviews.append(...)`, `await fake.session(id).send(event)` and `await fake.session(id).next_command("response.create")`. The backend has no test hooks: it only sees different URLs.
- **Real services**: tests marked `real` run only with `--complete` and use the real URLs and keys. The voice conversation (`e2e/`) runs only with `--complete`.
- **Frontend**: `tsc --noEmit` (the type check against the generated types) and Vitest for the pure logic in `conversation/transcript.ts` and `conversation/status.ts`.

---

## Commit 1: Live API Spike

### Summary
A small script in `drafts/d3-liveDelegation/` runs a real Live session with a note-taker and fake tools and records how the Live API really behaves. It settles the open points of section 17 of the high-level plan before any app code depends on them. The findings go into the draft's README and into section 17.

### How it works
The script is the d2 draft (`drafts/d2-realtimeVoice/realtime_voice.py`, Live mode only) extended by a sideband and a note-taker. The terminal plays the browser: a WebSocket primary connection carries the microphone and the speaker, and a second WebSocket attaches as the sideband, as the backend will. The primary connection receives the same events as the browser's data channel (transcripts, delegation and nested Responses events, `session.closed`), so it stands in for the data channel. The WebRTC-specific parts (the create response with the SDP answer, the sideband attaching before the browser connects) are checked in the real browser in commit 5.

### What users notice
Nothing. Only the developer runs the spike, with headphones, by talking to it.

### Implementation
- **`drafts/d3-liveDelegation/spike.py`** (one file, same style and docstring as d2):
  - Primary: `session.start` with `instructions` (a short version of the voice rules), `input` (a developer kickoff message), the voice, and `delegation.responses` with `gpt-6-luna`, reasoning `low` and four fake tools with the real names and strict schemas: `get_questionnaire(ids)`, `web_search(query)`, `submit_initial(question_1, question_2, question_3, summary)` and `submit_follow_up(question_1, question_2, question_3)`, where only `question_2` is the follow-up and the other two are optional additions, as in the app. Three questions are enough.
  - Sideband: attaches to `/live/sessions/{id}/attach` after `session.started` and handles the tool calls as the backend will (nested `response.output_item.done` with a `function_call`, then `response.item.create` and `response.create`). `submit_initial` sends `session.commentary.append` with the summary it received, sleeps 8 seconds (the review), sends `session.update` with the phase 2 tool set and returns one follow-up for question 2. `submit_follow_up` returns "say goodbye".
  - Both connections write every event (with a wall clock timestamp and the connection's name) to `events-<timestamp>.jsonl` next to the script. Audio deltas are logged only by type and size.
  - After the goodbye, the sideband sends `session.close` once the agent has been silent for 2.5 seconds.
  - Options: `--language de|en` (default `de`, the app's default) and `--voice` (default per language; try `juni`, `nuri` and `flitz` for German, `marin` and the voices listed in the docs for English).
- **`drafts/d3-liveDelegation/README.md`**: how to run it (like d2: its own `.venv`, Python 3.13, `websockets` and `sounddevice`) and a findings table with one row per question below: verified or not, the evidence (event names from the log) and the consequence for the app.
- **Questions the run must answer** (each with the fallback the app uses if the answer is no):
  1. Does the note-taker see the whole conversation? Answer all three questions by voice, then check the `submit_initial` arguments in the log. Fallback: the backend writes the answers from its saved transcript with one Responses call that uses the same tool model (section 17 of the high-level plan expects this to work).
  2. Does the `session.update` tool swap take effect mid-session? The phase 2 call must be `submit_follow_up`. While answering the follow-up, also add something new about question 1: it must arrive in `question_1`, not in `question_2`, and `question_3` must stay empty. Fallback for the swap: the session is created with all four tools, and the tool of the wrong phase returns an AI message.
  3. Does the primary connection receive `session.delegation.*` and the nested `response.event`s, and which nested events mark the start and the end of a tool's work? Expected: `response.output_item.done` with the `function_call` starts it, and the next `response.created` of the same delegation (after the backend sent the output) ends it; the first `response.completed` arrives right after the function call, before the tool ran, so it cannot be the end. Fallback: the indicator is the agent's spoken notice only, and `status.ts` knows only „Hört zu" and „Spricht".
  4. Is the commentary summary read aloud while `submit_initial` is still pending, and does the follow-up wait until the summary is finished? Fallback: the `follow_ups` text starts with the summary, so the agent speaks it after the review.
  5. Are `start_ms` and `end_ms` of input and output deltas on the same session clock, and does `agent.start_ms - founder.end_ms` match the felt delay? Compare with the d2 latency readout. Also note how often short founder sounds ("mhm") interleave with the agent's speech and split its transcript messages (decision 7). Fallback for the timing: the reflected `session.output_audio.delta` timing on the sideband for the agent's start.
  6. Does the agent speak first with the `input` kickoff alone, with the commentary alone, or only with both? The app uses the smallest combination that works. (In the app the session is created before the browser's audio is connected; whether the greeting waits for that connection can only be seen in the browser, so commit 5 checks it.)
  7. Is the output transcript produced at speaking speed, and how long is the pause between the agent's last words before `submit_follow_up` returns and the start of its goodbye? `GOODBYE_SILENCE_S` (2.5 seconds as a start) must be clearly above that pause. Fallback for the speed: the reflected output audio's `end_ms` against the session clock.
  8. `expires_at` in `session.started` gives the session's duration limit. `CONVERSATION_TIME_LIMIT_S` (30 minutes) must stay below it.
  9. Do the German voices (`juni`, `nuri`, `flitz`) sound natural, and which one fits best? Which English voice sounds best? The two choices go into the config module.
  10. Which `reasoning.effort` values do `gpt-6-luna` and the second offered model (`gpt-6-sol`, or whatever is current) accept in delegation and in the Responses API? The levels every offered model accepts become `THINKING_LEVELS`, and the lowest one becomes the default.
- **`.gitignore`**: add `drafts/**/events-*.jsonl`.
- **`_docs/planning/high-level-plan.md` section 17**: replace each open point with its result in one line ("Verified: ..." or "Not supported, fallback used: ..."). If a fallback is used, update the sections it affects (7, 8 or 12) in the same commit, following the two passes of AGENTS.md section 2. Where a later commit says "per the spike", the draft's README is the reference.

### Done when
The findings table answers all ten questions, and section 17 of the high-level plan reflects them.

### Status: implemented, run pending
Implemented on 2026-11-16 (`drafts/d3-liveDelegation/`). The run with a real key and a real voice is still open (see Operator to-dos): the developer decided to run it later, together with the app. Until then, the findings table holds what OpenAI's documentation and SDK say about each question, its "Run" column is open, and section 17 of the high-level plan points to the spike instead of listing results. So the "Done when" above is reached only after the run.

### Decision log
1. **Verified without a key.** Because the real run comes later, the script was checked as far as possible without OpenAI: every event it sends was validated against the official SDK's Live schemas (`openai` 3.51.0, including a check for unknown fields), and a local mock Live server ran it end to end with fake audio devices. Covered: the sideband path, a refused attach, the tool swap, a replayed tool call handled once, the goodbye close (also delayed by founder speech), Ctrl+C, the effort probe, and a log that contains neither the key nor audio bytes. The mock harness was a throwaway and is not committed, because the spike itself is a throwaway too.
2. **The sideband may be refused, so the primary can take over.** OpenAI documents the sideband only for WebRTC and SIP sessions, while the spike's primary connection is a WebSocket (the terminal cannot do WebRTC). If the attach is refused, the primary connection answers the tools, so a run still answers all ten questions, and the log and the summary say which connection acted. The app's sideband is then first checked with the real browser call.
3. **Question 10 has its own mode, `--probe-efforts`.** A voice conversation cannot tell which thinking levels a model accepts. The probe starts one short Live session per model and level (it asks the note-taker once; the nested `response.created` means accepted, an `error` means rejected) and sends one streamed Responses API request each, without audio. It tests the union of the levels the docs and the SDK name, because they disagree (`minimal` and `max`), on `gpt-6-luna` and `gpt-6.1-sol`: OpenAI's model page marks `gpt-6-sol` as superseded by `gpt-6.1-sol`, which is "whatever is current" in question 10.
4. **Question 6 has its own option, `--kickoff input|commentary|both`.** OpenAI's greeting recipe uses both, so `both` is the default and the two short runs with one of them settle whether the app needs both.
5. **The goodbye close follows the app's rule, not only the agent's silence.** The spike closes once the agent spoke after the completion and then nobody spoke for 2.5 seconds (capped at 30 seconds), exactly like the app's goodbye watch in "Completion and goodbye". This tests the mechanism the app will use, including that a founder who still talks is not cut off.
6. **The log keeps timing, drops payloads.** Audio payloads are replaced by their size, but their other fields stay, because the sideband's reflected output audio carries `start_ms`/`end_ms` (the fallbacks of questions 5 and 7). The script's own commands are logged too (`"dir": "sent"`), because the order of commands and events is the evidence for questions 2, 4 and 7. Outgoing microphone chunks (50 per second) are not logged.
7. **Prompts follow OpenAI's Live prompting template.** The voice prompt uses the `Delegation policy:` block with `Generate <|SpawnThinking|> when:` and `Do not generate <|SpawnThinking|> when:`, as commit 4 plans for the app, so the spike also shows whether that template makes the agent hand over reliably.
8. **Small additions for a smooth run:** `--founder` and `--company` (fictional defaults), `--effort` (default `low`, as planned), an exit summary with the numbers several questions need (session limit, reply times, received event types per connection), and pinned `websockets==17.4` and `sounddevice==0.5.6` (the current releases).

### Notes for later commits (from the documentation research)
- **Commit 3:** the second offered model is `gpt-6.1-sol`, not `gpt-6-sol`. `THINKING_LEVELS` must come from the probe, because the docs (`none` to `max`) and the SDK's delegation type (`none`, `minimal` to `xhigh`) disagree.
- **Commit 4:** each `session.*.append` takes at most 500 tokens, so `summary_commentary` with its summary must stay well below that. A non-null `delegation_id` is rejected under Responses delegation, so `null` (as planned) is the only option. The attach replays the last 3 seconds of events with their original `event_id`.
- **Commit 5:** the browser's data channel receives every server event by default (`session.client.data_channel` allow-lists exist but are not used, decision 4). The WebRTC create returns HTTP 201 with `session.id` and `transport.sdp`, and the session config must omit `audio.format` for WebRTC.

### Operator to-dos
- Run the spike as described in `drafts/d3-liveDelegation/README.md` (a key in `drafts/d3-liveDelegation/.env` or `OPENAI_API_KEY`, headphones, well under $1), then hand the `events-*.jsonl` paths and your impressions (voice quality, felt delay) to the agent, which fills in the "Run" column and section 17 of the high-level plan.
- Commits 3 to 5 take values from the run (voices, thinking levels, the kickoff variant, `GOODBYE_SILENCE_S`, the status events). If they are implemented before the run, they start from the documented defaults above, and the run confirms or corrects them.

---

## Commit 2: Foundation, Login and Access Codes

### Summary
This commit creates the whole project skeleton and the first real feature on top of it:
- **Skeleton:** the containers, the three scripts with their preflight checks, the secrets file, the central config module, the error type, logging, the database with migrations, the frontend with its API client, notifications and colour tokens, the type generation and the test suite.
- **Feature:** the team logs in with its shared login and creates access codes. Founders sign up with a code, log in, see their conversations and unlock new ones with further codes.

### How it works
- **Scripts:** developers run `setup.sh`, `start.sh` and `test.sh`. Each script first runs its preflight bundle, then works inside the containers. The scripts never parse the secrets file: `setup.sh` only creates it from the template, and everything that needs its values asks the backend container (`python -m app.cli ...`), so the config module stays its only reader.
- **One login (decision 1):** one page, one endpoint, one function. If the email is the team's email from the secrets file, the password is compared with the team's password. Otherwise the founder is looked up and the password is checked against the stored hash. A failure gives the same message either way. A successful login writes the role (and the founder's ID) into Starlette's signed session cookie, and every route declares the role it needs through one dependency.
- **One redemption step:** an access code is a random 8-character code, stored only as a SHA-256 hash, bound to an email, valid for 24 hours and usable once. `redeem_access_code` checks the code, marks it as used and creates the Ready conversation in one transaction. Signup and "Neues Gespräch" both call it, so they cannot behave differently, and a rejected code creates nothing (at signup not even the account).
- **One way to the database (decision 10):** every route is `async def` and runs each database step through `run_db`.

### What users notice
- **Team:** opens `http://localhost:5173`, clicks „Anmelden", logs in with the team's email and password and lands on „Zugangscodes". Creates a code for a founder's email, copies it, and sees all codes with their state.
- **Founder:**
  - Opens the welcome page, signs up with the code and lands in „Meine Gespräche", where the new conversation is listed as „Bereit". Starting it comes in commit 5.
  - A wrong, expired, used or foreign code is refused with a plain message, and nothing is created.
  - Logs out and in again, and unlocks another conversation with a new code.
- **Developer:** runs `setup.sh`, fills in the four values it names (two API keys, the team's email and password), runs `start.sh` and opens `http://localhost:5173`. `test.sh` runs the backend tests and the frontend type check.

### Implementation: project and scripts
- **`.gitignore`**: add `secrets/secrets.yaml`, `node_modules/`, `frontend/src/api/.openapi.json` and `.pytest_cache/`, and keep the existing entries.
- **`secrets/secrets.example.yaml`**: the committed template, every value empty, each with a one-line comment:
  - `openai_api_key: ""` (create one at platform.openai.com; it needs access to `gpt-live-1`);
  - `serper_api_key: ""` (create one at serper.dev);
  - `team_email: ""` (the email the team logs in with, for example admin@example.com);
  - `team_password: ""` (the team's password, kept here in plain text on purpose: one shared login for a local MVP).
  - A header comment says that `setup.sh` copies this file to `secrets.yaml` and adds a generated `session_secret`, and that only the backend's config module reads the file.
- **`docker-compose.yml`**: the services `db`, `backend` and `frontend` as described under Containers, with a comment at `POSTGRES_HOST_AUTH_METHOD` explaining decision 2 and that `POSTGRES_DB` must match `DATABASE_NAME` in the config module. The backend's healthcheck and the `e2e` service come in commit 6, where `--wait` first needs them.
- **`backend/Dockerfile`**: Python slim image, installs the pinned dependencies from `pyproject.toml` including the test group (the tests run in this image), copies the code, default command `sh -c "alembic upgrade head && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --reload"`.
- **`backend/pyproject.toml`**: pinned `fastapi`, `uvicorn[standard]`, `pydantic`, `sqlalchemy`, `psycopg[binary]`, `alembic`, `argon2-cffi`, `itsdangerous`, `pyyaml`, `httpx`; test group: `pytest`, `pytest-asyncio`, `asgi-lifespan`. The pytest settings live here (`asyncio_mode = "auto"`, a session-wide event loop, the marker `real`).
- **`frontend/Dockerfile`**: Node LTS, `npm ci`, command `npm run dev -- --host 0.0.0.0`. Compose mounts `./frontend` at `/app` with an anonymous volume for `/app/node_modules`, so the image's installed packages are used; `compose_up` passes `--renew-anon-volumes`, so a rebuilt image's packages are always the ones in use.
- **`frontend/package.json`**: pinned `react`, `react-dom`, `react-router`, `openapi-fetch`, `lucide-react`; dev: `typescript`, `vite`, `@vitejs/plugin-react`, `openapi-typescript`, `@types/react`, `@types/react-dom`. Scripts: `dev`, `check` (`tsc --noEmit`) and `types` (`openapi-typescript src/api/.openapi.json -o src/api/types.ts`).
- **`frontend/vite.config.ts`**: the React plugin and the `/api` proxy to `http://backend:8000`.
- **`scripts/helpers/common.sh`**: the `set -euo pipefail` convention, the output helpers `info`, `success` and `fail`, `compose()` (runs `docker compose` from the repo root), `compose_up()` (`compose up --build --renew-anon-volumes "$@"`, the one way the app is started, so a rebuilt frontend image's packages are always the ones in use) and `backend_cli()` (`compose run --rm --no-deps -T backend python -m app.cli "$@"`).
- **`scripts/helpers/preflight.sh`**: one function per check, each printing a high-level reason and a practical fix on failure:
  - `check_docker_installed`, `check_docker_running`;
  - `check_secrets_file` ("secrets/secrets.yaml is missing. Run ./scripts/setup.sh first.");
  - `check_secrets_complete` (`backend_cli check-secrets`, which names each empty value and how to fill it);
  - `check_internet`, `check_openai_key`, `check_serper_key` (`backend_cli check-internet`, `check-openai-key`, `check-serper-key`).
  - Bundles: `preflight_setup` (Docker), `preflight_start` (Docker, secrets file, secrets complete, internet, both keys), `preflight_test` (Docker and the secrets file; with `--complete` also secrets complete, internet and both keys, because only the real tests need them).
- **`scripts/helpers/generate-types.sh`**: `backend_cli openapi > frontend/src/api/.openapi.json`, then `compose run --rm --no-deps frontend npm run types`.
- **`scripts/setup.sh`**: `preflight_setup`, `compose build`, then, only if `secrets/secrets.yaml` does not exist yet, copies the template to it and appends `session_secret: "<openssl rand -hex 32>"`. The file is created on the host, so it belongs to the developer, who edits it next; it is never overwritten. Then `check_secrets_complete`. It ends with the list of values still to fill in (if any) and the next step: `./scripts/start.sh`.
- **`scripts/start.sh`**: `preflight_start`, `generate-types.sh`, prints the URL, then `compose_up` in the foreground (Ctrl+C stops everything).
- **`scripts/test.sh [--complete]`**: `preflight_test`, `generate-types.sh`, `compose run --rm backend pytest [--complete]` (compose starts the database first because the backend depends on it), then `compose run --rm --no-deps frontend npm run check`. It stops at the first failing part and says which part failed. Commit 6 adds the voice conversation for `--complete`.

### Implementation: backend
- **`app/config.py`**: the constants of this commit, each with a comment on what it tunes:
  - Database: `DATABASE_HOST` (`db`), `DATABASE_USER` (`postgres`, the image's default user), `DATABASE_NAME` (`app`), and `database_url(name=DATABASE_NAME)`. The comment explains decision 2.
  - Files: `SECRETS_PATH` (`/secrets/secrets.yaml`).
  - Access codes: `ACCESS_CODE_VALID_HOURS` (24), `ACCESS_CODE_LENGTH` (8), `ACCESS_CODE_ALPHABET` (capital letters and digits without the look-alikes `0`, `O`, `1`, `I`).
  - URLs and timeouts: `OPENAI_API_URL`, `SERPER_URL`, `KEY_CHECK_TIMEOUT_S`.
  - `Secrets` and `secrets()` as described under Backend conventions.
- **`app/cli.py`**: the commands the scripts run, each a small function with exit code 0 (ok) or 1 (problem, message on stderr). Their output is for developers, so it is English:
  - `check-secrets`: loads the file as `Secrets` and names every empty value with its fix (for example "serper_api_key is empty. Create a key at serper.dev and add it in secrets/secrets.yaml.").
  - `check-internet`, `check-openai-key` (`GET {OPENAI_API_URL}/models`), `check-serper-key` (one search with one result). "Unreachable" and "key rejected" get different messages.
  - `openapi`: prints `create_app().openapi()` as JSON.
- **`app/errors.py`**: `AppError` and `install_error_handlers(app)` as described under Backend conventions. No error of this commit can reach the AI, so none sets `ai_message`; the generic AI text arrives with the context system's messages in commit 4.
- **`app/logs.py`**, **`app/db.py`**: as described under Backend conventions. `get_engine()` is cached and created on first use, so the tests can point it at the test database first.
- **`app/models.py`**: `Founder`, `AccessCode` and `Conversation`, with every column from the data model (including the ones commit 4 fills, because the conversation's states and fields are known now). **`migrations/`**: Alembic set up for `app.models.Base.metadata` and `config.database_url()`, with the first migration creating these three tables.
- **`app/security.py`**:
  - `hash_password` and `verify_password` (argon2 `PasswordHasher`) for founders.
  - `normalize_email` (trim, lowercase), `generate_access_code`, `normalize_access_code` (trim, uppercase) and `hash_access_code` (SHA-256 hex; a fast hash is enough because the code is random and looked up by its hash).
  - `require_founder` (returns the founder's ID from the session; 401 without a login, 403 for the team) and `require_team` (401 without a login, 403 for a founder). Both read only the cookie.
  - `install_sessions(app)`: Starlette's `SessionMiddleware` with the session secret and its default cookie settings.
- **`app/accounts.py`** (database steps for `run_db`):
  - Every email, including the team's email from the secrets file, goes through `normalize_email` before it is compared or stored.
  - `signup(session, request) -> SignupResponse`: refuses the team's email and an existing email with the same message, „Zu dieser E-Mail-Adresse gibt es schon ein Konto. Bitte melden Sie sich an.", then creates the founder and calls `redeem_access_code`, all in the one transaction of the step.
  - `login(session, request) -> (Me, founder_id | None)`: the team's email is compared with the team's password, every other email goes through the founders. Any failure: „Die Anmeldedaten sind falsch." with status 400, because 401 is reserved for a missing login and makes the API client open the login page.
  - `me(session, role, founder_id) -> Me`: the founder's name and company, or the team's email as `name` for the team.
  - The docstring states how the team login works and that its password is plain text on purpose (decision 1).
  - After signup and login, the route clears the session and writes `role` and `founder_id`.
- **`app/access_codes.py`**:
  - `create_access_code(session, email) -> CreatedAccessCode`: the plain code is returned once and never stored.
  - `list_access_codes(session)`: newest first, with the computed state.
  - `access_code_state(row, now)`: the one place that computes unused, used and expired.
  - `redeem_access_code(session, code, email) -> Conversation`: selects by hash `FOR UPDATE` (two simultaneous redemptions of one code cannot both succeed) and checks in this order, each failure an `AppError`:
    - not found: „Diesen Zugangscode gibt es nicht. Bitte prüfen Sie ihn auf Tippfehler."
    - another email: „Dieser Zugangscode wurde für eine andere E-Mail-Adresse erstellt."
    - used: „Dieser Zugangscode wurde schon benutzt."
    - expired: „Dieser Zugangscode ist abgelaufen. Bitte fragen Sie das Team nach einem neuen."
    On success it sets `used_at` and `conversation_id` and creates the conversation in state `ready`. The docstring states that this is the only way a code's state changes.
- **`app/conversations.py`**: in this commit `list_founder_conversations(session, founder_id)` (newest first, as `ConversationSummary`: `id`, `state`, `created_at`, `started_at`) and `unlock_conversation(session, founder_id, code) -> ConversationSummary` ("Neues Gespräch": reads the founder's email and calls `redeem_access_code`).
- **`app/schemas.py`**: the models this commit needs: `Role`, `ConversationState`, `AccessCodeState`, `AppConfig` (`access_code_valid_hours`), `SignupRequest` (`name`, `email`, `password`, `company_name`, `code`, with length limits), `SignupResponse`, `LoginRequest`, `Me`, `CodeRequest`, `ConversationSummary`, `AccessCodeCreate` (`email`), `AccessCodeRow` (`email`, `created_at`, `expires_at`, `state`, `conversation_id`), `CreatedAccessCode` (`code`, `email`, `expires_at`), `ErrorResponse`.
- **Routes** (all `async def`, every database step through `run_db`; every route declares `response_model` and its error responses with `ErrorResponse`, so the generated types know them):
  - `routes/public.py`: `GET /api/app-config`.
  - `routes/auth.py`: signup (also logs the founder in), login, logout, me.
  - `routes/founder.py`: `GET` and `POST /api/my/conversations`; the `POST` returns the new `ConversationSummary`.
  - `routes/team.py`: `GET` and `POST /api/team/access-codes`.
- **`app/main.py`**: `create_app()` with the lifespan (logging, a database check), sessions, the error handlers and the routers. There is no module-level `app`: uvicorn calls `create_app` as a factory, so importing the module has no side effects, and the tests and the `openapi` command build their own app.

### Implementation: frontend
- **`index.html`, `src/main.tsx`, `src/App.tsx`**: the React root; `AppProvider` loads `/app-config` and `/auth/me` once at start and offers `appConfig`, `me` and `setMe`; the routes `/`, `/signup`, `/login`, `/conversations`, `/team/access-codes` and a not-found page.
- **`RequireRole`**: wraps the founder routes and the team routes. Without a login it goes to `/login`, and with the other role it goes to that role's start page. The start page per role is one constant in `App.tsx` (founder: `/conversations`; team: `/team/access-codes`, which commit 6 changes to `/team/conversations`).
- **`styles/tokens.css` and `styles/base.css`**: the tokens from the conventions, a light theme, the system font, comfortable spacing, and the classes for buttons (`.button`, `.button-primary`, `.button-danger`), form fields, cards and state badges. Everything uses tokens.
- **`notifications/`**: `NotificationsProvider`, `useNotify()` and `useConfirm()` as described. Toasts sit bottom right and disappear after a few seconds. The confirmation dialog has a title, a short text, „Abbrechen" and the confirm button (red when `danger`).
- **`api/client.ts`**: as described under Frontend conventions. This commit's methods: `appConfig`, `me`, `signup`, `login`, `logout`, `myConversations`, `unlockConversation`, `accessCodes`, `createAccessCode`. `api/types.ts` is generated and committed.
- **`labels.ts`**: conversation states (`ready` „Bereit", `in_progress` „Läuft", `completed` „Abgeschlossen", `unfinished` „Nicht abgeschlossen") and access code states (`unused` „Unbenutzt", `used` „Benutzt", `expired` „Abgelaufen").
- **`layout/PageShell.tsx`**: a header with „Voice Agent for Investor Pitches", the area name („Gründerbereich" or „Teambereich"), the logged-in name (the founder's name, or the team's email) and „Abmelden" (logs out, then goes to `/`). The team area also gets its navigation, in this commit only „Zugangscodes". The content is centered with a readable maximum width and works down to phone width.
- **Pages**:
  - **Welcome (`/`)**: the heading „Willkommen beim Voice Agent for Investor Pitches", the letter „Hier führen Sie Ihr Erstgespräch mit uns als Investor: ein Sprachgespräch von etwa 10 bis 15 Minuten mit einem KI-Agenten. Er fragt nach Ihrem Startup und schreibt Ihre Antworten für unser Investmentteam auf. Sie brauchen den Zugangscode, den Ihnen das Team geschickt hat, einen ruhigen Ort und ein Mikrofon.", then „Registrieren" (primary) and „Anmelden". Logged-in users go to their start page.
  - **Signup (`/signup`)**: „Name", „E-Mail", „Passwort", „Firmenname", „Zugangscode" and the button „Registrieren", with browser validation (`required`, `type="email"`). The backend's message appears inline above the button, and the form keeps its values. On success, `setMe` is called and the founder goes to `/conversations`. Below the form: „Schon registriert? Anmelden".
  - **Login (`/login`)**: „E-Mail", „Passwort" and „Anmelden". The error appears inline. On success, `setMe` is called and the user goes to their role's start page. Below the form: „Noch kein Konto? Registrieren".
  - **Meine Gespräche (`/conversations`)**:
    - At the top, the card „Neues Gespräch" with the field „Zugangscode" and the button „Gespräch freischalten". On success: the toast „Gespräch freigeschaltet." and the list reloads. Errors appear inline in the card.
    - Below, the list, newest first: date and time (`started_at`, else `created_at`, formatted for `de-DE`) and the state badge. Empty: „Noch keine Gespräche."
    - The rows are not clickable yet.
  - **Zugangscodes (`/team/access-codes`)**:
    - The form „Code erstellen" with „E-Mail" and „Erstellen".
    - After creating, a highlighted box with the code in a large monospace font, „Kopieren" (clipboard, then the toast „Code kopiert.") and „Senden Sie diesen Code an die angegebene E-Mail-Adresse. Er wird nur jetzt angezeigt und ist 24 Stunden gültig." (the hours come from `appConfig`).
    - Below, the table, newest first: „E-Mail", „Erstellt", „Status" („Unbenutzt, gültig bis" with the date and time, „Benutzt" or „Abgelaufen").
  - **Not found**: „Diese Seite gibt es nicht." and the link „Zur Startseite".

### Tests
- `tests/conftest.py`: the test database fixture (creates `app_test` if it does not exist, upgrades it with Alembic, empties all tables before each test), the secrets fixture, the in-process app client, helpers to log in as the team and to sign up a founder with a fresh code, and the `--complete` option (without it, tests marked `real` are skipped).
- `test_auth.py`:
  - Signup creates the account and a Ready conversation, uses the code and logs the founder in.
  - A rejected code at signup creates no account.
  - An existing email and the team's email are refused with the same message.
  - Login as founder and as team; a wrong password and an unknown email give the same message.
  - `GET /api/auth/me` returns `null` after logout.
  - Role guards: 401 without a login, 403 on the other role's routes.
- `test_access_codes.py`:
  - The plain code appears once, and only its hash is stored.
  - Unused, used and expired (by setting `expires_at` in the past).
  - Single use; email binding.
  - Normalization: spaces and lowercase in the code, letter case in the email.
  - "Neues Gespräch" goes through the same redemption (a used code is refused there too).
- `test_errors.py`: an `AppError` returns only its user message; a validation error returns the generic German message; an unexpected exception returns the generic message, and neither the response nor the logs (including the server's own error log) contain its text.
- `test_cli.py`: the template with an added session secret (what `setup.sh` writes) parses as `Secrets`, so template and model cannot drift apart; `check-secrets` names the empty values.

### Docs and cleanup
- **README**: replace the current two lines with the two-part structure from section 14 of the high-level plan.
  - Team part (German): logging in, creating and sending access codes.
  - Developer part (English): requirements (Docker, an OpenAI key, a Serper key), `setup.sh` and the four values to fill in, `start.sh`, `test.sh`, the secrets file (changes take effect after a restart), what to do when a preflight check fails, and where things live (config module, error type, API client and generated types, notifications, colour tokens).
- **AGENTS.md section 6** (cross-language contract): replace "The tests fail if the committed types are out of date." with the real mechanism (decision 9): `start.sh` and `test.sh` regenerate the types, `test.sh` type-checks the frontend against them, and the regenerated file is committed with the change.
- No leftovers: no placeholder pages or unused helpers.
- Every new file starts with its docstring or header comment. Examples: `access_codes.py` states that redemption is the only state change; `accounts.py` states how the one login tells the team from founders; `config.py` states why the database has no password.

### Status: completed
Implemented on 2026-11-16. `./scripts/test.sh` passes (28 backend tests and the frontend type check). Beyond the plan's tests, a throwaway Playwright run in an isolated compose project (own containers and database, test secrets in a temporary folder, removed afterwards) clicked through every flow of this commit in Chrome: welcome page, team login with a wrong and the right password, creating and copying a code, signup with a wrong and with a normalized code, „Neues Gespräch" with a used and a new code, the role and guest guards, logout and login, the not-found page and phone width. It found one bug (logout, decision 6 below), which is fixed. The backend's log lines of that run contained no names, emails, passwords or codes.

### Decision log
1. **Versions (checked on 2026-11-16).** Python 3.15.2, Node 26 (the active LTS), PostgreSQL 18.7. The PostgreSQL 18 image keeps its data below `/var/lib/postgresql`, so the named volume is mounted there and not at the old `.../data`. Backend: FastAPI 0.163.1 on Starlette 1.10.0, SQLAlchemy 2.1.8, psycopg 3.3.9, Alembic 1.20.1, pytest 9.2 with pytest-asyncio 1.5. Frontend: React 19.3, React Router 8.5, Vite 8.3, openapi-fetch 0.17, openapi-typescript 7.13.
2. **TypeScript stays on 5.9.3, not 7.0.** TypeScript 7 (the native Go port) has no JavaScript compiler API yet, which openapi-typescript needs to generate the types (its peer dependency is TypeScript 5). Upgrade once openapi-typescript supports 7. The reason is written in `frontend/tsconfig.json`.
3. **Backend dependencies are PEP 735 dependency groups.** The backend is not a distributable package, and pip cannot install a project's `[project].dependencies` without building the project. `[dependency-groups]` with `app` and `test` (which includes `app`) is installed by `pip install --group test` with no build step. `starlette` is pinned too, because the code imports its session middleware directly.
4. **The test database is recreated at every test session** (the plan said "creates it if it does not exist"). Dropping and recreating `app_test` takes under a second and means the migrations are always tested from scratch, so an edited migration can never leave a stale test schema behind. A new test (`tests/test_database.py`) compares the migrated schema with the models, so neither can change without the other. The first migration was generated with Alembic's autogenerate and reviewed by hand.
5. **App state in its own file, and one guard for guest pages.** `AppProvider`, `useApp` and `START_PAGES` live in `src/AppProvider.tsx` instead of `App.tsx`, because the pages import them and `App.tsx` imports the pages (a circular import otherwise). Guest pages (welcome, signup, login) all send a logged-in user to their start page (the plan said this only for the welcome page); signup and login reach the start page through this same guard after setting the user, instead of navigating themselves.
6. **Logout reloads the app at `/`.** The browser test showed that `setMe(null)` followed by `navigate("/")` ends on `/login`: the founder page's role guard re-renders before the router's navigation applies. Logging out now loads the app afresh at the welcome page, exactly like the API client's 401 handling, so no state of the old login survives.
7. **Response models come from the return annotations** (`async def login(...) -> Me`), which FastAPI turns into the same `response_model` in the OpenAPI schema without writing the model twice. The error responses are declared once (`ERROR_RESPONSES` in `errors.py`) on every router.
8. **Routes that never wait are `async def` too** (decision 10). AGENTS.md's rule "a route that never awaits is a plain `def`" exists to keep blocking work off the event loop; the two routes that never await (`app-config`, `logout`) do no blocking work at all, so they stay `async def` and the rule "every route is `async def`" holds without exception.
9. **Small additions the plan's text did not name:** an `id` in `AccessCodeRow` (the table's row key); `ROLE_AREAS` in `labels.ts` (the area names are labels of the role values); `src/format.ts` (the one date formatter); `GET /api/docs` (FastAPI's API documentation, reachable through the proxy); the 401 and 403 messages („Bitte melden Sie sich an.", „Dafür haben Sie keine Berechtigung."); 409 for a taken email; a light email check (`x@y`, like the browser's `type="email"`) at signup and code creation, but not at login, so any team email works; „Zugangscode für {email}" in the code box, because the form is cleared after creating; „Noch keine Zugangscodes." for an empty list; a toast when copying fails; a retry screen when the app's first load fails; `--progress quiet` for the scripts' one-off containers, so their output shows only the checks.
10. **Logging.** `configure_logging` uses `basicConfig` (which leaves pytest's log capture alone) and routes uvicorn's own loggers to the same format. An `AppError`'s log message is a key=value fragment (`reason=access_code_used access_code_id=...`), logged as `event=request_refused status=... path=... reason=...`. The secrets loader builds its error messages from field names and error types only, because Pydantic's own messages would repeat the offending value, which can be a secret.
11. **Additional tests** for mechanisms the plan relies on: two simultaneous redemptions of one code (exactly one succeeds), the key checks' three outcomes (unreachable, rejected, other) without a key in the output, a broken and a missing secrets file, and the app config.

### Notes for later commits
- **Commit 6:** the official Playwright image matching the current `playwright` (1.65.2) is `mcr.microsoft.com/playwright/python:v1.65.2-noble`; it is already pulled on this machine.
- The compose file sets no project name on purpose: each worktree gets its own containers and database volume.

### Operator to-dos
- Fill in the four values `setup.sh` named in `secrets/secrets.yaml` (created on this machine with a generated session secret): `openai_api_key`, `serper_api_key`, `team_email`, `team_password`. Then `./scripts/start.sh` passes its preflight and starts the app.

---

## Commit 3: Settings, Question Catalog and the Context System

### Summary
The team can change the agent's settings (conversation language, agent name, models and thinking levels) and edit the question catalog, with „Auf Standard zurücksetzen" for both. This commit also creates the context system, which ships the default catalog. Commit 4 adds the prompts to it.

### How it works
- **One rule for every team-editable value** (`team_values.py`): a `TeamValue` names a database key, its Pydantic model and its shipped default. `seed_all` inserts each default once (`INSERT ... ON CONFLICT DO NOTHING`) when the backend starts, so the first launch copies the defaults, and later launches and software updates never overwrite the team's version. The app reads only the database. „Auf Standard zurücksetzen" writes the current shipped default back. Settings and catalog are two instances of this one mechanism.
- **Where the defaults live:** the default settings are values, so they live in the config module, together with the allowed languages (each with its voice), the offered models and the thinking levels. The default catalog is text, so it lives in the context system (`catalog.json`).
- **The allowed values have one source:** `schemas.py` builds the `Literal` types for languages, models and thinking levels from the config module, so validation, the OpenAPI schema, the generated frontend types and the options on the settings page all follow it.
- **Question IDs:** the catalog keeps a `next_id` counter. A new question gets the next ID, and IDs are never handed out twice, also not after removing questions or a reset. "Anything else?" is an ordinary question with ID 11 (decision 3).

### What users notice
- **Team:**
  - Opens „Einstellungen" and sees two cards: „Agent" and „Fragenkatalog".
  - Can rename the agent, switch the conversation language, choose the models and thinking levels, and add, edit, remove and reorder questions.
  - Saves each card on its own and can reset each card to the shipped default after a confirmation.
- Nothing changes for founders yet. Conversations use these values from commit 4 on.

### Implementation: backend
- **`app/config.py`** adds:
  - `LANGUAGES`: `{"de": LanguageConfig(label="Deutsch", name="German", voice=...), "en": LanguageConfig(label="Englisch", name="English", voice=...)}` with the voices chosen in the spike. `label` is what the settings page shows, `name` is what the English prompts say. `LanguageConfig` is a small Pydantic model defined in the config module itself, because `schemas.py` imports the config module.
  - `MODELS`: the offered note-taker and reviewer models, `gpt-6-luna` first (the current models at implementation time; the comment explains that `gpt-6-luna` is OpenAI's recommended delegation model).
  - `THINKING_LEVELS`: the levels the spike found accepted by every offered model, lowest first, each with its German label (for example `{"low": "Niedrig", "medium": "Mittel", "high": "Hoch"}`).
  - `DEFAULT_SETTINGS`: a dict validated as `Settings` by `team_values.py`: language `de`, agent name `Mira`, `gpt-6-luna` with the lowest thinking level for both note-taker and reviewer. The comment explains why the defaults are fast: the note-taker decides how fast founders' questions are answered and how long the "writing down" waits take.
- **`app/context/__init__.py`**: `context()` loads every JSON document in `context/documents/` once (cached), validates each with its Pydantic model and raises one clear error that names the file and the problem. The lifespan calls it at startup, before anything else uses it, so a broken document stops the app. This commit adds the `catalog.json` model, `default_questions`: a list of `CatalogQuestion` with unique IDs of 1 or more and non-empty texts, and `default_catalog()`, which returns `Catalog(questions=default_questions, next_id=highest ID + 1)`, so `next_id` is never written by hand.
- **`context/documents/catalog.json`**: the eleven default questions of section 7 of the high-level plan, in German, because the team reads and edits them (the agent asks them in the conversation language):
  1. Branche: „In welcher Branche ist Ihr Startup tätig?" Kontext: „Die Marktkategorie, zum Beispiel Health Tech, B2B-Software oder Climate Tech. Ein oder zwei Wörter reichen; bei mehreren Branchen zählt, welche an erster Stelle steht."
  2. Team: „Wer gehört zu Ihrem Gründungsteam, und welche Rollen und Erfahrungen bringen Sie mit?" Kontext: „Die Zahl der Gründer und Mitarbeitenden, wer wofür verantwortlich ist und welche Erfahrung dieses Team befähigt, das Unternehmen aufzubauen."
  3. Produkt: „Welches Problem lösen Sie, und wie löst Ihr Produkt es?" Kontext: „Das Problem der Kunden, die Lösung in einfachen Worten und was sie besser macht als die Art, wie das Problem heute gelöst wird."
  4. Entwicklungsstand: „Wie weit ist Ihr Produkt heute?" Kontext: „Idee, Prototyp, MVP, Pilot oder fertiges Produkt, dazu was schon gebaut ist und was noch fehlt."
  5. Traktion: „Welche Traktion haben Sie bisher?" Kontext: „Messbare Fortschritte wie Nutzer, zahlende Kunden, Umsatz, Wachstum, Pilotprojekte oder Absichtserklärungen, wenn möglich mit Zahlen. ‚Noch keine‘ ist eine gültige Antwort."
  6. Zielmarkt: „Wer sind Ihre Zielkunden, und wie groß ist Ihr Markt?" Kontext: „Das Kundensegment, die Region, in der das Startup beginnt, und die Marktgröße (zum Beispiel die Zahl möglicher Kunden oder das Marktvolumen)."
  7. Wettbewerb: „Wer sind Ihre wichtigsten Wettbewerber, und wie heben Sie sich von ihnen ab?" Kontext: „Direkte Wettbewerber und die Alternativen, die Kunden heute nutzen, und der Vorteil des Startups gegenüber ihnen."
  8. Finanzierungsbedarf: „Wie viel Kapital brauchen Sie, warum, und wofür setzen Sie es ein?" Kontext: „Der Betrag, der Grund für die Finanzierung zum jetzigen Zeitpunkt und die wichtigsten Verwendungszwecke (zum Beispiel Einstellungen, Produktentwicklung oder Vertrieb)."
  9. Geplante Runde: „Welche Finanzierungsrunde planen Sie, und wann?" Kontext: „Die Art der Runde (Pre-Seed, Seed, Series A, ...) und der geplante Zeitpunkt."
  10. Nächster Schritt: „Was ist der nächste große Meilenstein Ihres Startups?" Kontext: „Das nächste konkrete Ziel, auf das das Startup hinarbeitet (zum Beispiel ein Launch, die ersten zahlenden Kunden oder eine wichtige Einstellung), und bis wann es erreicht sein soll."
  11. Sonstiges: „Gibt es noch etwas, das Sie uns erzählen möchten?" Kontext: „Raum für Wichtiges, das die anderen Fragen nicht abgedeckt haben."
- **`app/schemas.py`** adds:
  - `Language`, `ModelName` and `ThinkingLevel` (`Literal`s built from the config module) and `Settings`, with `agent_name` trimmed and 1 to 40 characters long.
  - `CatalogQuestion`, `Catalog`, `CatalogQuestionEdit` and `CatalogEdit`: all texts trimmed and non-empty, with length limits; at least one question; the given IDs unique.
  - `Option` (`value`, `label`) and `SettingsPage` (`settings`, plus the options `languages`, `models` and `thinking_levels` from the config module).
- **`app/models.py`** and a migration: `TeamValueRow` (`team_values`).
- **`app/team_values.py`**:
  - `TeamValue`, `TEAM_SETTINGS`, `TEAM_CATALOG`, `seed_all`, `read`, `save` and `reset`.
  - `save_catalog(session, edit)`: keeps the given IDs, gives every new question (`id` is `None`) the next ID, and then sets `next_id` to at least the highest ID + 1, so no ID is ever handed out twice.
  - The catalog reset keeps `next_id = max(current, default)`, so a reset never brings back an ID that a removed question had.
  - The module docstring states the rule (seeded once, read only from the database, never overwritten by updates, reset copies the default) and that conversations copy these values at START.
- **`app/main.py`**: the lifespan validates the context system and runs `seed_all`.
- **`routes/team.py`**: `GET`/`PUT /api/team/settings`, `POST /api/team/settings/reset`, `GET`/`PUT /api/team/catalog` and `POST /api/team/catalog/reset`. Each returns the full `SettingsPage` or `Catalog`, so the UI always shows what was stored.

### Implementation: frontend
- **Team navigation**: adds „Einstellungen".
- **Einstellungen (`/team/settings`)**: two cards, each its own form with „Speichern" (disabled until something changed) and „Auf Standard zurücksetzen" (secondary, with confirmation). After saving or resetting, the card shows the returned values, and the toast „Gespeichert." or „Auf Standard zurückgesetzt." appears. Backend errors appear inline at the top of the card. An info button next to the page title explains: „Änderungen gelten ab dem nächsten Gespräch. Laufende und vergangene Gespräche behalten ihre Einstellungen und Fragen."
  - **Card „Agent"**: „Name des Agenten", „Gesprächssprache" (select with the language labels), „Protokollant: Modell" and „Protokollant: Denkstufe", „Prüfer: Modell" and „Prüfer: Denkstufe" (selects with the options from `SettingsPage`). Two info hints: the note-taker is „Die KI im Hintergrund, die nachschlägt und die Antworten aufschreibt.", the reviewer „Die KI, die die Antworten prüft und Rückfragen auswählt." Reset confirmation: title „Auf Standard zurücksetzen?", text „Die Agent-Einstellungen werden auf den Standard zurückgesetzt. Ihre Änderungen gehen verloren.", confirm button „Zurücksetzen" (red).
  - **Card „Fragenkatalog"**: one block per question, in order, with „Thema" (input), „Frage" (textarea) and „Kontext" (textarea, with the info hint „Was eine vollständige Antwort abdeckt. Der Agent nutzt das, um die Frage zu erklären, der Prüfer, um die Antwort zu prüfen."), plus the icon buttons „Nach oben", „Nach unten" and „Entfernen" (removal is local until „Speichern"). „Frage hinzufügen" adds an empty block at the end. All fields are `required`. Every question behaves the same; there is no locked row. Reset confirmation: the same as the agent card with the text „Der Fragenkatalog wird auf den Standard zurückgesetzt. Ihre Änderungen gehen verloren."
- **`api/client.ts`**: `settings`, `saveSettings`, `resetSettings`, `catalog`, `saveCatalog`, `resetCatalog`.

### Tests
- `test_team_values.py`:
  - The first start seeds both values; a second seeding after an edit keeps the edit.
  - Saving: an empty question, duplicate IDs, an empty catalog, an unknown model and an unknown thinking level are refused.
  - New questions get new IDs, and removing and adding never reuses an ID.
  - Both resets restore the defaults, and the catalog reset keeps `next_id`.
  - "Anything else?" can be edited and removed like any other question.
  - The team role is required.
- `test_context.py`: the shipped documents load; a broken document (written to a temporary directory) fails with a message that names the file.

### Docs and cleanup
- **README**:
  - Team part (German): changing the settings and the catalog, what „Auf Standard zurücksetzen" does, and when changes apply.
  - Developer part: the context system (where it lives, how it is validated) and the rule for team-editable values.
- **High-level plan**: section 9 matches what was built (models, thinking levels and voices from the spike).

### Status: completed
Implemented on 2026-11-16. `./scripts/test.sh` passes (50 backend tests and the frontend type check). Beyond the plan's tests, a throwaway Playwright run in an isolated compose project (removed afterwards) used the settings page in Chrome: the navigation, all info buttons, saving and reloading the agent card (trimmed name, language, model, thinking level), both reset confirmations (cancel and confirm), moving, removing and adding questions (the new one is focused and gets ID 12), the browser's required-field check, the catalog reset keeping the ID counter, and phone width without horizontal scrolling. No console errors, and the backend logged only events and keys.

### Decision log
1. **The offered models are `gpt-6-luna` and `gpt-6.1-sol`.** OpenAI also released `gpt-6-astra` (September 2026, its most capable model). It is not offered: its API access is still rolled out in stages, it is slower than a voice note-taker should be, and the spike's effort probe does not cover it. Adding it later is one line in `config.MODELS` once the probe confirms its levels.
2. **The thinking levels are low, medium, high and xhigh** („Niedrig", „Mittel", „Hoch", „Sehr hoch"): the levels both models accept according to both OpenAI's model pages and the SDK's delegation type (`none` and `minimal` are missing for `gpt-6.1-sol`, `max` is missing in delegation). So the lowest level, and the default, is `low`. The spike's `--probe-efforts` run confirms or corrects this list.
3. **The voices are `juni` (German) and `marin` (English)**, the spike's documented defaults, until the spike's voice comparison decides.
4. **`MODELS` maps each model to its German label, like `THINKING_LEVELS`.** The settings page then gets every choice in one shape (`Option`: value and label) from the config module, and the frontend lists no value itself.
5. **One `TeamValue` mechanism with a reset hook.** `reset_value` says what a reset stores: the shipped default, and for the catalog the default with `next_id = max(current, default)`. Seeding is one `INSERT ... ON CONFLICT DO NOTHING` per value. `save_catalog` numbers new questions from `max(next_id, highest given ID + 1)`, so even an ID the client invents cannot collide with a new one, and catalog save and reset lock the row, so two simultaneous saves cannot hand out the same ID.
6. **The settings routes build `SettingsPage` on the event loop** (`settings_page(settings)`, a pure function), around the database step that reads, saves or resets the settings. So `read`, `save` and `reset` stay generic for both values.
7. **The context loader is generic.** `Context` has one field per document (named like the file), so validation errors start with the document's name; a missing or unknown file is an error too. `load_context(directory)` is what the tests call with a temporary copy, and the location is `config.CONTEXT_DOCUMENTS_DIR`. The separate database check of the lifespan was removed: seeding is the app's first query and fails the same way.
8. **Frontend:** one hook, `pages/team/useTeamValue.ts`, gives both cards the same behaviour (load, draft, „Speichern" only when changed, reset after confirmation, inline errors, toasts), mirroring the backend's one rule. The info button (`layout/InfoButton.tsx`) opens its explanation as a full-width line below its row instead of a floating popover, so it never overflows a phone screen. The text length limits are not repeated in the frontend (the backend refuses too long texts with the generic message), so they stay in one place. Questions are numbered by position („Frage 1"); their IDs are not shown.
9. **The info hints of the note-taker and the reviewer sit on their model fields.** The role-guard checks of the new routes extend the existing role-guard test in `test_auth.py` instead of a second guard test, so one test covers every team route.

### Deviations
- The plan lists the role check under `test_team_values.py`; it is in `test_auth.py` with all other role guards (decision 9).

### Inconsistencies found
- High-level plan section 9 said "thinking at the lowest level". For `gpt-6-luna` alone that would be `none`, but `gpt-6.1-sol` does not accept it, and the settings only offer levels every model accepts, so the lowest offered level is `low`. Section 9 now says so.
- Removing an offered model or level from the config module later would make the team's stored settings invalid. The comment above `LANGUAGES` in the config module says that the team's settings must then be changed or reset; past conversations keep their own copies.

### Operator to-dos
- None new. The spike run (Commit 1) confirms or corrects the voices and thinking levels; a change is one edit in the config module, followed by „Auf Standard zurücksetzen" in the Team area for an existing database.

---

## Commit 4: The Conversation Engine (Backend)

### Summary
The backend can run a whole conversation:
- It starts a Live session for a Ready conversation and attaches to it through the sideband.
- It saves the transcript and runs the four tools.
- It has the answers reviewed and swaps the tools for the follow-ups, or completes the conversation directly when there are none.
- It completes the conversation and ends the session after the goodbye.
- It handles every early end, treats a connection lost before the founder spoke as a failed start, and measures the reply times.

All prompts, tool texts, the FAQ and the AI messages move into the context system. The browser side follows in commit 5. This commit is fully tested against the fake outside world.

### How it works
Everything in "The conversation at runtime" (Target Architecture) is built here. Read it fully before starting, plus the spike's findings in `drafts/d3-liveDelegation/README.md`. Wherever the spike chose a fallback, that fallback replaces the main path described there. In short:
- **START:** claims the conversation (Ready to In progress, with the copies of settings and questionnaire), creates the Live session (voice prompt, kickoff, voice of the language, note-taker with the phase 1 tools), attaches the sideband, starts the sideband task and returns the SDP answer. If OpenAI fails, the conversation goes back to Ready.
- **The sideband task:** sends the kickoff once the session started, turns transcript deltas into messages (saved on every speaker change) and reply times (logged), notes when the founder first spoke, runs every tool call as its own task, enforces the time limit, and on every exit leaves the conversation in its final state.
- **Phases:** `submit_initial` stores the answers and the summary, lets the agent read the summary aloud, runs the review and stores its result. With follow-ups it swaps the tools and hands them to the agent; without, the conversation is complete. `submit_follow_up` stores the last answers and completes the conversation. After the goodbye, the backend closes the session.
- **Ending:** one `end_call` serves the end route, the time limit and the sideband's exit. A connection lost before the founder spoke puts the conversation back to Ready; every other end goes through `finish_conversation`, where the first write wins. Then `close_session` ends the session at OpenAI, attaching once more if the sideband dropped, so the founder's call never outlives its conversation. The startup sweep finishes conversations a crash cut off.

### What users notice
Nothing in the browser yet: the founder's START button comes in commit 5. The founder's view endpoint already exists and is used there.

### Implementation: context system
- **`context/documents/prompts.json`**: maps each prompt name to the ordered list of entries it consists of, each written as `document.entry`:
  - `voice_instructions`: `voice_agent.role`, `voice_agent.style`, `voice_agent.flow`, `voice_agent.delegation`, `voice_agent.founders_questions`, `voice_agent.faq`, `voice_agent.questionnaire`;
  - `voice_kickoff`: `voice_agent.kickoff`;
  - `note_taker_instructions`: `note_taker.role`, `note_taker.answers`, `note_taker.search`, `note_taker.reporting`;
  - `reviewer_instructions`: `reviewer.rules`.
- **Documents** (texts in English, because only the AI reads them). `voice_agent.json`, `note_taker.json`, `reviewer.json` and `messages.json` are entry documents (`{"entries": {"name": "text"}}`). `tools.json`, `faq.json` and `catalog.json` have their own validated shapes.
  - `voice_agent.json`:
    - `role`: you are {agent_name}, the voice agent of an investor in startups, in the first conversation with {founder_name}, founder of {company_name}; speak {language} (the language's English `name` from the config module), and follow the founder if they switch language.
    - `style`: warm, natural, short turns of one to three sentences, one question at a time, no lists or URLs read aloud, stop and listen when interrupted; in German, address the founder formally with "Sie".
    - `flow`: the steps of section 7 of the high-level plan from the agent's point of view:
      - asking the questions in order, skipping questions already answered in full, asking only for the missing part of a partial answer;
      - no repetition unless asked, no follow-ups of its own, always returning to the questionnaire, rephrasing only when not understood;
      - when every question has an answer, handing over the writing down;
      - reading the summary as a statement when it arrives ("Here is what I've written down: ...") and finishing it before anything else;
      - then asking only the given follow-ups, one at a time in the given order ("Coming back to your traction: ..."); if the founder adds or corrects something about another question, accepting it briefly and moving on without asking more about it; when every follow-up has an answer, handing over the writing down again;
      - when the note-taker reports that everything is written down, thanking the founder, saying the team will be in touch, and saying goodbye.
    - `delegation`: the trigger list (`Generate <|SpawnThinking|> when:` as OpenAI's prompting guide prescribes):
      - at the start, to look up {company_name};
      - when the founder asks a valid general question that the FAQ does not answer;
      - when every question has an answer, to write everything down;
      - when every follow-up has an answer, to write everything down;
      - when it needs to reread questions.
      It also says to acknowledge at once ("Let me look that up." or "I'm writing everything down, one moment.") and to keep the conversation going while waiting.
    - `founders_questions`:
      - answer only valid questions (the conversation, the startup, the investor, the process) and politely decline others;
      - process questions only from the FAQ;
      - general information only from the search results, naming the source;
      - if neither has it, say honestly that you cannot provide or do not know this information, and never make anything up;
      - never promise anything on the investor's behalf, never rate the startup.
    - `faq`: "Questions about this process are answered only from these answers:" followed by {faq}.
    - `questionnaire`: "Ask these questions in this order:" followed by {questionnaire}.
    - `kickoff`: begin now; greet {founder_name} by name, mention {company_name}, explain the conversation (about 10 to 15 minutes, one question at a time, follow-ups at the end), say you are quickly looking up {company_name} online and hand that over, and ask whether there are any important questions before starting.
  - `note_taker.json`:
    - `role`: you work in the background for the voice agent, you are the only one who calls tools, and you report back in short sentences the agent can say.
    - `answers`:
      - write every answer in the founder's own words and in the conversation language, cleaned of fillers and repetitions;
      - collect everything the founder said about a question, wherever in the conversation it was said;
      - never invent anything; write a declined question as declined;
      - write the summary as a short statement of four to six sentences in the conversation language, without judgement;
      - in the follow-up round, write each follow-up answer into its own question's field, and anything the founder added or corrected about another question into that question's field; leave a field empty if nothing was said about its question in this round; every piece of information goes to the question it belongs to, never into a field just because that field's follow-up was being asked.
    - `search`: one search per question; at the start, search for the company name; never put confidential details from the conversation into a query; use startup results only as background and ignore them if they describe another company; report general answers with the source's name.
    - `reporting`: pass on tool results and AI messages faithfully; after `submit_initial`, pass on the follow-ups exactly in the given order, or the instruction to say goodbye.
  - `reviewer.json`:
    - `rules`:
      - read every answer against its question, its context and the other answers;
      - select a follow-up only when information the context asks for is missing, vague or contradictory;
      - at most one per question, and few in total; never for an answer the founder declined;
      - always select a question that invites the founder to add anything (like "Is there anything else you'd like to tell us?"), worded as a closing round, for example "Before we finish: is there anything you'd like to add or correct?", so the founder gets the last word and can correct the summary;
      - write the follow-up questions and the explanations in German, because the team reads them (the agent asks them in the conversation language); the explanation says what is missing or unclear;
      - never judge the startup.
  - `tools.json`: per tool, the `description` (what it does, when to call it, one short example) and the descriptions of its fixed fields (`get_questionnaire.ids`, `web_search.query`, `submit_initial.summary`). It also holds the three templates for the generated answer field descriptions: `answer_field` for phase 1 ("{topic}: {question} Covers: {context}"), and for phase 2 `follow_up_field` ("{topic}, follow-up, must be answered: {follow_up_question} Missing: {explanation}") and `addition_field` ("{topic}: {question} Optional: only what the founder added or corrected about this question in the follow-up round; leave empty if nothing.").
  - `faq.json`: the default FAQ of section 7 of the high-level plan as `{"faq": [{"question": ..., "answer": ...}]}`.
  - `messages.json` (AI messages and spoken texts): `summary_commentary` ({summary}), `follow_ups` ({follow_ups}), `completed`, `missing_answers` ({questions}), `invalid_arguments` ({fields}), `unknown_questions` ({ids}), `already_submitted`, `search_failed`, `search_empty`, `conversation_ended`, `generic_error`.
- **`app/context/__init__.py`** adds:
  - `prompt(name, **values)`: joins the prompt's entries with blank lines and fills the placeholders with `str.format`.
  - `text(key, **values)`: one entry, for example `text("messages.completed")`.
  - `render_questionnaire(entries)`, `render_faq(faq)` and `render_follow_ups(entries)`: the one place where lists become prompt text.
  - Load-time validation: every entry named in `prompts.json` exists.
  - The docstring explains the `document.entry` names and that literal braces are written `{{ }}`.
- **`app/errors.py`**: an `AppError` without `ai_message` gives the AI the `generic_error` text.

### Implementation: backend modules
- **`app/config.py`** adds:
  - URLs and the voice model: `OPENAI_WS_URL`, `LIVE_MODEL` (`gpt-live-1`, fixed and not team-editable).
  - Live session: `LIVE_CREATE_TIMEOUT_S` (15), `SIDEBAND_ATTACH_TIMEOUT_S` (5).
  - Conversation: `CONVERSATION_TIME_LIMIT_S` (30 minutes, below the session limit the spike found), `GOODBYE_SILENCE_S` (2.5, per the spike), `GOODBYE_MAX_WAIT_S` (30), `END_WAIT_S` (3, how long the end route waits for the call's cleanup).
  - Review: `REVIEW_ATTEMPTS` (2), `REVIEW_TIMEOUT_S` (30), `REVIEW_RETRY_DELAY_S` (2).
  - Search: `SEARCH_RESULT_COUNT` (5), `SEARCH_TIMEOUT_S` (4).
  - `REPLY_TIME_TARGET_MS` (1500, used only in the end-of-conversation log line).
- **`app/schemas.py`** adds `EndReason`, `Speaker`, `ToolName`, `TranscriptMessage`, `FollowUp`, `QuestionnaireEntry`, `Questionnaire`, `ReviewFollowUp`, `ReviewOutput`, `SearchResult`, `StartRequest`, `StartResponse`, `EndRequest` and `ConversationView`.
- **`app/models.py`** and a migration: `TranscriptMessageRow`.
- **`backend/pyproject.toml`**: adds the pinned `websockets` (the sideband's client). It must be listed itself, not arrive only through `uvicorn[standard]`.
- **`app/http.py`**: the shared `httpx.AsyncClient`, opened and closed in the lifespan.
- **`app/search.py`**: `search(query, language) -> list[SearchResult]` as described. A timeout, an HTTP error or an unexpected body is an `AppError` with `search_failed`. The docstring says the work is one awaited HTTP call on the loop that holds nothing while it waits.
- **`app/conversations.py`** adds, each a short step for `run_db`:
  - `new_questionnaire(catalog)`: the catalog questions as entries with empty answers;
  - `claim_start`, `revert_start` (also deletes the conversation's transcript messages), `read_questionnaire`;
  - `store_initial` (only once: if answers were already stored, `AppError` with `already_submitted`), `store_review` (completes the conversation when there are no follow-ups), `store_follow_up_answers` (writes every non-empty field as its entry's `follow_up_answer`, then completes the conversation); all three only for an In progress conversation, otherwise `AppError` with `conversation_ended`;
  - `save_message` (writes nothing for a Ready conversation), `finish_conversation`, `sweep_after_restart`;
  - `founder_view(session, founder_id, id) -> ConversationView`: 404 for another founder's conversation; `summary` only when Completed; `agent_name` from the conversation's settings.
- **`app/ai/transcript.py`**:
  - `TranscriptBuilder.add(speaker, delta, start_ms, end_ms)` returns the finished message when the speaker changes, and `flush()` returns the last one.
  - A message's text is its deltas joined as received and trimmed when finished. Empty messages are dropped. The browser follows the same rule.
  - `ReplyTimes` records `agent.start_ms - founder.end_ms` at every switch from founder to agent (negative values are overlaps such as backchannels and are not counted) and gives count, median and maximum.
- **`app/ai/tools.py`**:
  - `tool_model`, `answer_field`;
  - `phase_1_tools(questionnaire)` and `phase_2_tools(questionnaire)`: each returns the tool definitions for the session and the argument models by tool name;
  - one handler per tool, all with the signature `async def handler(call, arguments) -> str`, `HANDLERS: dict[ToolName, handler]`, and `run_tool`, the one runner that calls them.
  Behaviour as in "Tools" under Target Architecture.
- **`app/ai/reviewer.py`**: `review(questionnaire, settings) -> (follow_ups, reviewed)` as described under "Reviewer"; the JSON schema is `ReviewOutput.model_json_schema()`.
- **`app/ai/live.py`**: `LiveCall` (the call's state: IDs, settings, phase, argument models, socket, sideband task, transcript builder, reply times, `founder_spoke`, `closing`, the `spoke` event, running tasks), the registry, `start_call`, `run_sideband`, `end_call`, `close_session`, `send` (serializes an event and logs only its type) and `attach` (used at START and by `close_session`).
  - The module docstring states: one backend process (the registry is in memory); a call's cleanup acts only on its own `LiveCall` ("One call, one owner"); all work runs on the loop except database steps through `run_db`; nothing holds a database session while it waits on OpenAI; and what each wait holds.
- **`routes/founder.py`** adds `GET /api/my/conversations/{id}`, `POST /api/my/conversations/{id}/start` and `POST /api/my/conversations/{id}/end`. Start and end check ownership in their first database step.
- **`app/main.py`**: the lifespan also opens the HTTP client and runs `sweep_after_restart`. On shutdown, it cancels the sideband tasks and waits for them (each ends its call), then closes the HTTP client.

### Tests
- **`tests/fakes.py`**: the fake outside world described under Testing approach. Its Live part records each create body. Per session, it accepts attaches, lets the test push events or drop the socket without `session.closed`, and collects the backend's commands from every attach. It answers `session.close` with `session.closed`. Reviews and search results are queued per test, and an empty queue fails the test.
- `test_conversation_start.py`:
  - The create body contains the founder's name, the company, the questionnaire, the voice of the language, the note-taker settings and the phase 1 tools with strict schemas.
  - The SDP answer and the agent's name are returned, and the sideband is attached before the route returns.
  - Copies are taken at START, so a later catalog edit leaves them unchanged.
  - A second START gets 409; another founder's conversation gets 404.
  - A failing create and a failing attach both return the conversation to Ready with the copies cleared.
- `test_sideband.py`:
  - The kickoff commentary is sent on `session.started` (if the spike kept it).
  - Deltas become messages on speaker changes, saved in order.
  - Reply times are logged per reply and as a summary at the end.
  - A test answer containing a unique marker string never appears in the logs.
- `test_tools.py`:
  - `get_questionnaire` with all, some and unknown IDs.
  - `web_search` success, empty and failure, and the query is not logged.
  - A handler that raises an unexpected exception: the note-taker gets `generic_error`, and the log has only the exception's type.
  - `submit_initial`:
    - With empty answers: names the missing questions and stores nothing.
    - With invalid arguments: names only fields.
    - With follow-ups: stores answers and summary; the summary commentary is sent before the tool output; the follow-ups are stored with at most one per question and unknown IDs dropped; `session.update` carries the phase 2 tools with a field for every entry, described as a follow-up only where one was selected; the output lists the follow-ups in order.
    - Without follow-ups: the conversation is Completed, no `session.update` is sent, the output is the `completed` text, and `session.close` follows after the configured silence (set very short in the test).
    - When the review fails twice: `reviewed` is false, there are no follow-ups, and the conversation is Completed.
    - A second call after a successful one: `already_submitted`, and nothing changes (no second summary commentary, no second review).
  - `submit_follow_up`: missing follow-up answers are named, while empty fields of entries without a follow-up are fine; an addition to an entry without a follow-up is stored as its `follow_up_answer`; on success, Completed and `session.close` after the configured silence. Founder speech after the goodbye delays the close until both are silent.
- `test_conversation_end.py`:
  - A lost connection before the founder spoke returns the conversation to Ready, with the copies cleared and the saved greeting deleted.
  - The end route with `stopped` gives Unfinished (stopped) and sends `session.close`, also before the founder spoke. Its returned view already contains the message that was in progress when STOPP was pressed.
  - After a failed start, a new START while the old call is still cleaning up: the old cleanup neither resets nor closes the new call.
  - A `session.closed` from the fake after the founder spoke gives Unfinished (connection lost), and the backend sends no `session.close` afterwards.
  - A dropped sideband after the founder spoke gives Unfinished (connection lost) and a second, short attach that sends `session.close`; before the founder spoke, it gives Ready and the same close. A failing second attach is logged and changes nothing else.
  - `connection_lost` after Completed changes nothing.
  - The time limit (set short) gives Unfinished (time limit), written before the close command.
  - The startup sweep, and the shutdown ending running calls.
  - The founder view shows the summary only when Completed and never the questionnaire or the settings.
- `test_reviewer.py` (fake): the request carries the strict schema; unknown IDs are dropped and duplicates reduced to the first; timeouts are retried after the configured pause (set very short in the test) up to the configured attempts.
- `test_context.py` adds: every prompt and every text renders with sample values for its placeholders, so a misspelled placeholder fails here and not at START.
- **Real tests (`real` marker, run with `--complete`)**:
  - The reviewer on three prepared questionnaires in `tests/data/`: complete answers give few follow-ups; a vague traction answer gets a traction follow-up; the "anything else" question is always selected; never more than one per question.
  - A real Serper search for "Venture Capital" returns results.

### Docs and cleanup
- **README developer part**: the architecture overview (the diagram from section 5 of the high-level plan, the three AI roles, the two phases and the tools), where the AI module and the context documents live, and that `--reload` restarts end running conversations.
- **High-level plan**: sections 7, 11 and 12 match the built behaviour, including any fallback from the spike.
- **Cleanup**: no prompt or AI text remains in Python code (search for quoted English sentences in `app/ai/`, `app/search.py` and `app/errors.py`). Every new module states where its work runs (AGENTS.md, "Never freeze the server").

### Status: completed
Implemented on 2026-11-16. `./scripts/test.sh` passes (93 backend tests and the frontend type check, three runs in a row without a flaky test); the four `real` tests (reviewer and Serper) are written but skipped until `--complete` runs with real keys (see Operator to-dos). The spike has not been run yet, so every main path of "The conversation at runtime" is built as described, without fallbacks.

### Decision log
1. **"One call, one owner" holds in the database too.** The plan keeps each cleanup on its own `LiveCall`, but `revert_start`, `finish_conversation` and `save_message` were keyed by the conversation ID alone. After a failed start, the old call's cleanup (founder not spoken, so `revert_start`) would have put the founder's next attempt back to Ready, and its flushed greeting would have landed in the new attempt. Every write of a call is now conditional on its own START: `claim_start` returns `started_at` (in the internal model `StartedConversation`), the call keeps it, and the store steps, `save_message`, `revert_start` and `finish_conversation` match it. The end route without a registered call (after a restart) finishes any running attempt.
2. **The shutdown waits for a call that is already cleaning up instead of cancelling it again** (`LiveCall.ending`). The tests showed that a second cancellation cut the cleanup short (for example when the time limit was reached just before a `--reload` restart), leaving the call in the registry and its session possibly open.
3. **The tool swap changes only what the note-taker sees.** The call keeps the argument models of both phases (`LiveCall.tool_models`), so a late `submit_initial` after the swap still reaches its handler and gets `already_submitted` instead of the generic error. The current phase is implicit in what was stored.
4. **The kickoff is sent both ways** (the `input` developer message and the commentary at `session.started`), OpenAI's recipe, because the spike has not decided yet. The browser check in commit 5 removes the `input` message if the greeting starts before the browser is connected.
5. **The summary has two more checks**: empty (`missing_summary`) and longer than `SUMMARY_MAX_CHARS` (1200 characters, well below the 500 tokens one commentary allows; `summary_too_long`). In both cases nothing is stored and the note-taker submits again. Missing answers are checked first.
6. **No AI text in Python code, also for lists.** The line templates of the rendered lists live in the documents (`voice_agent.questionnaire_item` and `faq_item`, `messages.follow_up_item` and `question_reference`), and the load-time check also verifies that every entry `prompts.json` names exists. `unknown_questions` names the valid IDs too (`{valid_ids}`).
7. **Errors only the AI reads** are raised with `AppError.for_ai(log_message, ai_message)` (the user message is the generic one, the status 500), and `message_for_ai` turns any exception into the AI message or `generic_error`. 404 and 502 joined the declared error responses.
8. **The reviewer tries every output text of the response's message items** and takes the first valid `ReviewOutput`: OpenAI's community reports that `gpt-6-luna` occasionally adds a second message item to structured outputs. Follow-ups without text are dropped, and the result is in questionnaire order.
9. **Small additions:** `SearchResult.snippet` defaults to empty (Serper omits it for a few results); `hl` is the conversation's language code; the sideband logs every command it sends by type (`event=sent`) and the reason code of `session.closed`; a failed `save_message` loses one message but never ends the conversation; `save_message` reads with `FOR SHARE`, so it cannot interleave with a `revert_start`; the JSONB copies use `none_as_null`, so a revert writes SQL NULL; `http.open_client` restores the previous client (only the tests nest two apps); the end route checks ownership with its own first step (`check_owner`), because `end_call` is keyed by the conversation.
10. **Tests:** the fake outside world as planned, served by uvicorn in the session's event loop; the `fake` fixture also shortens the waits (goodbye silence, review retry pause). The `app` fixture checks that no call outlives its app, which found decision 2. Beyond the plan's list: unit tests of the transcript rule and the reply times, the summary checks, a second message item in the review response, the render functions, and a `prompts.json` that names a missing entry. The real tests use three prepared questionnaires in `tests/data/` (complete, vague traction, declined funding answers).

### Deviations
- `StartedConversation` (internal, not part of the API) is an addition to the models listed in the plan, and `LiveCall` has `tool_models` and `ending` instead of a separate phase field (decisions 1 to 3).
- `messages.json` has four more entries than listed (`missing_summary`, `summary_too_long`, `follow_up_item`, `question_reference`), and `voice_agent.json` two (`questionnaire_item`, `faq_item`); decisions 5 and 6.

### Inconsistencies found
- "One call, one owner" in the plan covered the in-memory objects but not the database writes, and the plan's own test ("the old cleanup neither resets nor closes the new call") could not pass without decision 1.

### Notes for commit 5
- `POST /api/my/conversations/{id}/start` takes `{"sdp"}` and answers `{"sdp", "agent_name"}`; 409 means another tab started it, 502 that OpenAI failed (the conversation is Ready again). `POST .../end` takes `{"reason": "stopped" | "connection_lost"}` and answers the `ConversationView` once the call's cleanup has run (at most `END_WAIT_S`).
- If the greeting starts before the browser is connected, remove the `input` kickoff message in `live.start_call` (decision 4) and keep the commentary.

### Operator to-dos
- Once the two API keys are in `secrets/secrets.yaml`, run `./scripts/test.sh --complete` once: it runs the reviewer on the prepared questionnaires and a real Serper search (a few cents).
- The spike run from commit 1 is still open; its findings may switch a main path here to its fallback.

---

## Commit 5: The Founder's Conversation (Browser)

### Summary
Founders can now have the conversation. They open a Ready conversation, see the short tutorial, pass the device check and press START. They talk to the agent with a live transcript and status, can stop at any time with STOPP, and see the outcome message below the conversation. Past conversations open in the same conversation view, filled from the database.

### How it works
- **One page for a conversation (`/conversations/:id`):** it loads the founder's `ConversationView` and renders it by its state, always by the same rule. Ready: three steps (tutorial, device check, call). Any other state: the conversation view with the stored transcript and the outcome message. After a call ends, the page renders the view the backend returned; if it is Ready again (a failed start), the founder also sees the toast „Das Gespräch konnte nicht starten. Bitte versuchen Sie es erneut." If the start request itself fails, the page shows the backend's message as a toast, reloads the view and renders it by the same rule.
- **The page owns the microphone stream:** the device check opens it, the call uses it, and it is stopped only when the page is left. A retry after a failed start therefore uses the same working microphone, and permission is asked once.
- **The call (`call/useCall.ts`):** the browser side described in "The conversation at runtime". It ends in exactly one `handleEnd(reason)`, also when the page is left while the call runs.
- **One conversation view (`conversation/ConversationView.tsx`):** it renders the transcript messages in chat style, the status, the outcome message and an action slot (STOPP during a call, „Aktualisieren" for a conversation running elsewhere). Live, the messages come from the data channel; later, from the database. The Team area reuses it in commit 6.
- **One audio level hook (`audio/useAudioLevel.ts`):** the microphone meter of the device check and the agent's „Spricht" use the same measurement (Web Audio `AnalyserNode`, RMS, updated per animation frame).

### What users notice
**F1 (getting ready) and F2 to F5 (conversation, finish, early end, past conversations)**, step by step:
1. After signup or „Gespräch freischalten", the founder goes straight into the new conversation (the IDs come from `SignupResponse` and the returned `ConversationSummary`). In „Meine Gespräche", every row now opens its conversation.
2. **Tutorial** (skippable, shown before every conversation): six slides, each with one icon (`lucide-react`) and one sentence, with „Zurück", „Weiter" and „Tutorial überspringen". The last slide's button says „Zum Gerätetest". The slides:
   1. „Suchen Sie sich einen ruhigen Ort. Kopfhörer sind optional."
   2. „Sprechen Sie ganz natürlich. Der Agent stellt eine Frage nach der anderen."
   3. „Sie können jederzeit auch selbst Fragen stellen."
   4. „Rückfragen kommen am Ende."
   5. „Der Agent beendet das Gespräch, wenn alles aufgeschrieben ist."
   6. „STOPP beendet das Gespräch endgültig."
3. **Gerätetest**: three rows, each with a state icon (checking, passed, problem) and, on a problem, a short fix:
   - **„Verbindung"**: `GET /app-config` (our server) and a `no-cors` request to `openai_reachability_url` (OpenAI), each with `connection_check_timeout_ms`. Problems: „Unser Server ist nicht erreichbar." or „OpenAI ist nicht erreichbar. Bitte prüfen Sie Ihre Internetverbindung oder Firewall.", each with „Erneut prüfen".
   - **„Mikrofon"**: the button „Mikrofon erlauben" asks for permission. The row passes once the stream is open. A select lists the microphones and restarts the stream on change, and a level meter shows the input with the hint „Sprechen Sie, um Ihr Mikrofon zu testen." If the permission is blocked: „Ihr Browser hat das Mikrofon blockiert. Klicken Sie auf das Symbol neben der Adressleiste, erlauben Sie das Mikrofon und versuchen Sie es erneut." with „Erneut versuchen".
   - **„Lautsprecher"**: a speaker select where the browser supports `setSinkId`, elsewhere the note „Ihr Browser nutzt den Standardlautsprecher. In Chrome können Sie einen auswählen." „Testton abspielen" plays a short two-tone chime, generated with Web Audio and played through an `<audio>` element on the chosen speaker (the same path as the agent's voice). Then „Ich habe ihn gehört" passes the row, and „Ich habe nichts gehört" shows „Prüfen Sie die Lautstärke und den gewählten Lautsprecher und spielen Sie den Ton noch einmal ab."
   - **START** (blue) is enabled once all three rows passed.
4. **Call**:
   - Pressing START disables it at once and shows the conversation view with the status „Verbinde ..." until the data channel opens. STOPP appears once the start request has returned, so there is always a call to stop.
   - While the call runs, the header shows no navigation and no „Abmelden": STOPP is the way out.
   - Then the transcript grows live: the founder's messages on the right labelled „Sie", the agent's on the left labelled with the agent's name, auto-scrolled to the newest. (The Team area shows the founder's name instead of „Sie".)
   - The status pill shows „Hört zu", „Spricht", „Schlägt nach ..." or „Schreibt Ihre Antworten auf ...".
   - **STOPP** (red) asks „Jetzt beenden?" with „Das Gespräch wird als nicht abgeschlossen gespeichert und kann nicht eingereicht werden." and the buttons „Weitersprechen" and „Beenden" (red).
   - While the call runs, closing or reloading the tab triggers the browser's own "leave page?" warning. Leaving the page inside the app anyway (the browser's Back button) ends the call like a lost connection.
5. **End**: the view switches to the stored conversation from the backend's answer, with the outcome message below the last message:
   - **Completed**: a check icon, „Vielen Dank, Ihr Gespräch ist abgeschlossen.", a prominent button „Zusammenfassung anzeigen" (then „Zusammenfassung ausblenden", with `aria-expanded`) that expands the summary, and „Das Team prüft Ihre Antworten und meldet sich bei Ihnen."
   - **Unfinished**: „Dieses Gespräch wurde vor dem Abschluss beendet.", the reason („Das Gespräch wurde mit STOPP beendet.", „Die Verbindung wurde unterbrochen." or „Das Zeitlimit wurde erreicht."), then „Die Antworten konnten nicht eingereicht werden. Für einen neuen Versuch ist ein neuer Zugangscode vom Team nötig." No summary. The texts are neutral, because the Team area shows the same message.
6. **Failed start**: if the start request fails, or the connection is lost before the founder said anything, the conversation is Ready again: the founder sees the toast „Das Gespräch konnte nicht starten. Bitte versuchen Sie es erneut." and is back at the device check with START enabled and the same microphone. (If another tab started the conversation in the meantime, the toast says „Dieses Gespräch kann nicht mehr gestartet werden." and the page shows the running conversation.)
7. **Reopening**: a past conversation shows the same view with its outcome message. A conversation that is running in another tab shows „Dieses Gespräch läuft gerade." with „Aktualisieren" instead of an outcome.

### Implementation: backend additions
- **`AppConfig`** gains, all from new constants in the config module: `openai_reachability_url` (derived from `OPENAI_API_URL`), `connection_check_timeout_ms`, `speaking_level_threshold` and `speaking_hold_ms` (the agent stays „Spricht" this long after its level drops, so the status does not flicker between words).

### Implementation: frontend
- **`audio/useAudioLevel.ts`**: `useAudioLevel(stream: MediaStream | null) -> number` (0 to 1), one `AudioContext` per stream, cleaned up on change and unmount.
- **`call/useCall.ts`**:
  - `start(conversationId, micStream, speakerId)`; returns `{messages, status, agentName, phase: "connecting" | "live" | "ended", stop()}`.
  - `stop()` runs `handleEnd("stopped")`.
  - `handleEnd(reason)` runs once: it mutes the agent's audio element, calls `api.endConversation` and waits for the returned `ConversationView`, then closes the peer connection (also if the report failed) and hands the view to the page. If the report failed, the page reloads the view with `api.conversation`. It never touches the microphone stream, which belongs to the page.
  - Unmounting while a call runs calls `handleEnd("connection_lost")`, so no call outlives its page.
  - While a call runs, `useCall` sets `callActive` in the `AppProvider`, and `PageShell` hides its navigation and „Abmelden" while it is true.
  - Data channel messages are parsed with `JSON.parse` and passed to the two pure functions. Unknown event types are ignored.
- **`conversation/transcript.ts`**: `appendDelta(messages, speaker, delta, startMs, endMs)`, with the same rule as `TranscriptBuilder` (the comment points to the `TranscriptMessage` description as the definition). It uses the generated `TranscriptMessage` type.
- **`conversation/status.ts`**: `reduceActivity(activity, event)` and `displayStatus(activity, agentSpeaking)`. The activity of each tool is a record typed with the generated `ToolName` (`web_search`: „Schlägt nach ...", both submit tools: „Schreibt Ihre Antworten auf ...", `get_questionnaire`: none), so a new tool fails the type check until it has an entry.
- **`conversation/ConversationView.tsx`** (props: `messages`, `agentName`, `founderLabel` („Sie" for the founder, the founder's name in the Team area), `status?`, `outcome?` (the `ConversationView` whose outcome is shown), `actions?`), **`conversation/StatusPill.tsx`** and **`conversation/OutcomeMessage.tsx`**, which shows one thing per state: Completed the success message, Unfinished the unfinished message, In progress „Dieses Gespräch läuft gerade.", Ready nothing.
- **`labels.ts`** adds the end reason texts, typed with the generated `EndReason` and used by `OutcomeMessage` (and in commit 6 by the Team detail).
- **`pages/founder/ConversationPage.tsx`** (the step logic and the microphone stream, stopped on unmount), **`Tutorial.tsx`** and **`DeviceCheck.tsx`** (opens and switches the page's microphone stream). The router adds `/conversations/:id`.
- **`api/client.ts`**: `conversation`, `startConversation`, `endConversation`.
- **Vitest**: added to `package.json`; `npm run check` becomes `tsc --noEmit && vitest run`. Tests:
  - `transcript.test.ts`: speaker changes, joined deltas, trimming, empty messages.
  - `status.test.ts`: the activity starts on a function call, ends with the next response of the same delegation, ignores other delegations, and the display priority (activity, then speaking, then listening).

### Manual check (Done when)
A full conversation in Chrome on `http://localhost:5173`:
- The WebRTC create response matches what the spike and the docs said (`session.id`, `transport.sdp`), and the sideband attaches before the browser connects.
- The greeting is heard and shown from its first word. If it starts before the browser is connected, the kickoff is sent only as the commentary at `session.started` (no `input` message), and this check is repeated.
- The greeting comes with the startup lookup, and a FAQ answer and a web search answer work.
- All questions are asked, the summary is read aloud while „Schreibt Ihre Antworten auf ..." shows, and the follow-ups follow, the closing round last.
- After the goodbye, the call ends by itself and the success message appears.
- A second conversation stopped with STOPP shows the unfinished message.
- A third conversation where the tab is closed during the greeting is Ready again when reopened.

### Docs and cleanup
- **README**: team part (German): what a founder experiences (welcome, signup with an access code, tutorial, device check, conversation, outcome message), in a few sentences. Developer part: Chrome is recommended (speaker selection).
- **High-level plan**: section 8 matches the screens as built.
- **Cleanup**: signup and „Gespräch freischalten" now navigate into the new conversation, replacing the list reload of commit 2, and no unused code from it remains.

### Status: completed
Implemented on 2026-11-16. `./scripts/test.sh` passes (94 backend tests, the type check and 8 Vitest tests). The manual check ran as a throwaway browser check: Chrome (Playwright) in an isolated compose project (removed afterwards) against the real OpenAI and Serper, with a microphone that carries only faint noise, so the founder never speaks. Covered:
- signup straight into the conversation, all six tutorial slides, the device check (including „Ich habe nichts gehört");
- START: the WebRTC create answered as documented, the sideband attached before the browser connected, and the greeting arrived from its first word with the startup lookup („Schlägt nach ..." while it ran);
- STOPP, first „Weitersprechen", then „Beenden": Unfinished (stopped), and the live transcript equalled the stored one;
- „Neues Gespräch" straight into the next conversation; closing the tab during the greeting: Ready again within two seconds;
- the Completed outcome with its summary toggle and a conversation running elsewhere with „Aktualisieren" (both prepared in the database);
- phone width without horizontal scrolling.

What needs a founder who answers (all questions, the summary read aloud, the follow-ups, the goodbye and the success message after a real conversation) is covered by the voice test of commit 6, which plays recorded answers.

### Decision log
1. **The kickoff stays as both the `input` message and the commentary** (commit 4, decision 4). Over WebRTC the greeting starts only once the browser's audio flows, so it is heard and shown from its first word; the plan's condition for removing the `input` message never occurs. The check also found that a microphone stream carrying no audio at all (a Web Audio stream without a source) gets no greeting: the commentary stays pending (`context_injection_incomplete`), and OpenAI closes the session as `expired` after about 30 seconds, which the app treats as a failed start (Ready). A real microphone always carries room noise.
2. **The agent no longer guesses how to address the founder.** In the check it greeted the test founder as „Herr Founder", a gender guessed from a name. The voice agent's style entry now says to use the full name without „Herr" or „Frau".
3. **The offer waits for ICE gathering** (OpenAI's WebRTC guide: the server takes no later candidates), at most `ICE_GATHERING_TIMEOUT_MS` (3 seconds; without STUN servers gathering takes milliseconds). It is a config value sent through `AppConfig` like the other browser values.
4. **The generated types name the tools.** No route carries `ToolName`, so `schemas.BROWSER_TYPES` lists the types the browser needs anyway, and `main.py` adds them to the OpenAPI schema. `status.ts` is typed with the generated `ToolName` as planned; `tests/test_app_config.py` checks it, together with the app config (moved there from `test_access_codes.py`).
5. **One audio measurement, two hooks, one speaker path.** `useAudioLevel` (the meter, a value per frame) and `useSpeaking` (changes state only when the answer flips, so the conversation view does not re-render 60 times a second) share one measurement. `audio/speaker.ts` is the one output path (`openSpeaker`) of the test tone and the agent's voice.
6. **Every end of a call, also a closing tab, goes through `handleEnd`.** The end report is sent with `keepalive`, and `pagehide` runs `handleEnd`, so closing or reloading the tab reports the end at once instead of waiting until OpenAI notices the lost connection. An end while the START request still runs waits for it. The call's phases are `idle`, `starting`, `connecting`, `live` and `ending`: STOPP appears from `connecting` on (a call exists), and the status shows „Wird beendet ..." while the end is reported (at most `END_WAIT_S`).
7. **The page owns the whole device setup** (microphone stream, chosen speaker, passed checks), so after a failed start the founder is back at a passed device check with START enabled, as planned. The microphone is also released once the conversation can no longer start (Completed, Unfinished, or running elsewhere), so the browser stops recording while the founder reads the outcome; a retry after a failed start still keeps it.
8. **Signup lands in the new conversation through one transition** (`startTransition` around `setMe` and the navigation). React Router applies navigations as transitions, so the guest-page guard would otherwise see the login first and send the founder to the list. Verified in the browser.
9. **Small additions:**
   - `cancelLabel` in the confirmation module (for „Weitersprechen").
   - A back link „Meine Gespräche" on the conversation page; during a call the header's app name is not a link either.
   - „Das Mikrofon ließ sich nicht öffnen. ..." for a microphone that fails for another reason than a block.
   - The microphone select only with more than one microphone; changing the speaker resets the speaker check.
   - The toast „Gespräch freigeschaltet." before going into the new conversation; „Noch keine Nachrichten." for a stored conversation without messages.
   - The page headings „So läuft das Gespräch", „Gerätetest" and „Ihr Gespräch" (with the date).
   - The start failure text lives in the page as well, because a start that fails after the START request (connection lost before the founder spoke) returns a Ready view, not the backend's 502 message.
   - OpenAI answers the device check's no-cors request with 401, which the browser's console lists; that is expected, because any answer proves the path.
10. **Vitest 5.1.0** (supports Vite 8). `npm run check` runs `tsc --noEmit && vitest run`, and test.sh's part is now called „Frontend checks".

### Deviations
- `useCall` has the phases of decision 6 instead of `connecting`, `live` and `ended`; the microphone is released earlier than "only when the page is left" (decision 7); `AppConfig` has `ice_gathering_timeout_ms` (decision 3); `audio/speaker.ts` is an additional file (decision 5).
- The voice style change (decision 2) belongs to the context documents of commit 4, but the browser check found it.

### Inconsistencies found
- The manual check's "if the greeting starts before the browser is connected" cannot happen: the greeting waits for the browser's audio (decision 1).
- Commit 6's voice test replaces `getUserMedia` with a Web Audio stream. That stream must carry audio between the clips (a faint noise floor), or the session never starts (decision 1).

### Notes for commit 6
- The fake microphone of the voice test keeps a faint noise floor between its clips (the throwaway check used noise at an amplitude of 0.002, which the server's voice detection ignores).
- The status pill shows „Hört zu" while nobody speaks and no tool runs, which is the voice test's signal to play the next answer.

### Operator to-dos
- Have one conversation yourself in Chrome. It checks what no test can judge: how natural the German voice sounds and how fast the replies feel.
- The spike run is still open (see commit 1).

---

## Commit 6: Team Review, Voice Test and Final Polish

### Summary
The team can find and read every conversation:
- a searchable, filterable list;
- a detail page with the same conversation view the founders see;
- the team-only details: questionnaire, summary, follow-ups with explanations, the "not reviewed" note and the settings used;
- „Aktualisieren", also while a conversation is running.

`test.sh --complete` gains the real voice conversation in Chrome. The README and the high-level plan get their final pass.

### How it works
- **Team list and detail** read only from the database, as plain request and response (no live updates). The list endpoint returns every conversation, newest first, and the page filters them in the browser, so search and filter react while typing and the backend needs no query parameters. The detail reuses `ConversationView` and `OutcomeMessage` from commit 5 and adds the team-only cards around it. „Aktualisieren" reloads the detail; while a conversation runs, this shows the messages saved so far and, after the first submit, the answers.
- **The voice test** runs a real conversation through the real app:
  - Chrome in the `e2e` container plays founder answers into the app instead of a microphone. The answers are generated at the start of each run with OpenAI's text-to-speech.
  - It answers whenever the agent stops talking, following a short script with a fallback answer, so the test does not depend on the exact wording the agent chooses.
  - Afterwards it checks the stored result in the database: Completed, every answer, the summary and the answered follow-ups.

### What users notice
**T2 (review conversations)**, step by step:
1. After login, the team lands on **„Gespräche"** (the navigation is now „Gespräche", „Zugangscodes", „Einstellungen").
2. **Gespräche (`/team/conversations`)**:
   - A search field („Nach Gründer, E-Mail oder Firma suchen"), a state filter („Alle Status" and the four state labels) and the table, newest first: „Datum", „Gründer" (name and email), „Firma", „Status".
   - Search and filter apply while typing (case-insensitive, in name, email and company). Clicking a company name puts it into the search field, which shows all of its conversations. Clicking a row opens the detail.
   - Empty result: „Keine passenden Gespräche."
3. **Gesprächsdetails (`/team/conversations/:id`)**:
   - „Zurück zu den Gesprächen" and **„Aktualisieren"** (reloads everything, then the toast „Aktualisiert.").
   - The founder's conversation view (transcript and outcome message, exactly as the founder sees it, with the founder's name instead of „Sie").
   - Next to it on wide screens, below it on narrow screens, the cards:
     - **„Gründer"**: name, email, company.
     - **„Gespräch"**: state, created, started, ended, and the end reason (the text from `labels.ts`).
     - **„Fragebogen"**: the summary first, then per question: the topic, the question, the answer; if a follow-up was selected, its question and the reviewer's explanation („Begründung"); and if there is a follow-up answer (the answer to the follow-up, or an addition the founder made in that round), it under „Aus der Rückfragerunde". When `reviewed` is false, the note „Nicht geprüft: Die automatische Prüfung ist fehlgeschlagen, deshalb gab es keine Rückfragen."
     - **„Verwendete Einstellungen"**: agent name, conversation language, note-taker and reviewer model and thinking level.
   - Everything that does not exist yet shows „Noch nicht verfügbar" (for example the questionnaire of a Ready conversation, or the answers before the first submit).
4. **Zugangscodes**: a used code's state links to its conversation.

### Implementation: backend
- **`app/schemas.py`** adds `TeamConversationRow` (`id`, `created_at`, `started_at`, `state`, `founder_name`, `founder_email`, `company_name`) and `TeamConversationDetail`.
- **`app/conversations.py`** adds:
  - `list_team_conversations(session)`: one query joining founders, newest first.
  - `team_detail(session, id)`: one read of the conversation, its founder and its transcript. The view part is built by the same function as `founder_view`, so the founder and the team see the same thing.
- **`routes/team.py`**: `GET /api/team/conversations` and `GET /api/team/conversations/{id}`.
- **`app/cli.py`** adds two commands for `test.sh --complete`: `create-access-code EMAIL` (prints a new code for that email through `access_codes.create_access_code`; developers can also use it to try the founder flow without the Team area) and `print-openai-key` (for the voice test's text-to-speech, passed on as an environment variable and never written to a file).

### Implementation: frontend
- **Pages**: `pages/team/ConversationsPage.tsx` and `pages/team/ConversationDetailPage.tsx`, with the detail cards as small components in the same folder. The router adds both, and the team's start page becomes `/team/conversations`. The access code table links used codes to their conversation.
- **`api/client.ts`**: `teamConversations`, `teamConversation`.

### Implementation: voice test (`--complete` only)
- **`docker-compose.yml`**: the backend's healthcheck (see Containers), and the `e2e` service (profile `e2e`): built from `e2e/`, `./e2e` mounted, `network_mode: "service:frontend"`, and the environment variables `OPENAI_API_KEY`, `E2E_EMAIL` and `E2E_CODE`, passed in by `test.sh`.
- **`e2e/Dockerfile`** and **`e2e/requirements.txt`**: the official Playwright Python image, whose tag matches the pinned `playwright` version, plus the pinned `pytest`, `pytest-playwright`, `httpx` and `psycopg[binary]`, installed when the image is built (AGENTS.md: dependencies are installed only by the container build).
- **`e2e/founder_script.json`** (German, because the default conversation language is German):
  - the company name the test signs up with (a fictional startup);
  - the opening answer: „Nein, ich habe keine Fragen. Wir können gerne anfangen.";
  - one pitch of about 150 words that answers all ten topic questions of the default catalog for that startup;
  - the closing answer: „Nein, das ist alles.";
  - the fallback for every further turn: „Dazu möchte ich gerade nicht mehr ins Detail gehen."
- **`e2e/clips.py`**: turns each text into a WAV clip with OpenAI's current text-to-speech model (looked up at implementation time) at the start of each run, into a temporary folder. Its docstring explains why this test calls OpenAI directly: it plays the founder, not the app.
- **`e2e/test_voice_conversation.py`**:
  1. Chrome flags: `--use-fake-ui-for-media-stream` (accepts the permission prompt), `--use-fake-device-for-media-stream` (device lists are not empty) and `--autoplay-policy=no-user-gesture-required`.
  2. An init script replaces `getUserMedia` with a stream from a Web Audio destination and exposes `window.__fakeMic.play(url)`. The clips are served through `page.route("**/__e2e/clips/*")`, so the app itself contains no test code.
  3. Sign up on `http://localhost:5173/signup` with a test name and password, `E2E_EMAIL`, `E2E_CODE` and the script's company, then „Tutorial überspringen". In the device check: „Mikrofon erlauben", „Testton abspielen", „Ich habe ihn gehört", then „START".
  4. Loop: when the status pill shows „Hört zu" and the last message is a new agent message, play the next clip (the script in order, then the fallback). Stop at the success message, or fail after 12 minutes or 30 turns.
  5. In the browser: the success message and a non-empty summary behind „Zusammenfassung anzeigen".
  6. In the database (`postgresql://postgres@db:5432/app`, the app's database, see the config module), for the conversation ID from the page URL: the state is `completed`, the summary and every answer are non-empty, at least one follow-up was selected, and every entry with a selected follow-up has a follow-up answer.
- **`scripts/test.sh --complete`** additionally, after the other parts:
  - starts the stack with `compose_up -d --wait` (the same start as `start.sh`, in the background, waiting for the backend's healthcheck);
  - creates the email `e2e-<timestamp>@example.com` and its code with `backend_cli create-access-code`, and reads the key with `backend_cli print-openai-key` into an environment variable;
  - runs `compose --profile e2e run --rm --build e2e` (`--build`, because the e2e image is not part of `compose_up`);
  - prints the backend's reply time lines of this conversation from `compose logs backend`;
  - stops the stack (`compose stop`).
  The README says to stop a running `start.sh` first, and that the test's founder and conversation stay in the database and show up in the Team area.

### Docs and cleanup (final pass over the whole repo)
- **README**: complete both parts as listed in section 14 of the high-level plan, and check that it stays compact.
  - Team part (German): reviewing conversations (list, search, filter, the view, „Aktualisieren", what the questionnaire shows, "not reviewed").
  - Developer part: `--complete` with its cost, `create-access-code`, and the deliberate trade-offs from section 16 of the high-level plan.
- **High-level plan**: section 13 describes the voice test as built, sections 3 and 15 match the app, and section 17 keeps the spike's results.
- **Repo-wide pass 2 (AGENTS.md section 2)**: search the backend, the frontend, the context documents, the scripts, AGENTS.md, the README and `_docs/` for stale claims, especially:
  - "polling" and "live updates";
  - "Anything else" described as fixed, special or always last;
  - team members, usernames or team password hashes;
  - a database password;
  - the old type check sentence;
  - any mention of a summary in the Unfinished message.
- **Text check**: no long dashes anywhere in the repo, and no short dashes used as a pause in text users or the model read (`grep` for U+2014 and U+2013 over the repo).
- **Language check**: every text a user reads is German; prompts, code and developer docs are English.
- **Header check**: every file starts with its docstring or header comment, and none cites plan items.

### Status: completed
Implemented on 2026-11-16. `./scripts/test.sh` passes (103 backend tests, the type check and 9 Vitest tests), and `./scripts/test.sh --complete` passes (the 4 real-API tests and the voice conversation). The voice test ran eleven times during this commit. Its real runs found flaws in the conversation itself (the goodbye watch and the prompts of commit 4), which this commit fixed with the developer's decisions (decisions 3 to 8); one run failed only because a code edit restarted the backend mid-conversation (uvicorn's `--reload`). The last two runs in a row followed every rule of section 7 of the high-level plan: the startup lookup during the greeting, the questions with the answered ones skipped, the writing down with the stored summary read once, every follow-up in order with the closing round last (also when the founder declined each), the writing down again, the full goodbye, and the success message. A throwaway browser check of the team pages (isolated compose project with test secrets, removed afterwards) covered the list, search, state filter, the company click, the detail cards with the settings' labels, „Noch nicht verfügbar", „Nicht geprüft", „Aktualisieren", the link of a used code and phone width.

### Decision log
1. **Versions (checked on 2026-11-16).** Playwright 1.65.2 with its official image `v1.65.2-noble` (there is no newer image), pytest-playwright 0.10.0, pytest 9.2.0, httpx 0.28.1, psycopg 3.3.9. pytest-playwright's `base_url` fixture triggers one deprecation warning under pytest 9.2; it is harmless and left visible.
2. **The founder's voice comes from `gpt-audio-1.5`** (Chat Completions with audio output, voice `cedar`). OpenAI deprecated every model of `/v1/audio/speech` (shutdown on 2027-01-06) and names no successor for that endpoint. The model is conversational, so `clips.py` compares the transcript it returns with the script text and fails the run if a clip was not read verbatim.
3. **The goodbye watch waits for the note-taker's report** (developer decision). The first real run closed the session 2.7 seconds after the completion, before the goodbye: the watch took the end of the agent's handover sentence for the goodbye, while the note-taker needs 1 to 7 seconds to pass the completion on. The watch now waits until the note-taker's next response after the completion has finished (matched by response IDs on the sideband), then closes once the agent has spoken and 2.5 seconds of silence followed; speech counts by its time, so no event order matters. `GOODBYE_MAX_WAIT_S` rose from 30 to 120 seconds, because without follow-ups the agent first reads a summary of up to a minute. The fake world answers `response.create` with the note-taker's report, as the real API does.
4. **The sideband logs the note-taker's work** (`delegation_created`, `note_taker_started`, `note_taker_finished` with outcome and duration, `note_taker_reported`), with IDs only and never its text. This is the "writing down waits are measured and logged" of section 12 of the high-level plan, and it made the diagnosis below possible.
5. **The backend starts the startup lookup** (developer decision after a root-cause analysis). A probe of five variants against the real API showed that `gpt-live-1` hands work over (`<|SpawnThinking|>`) only in its replies to the founder. The greeting is commentary, not a reply, so the lookup it announced never started; in three runs it ran minutes later, together with the writing down. The call's opening, sent once the session started, is now two things from the context system: the greeting as commentary (`voice_kickoff`, only the words to say; an instruction-style text left the agent silent in one of two probes) and the lookup request to the note-taker (`note_taker_kickoff`, a developer message plus `response.create`). The search then runs within 1 to 3 seconds, during the greeting, through the normal `web_search` tool and status; the agent announces it and uses the result only as background.
6. **The voice prompt follows OpenAI's GPT-Live prompting guide** (developer decision to diagnose and tune):
   - Every hand-over uses the trained wording "generate <|SpawnThinking|>". The old "hand that over" was spoken aloud („… und übergebe das") instead of being done.
   - While a search runs, the agent keeps talking; while everything is written down, it waits in silence. "Keep the conversation going" made it invent a summary and a follow-up of its own and then read the real summary a second time.
   - It never summarizes, asks follow-ups of its own, says that something is written down, or says goodbye before it has heard so.
   - A declined question or follow-up counts as answered, and every ending goes through writing down (the developer's idea: the submit tool is the only way out, also when the founder declines everything). Before, the agent said goodbye after a declined follow-up in two of five runs, and nothing was submitted.
   - The follow-up instruction no longer quotes an English example, which the agent once copied word for word.
   - After each question the agent stops and waits, and it never answers for the founder. In one run it greeted, asked whether the founder had questions, and then ran the whole interview alone, answering as the founder; the lookup's report had reached it mid-greeting, so its background now "needs no reply".
7. **The note-taker has a procedure**: every request from the agent is done with a tool call first, and answers and summaries go only into the submit tools, never into its text. In one run it answered a writing-down request with a summary in text, which the agent read out. Only the founder's own words count as answers, never the agent's: in the run where the agent spoke for the founder, the invented answers were stored.
8. **The reviewer's closing round rule comes first**, also when the founder already said there is nothing else. In one run the founder's „Nein, das ist alles" counted as a declined answer, and the closing round was missing.
9. **„Schreibt Ihre Antworten auf ..." starts with the note-taker's `response.output_item.added`** of a function call (its `done` stays as a fallback), so it shows while the note-taker composes the answers. Those seconds showed „Hört zu" before, and the voice test answered into them.
10. **The voice test's turn-taking and checks**: it answers 1.5 seconds after an agent message that ends with a question and 8 seconds after any other, so it never talks into "one moment, I'm writing everything down". It asserts that every scripted answer was played, that „Schreibt Ihre Antworten auf ..." was shown, and that the stored answers contain a fact only the founder said (the co-founder's surname), because the run in which the agent invented the answers passed the plan's checks.
11. **Team pages**: the settings card labels the stored values with the options of `GET /api/team/settings`, so the labels stay in the config module; the detail page widens the content (`.content:has(.detail-layout)`); a list row opens the detail, and its company name is a button that searches for the company.
12. **CLI**: argparse subcommands (`create-access-code` takes the email). `create-access-code` validates the email like the team area; `print-openai-key` prints only the key, for test.sh's variable.
13. **pytest lists its five slowest tests on every run** (`--durations=5`). It showed that the goodbye tests had silently fallen back to the wait cap, which led to the event-order fix in decision 3.
14. **The backend's healthcheck** checks every second while the app starts and every 30 seconds afterwards (`start_interval`), so it does not fill the backend's log.

### Deviations
- The backend starts the startup lookup instead of the agent handing it over (decision 5), and the agent waits silently while everything is written down instead of "keeps talking" (decision 6). Sections 7 and 17 of the high-level plan describe both.
- The changes to the goodbye watch, the prompts and the status belong to commits 4 and 5; this commit's voice test found them.

### Inconsistencies found
- The plan's prompt wording ("hand that search over", "keep the conversation going while you wait") contradicted OpenAI's guidance for `gpt-live-1`. The spike would have shown it, but it has not been run.
- "Once the agent has spoken after the completion" (the goodbye rule) did not account for the note-taker's report time, and `GOODBYE_MAX_WAIT_S` (30) was shorter than the summary read before a goodbye without follow-ups.
- The reviewer's "never for an answer the founder declined" collided with "always the closing round".
- The plan's voice test checked only that the answers are non-empty, so a conversation the agent held with itself passed.

### Known limits
- Prompt-only, by nature: *that* the agent hands work over during the conversation, waits for the founder's answers and says goodbye only after the confirmation. In the final runs it followed every rule; if it ever ended without writing down, the conversation would stay „Läuft" until STOPP and end Unfinished. The voice test of every `--complete` run checks exactly this, and that the answers are the founder's.
- OpenAI's transcript of the agent sometimes starts with a filler or stray characters („Hm.", once „ေးေး"); this is not the app's text.
- Reply times per conversation: medians of 0.2 to 1.2 seconds; single replies up to 2.4 seconds.

### Operator to-dos
- Have one conversation yourself in Chrome: it judges what no test can (how natural the voice sounds, how fast the replies feel).
- The spike's remaining questions (the session time limit, the voices, the thinking levels; see commit 1).
- The voice test's founders (`e2e-<timestamp>@example.com`) and their conversations stay in the database and show up in the Team area, like real ones.

---

## Coverage Check

Every requirement and every user story has a commit that delivers it.

| Requirement | Delivered in |
|---|---|
| Voice in the browser: speak, understand, answer by voice | Commits 4 and 5 |
| Low latency (ideally under 1 to 2 seconds) | Commit 1 (verified), commit 4 (measured and logged), commit 6 (measured in the real voice test) |
| Natural speech output | Commit 1 (voices chosen), commit 3 (voice per language in the config module) |
| Start/stop by button | Commit 5 |
| Asks instead of only answering; follows up once if vague | Commit 4 (prompts, reviewer, at most one follow-up per question) |
| Common thread, no repetition | Commit 4 (voice prompt, one session for the whole conversation) |
| Transcript visible (who said what) | Commit 5 (live), commit 6 (Team area) |
| Past conversations with timestamps | Commit 2 (lists), commit 5 (founder view), commit 6 (Team list and detail) |
| At least 2 settings | Commit 3 (conversation language, agent name, catalog, models, thinking levels) |
| Summary at the end, result stored in a structured way | Commit 4 (questionnaire and summary), commit 5 (success message), commit 6 (Team detail) |
| Bonus: tool calling, web search for the startup | Commit 4 |
| Bonus: streaming | Commit 5 (voice and transcript stream live) |
| Bonus: good UI/UX | Commits 2, 3, 5 and 6 |

| User story | Delivered in |
|---|---|
| T1 Invite a founder | Commit 2 |
| T2 Review conversations | Commit 6 |
| T3 Adjust the agent | Commit 3 |
| F1 Sign up and get ready | Commit 2 (signup), commit 5 (tutorial, device check) |
| F2 Have the conversation | Commits 4 and 5 |
| F3 Finish and have the result stored | Commits 4 and 5 |
| F4 The conversation stops early | Commits 4 and 5 |
| F5 Come back for another conversation | Commit 2 (unlock), commit 5 (past conversations) |
| D1 Set up, start and test | Commit 2, completed in commit 6 |
