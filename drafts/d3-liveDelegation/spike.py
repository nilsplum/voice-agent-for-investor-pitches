#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets==17.4", "sounddevice==0.5.6"]
# ///
"""Live API spike: a real GPT-Live session with a note-taker, fake tools and a sideband.

It settles the open points of section 17 of _docs/planning/high-level-plan.md before any app
code depends on them. The questions, how to run them and the findings are in README.md next to
this file.

The terminal plays the browser, and a second connection plays our backend:
  primary   WebSocket /live/sessions: microphone in, speaker out, transcript on screen. It
            receives the same events as the browser's data channel, so it shows what the
            browser will be able to see (transcripts, delegation and nested Responses events).
  sideband  WebSocket /live/sessions/{id}/attach: sends the kickoff, answers the note-taker's
            tool calls, reads the summary out through a commentary, swaps the tools and ends the
            session after the goodbye, exactly as the backend will. OpenAI documents the sideband
            for WebRTC and SIP sessions only, so if the attach to this WebSocket session is
            refused, the primary takes over these duties and the log and the summary say so.

The tools are fakes with the app's real names and strict schemas over three questions.
submit_initial hands the summary to the voice agent, "reviews" for 8 seconds, swaps the tools to
phase 2 and returns one follow-up for question 2. submit_follow_up completes the conversation.

Every event of every connection is appended to events-<timestamp>.jsonl next to this file, with
a wall clock timestamp, the connection's name and its direction. Audio payloads are replaced by
their size (their timing fields are kept), the outgoing microphone chunks are not logged, and the
API key is never written anywhere.

Run:   .venv/bin/python spike.py                          (German, voice juni; headphones)
       .venv/bin/python spike.py --language en --voice marin
       .venv/bin/python spike.py --kickoff commentary     (which kickoff makes the agent speak first)
       .venv/bin/python spike.py --probe-efforts          (no audio: accepted reasoning efforts)
"""

import argparse
import array
import asyncio
import base64
import itertools
import json
import math
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

import sounddevice as sd
from websockets import ConnectionClosed, InvalidHandshake, InvalidStatus
from websockets.asyncio.client import connect

# --- Endpoints and models ---------------------------------------------------------------
API_URL = "https://api.openai.com/v1"
LIVE_URL = "wss://api.openai.com/v1/live/sessions"
LIVE_MODEL = "gpt-live-1"
NOTE_TAKER_MODEL = "gpt-6-luna"  # OpenAI's recommended starting point for Responses delegation
NOTE_TAKER_EFFORT = "low"

# --- Tuning (audio as in d2) ------------------------------------------------------------
RATE = 24_000          # the Live API's native PCM rate: no resampling anywhere
CHUNK_MS = 20          # microphone chunk size
JITTER_MS = 80         # play the agent's audio at most this long after it arrives
ECHO_TAIL_S = 0.35     # speakers mode: keep the microphone muted this long after the agent stops
VOICE_RMS = 500        # microphone level that counts as "you are speaking" (latency readout only)

# --- The fake backend -------------------------------------------------------------------
REVIEW_S = 8               # how long the fake review takes, so the summary is read while it "runs"
GOODBYE_SILENCE_S = 2.5    # after the goodbye began: close once nobody spoke for this long
GOODBYE_MAX_WAIT_S = 30    # close at the latest this long after the completion
ATTACH_TIMEOUT_S = 5
PROBE_MODELS = ["gpt-6-luna", "gpt-6.1-sol"]  # the note-taker models the settings will offer
PROBE_EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]  # union of docs and SDK
PROBE_TIMEOUT_S = 20

LANGUAGES = {"de": ("German", "juni"), "en": ("English", "marin")}  # name for the prompts, default voice

# Three catalog questions in German, as the team writes them in the app (the agent asks them in the
# conversation language). Question 2 gets the follow-up, so 1 and 3 are optional in phase 2.
QUESTIONS = {
    1: ("Produkt", "Welches Problem lösen Sie, und wie löst Ihr Produkt es?",
        "Das Problem der Kunden, die Lösung in einfachen Worten und was sie besser macht als heute."),
    2: ("Traktion", "Welche Traktion haben Sie bisher?",
        "Messbare Fortschritte wie Nutzer, zahlende Kunden, Umsatz oder Pilotprojekte, wenn möglich mit Zahlen."),
    3: ("Finanzierungsbedarf", "Wie viel Kapital brauchen Sie, warum, und wofür setzen Sie es ein?",
        "Der Betrag, der Grund für die Finanzierung und die wichtigsten Verwendungszwecke."),
}
FOLLOW_UP_ID = 2
FOLLOW_UP = ("Können Sie Ihre Traktion mit Zahlen belegen, zum Beispiel Nutzer, Kunden oder Umsatz?",
             "Die Antwort nennt keine Zahlen.")

