#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["sounddevice>=0.5,<0.6", "websockets>=15,<18"]
# ///
"""Exploratory OpenAI Realtime voice-quality test. Python 3.11+; use headphones.

Run these commands from the drafts/d1-realtimeAPI/ directory:

Install: python -m pip install 'sounddevice>=0.5,<0.6' 'websockets>=15,<18'
Run:     python realtime_voice.py
Or:      uv run --python 3.13 realtime_voice.py

Uses OPENAI_API_KEY, or asks for it without echoing/saving it. Ctrl+C quits.
--check verifies the real API and generated audio without opening a microphone.
API reference: https://developers.openai.com/api/docs/guides/realtime-conversations
"""

import argparse
import asyncio
import base64
from collections import deque
from contextlib import ExitStack
from dataclasses import dataclass
import getpass
import json
import os
import sys
import threading
import time
from urllib.parse import urlencode


RATE = 24_000  # Realtime PCM: mono, signed 16-bit little-endian, 24 kHz.
CHUNK = 480  # 20 ms of microphone audio per network message.
# Deltas arrive in irregular network bursts while the DAC drains at a fixed rate. Each reply
# waits for this cushion, so a late delta drains it instead of zero-padding mid-word, which is
# heard as a click. It only delays replies whose first deltas hold less than 200 ms of audio.
PREBUFFER = RATE // 5  # 200 ms jitter buffer, in samples.
INSTRUCTIONS = """You are a friendly AI voice conversation partner.
Speak warmly and naturally, with expressive intonation and a relaxed, brisk pace.
Use everyday spoken language, contractions, and varied phrasing. Avoid a scripted
or announcer-like delivery, exaggerated enthusiasm, and repetitive filler.
Usually answer in one to three short sentences. Go deeper when asked.
Listen carefully, respond to what was actually said, and ask one relevant follow-up
question when it helps the conversation. Do not turn every reply into a question.
Match the user's language; begin in English unless instructed otherwise.
For ordinary conversation, answer directly without preambles or extended reasoning.
If speech is unclear, ask briefly for clarification. Never invent unheard words.
Do not treat background sounds or silence as a request to speak.
"""


@dataclass
class AudioPart:
    received: int = 0
    played: int = 0
    done: bool = False


