# Voice Agent for Investor Pitches

A web-based voice agent that conducts the first conversation between an investor and a startup
founder. The first part of this README is for the investment team (in German, like the app), the
second part for developers.

## Für das Team

### Anmelden
Öffnen Sie http://localhost:5173 und klicken Sie auf „Anmelden". Das Team hat ein gemeinsames
Login: die E-Mail-Adresse und das Passwort, die ein Entwickler in `secrets/secrets.yaml` eingetragen
hat. Danach sind Sie im Teambereich bei „Gespräche".

### Gründer einladen
1. Unter „Zugangscodes" die E-Mail-Adresse des Gründers eingeben und „Erstellen" klicken.
2. Den Code mit „Kopieren" kopieren und selbst an den Gründer schicken (die App verschickt keine
   E-Mails). Der Code wird nur dieses eine Mal angezeigt.
3. Ein Code ist 24 Stunden gültig, nur einmal nutzbar und nur mit dieser E-Mail-Adresse. Er schaltet
   genau ein Gespräch frei: bei der Registrierung oder später unter „Neues Gespräch". Für ein
   weiteres Gespräch schicken Sie einen neuen Code.
4. Die Liste zeigt jeden Code mit seinem Status: „Unbenutzt" (mit Ablaufzeit), „Benutzt" oder
   „Abgelaufen". Ein benutzter Code führt zu seinem Gespräch.