# --- Prompts and texts (short versions of the app's context system) ----------------------
VOICE_INSTRUCTIONS = """\
You are Mira, the voice agent of an investor in startups, in a first conversation with {founder}, \
founder of {company}. Speak {language}. If the founder switches language, follow. In German, address \
the founder formally with "Sie".

Style: warm and natural. Short turns of one to three sentences, one question at a time. Never read \
lists or URLs aloud. Stop and listen when the founder interrupts.

Flow:
- Ask the questions below in order, one at a time. Skip a question the founder already answered in \
full; if it is partly answered, say so and ask only for the rest.
- Do not repeat yourself unless asked, and do not ask follow-up questions of your own: follow-ups come \
from the review at the end.
- When every question has an answer, hand over the writing down.
- When a summary arrives, read it to the founder as a statement ("Here is what I've written down: ...") \
and finish it before anything else.
- Then ask only the follow-ups you are given, one at a time. If the founder adds or corrects something \
about another question, accept it briefly and move on. When every follow-up has an answer, hand over \
the writing down again.
- When you hear that everything is written down, thank the founder, say the team will be in touch, \
and say goodbye.

Delegation policy:
Backend tools:
- Web search: looks up the startup and public information.
- Questionnaire: rereads the questions.
- Writing down: writes the founder's answers down and has them reviewed.
Generate <|SpawnThinking|> when:
- the conversation starts, to look up {company} online;
- the founder asks a general question that needs a web search;
- every question has an answer, to write everything down;
- every follow-up has an answer, to write everything down;
- you need to reread the questions.
Do not generate <|SpawnThinking|> when:
- you can answer from the conversation;
- you need a brief clarification first.
Generate <|SpawnThinking|> before giving an answer that depends on backend work. Do not guess the \
result while waiting. Acknowledge at once ("Let me look that up." or "I'm writing everything down, \
one moment.") and keep the conversation going while you wait.

Ask these questions in this order:
{questions}"""

KICKOFF = """\
Begin now. Greet {founder} by name and mention {company}. Explain the conversation: a few minutes, \
one question at a time, follow-ups at the end. Say you are quickly looking up {company} online and hand \
that over. Then ask whether {founder} has any important questions before you start, and listen."""

NOTE_TAKER_INSTRUCTIONS = """\
You work in the background for Mira, the voice agent in a first conversation between an investor and a \
startup founder. You are the only one who calls tools, and you report back in short sentences Mira \
can say. The conversation comes from live transcripts, which can contain mistakes and later corrections.

Answers: write every answer in the founder's own words and in the conversation language, cleaned of \
fillers and repetitions. Collect everything the founder said about a question, wherever in the \
conversation it was said. Never invent anything; write a declined question as declined. Write the \
summary as a short statement of two to four sentences in the conversation language, without judgement.

Follow-up round: write the follow-up answer into its own question's field, and anything the founder \
added or corrected about another question into that question's field. Leave a field empty if nothing \
was said about its question in this round. Every piece of information goes to the question it belongs \
to, never into a field just because that field's follow-up was being asked.

Search: one search per question. At the start, search for the company name. Use the results only as \
background.

Reporting: pass on tool results faithfully. After submit_initial, pass on the follow-ups exactly as \
given, or the instruction to say goodbye."""

SUMMARY_COMMENTARY = ("The answers are written down and are being checked now. Read this summary to the "
                      "founder as a statement, starting with \"Here is what I've written down:\", and "
                      "finish it before anything else. Summary: {summary}")
FOLLOW_UPS_OUTPUT = ("The review selected one follow-up. Once the summary is read, ask it, then write the "
                     "answer down with submit_follow_up. Question {id} ({topic}): {question}")
COMPLETED_OUTPUT = ("Everything is written down. Thank the founder, say the team will be in touch, "
                    "and say goodbye.")
UNAVAILABLE_OUTPUT = "This tool is not available at this point of the conversation."
FAKE_SEARCH = [{"title": "Fake result", "link": "https://example.com",
                "snippet": "This is a fake search result from a test. It contains no information."}]


