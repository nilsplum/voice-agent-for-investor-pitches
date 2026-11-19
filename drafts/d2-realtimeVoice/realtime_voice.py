#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["websockets>=14", "sounddevice>=0.5"]
# ///
"""Talk to OpenAI's newest speech-to-speech models in real time, from the terminal.

Two backends (both stream raw 24 kHz PCM16 over a WebSocket, no resampling, no codecs):

  live      gpt-live-1         Live API (Sep 2026). Full-duplex: listens while it talks,
                               natural turn-taking (~0.8 s), backchannels. Default.
  realtime  gpt-realtime-2.1   Realtime API (Jul 2026). Classic turn-based voice model
                               with semantic VAD and configurable reasoning.

Run:   .venv/bin/python realtime_voice.py                 (needs OPENAI_API_KEY or a .env file)
       .venv/bin/python realtime_voice.py --api realtime --voice cedar
       .venv/bin/python realtime_voice.py --voice juni     (native German Live voice)

Headphones give the best experience: you can talk over the model and it stops.
On laptop speakers the mic is muted while the model talks so it doesn't hear itself.
"""

import argparse
import array
import asyncio
import base64
import json
import math
import os
import sys
import threading
import time
from pathlib import Path

import sounddevice as sd
from websockets import ConnectionClosed, InvalidStatus, State
from websockets.asyncio.client import connect

# --- Tuning -----------------------------------------------------------------------------
RATE = 24_000          # native rate of both APIs -> zero resampling on the server
CHUNK_MS = 20          # mic chunk size; small chunks = the model hears you sooner
JITTER_MS = 80         # play audio at most this long after it arrives (smooths network jitter)
ECHO_TAIL_S = 0.35     # speakers mode: keep mic muted this long after the model stops
VOICE_RMS = 500        # mic level that counts as "you are speaking" (only for the latency readout)

LIVE = dict(
    url="wss://api.openai.com/v1/live/sessions",
    model="gpt-live-1",
    backend="gpt-6-luna",  # model the Live voice hands harder questions to (docs' recommended start)
)
REALTIME = dict(
    url="wss://api.openai.com/v1/realtime?model={model}",
    model="gpt-realtime-2.1",
    reasoning="low",       # minimal | low | medium | high | xhigh  (higher = slower first audio)
    eagerness="high",      # semantic VAD: low | medium | high | auto  (high = answers sooner)
)

INSTRUCTIONS = """\
You are Mira, having a relaxed, real-time voice conversation with the user.

Voice: speak warmly and naturally, at an unhurried pace. Be clear and direct, not overly cheerful.
Sound like a real person on a call: contractions, natural rhythm, an occasional "hmm" or soft laugh
when it fits. Never sound like you are reading text.

Conversation:
- Keep turns short: usually one to three sentences, then hand the turn back.
- Answer questions directly first, then add one interesting detail or ask something back.
- Be genuinely curious: ask one specific follow-up question about what the user just said.
- If the user interrupts or starts talking, stop and listen.
- If you did not catch something, say so briefly and ask them to repeat.
- Never use lists, markdown, or read out URLs.

Language: speak English unless the user speaks another language; then switch to it and stay there.
"""

GREETING = "Greet the user now, briefly and warmly. Introduce yourself as Mira and ask one easy question to get the conversation going. Then pause and listen."