class Player:
    """Small streaming player; count audible samples, not downloaded samples."""

    def __init__(self):
        self.lock = threading.Lock()
        self.queue = deque()
        self.scheduled = deque()
        self.parts = {}
        self.buffering = True
        self.underflows = 0  # PortAudio missed a hardware deadline.
        self.gaps = 0  # The network fell behind mid-reply; a hole was zero-filled.

    def append(self, key, pcm):
        if len(pcm) % 2:
            raise RuntimeError("Received an incomplete PCM16 sample.")
        if pcm:
            with self.lock:
                self.parts.setdefault(key, AudioPart()).received += len(pcm) // 2
                self.queue.append((key, memoryview(pcm)))

    def finish(self, key):
        with self.lock:
            if key in self.parts:
                self.parts[key].done = True

    def advance(self, now):
        # PortAudio's DAC clock accounts for audio still in the hardware buffer.
        while self.scheduled:
            key, start, frames = self.scheduled[0]
            if start + frames / RATE > now:
                break
            self.parts[key].played += frames
            self.scheduled.popleft()
        for key in list(self.parts):
            part = self.parts[key]
            if part.done and part.played == part.received:
                del self.parts[key]

    def callback(self, outdata, frames, timing, status):
        outdata[:] = b"\0" * len(outdata)
        with self.lock:
            self.underflows += bool(status.output_underflow)
            self.advance(timing.currentTime)
            if self.buffering:
                # Start with a full cushion, or at once if the newest audio completes its reply.
                queued = sum(len(pcm) for _, pcm in self.queue) // 2
                if not queued or (queued < PREBUFFER and not self.parts[self.queue[-1][0]].done):
                    return
                self.buffering = False
            offset, key = 0, None
            while self.queue and offset < len(outdata):
                key, pcm = self.queue.popleft()
                count = min(len(pcm), len(outdata) - offset)
                outdata[offset:offset + count] = pcm[:count]
                self.scheduled.append(
                    (key, timing.outputBufferDacTime + offset / (2 * RATE), count // 2)
                )
                if count < len(pcm):
                    self.queue.appendleft((key, pcm[count:]))
                offset += count
            if not self.queue:
                # The reply ended, or a hole began; either way, rebuild the cushion first.
                self.buffering = True
                if key is not None and not self.parts[key].done:
                    self.gaps += 1

    def interrupt(self, now):
        with self.lock:
            self.advance(now)
            for key, start, frames in self.scheduled:
                self.parts[key].played += max(0, min(frames, int((now - start) * RATE)))
            cuts = [
                (key, part.played * 1000 // RATE)
                for key, part in self.parts.items()
                if part.played < part.received or not part.done
            ]
            self.queue.clear()
            self.scheduled.clear()
            self.parts.clear()
            self.buffering = True
            return cuts


def session_config(args):
    vad = {"create_response": True, "interrupt_response": True}
    if args.vad == "fast":
        vad.update(type="server_vad", threshold=0.5,
                   prefix_padding_ms=300, silence_duration_ms=300)
    else:
        vad.update(type="semantic_vad", eagerness="high")
    return {
        "type": "realtime",
        "output_modalities": ["audio"],
        "instructions": INSTRUCTIONS + "\n" + args.instructions,
        "reasoning": {"effort": args.effort},
        "max_output_tokens": 2048,
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": RATE},
                "noise_reduction": {"type": args.noise_reduction or "near_field"},
                "turn_detection": vad,
            },
            "output": {
                "format": {"type": "audio/pcm", "rate": RATE},
                "voice": args.voice,
                "speed": 1.0,
            },
        },
    }


async def send(ws, event_type, **fields):
    await ws.send(json.dumps({"type": event_type, **fields}))


async def receive(ws):
    event = json.loads(await ws.recv())
    if event["type"] == "error":
        error = event["error"]
        raise RuntimeError(f"API {error.get('code', 'error')}: {error['message']}")
    return event


async def configure(ws, args):
    async with asyncio.timeout(20):
        while (await receive(ws))["type"] != "session.created":
            pass
        await send(ws, "session.update", session=session_config(args))
        while (await receive(ws))["type"] != "session.updated":
            pass


async def check_api(ws):
    """A short paid request: test actual session setup and PCM generation."""
    started, audio_bytes = time.perf_counter(), 0
    await send(ws, "response.create", response={"instructions": "Say only: Hello there!"})
    async with asyncio.timeout(30):
        while True:
            event = await receive(ws)
            if event["type"] == "response.output_audio.delta":
                pcm = base64.b64decode(event["delta"], validate=True)
                if len(pcm) % 2:
                    raise RuntimeError("API returned invalid PCM16 audio.")
                if not audio_bytes:
                    print(f"First audio: {(time.perf_counter() - started) * 1000:.0f} ms after request")
                audio_bytes += len(pcm)
            elif event["type"] == "response.done":
                response = event["response"]
                if response["status"] != "completed" or not audio_bytes:
                    raise RuntimeError(f"Audio check failed: {response.get('status_details') or response['status']}")
                print(f"API check passed: {audio_bytes / (2 * RATE):.2f} s of PCM audio received.")
                return