# --- Tools ------------------------------------------------------------------------------
def tool(name, description, fields):
    """A strict function tool. fields: {field name: (JSON schema of the value, description)}."""
    return {
        "type": "function", "name": name, "description": description, "strict": True,
        "parameters": {
            "type": "object",
            "properties": {key: {**schema, "description": text} for key, (schema, text) in fields.items()},
            "required": list(fields),
            "additionalProperties": False,
        },
    }


STRING = {"type": "string"}
GET_QUESTIONNAIRE = tool(
    "get_questionnaire", "Rereads questions with their context. Example: ids [2] rereads question 2.",
    {"ids": ({"type": "array", "items": {"type": "integer"}}, "IDs of the questions to reread; empty for all.")})
WEB_SEARCH = tool(
    "web_search", "Searches the web: the startup at the start, and general questions the founder asks.",
    {"query": (STRING, "The search query, without confidential details from the conversation.")})
SUBMIT_INITIAL = tool(
    "submit_initial", "Writes down one answer per question and a summary once every question has an answer.",
    {**{f"question_{qid}": (STRING, f"{topic}: {question} Covers: {context}")
        for qid, (topic, question, context) in QUESTIONS.items()},
     "summary": (STRING, "A short statement of all answers, two to four sentences, in the conversation language.")})
SUBMIT_FOLLOW_UP = tool(
    "submit_follow_up", "Writes down the follow-up round once every follow-up has an answer.",
    {f"question_{qid}": (STRING, f"{topic}, follow-up, must be answered: {FOLLOW_UP[0]} Missing: {FOLLOW_UP[1]}"
                         if qid == FOLLOW_UP_ID else
                         f"{topic}: {question} Optional: only what the founder added or corrected about this "
                         "question in the follow-up round; leave empty if nothing.")
     for qid, (topic, question, _) in QUESTIONS.items()})
PHASE_1_TOOLS = [GET_QUESTIONNAIRE, WEB_SEARCH, SUBMIT_INITIAL]
PHASE_2_TOOLS = [GET_QUESTIONNAIRE, WEB_SEARCH, SUBMIT_FOLLOW_UP]


# --- Event log --------------------------------------------------------------------------
class EventLog:
    """One JSON line per event: {t (wall clock), conn, dir, event} or {t, conn, note}."""

    def __init__(self, path: Path):
        self.path, self.file = path, path.open("a", encoding="utf-8")
        self.counts: Counter[str] = Counter()

    def event(self, conn: str, direction: str, event: dict):
        event = dict(event)
        for key in ("delta", "audio"):  # audio payloads: keep only their size
            if "audio" in event.get("type", "") and isinstance(event.get(key), str):
                event[key] = f"<{len(event[key]) * 3 // 4} bytes>"
        if direction == "received":
            kind = event.get("type", "?")
            if kind == "response.event":
                kind += f"[{event.get('event', {}).get('type')}]"
            self.counts[f"{conn}: {kind}"] += 1
        self._write({"t": round(time.time(), 3), "conn": conn, "dir": direction, "event": event})

    def note(self, conn: str, text: str):
        self._write({"t": round(time.time(), 3), "conn": conn, "note": text})

    def _write(self, record: dict):
        self.file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.file.flush()