# --- Audio ------------------------------------------------------------------------------
class Audio:
    """Mic -> asyncio queue, asyncio -> speaker. Raw PCM16 mono at RATE, callbacks run on PortAudio threads."""

    def __init__(self, loop, mic=None, speaker=None, echo_guard=False):
        self.loop, self.echo_guard = loop, echo_guard
        self.mic_chunks: asyncio.Queue[bytes] = asyncio.Queue()
        self.lock = threading.Lock()
        self.buf = bytearray()     # model audio waiting to be played
        self.playing = False       # False while waiting for the jitter buffer to fill
        self.waiting_since = 0.0
        self.item_id = None        # Realtime: assistant item currently being played ...
        self.played_bytes = 0      # ... and how much of it actually reached the speaker
        self.last_played = 0.0     # when the speaker last output model audio
        self.last_voice = 0.0      # when the mic last heard the user
        self.on_latency = None     # callback(seconds) when the model starts answering
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

    def model_is_talking(self) -> bool:
        return bool(self.buf) or time.monotonic() - self.last_played < ECHO_TAIL_S

    def _mic_callback(self, data, frames, time_info, status):
        chunk = bytes(data)
        if self.echo_guard and self.model_is_talking():
            chunk = bytes(len(chunk))  # send silence so the model doesn't hear itself through the speakers
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
                if self.on_latency and self.last_played < self.last_voice < now - 0.1:  # you spoke, then paused
                    lag = now - self.last_voice + self.mic.latency + self.out.latency
                    self.loop.call_soon_threadsafe(self.on_latency, lag)
            take = min(n, len(self.buf)) if self.playing else 0
            out[:take] = self.buf[:take]
            del self.buf[:take]
            if take:
                self.played_bytes += take
                self.last_played = now
            if take < n:
                self.playing = False  # ran dry: refill the jitter buffer before playing again
        out[take:] = bytes(n - take)

    def play(self, pcm: bytes, item_id=None):
        with self.lock:
            if item_id != self.item_id:
                self.item_id, self.played_bytes = item_id, 0
            if not self.buf:
                self.waiting_since = time.monotonic()
            self.buf += pcm

    def interrupt(self):
        """Drop unplayed audio. Returns ms of the current item the user actually heard, or None if idle."""
        with self.lock:
            if not self.buf:
                return None
            self.buf.clear()
            self.playing = False
            return self.played_bytes * 1000 // (RATE * 2)


# --- Terminal transcript ----------------------------------------------------------------
class Transcript:
    LABELS = {"you": "\n\033[2mYou:\033[0m ", "ai": "\n\033[1;36mMira:\033[0m "}

    def __init__(self):
        self.speaker = None

    def write(self, who: str, text: str, end_turn=False):
        if who != self.speaker:
            print(self.LABELS[who], end="")
        print(text, end="", flush=True)
        self.speaker = None if end_turn else who

    def note(self, text: str):
        print(f"\n\033[2m{text}\033[0m", end="", flush=True)
        self.speaker = None


# --- Session setup ----------------------------------------------------------------------
async def start_live(ws, args):
    await ws.send(json.dumps({
        "type": "session.start",
        "session": {
            "model": args.model or LIVE["model"],
            "instructions": INSTRUCTIONS,
            "input": [{"type": "message", "role": "developer", "content": [{"type": "input_text", "text": GREETING}]}],
            "audio": {"format": {"type": "audio/pcm", "rate": RATE}, "output": {"voice": args.voice}},
            # Harder questions get handed to a text model in the background while the voice keeps talking.
            "delegation": {"type": "responses", "responses": {"model": LIVE["backend"]}},
        },
    }))
    async for raw in ws:
        event = json.loads(raw)
        if event["type"] == "session.started":
            return
        if event["type"] in ("error", "session.closed"):
            sys.exit(f"Live session failed to start: {json.dumps(event, indent=2)}")


async def start_realtime(ws, args):
    await ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "type": "realtime",
            "instructions": INSTRUCTIONS,
            "output_modalities": ["audio"],
            "reasoning": {"effort": REALTIME["reasoning"]},
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": RATE},
                    "noise_reduction": {"type": "near_field"},
                    "transcription": {"model": "gpt-live-transcribe"},  # only for the on-screen transcript
                    "turn_detection": {"type": "semantic_vad", "eagerness": REALTIME["eagerness"]},
                },
                "output": {"format": {"type": "audio/pcm", "rate": RATE}, "voice": args.voice},
            },
        },
    }))
    # Let the model speak first; the greeting instruction applies to this one response only.
    await ws.send(json.dumps({"type": "response.create", "response": {"instructions": INSTRUCTIONS + "\n" + GREETING}}))


# --- Main loops -------------------------------------------------------------------------
async def send_mic(ws, audio, event_type):
    while True:
        chunk = await audio.mic_chunks.get()
        await ws.send(json.dumps({"type": event_type, "audio": base64.b64encode(chunk).decode()}))