### Was Gründer erleben
Gründer registrieren sich mit dem Zugangscode und landen direkt in ihrem Gespräch. Ein kurzes
Tutorial (überspringbar) erklärt den Ablauf, der Gerätetest prüft Verbindung, Mikrofon und
Lautsprecher. Mit START beginnt das Sprachgespräch: Der Agent begrüßt, stellt die Fragen
nacheinander (bleibt eine Antwort unklar, fragt er einmal nach) und schreibt die Antworten auf, das
Transkript erscheint live. Mit „Stummschalten" oben rechts schalten Gründer ihr Mikrofon kurz stumm
(der Status zeigt dann „Mikrofon stumm"). Kleine Markierungen im Verlauf zeigen, wenn der Agent im
Hintergrund sucht oder aufschreibt; die Rückfragerunde steht in einem eigenen Abschnitt
„Rückfragen". Wer früher aufhören möchte, sagt es dem Agenten: Er schreibt das bisher Gesagte auf
und verabschiedet sich. STOPP bricht das Gespräch jederzeit ab. Am Ende steht unter dem Gespräch die
Abschlussmeldung: mit Zusammenfassung, wenn alles aufgeschrieben wurde, sonst mit dem Grund des
Abbruchs. Unter „Meine Gespräche" sehen Gründer ihre Gespräche jederzeit wieder.

### Gespräche prüfen
- „Gespräche" zeigt alle Gespräche, das neueste zuerst. Die Suche findet Gründer, E-Mail-Adressen
  und Firmen, der Filter grenzt nach Status ein; ein Klick auf eine Firma zeigt alle ihre Gespräche.
- Ein Gespräch zeigt oben die Fakten (Status und Zeiten, Gründer, verwendete Einstellungen),
  darunter den Fragebogen: die Zusammenfassung (nach einer Rückfragerunde die aktualisierte), jede
  Antwort, die Rückfragen des Prüfers mit Begründung und was der Gründer in der Rückfragerunde
  ergänzt hat. Zuletzt folgt der aufklappbare „Gesprächsverlauf": das Transkript mit der
  Abschlussmeldung, genau wie der Gründer es sieht; dort stehen auch die Rückfragen, die der Agent
  direkt im Gespräch gestellt hat. „Nicht geprüft" heißt, dass die automatische Prüfung
  fehlgeschlagen ist und es deshalb keine Rückfragerunde gab. „Nicht beantwortet" steht bei Fragen,
  die offen blieben, weil der Gründer das Gespräch früher beendet hat.
- Die Seite aktualisiert sich nicht von selbst: „Aktualisieren" lädt den aktuellen Stand, auch
  während ein Gespräch läuft (die bisherigen Nachrichten, nach dem ersten Aufschreiben die Antworten).

### Einstellungen
Unter „Einstellungen" passen Sie den Agenten an. Änderungen gelten ab dem nächsten Gespräch;
laufende und vergangene Gespräche behalten ihre Einstellungen und Fragen.
- **Agent:** Name, Gesprächssprache (Deutsch oder Englisch, jeweils mit passender Stimme) sowie
  Modell und Denkstufe des Protokollanten (die KI im Hintergrund, die nachschlägt und die Antworten
  aufschreibt) und des Prüfers (die KI, die die Antworten prüft und Rückfragen auswählt). Schnell
  ist hier meist besser: Der Protokollant bestimmt, wie lange Gründer auf Antworten warten.
- **Fragenkatalog:** Fragen hinzufügen, bearbeiten, entfernen und verschieben, jede mit Thema,
  Frage und Kontext (was eine vollständige Antwort abdeckt). Der Agent stellt sie in dieser
  Reihenfolge.
- Jede Karte hat ihr eigenes „Speichern". „Auf Standard zurücksetzen" stellt nach einer Bestätigung
  den mitgelieferten Standard wieder her.

## For developers

### Requirements
Docker (Docker Desktop), an OpenAI API key with access to `gpt-live-1`, and a Serper API key
(serper.dev). Everything else runs in containers. Founders use a desktop browser; Chrome is
recommended, because not every browser lets a website choose the speaker.

### Setup, start and tests
```bash
./scripts/setup.sh           # once: builds the containers and creates secrets/secrets.yaml
./scripts/start.sh           # the app at http://localhost:5173 (Ctrl+C stops it)
./scripts/test.sh            # the test suite, in the containers
./scripts/test.sh --complete # also the real APIs and a whole voice conversation (both keys, under $1)
```
- `setup.sh` creates `secrets/secrets.yaml` (git-ignored) from `secrets/secrets.example.yaml`,
  generates the session secret and names the four values to fill in: `openai_api_key`,
  `serper_api_key`, `team_email` and `team_password`. Only the backend's config module reads this
  file, and changes take effect after a restart. After a dependency changed, run `setup.sh` again:
  it rebuilds the containers.
- Every script starts with its preflight checks (Docker, the secrets file, the internet connection,
  both keys). A failing check says what is wrong and how to fix it; fix it and run the script again.
- `test.sh` regenerates the frontend types, runs the backend tests (pytest against a real
  PostgreSQL, with the outside APIs faked), type-checks the frontend against the new types and runs
  its unit tests (Vitest).
- `test.sh --complete` also runs the writing down (on recorded conversations), the reviewer and the
  web search against the real APIs and, last, a
  whole voice conversation: the real app in Chrome (Playwright, `e2e/`), whose founder answers with
  recorded speech, checked in the browser and in the database; it prints the backend's reply times.
  It starts the app in the background, so stop a running `start.sh` first. Its founder and
  conversation stay in the database and show up in the Team area.
- To try the founder's side without the Team area, run
  `docker compose exec backend python -m app.cli create-access-code you@example.com` while the app
  runs: it prints a new access code for that email.
- The database runs only inside the containers, without a password; its data lives in a Docker
  volume. While the app runs, the API documentation is at http://localhost:5173/api/docs.

### Architecture
```
  Browser (React)                              OpenAI
 +------------------+   audio + events    +------------------------------+
 |  Founder area    |<----- WebRTC ------>|  Live session                |
 |  Team area       |                     |   voice agent (gpt-live-1)   |
 +--------+---------+                     |   note-taker (delegation)    |
          | HTTP (one API client)         +--------------+---------------+
 +--------v---------+     sideband: tools, transcript,   |
 |  Backend         |<------------- session control -----+
 |  (FastAPI)       |------> Writing down, review (OpenAI Responses API)
 |                  |------> Serper (web search)
 +--------+---------+
 +--------v---------+
 |  PostgreSQL      |
 +------------------+
```
- **Three AI roles, one rule: the models talk and trigger; the backend writes, decides and says
  what comes next.** The voice agent (`gpt-live-1`) talks and listens, and follows up once right
  away when an answer stays vague. It calls no tools: it hands work to the note-taker, keeps
  talking while a search runs and waits while the answers are written down. The note-taker, a text
  model attached to the same Live session through OpenAI's Responses delegation, is the only AI
  that calls our tools; it only triggers them, passes a search's results on and otherwise replies
  „OK". Its model (the settings'
  „Protokollant") also writes the answers down: one structured Responses API call by the backend
  writes every answer in the founder's words from the saved transcript, the summary, and whether the
  founder wants to stop. The reviewer, another such call, checks the answers against the transcript
  and selects the follow-ups still needed: at most one per question, and none for a question the
  agent already followed up on.
- **Two phases and three tools.** In phase 1 the agent asks the catalog questions, then hands over
  `submit_initial` (no input): the answers are written down and stored. Every next step reaches the
  voice agent as a message from the backend: missing questions to ask, or the summary to read aloud
  while the review runs, then the follow-up round (its rules and questions) or the goodbye. For the
  round, the backend swaps `submit_initial` for `submit_follow_up`, which writes down only what was
  said in the round and the final summary, which replaces the first one without being read aloud.
  A founder who wants to stop ends with what was said: stored, Completed, without a review.
  `web_search` (Serper) works in both phases; its results reach the agent as the note-taker's reply.
  The startup is looked up while the agent greets: the backend asks the note-taker for it when the
  session starts, because the voice agent can hand work over only in reply to the founder; its
  result is background for the agent. The voice
  agent names the tool in each hand-over, and the backend guards the note-taker's procedure: a
  request it answers with text alone gets a reminder, and the voice agent is told to ignore that text.
- **One call.** START creates the Live session on the backend (the OpenAI key never reaches the
  browser) and attaches the sideband, a WebSocket through which the backend runs the tools, saves
  the transcript and ends the session. The audio goes straight between the browser and OpenAI. The
  browser builds the live transcript and the status from the events on its own connection, and
  reports the end of its call exactly once. The calls live in the backend's memory, so a backend
  restart, also uvicorn's `--reload` after a code change, ends running conversations as unfinished.
- **Reply times** (end of the founder's words to the start of the agent's reply) are logged per
  reply (`event=reply_time`) and summed up per conversation (`event=reply_times`). Every switch from
  the founder to the agent counts, also a short backchannel such as „Mhm". Every response of the
  note-taker is logged with its duration (`event=note_taker_finished`), and so is every structured
  call, the writing down and the review (`event=structured_call`).

### Context system and team-editable values
- Every text the AI reads lives in the context system: JSON documents in
  `backend/app/context/documents/`, each validated by its Pydantic model when the backend starts (a
  broken document stops it with a message that names the file). A prompt is a list of named entries
  (`prompts.json`), so every piece is written once; `catalog.json` holds the default questions.
- The settings and the question catalog follow one rule (`backend/app/team_values.py`): the shipped
  default (the settings in the config module, the catalog in `catalog.json`) is copied into the
  database on the very first launch, the app reads only the database, and software updates never
  overwrite the team's version. A changed default reaches an existing database only through
  „Auf Standard zurücksetzen". Every conversation copies both when it starts.

### Where things live
| What | Where |
|---|---|
| Every constant and tunable value, the default settings and the secrets loader | `backend/app/config.py` |
| The one error type (user, AI and log message) and its handlers | `backend/app/errors.py` |
| Every shape (Pydantic models) | `backend/app/schemas.py` |
| Database access (`run_db`), tables and migrations | `backend/app/db.py`, `models.py`, `migrations/` |
| Prompts, tool texts, FAQ, AI messages and the default catalog (the context system) | `backend/app/context/` |
| Everything that talks to OpenAI: the Live session, the sideband, the tools, the writing down, the reviewer | `backend/app/ai/` |
| Conversation states, questionnaire and transcript | `backend/app/conversations.py` |
| The settings and the catalog (seed, read, save, reset) | `backend/app/team_values.py` |
| The one API client and the generated types (commit them with the backend change) | `frontend/src/api/` |
| The founder's call (WebRTC), the one conversation view, the audio level and the speaker | `frontend/src/call/`, `conversation/`, `audio/` |
| Toasts and confirmations | `frontend/src/notifications/` |
| Colour tokens | `frontend/src/styles/tokens.css` |
| German labels of the backend's values | `frontend/src/labels.ts` |
| The scripts and their preflight checks | `scripts/`, `scripts/helpers/` |
| The voice conversation test (only with `--complete`) | `e2e/` |

### Deliberate trade-offs
A local MVP, so these are left out on purpose:
- Password reset, email verification and sending emails (the team sends the codes itself), and
  separate team accounts or roles (one shared team login).
- Continuing an unfinished conversation: a new attempt needs a new code.
- Audio recordings (only transcripts are stored), and any AI judgement or scoring of startups.
- Live updates in the Team area („Aktualisieren" instead).
- Hosting, several investors per installation and mobile apps (a desktop browser, Chrome recommended).
- Privacy and legal handling, fact checking, monitoring, prompt analysis, and a knowledge base
  about the investor (the agent answers process questions from its FAQ and general ones with a web search).