# --- Audio (from d2, Live mode only) ----------------------------------------------------
class Audio:
    """Mic -> asyncio queue, asyncio -> speaker. Raw PCM16 mono at RATE, callbacks run on PortAudio threads."""

    def __init__(self, loop, mic=None, speaker=None, echo_guard=False):
        self.loop, self.echo_guard = loop, echo_guard
        self.mic_chunks: asyncio.Queue[bytes] = asyncio.Queue()
        self.lock = threading.Lock()
        self.buf = bytearray()     # agent audio waiting to be played
        self.playing = False       # False while waiting for the jitter buffer to fill
        self.waiting_since = 0.0
        self.last_played = 0.0     # when the speaker last output agent audio
        self.last_voice = 0.0      # when the mic last heard the founder
        self.on_latency = None     # callback(seconds) when the agent starts answering
        block = RATE * CHUNK_MS // 1000
        common = dict(samplerate=RATE, channels=1, dtype="int16", blocksize=block, latency="low")
        self.mic = sd.RawInputStream(device=mic, callback=self._mic_callback, **common)
        self.out = sd.RawOutputStream(device=speaker, callback=self._speaker_callback, **common)

    def __enter__(self):
        self.out.start()
        self.mic.start()
        return self

    def __exit__(self, *exc):
        self.mic.close()
        self.out.close()

    def agent_is_talking(self) -> bool:
        return bool(self.buf) or time.monotonic() - self.last_played < ECHO_TAIL_S

    def _mic_callback(self, data, frames, time_info, status):
        chunk = bytes(data)
        if self.echo_guard and self.agent_is_talking():
            chunk = bytes(len(chunk))  # silence, so the agent does not hear itself through the speakers
        else:
            samples = array.array("h", chunk)
            if math.sqrt(sum(s * s for s in samples) / len(samples)) > VOICE_RMS:
                self.last_voice = time.monotonic()
        self.loop.call_soon_threadsafe(self.mic_chunks.put_nowait, chunk)

    def _speaker_callback(self, out, frames, time_info, status):
        now, n = time.monotonic(), len(out)
        with self.lock:
            if not self.playing and self.buf and (
                len(self.buf) >= JITTER_MS * RATE * 2 // 1000 or now - self.waiting_since >= JITTER_MS / 1000
            ):
                self.playing = True
                if self.on_latency and self.last_played < self.last_voice < now - 0.1:  # founder spoke, then paused
                    lag = now - self.last_voice + self.mic.latency + self.out.latency
                    self.loop.call_soon_threadsafe(self.on_latency, lag)
            take = min(n, len(self.buf)) if self.playing else 0
            out[:take] = self.buf[:take]
            del self.buf[:take]
            if take:
                self.last_played = now
            if take < n:
                self.playing = False  # ran dry: refill the jitter buffer before playing again
        out[take:] = bytes(n - take)

    def play(self, pcm: bytes):
        with self.lock:
            if not self.buf:
                self.waiting_since = time.monotonic()
            self.buf += pcm


# --- Terminal transcript and reply times ------------------------------------------------
class Transcript:
    """Prints both sides as they stream and measures reply times from the transcript timestamps.

    A reply time is the agent's first start_ms after a founder message minus that message's last
    end_ms (the rule the app will use). Negative values are overlaps such as backchannels.
    """

    LABELS = {"founder": "\n\033[2mYou:\033[0m ", "agent": "\n\033[1;36mMira:\033[0m "}

    def __init__(self):
        self.speaker = None        # who spoke last, for the reply times
        self.labelled = None       # whose label the current screen line starts with
        self.founder_end_ms = 0
        self.reply_ms: list[int] = []

    def delta(self, speaker: str, text: str, start_ms: int, end_ms: int):
        if speaker == "agent" and self.speaker == "founder":
            self.reply_ms.append(start_ms - self.founder_end_ms)
            self.note(f"[transcript reply time {(start_ms - self.founder_end_ms) / 1000:.2f} s]")
        if speaker == "founder":
            self.founder_end_ms = end_ms
        self.speaker = speaker
        if speaker != self.labelled:
            print(self.LABELS[speaker], end="")
            self.labelled = speaker
        print(text, end="", flush=True)

    def note(self, text: str):
        print(f"\n\033[2m{text}\033[0m", end="", flush=True)
        self.labelled = None