async def talk(ws, args, sd):
    loop = asyncio.get_running_loop()
    microphone = asyncio.Queue(maxsize=10)  # Bound capture backlog to 200 ms.
    player = Player()
    capture_overflows = 0

    def enqueue(pcm, overflow):
        nonlocal capture_overflows
        capture_overflows += bool(overflow)
        if microphone.full():
            microphone.get_nowait()  # Never replay old microphone audio after a stall.
            capture_overflows += 1
        microphone.put_nowait(pcm)

    def capture(indata, frames, timing, status):
        loop.call_soon_threadsafe(enqueue, bytes(indata), status.input_overflow)

    async def upload():
        while True:
            try:
                pcm = await asyncio.wait_for(microphone.get(), timeout=2)
            except TimeoutError:
                raise RuntimeError("Microphone stopped delivering audio. Check its connection and permissions.") from None
            async with asyncio.timeout(2):
                await send(ws, "input_audio_buffer.append",
                           audio=base64.b64encode(pcm).decode("ascii"))

    async def download(output):
        active_response = None
        ignored = deque(maxlen=32)
        turn_ended = None
        transcript_key = None
        while True:
            event = await receive(ws)
            kind = event["type"]
            if kind == "input_audio_buffer.speech_started":
                if active_response:
                    ignored.append(active_response)
                # VAD cancels generation; the client must clear and truncate playback.
                cuts = player.interrupt(output.time)
                if cuts:
                    print("\n[Listening — interrupted playback]", flush=True)
                transcript_key = None
                turn_ended = None
                for (item_id, content_index), heard_ms in cuts:
                    await send(ws, "conversation.item.truncate", item_id=item_id,
                               content_index=content_index, audio_end_ms=heard_ms)
            elif kind == "input_audio_buffer.speech_stopped":
                turn_ended = time.perf_counter()
            elif kind == "response.created":
                active_response = event["response"]["id"]
            elif kind == "response.done":
                response = event["response"]
                if response["id"] == active_response:
                    active_response = None
                if response["status"] == "failed":
                    raise RuntimeError(f"Response failed: {response.get('status_details')}")
                if response["status"] == "incomplete":
                    print(f"\n[Response ended early: {response.get('status_details')}]", flush=True)
                # Cancelled responses may omit output_audio.done. Retire their parts too.
                for item in response.get("output", []):
                    for index, part in enumerate(item.get("content", [])):
                        if part["type"] == "audio":
                            player.finish((item["id"], index))
            elif event.get("response_id") in ignored:
                continue  # Discard any late audio/transcript from the interrupted response.
            elif kind == "response.output_audio.delta":
                player.append((event["item_id"], event["content_index"]),
                              base64.b64decode(event["delta"], validate=True))
                if turn_ended is not None:
                    elapsed = (time.perf_counter() - turn_ended) * 1000
                    print(f"\n[First audio: {elapsed:.0f} ms after turn-end event; excludes VAD]", flush=True)
                    turn_ended = None
            elif kind == "response.output_audio.done":
                player.finish((event["item_id"], event["content_index"]))
            elif kind == "response.output_audio_transcript.delta":
                key = (event["item_id"], event["content_index"])
                if key != transcript_key:
                    print("\nAI: ", end="", flush=True)
                    transcript_key = key
                print(event["delta"], end="", flush=True)

    with ExitStack() as stack:
        output = stack.enter_context(sd.RawOutputStream(
            samplerate=RATE, channels=1, dtype="int16", blocksize=0,
            device=args.output_device, latency="low", callback=player.callback,
        ))
        stack.enter_context(sd.RawInputStream(
            samplerate=RATE, channels=1, dtype="int16", blocksize=CHUNK,
            device=args.input_device, latency="low", callback=capture,
        ))
        print("Microphone on. Talk naturally; interrupt whenever you like. Ctrl+C to quit.", flush=True)
        await send(ws, "response.create", response={
            "instructions": session_config(args)["instructions"] +
            "\nStart now with a brief hello and one friendly question."
        })
        tasks = [asyncio.create_task(upload()), asyncio.create_task(download(output))]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            output.abort()  # Do not drain queued speech after Ctrl+C or a network error.
            if capture_overflows or player.underflows or player.gaps:
                print(f"\nAudio overruns: {capture_overflows}; output underflows: {player.underflows}; "
                      f"playback gaps: {player.gaps}.")