async def receive(ws, audio, transcript):
    cut_item = None  # Realtime: item we interrupted; ignore its late audio
    async for raw in ws:
        event = json.loads(raw)
        kind = event["type"]

        # Model audio (Live and Realtime)
        if kind in ("session.output_audio.delta", "response.output_audio.delta"):
            item = event.get("item_id")
            if not item or item != cut_item:
                audio.play(base64.b64decode(event["delta"]), item)

        # Realtime barge-in: the server cancels the response itself; we stop playback and tell it
        # how much the user actually heard so the conversation history matches reality.
        elif kind == "input_audio_buffer.speech_started":
            heard_ms = audio.interrupt()
            if heard_ms is not None and audio.item_id:
                cut_item = audio.item_id
                await ws.send(json.dumps({
                    "type": "conversation.item.truncate",
                    "item_id": cut_item, "content_index": 0, "audio_end_ms": heard_ms,
                }))

        # Transcripts: Live streams both sides continuously; Realtime sends whole turns.
        elif kind == "session.input_transcript.delta":
            transcript.write("you", event["delta"])
        elif kind == "session.output_transcript.delta":
            transcript.write("ai", event["delta"])
        elif kind == "conversation.item.input_audio_transcription.completed":
            transcript.write("you", event["transcript"].strip(), end_turn=True)
        elif kind == "response.output_audio_transcript.done":
            transcript.write("ai", event["transcript"].strip(), end_turn=True)

        elif kind == "response.done" and event["response"].get("status") == "failed":
            transcript.note(f"response failed: {event['response'].get('status_details')}")
        elif kind == "error":
            transcript.note(f"error: {event['error'].get('message')}")
        elif kind == "session.closed":
            return


async def close_live(ws):
    await ws.send(json.dumps({"type": "session.close"}))
    async for raw in ws:  # wait for the server to confirm, so the session is billed and closed cleanly
        if json.loads(raw)["type"] == "session.closed":
            return


async def main(args):
    key = api_key()
    if not key:
        sys.exit("Set OPENAI_API_KEY (environment variable or a .env file next to this script).")

    out_name = sd.query_devices(args.speaker, "output")["name"]
    echo_guard = args.speakers or (not args.headphones and "speaker" in out_name.lower())
    live = args.api == "live"
    model = args.model or (LIVE if live else REALTIME)["model"]
    url = LIVE["url"] if live else REALTIME["url"].format(model=model)

    loop = asyncio.get_running_loop()
    audio = Audio(loop, args.mic, args.speaker, echo_guard)
    transcript = Transcript()
    audio.on_latency = lambda s: transcript.note(f"[{s:.2f} s]")

    print(f"\033[1m{model}\033[0m · voice {args.voice} · "
          f"{sd.query_devices(args.mic, 'input')['name']} -> {out_name}")
    print("Speaker mode: your mic is muted while Mira talks so she doesn't hear herself "
          "(wear headphones to be able to interrupt her)." if echo_guard
          else "Full duplex: you can interrupt Mira at any time.")
    print("Connecting…", end="", flush=True)

    async with connect(url, additional_headers={"Authorization": f"Bearer {key}"},
                       max_size=None, compression=None) as ws:
        await (start_live(ws, args) if live else start_realtime(ws, args))
        print(" connected. Just start talking. Ctrl+C to quit.")
        with audio:
            if live:  # mic audio is now flowing; ask the model to open the conversation
                await ws.send(json.dumps({"type": "session.commentary.append", "delegation_id": None,
                                          "content": GREETING}))
            tasks = [asyncio.create_task(send_mic(ws, audio, "session.input_audio.append" if live
                                                  else "input_audio_buffer.append")),
                     asyncio.create_task(receive(ws, audio, transcript))]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()  # re-raise e.g. a dropped connection
            except asyncio.CancelledError:
                pass  # Ctrl+C: close the session cleanly below
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                if live and ws.state is State.OPEN:
                    try:
                        await asyncio.wait_for(close_live(ws), 3)
                    except Exception:
                        pass


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
    p.add_argument("--api", choices=["live", "realtime"], default="live", help="which OpenAI voice API (default: live)")
    p.add_argument("--voice", default="marin",
                   help="marin (default), cedar, ... ; Live-only German voices: juni, nuri, flitz")
    p.add_argument("--model", help="override the model id")
    p.add_argument("--mic", help="input device (name substring, see --devices)")
    p.add_argument("--speaker", help="output device (name substring, see --devices)")
    p.add_argument("--headphones", action="store_true", help="force full duplex (no echo guard)")
    p.add_argument("--speakers", action="store_true", help="force echo guard (mute mic while the model talks)")
    p.add_argument("--devices", action="store_true", help="list audio devices and exit")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.devices:
        print(sd.query_devices())
        sys.exit()
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        pass
    except InvalidStatus as e:  # e.g. bad API key or no access to the model
        sys.exit(f"\nConnection rejected (HTTP {e.response.status_code}): {e.response.body.decode(errors='replace')}")
    except ConnectionClosed as e:
        sys.exit(f"\nConnection closed by server: {e}")
    print("\nBye.")