# --- The session ------------------------------------------------------------------------
class Spike:
    def __init__(self, args, key: str, log: EventLog, transcript: Transcript):
        self.args, self.key, self.log, self.transcript = args, key, log, transcript
        language, _ = LANGUAGES[args.language]
        values = dict(founder=args.founder, company=args.company, language=language)
        questions = "\n".join(f"{qid}. {topic}: {question} (Covers: {context})"
                              for qid, (topic, question, context) in QUESTIONS.items())
        self.instructions = VOICE_INSTRUCTIONS.format(questions=questions, **values)
        self.kickoff = KICKOFF.format(**values)
        self.primary = None
        self.sideband = None
        self.session: dict = {}
        self.expires_in_s = None          # session.started's expires_at, relative to the start
        self.phase = 1
        self.handled_calls: set[str] = set()
        self.tasks: set[asyncio.Task] = set()
        self.ids = itertools.count(1)
        self.spoke = asyncio.Event()      # any transcript delta on the control connection
        self.completed_at = None          # wall clock of submit_follow_up's success
        self.agent_spoke_since_completion = False

    @property
    def control(self):
        """The connection that acts as our backend: the sideband, or the primary if the attach failed."""
        return self.sideband or self.primary

    def control_name(self):
        return "sideband" if self.sideband else "primary"

    async def send(self, ws, conn: str, event: dict):
        event = {**event, "event_id": f"spike_{next(self.ids)}"}
        self.log.event(conn, "sent", event)
        await ws.send(json.dumps(event))

    async def start(self, ws):
        """session.start on the primary connection and wait for session.started."""
        self.primary = ws
        session = {
            "model": LIVE_MODEL,
            "instructions": self.instructions,
            "audio": {"format": {"type": "audio/pcm", "rate": RATE}, "output": {"voice": self.args.voice}},
            "delegation": {"type": "responses", "responses": {
                "model": NOTE_TAKER_MODEL,
                "instructions": NOTE_TAKER_INSTRUCTIONS,
                "tools": PHASE_1_TOOLS,
                "tool_choice": "auto",
                "parallel_tool_calls": False,
                "reasoning": {"effort": self.args.effort},
            }},
        }
        if self.args.kickoff in ("input", "both"):
            session["input"] = [{"type": "message", "role": "developer",
                                 "content": [{"type": "input_text", "text": self.kickoff}]}]
        await self.send(ws, "primary", {"type": "session.start", "session": session})
        async for raw in ws:
            event = json.loads(raw)
            self.log.event("primary", "received", event)
            if event["type"] == "session.started":
                self.session = event["session"]
                self.expires_in_s = self.session["expires_at"] - time.time()
                self.log.note("primary", f"session expires in {self.expires_in_s:.0f} s")
                return
            if event["type"] in ("error", "session.closed"):
                sys.exit(f"Live session failed to start: {json.dumps(event, indent=2)}")

    async def attach(self):
        """Attach the sideband as the backend will. On refusal, the primary keeps the control duties."""
        url = f"{LIVE_URL}/{self.session['id']}/attach"
        try:
            self.sideband = await connect(url, additional_headers=auth(self.key), max_size=None,
                                          compression=None, open_timeout=ATTACH_TIMEOUT_S)
            self.log.note("sideband", "attached")
        except InvalidStatus as e:
            self.log.note("sideband", f"attach refused: HTTP {e.response.status_code} "
                                      f"{e.response.body.decode(errors='replace')[:300]}")
        except (InvalidHandshake, OSError, TimeoutError) as e:
            self.log.note("sideband", f"attach failed: {type(e).__name__}")
        if not self.sideband:
            self.transcript.note("Sideband attach failed, the primary connection handles the tools (see the log).")

    async def send_kickoff(self):
        if self.args.kickoff in ("commentary", "both"):
            await self.send(self.control, self.control_name(),
                            {"type": "session.commentary.append", "delegation_id": None, "content": self.kickoff})

    async def read(self, ws, conn: str, audio=None):
        """Read one connection until session.closed. The primary plays and prints; the control acts."""
        async for raw in ws:
            event = json.loads(raw)
            self.log.event(conn, "received", event)
            kind = event["type"]
            if conn == "primary":
                if kind == "session.output_audio.delta":
                    audio.play(base64.b64decode(event["delta"]))
                elif kind == "session.input_transcript.delta":
                    self.transcript.delta("founder", event["delta"], event["start_ms"], event["end_ms"])
                elif kind == "session.output_transcript.delta":
                    self.transcript.delta("agent", event["delta"], event["start_ms"], event["end_ms"])
                elif kind == "error":
                    self.transcript.note(f"error {event['error'].get('code')}: {event['error'].get('message')}")
            if ws is self.control:
                if kind in ("session.input_transcript.delta", "session.output_transcript.delta"):
                    self.spoke.set()
                    if kind == "session.output_transcript.delta" and self.completed_at:
                        self.agent_spoke_since_completion = True
                elif kind == "response.event":
                    self.on_response_event(event)
            if kind == "session.closed":
                return

    def on_response_event(self, event: dict):
        """A finished function call of the note-taker starts its fake handler as its own task."""
        nested = event.get("event", {})
        item = nested.get("item") or {}
        if nested.get("type") != "response.output_item.done" or item.get("type") != "function_call":
            return
        if item["call_id"] in self.handled_calls:  # the attach replays the last 3 seconds of events
            return
        self.handled_calls.add(item["call_id"])
        task = asyncio.create_task(self.run_tool(item))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def run_tool(self, item: dict):
        """Every call gets an answer, also when a handler fails, so the note-taker never hangs."""
        started = time.monotonic()
        name, call_id = item["name"], item["call_id"]
        try:
            arguments = json.loads(item.get("arguments") or "{}")
            self.transcript.note(f"[note-taker calls {name}: {json.dumps(arguments, ensure_ascii=False)}]")
            if name == "get_questionnaire":
                output = json.dumps([{"id": qid, "topic": t, "question": q, "context": c}
                                     for qid, (t, q, c) in QUESTIONS.items()
                                     if not arguments["ids"] or qid in arguments["ids"]], ensure_ascii=False)
            elif name == "web_search":
                output = json.dumps(FAKE_SEARCH)
            elif name == "submit_initial" and self.phase == 1:
                output = await self.submit_initial(arguments)
            elif name == "submit_follow_up" and self.phase == 2:
                output = COMPLETED_OUTPUT
                self.completed_at = time.time()
                self.start_task(self.close_after_goodbye())
            else:
                output = UNAVAILABLE_OUTPUT
        except Exception as e:
            output = f"The tool failed ({type(e).__name__}). Tell the founder it did not work this time."
            self.log.note(self.control_name(), f"tool {name} raised {type(e).__name__}: {e}")
        conn = self.control_name()
        await self.send(self.control, conn, {"type": "response.item.create", "item": {
            "type": "function_call_output", "call_id": call_id, "output": output}})
        # Appending the output alone does not resume the note-taker.
        await self.send(self.control, conn, {"type": "response.create"})
        self.log.note(conn, f"tool {name} answered after {time.monotonic() - started:.2f} s")

    async def submit_initial(self, arguments: dict) -> str:
        """Summary aloud while the fake review runs, then the tool swap and one follow-up."""
        self.phase = 2  # at once: a second submit_initial during the review gets UNAVAILABLE_OUTPUT
        conn = self.control_name()
        await self.send(self.control, conn, {"type": "session.commentary.append", "delegation_id": None,
                                             "content": SUMMARY_COMMENTARY.format(summary=arguments["summary"])})
        await asyncio.sleep(REVIEW_S)
        await self.send(self.control, conn, {"type": "session.update", "session": {
            "delegation": {"type": "responses", "responses": {"tools": PHASE_2_TOOLS}}}})
        topic = QUESTIONS[FOLLOW_UP_ID][0]
        return FOLLOW_UPS_OUTPUT.format(id=FOLLOW_UP_ID, topic=topic, question=FOLLOW_UP[0])

    async def close_after_goodbye(self):
        """Once the agent spoke after the completion and then nobody spoke for GOODBYE_SILENCE_S, close."""
        loop = asyncio.get_running_loop()
        give_up = loop.time() + GOODBYE_MAX_WAIT_S
        while loop.time() < give_up:
            self.spoke.clear()
            try:
                await asyncio.wait_for(self.spoke.wait(), GOODBYE_SILENCE_S)
            except TimeoutError:
                if self.agent_spoke_since_completion:
                    break
        self.log.note(self.control_name(), "goodbye silence reached, closing the session")
        await self.send(self.control, self.control_name(), {"type": "session.close"})

    def start_task(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)