async def run(args, key, sd):
    from websockets.asyncio.client import connect

    url = "wss://api.openai.com/v1/realtime?" + urlencode({"model": args.model})
    print(f"Connecting: {args.model} / {args.voice} / {args.effort} reasoning / {args.vad} turns", flush=True)
    async with connect(
        url, additional_headers={"Authorization": f"Bearer {key}"},
        compression=None, open_timeout=20, close_timeout=3,
        max_size=8 * 1024 * 1024,
    ) as ws:
        await configure(ws, args)
        print("Session configuration accepted.", flush=True)
        if args.check:
            await check_api(ws)
        else:
            await talk(ws, args, sd)


def device(value):
    return int(value) if value.isdecimal() else value


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="gpt-realtime-2.1",
                        choices=["gpt-realtime-2.1", "gpt-realtime-2.1-mini"])
    parser.add_argument("--voice", choices=["marin", "cedar"], default="marin")
    parser.add_argument("--effort", choices=["minimal", "low", "medium", "high", "xhigh"], default="minimal")
    parser.add_argument("--vad", choices=["semantic", "fast"], default="semantic",
                        help="semantic: natural turn endings; fast: reply after 300 ms silence")
    parser.add_argument("--noise-reduction", choices=["near_field", "far_field"],
                        help="auto-selects for common built-in mics; override for headset/laptop use")
    parser.add_argument("--input-device", type=device, help="microphone ID or name from --list-devices")
    parser.add_argument("--output-device", type=device, help="speaker/headphone ID or name")
    parser.add_argument("--instructions", default="", help="extra instructions, e.g. 'Speak German.'")
    parser.add_argument("--list-devices", action="store_true", help="list audio devices and exit")
    parser.add_argument("--check", action="store_true", help="paid API audio smoke test; no microphone or playback")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        import websockets  # noqa: F401
        sd = None
        if not args.check or args.list_devices:
            import sounddevice as sd
        if args.list_devices:
            print(sd.query_devices())
            return
        if not args.check:
            sd.check_input_settings(device=args.input_device, channels=1, dtype="int16", samplerate=RATE)
            sd.check_output_settings(device=args.output_device, channels=1, dtype="int16", samplerate=RATE)
            mic_name = sd.query_devices(args.input_device, "input")["name"]
            output_name = sd.query_devices(args.output_device, "output")["name"]
            if args.noise_reduction is None:
                built_in = any(word in mic_name.lower() for word in ("macbook", "built-in", "internal", "array"))
                args.noise_reduction = "far_field" if built_in else "near_field"
            print(f"Microphone: {mic_name} ({args.noise_reduction}); output: {output_name}")
            print("Use headphones: this minimal client has no acoustic echo cancellation.")
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key and sys.stdin.isatty():
            key = getpass.getpass("OpenAI API key (hidden, not saved): ").strip()
        if not key:
            raise RuntimeError("Set OPENAI_API_KEY, or start in an interactive terminal to enter your key.")
        asyncio.run(run(args, key, sd))
    except KeyboardInterrupt:
        print("\nGoodbye.")
    except ImportError as exc:
        print(f"Missing dependency: {exc}\nInstall: python -m pip install 'sounddevice>=0.5,<0.6' 'websockets>=15,<18'", file=sys.stderr)
        return 1
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        if 'key' in locals() and key:
            message = message.replace(key, "[redacted]")
        print(f"\nError: {message}", file=sys.stderr)
        if 'sd' in locals() and sd and isinstance(exc, (sd.PortAudioError, ValueError)):
            print("Try --list-devices and select the correct input/output. On macOS allow your terminal under System Settings → Privacy & Security → Microphone.", file=sys.stderr)
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403, 429):
            print("Check your API key, project model access, billing balance, and rate limits.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