# --- Reasoning effort probe (question 10, no audio) -------------------------------------
def probe_responses(key: str, model: str, effort: str) -> str:
    """Streamed, so the status line answers at once: a rejected effort is an HTTP 400 before any output."""
    body = json.dumps({"model": model, "input": "Reply with the single word OK.", "stream": True,
                       "reasoning": {"effort": effort}, "max_output_tokens": 256}).encode()
    request = urllib.request.Request(f"{API_URL}/responses", data=body, method="POST",
                                     headers={**auth(key), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT_S):
            return "accepted"
    except urllib.error.HTTPError as e:
        return f"rejected (HTTP {e.code}: {error_message(e.read())})"
    except (urllib.error.URLError, TimeoutError) as e:
        return f"no answer ({type(e).__name__})"


async def probe_delegation(key: str, model: str, effort: str, log: EventLog) -> str:
    """Start a Live session whose note-taker uses this effort and ask the note-taker once.

    The nested response.created means the Responses backend took the configuration: a rejected setting
    arrives as an error event (responses_validation_failed) instead.
    """
    conn = f"probe {model} {effort}"
    session = {"model": LIVE_MODEL, "instructions": "Stay silent.",
               "audio": {"format": {"type": "audio/pcm", "rate": RATE}},
               "delegation": {"type": "responses", "responses": {
                   "model": model, "instructions": "Reply with the single word OK.", "reasoning": {"effort": effort}}}}
    ids = itertools.count(1)

    async def send(ws, event):
        event = {**event, "event_id": f"probe_{next(ids)}"}
        log.event(conn, "sent", event)
        await ws.send(json.dumps(event))

    async def silence(ws):  # the session timeline advances with input audio
        chunk = base64.b64encode(bytes(RATE * CHUNK_MS // 1000 * 2)).decode()
        while True:
            await ws.send(json.dumps({"type": "session.input_audio.append", "audio": chunk}))
            await asyncio.sleep(CHUNK_MS / 1000)

    result, feeder = f"no answer within {PROBE_TIMEOUT_S} s", None
    async with connect(LIVE_URL, additional_headers=auth(key), max_size=None, compression=None) as ws:
        await send(ws, {"type": "session.start", "session": session})
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_S):
                async for raw in ws:
                    event = json.loads(raw)
                    log.event(conn, "received", event)
                    kind, nested = event["type"], event.get("event", {})
                    if kind == "session.started":
                        feeder = asyncio.create_task(silence(ws))
                        await send(ws, {"type": "response.item.create", "item": {
                            "type": "message", "role": "user",
                            "content": [{"type": "input_text", "text": "Reply with the single word OK."}]}})
                        await send(ws, {"type": "response.create"})
                    elif kind == "error":
                        result = f"rejected ({event['error'].get('code')}: {event['error'].get('message')})"
                        break
                    elif kind == "session.closed":
                        result = f"session closed ({event.get('reason')})"
                        break
                    elif kind == "response.event" and nested.get("type") == "response.created":
                        result = "accepted"
                        break
                    elif kind == "response.event" and nested.get("type") in ("response.failed", "response.incomplete"):
                        result = f"{nested['type']} ({json.dumps(nested.get('response', {}).get('error'))})"
                        break
        except TimeoutError:
            pass
        finally:
            if feeder:
                feeder.cancel()
            try:  # end the session cleanly so it stops billing
                await send(ws, {"type": "session.close"})
                async with asyncio.timeout(3):
                    async for raw in ws:
                        log.event(conn, "received", json.loads(raw))
                        if json.loads(raw)["type"] == "session.closed":
                            break
            except (ConnectionClosed, TimeoutError):
                pass
    return result


async def probe_efforts(key: str, log: EventLog, models: list[str]):
    print(f"{'model':<14} {'effort':<8} {'Responses API':<40} delegation")
    for model in models:
        for effort in PROBE_EFFORTS:
            responses = await asyncio.to_thread(probe_responses, key, model, effort)
            delegation = await probe_delegation(key, model, effort, log)
            log.note("probe", f"{model} {effort}: responses {responses}; delegation {delegation}")
            print(f"{model:<14} {effort:<8} {responses[:39]:<40} {delegation}", flush=True)


# --- Main -------------------------------------------------------------------------------
async def send_mic(ws, audio):
    while True:
        chunk = await audio.mic_chunks.get()
        await ws.send(json.dumps({"type": "session.input_audio.append", "audio": base64.b64encode(chunk).decode()}))


async def converse(args, key: str, log: EventLog):
    out_name = sd.query_devices(args.speaker, "output")["name"]
    echo_guard = args.speakers or (not args.headphones and "speaker" in out_name.lower())
    loop = asyncio.get_running_loop()
    audio = Audio(loop, args.mic, args.speaker, echo_guard)
    transcript = Transcript()
    audio.on_latency = lambda s: transcript.note(f"[heard after {s:.2f} s]")
    spike = Spike(args, key, log, transcript)

    print(f"\033[1m{LIVE_MODEL}\033[0m + {NOTE_TAKER_MODEL} ({args.effort}) · voice {args.voice} · "
          f"kickoff {args.kickoff} · {sd.query_devices(args.mic, 'input')['name']} -> {out_name}")
    print("Speaker mode: your mic is muted while Mira talks (wear headphones to interrupt her)." if echo_guard
          else "Full duplex: you can interrupt Mira at any time.")
    print("Connecting…", end="", flush=True)

    async with connect(LIVE_URL, additional_headers=auth(key), max_size=None, compression=None) as primary:
        await spike.start(primary)
        await spike.attach()
        print(f" session {spike.session['id']}, sideband {'attached' if spike.sideband else 'NOT attached'}. "
              "Ctrl+C ends the session.")
        try:
            with audio:
                readers = [asyncio.create_task(spike.read(primary, "primary", audio))]
                if spike.sideband:
                    readers.append(asyncio.create_task(spike.read(spike.sideband, "sideband")))
                mic = asyncio.create_task(send_mic(primary, audio))
                await spike.send_kickoff()  # the microphone is flowing now, as the docs require
                try:
                    # asyncio.wait, not await: Ctrl+C cancels this coroutine but not the reader,
                    # which still has to receive the session.closed of the close below.
                    await asyncio.wait([readers[0]])  # the primary ends with session.closed
                    readers[0].result()  # re-raise a dropped connection
                except asyncio.CancelledError:  # Ctrl+C: close the session ourselves
                    try:
                        await spike.send(primary, "primary", {"type": "session.close"})
                        await asyncio.wait([readers[0]], timeout=3)
                    except ConnectionClosed:
                        pass
                finally:
                    for task in [mic, *readers, *spike.tasks]:
                        task.cancel()
                    await asyncio.gather(mic, *readers, *spike.tasks, return_exceptions=True)
        finally:
            if spike.sideband:
                await spike.sideband.close()
            summarize(spike, log)


def summarize(spike: Spike, log: EventLog):
    """The numbers several findings need, so they don't have to be dug out of the log by hand."""
    replies = [ms for ms in spike.transcript.reply_ms if ms >= 0]
    print("\n\n\033[1mSummary\033[0m")
    if spike.session:
        print(f"session {spike.session['id']}: expires_at {spike.expires_in_s / 60:.1f} min after the start; "
              f"sideband {'attached' if spike.sideband else 'not attached'}")
    if replies:
        print(f"transcript reply times: {len(replies)} replies, median {statistics.median(replies) / 1000:.2f} s, "
              f"max {max(replies) / 1000:.2f} s ({len(spike.transcript.reply_ms) - len(replies)} overlaps not counted)")
    print("events received:")
    for kind, count in sorted(log.counts.items()):
        print(f"  {count:5}  {kind}")
    print(f"log: {log.path}")


def auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def error_message(body: bytes) -> str:
    try:
        return json.loads(body)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return body.decode(errors="replace")[:200]


def api_key():
    if key := os.environ.get("OPENAI_API_KEY"):
        return key
    env = Path(__file__).with_name(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip().removeprefix("export ") == "OPENAI_API_KEY":
                return value.strip().strip("'\"")
    return None


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--language", choices=list(LANGUAGES), default="de", help="conversation language (default: de)")
    p.add_argument("--voice", help="voice (default: juni for de, marin for en); German: juni, nuri, flitz")
    p.add_argument("--kickoff", choices=["input", "commentary", "both"], default="both",
                   help="how the agent is told to begin: session input, commentary after the start, or both")
    p.add_argument("--effort", default=NOTE_TAKER_EFFORT, help=f"note-taker reasoning effort (default: {NOTE_TAKER_EFFORT})")
    p.add_argument("--founder", default="Alex", help="the founder's name you play (default: Alex)")
    p.add_argument("--company", default="Nordlicht Robotics", help="the startup you play (default: Nordlicht Robotics)")
    p.add_argument("--probe-efforts", action="store_true", help="no conversation: test which reasoning efforts "
                   "the note-taker models accept in delegation and in the Responses API")
    p.add_argument("--mic", help="input device (name substring, see --devices)")
    p.add_argument("--speaker", help="output device (name substring, see --devices)")
    p.add_argument("--headphones", action="store_true", help="force full duplex (no echo guard)")
    p.add_argument("--speakers", action="store_true", help="force the echo guard (mute the mic while Mira talks)")
    p.add_argument("--devices", action="store_true", help="list audio devices and exit")
    args = p.parse_args()
    args.voice = args.voice or LANGUAGES[args.language][1]
    return args


async def main(args):
    key = api_key()
    if not key:
        sys.exit("Set OPENAI_API_KEY (environment variable or a .env file next to this script).")
    log = EventLog(Path(__file__).with_name(f"events-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"))
    log.note("spike", f"options: {json.dumps({k: v for k, v in vars(args).items()})}")
    if args.probe_efforts:
        await probe_efforts(key, log, PROBE_MODELS)
        print(f"log: {log.path}")
    else:
        await converse(args, key, log)


if __name__ == "__main__":
    args = parse_args()
    if args.devices:
        print(sd.query_devices())
        sys.exit()
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        pass
    except InvalidStatus as e:  # e.g. a wrong API key or no access to the model
        sys.exit(f"\nConnection rejected (HTTP {e.response.status_code}): {e.response.body.decode(errors='replace')}")
    except ConnectionClosed as e:
        sys.exit(f"\nConnection closed by the server: {e}")
    print("\nBye.")
