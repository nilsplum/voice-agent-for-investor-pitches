"""End-to-end test of realtime_voice.py against mock Live/Realtime servers, with fake audio devices (no sound, no API key)."""
import asyncio, base64, json, math, struct, sys, threading, time, types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # folder containing realtime_voice.py
sys.path.insert(0, str(ROOT))
import realtime_voice as rv
from websockets.asyncio.server import serve

FRAME = rv.RATE * rv.CHUNK_MS // 1000 * 2  # bytes per 20 ms

def tone(ms, freq=440):
    n = rv.RATE * ms // 1000
    return b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / rv.RATE))) for i in range(n))

class FakeStream:
    """Mimics sd.RawInputStream/RawOutputStream: calls the callback every 20 ms on a thread."""
    instances = []
    def __init__(self, device=None, callback=None, **kw):
        self.cb, self.latency, self.kind = callback, 0.01, "in" if "mic" in callback.__name__ else "out"
        self.running, self.played = False, bytearray()
        self.t0 = None
        FakeStream.instances.append(self)
    def start(self):
        self.running, self.t0 = True, time.monotonic()
        threading.Thread(target=self._run, daemon=True).start()
    def close(self): self.running = False
    def _run(self):
        while self.running:
            if self.kind == "in":
                loud = time.monotonic() - self.t0 < MIC_VOICE_SECONDS
                sample = struct.pack("<h", 3000) if loud else struct.pack("<h", 0)
                self.cb(sample * (FRAME // 2), FRAME // 2, None, None)
            else:
                buf = memoryview(bytearray(FRAME))  # fixed size like a cffi buffer
                self.cb(buf, FRAME // 2, None, None)
                self.played += bytes(buf)
            time.sleep(rv.CHUNK_MS / 1000)

rv.sd.RawInputStream = rv.sd.RawOutputStream = FakeStream
rv.api_key = lambda: "sk-test"
MIC_VOICE_SECONDS = 0.0
log = {}

async def live_server(ws):
    assert ws.request.headers["Authorization"] == "Bearer sk-test"
    log["path"] = ws.request.path
    start = json.loads(await ws.recv()); log["start"] = start
    await ws.send(json.dumps({"type": "session.started", "session": {"id": "s1"}}))
    log["mic_chunks"], log["other"] = 0, []
    async def reader():
        async for raw in ws:
            ev = json.loads(raw)
            if ev["type"] == "session.input_audio.append": log["mic_chunks"] += 1
            else:
                log["other"].append(ev["type"])
                if ev["type"] == "session.close":
                    await ws.send(json.dumps({"type": "session.closed", "reason": "close_requested"}))
                    return
    r = asyncio.create_task(reader())
    await asyncio.sleep(1.0)  # user "speaks" for 0.5 s, then silence
    audio = tone(600)
    log["sent_audio"] = audio
    await ws.send(json.dumps({"type": "session.output_transcript.delta", "event_id": "e", "delta": "Hi there!", "start_ms": 0, "end_ms": 600}))
    for i in range(0, len(audio), FRAME):  # real-time paced, like the Live mixer
        await ws.send(json.dumps({"type": "session.output_audio.delta", "delta": base64.b64encode(audio[i:i+FRAME]).decode()}))
        await asyncio.sleep(0.02)
    await ws.send(json.dumps({"type": "session.input_transcript.delta", "event_id": "e", "delta": "Hello Mira", "start_ms": 0, "end_ms": 500}))
    await r

async def realtime_server(ws):
    log["path"] = ws.request.path
    await ws.send(json.dumps({"type": "session.created", "session": {}}))
    log["update"] = json.loads(await ws.recv()); log["create"] = json.loads(await ws.recv())
    log["truncate"], log["mic_zero_while_playing"], log["mic_chunks"] = None, [], 0
    async def reader():
        async for raw in ws:
            ev = json.loads(raw)
            if ev["type"] == "input_audio_buffer.append":
                log["mic_chunks"] += 1
                log["mic_zero_while_playing"].append(set(base64.b64decode(ev["audio"])) == {0})
            elif ev["type"] == "conversation.item.truncate": log["truncate"] = (ev, time.monotonic())
    r = asyncio.create_task(reader())
    a = tone(2000)  # 2 s answer, sent as a burst (Realtime generates faster than real time)
    for i in range(0, len(a), 4800):
        await ws.send(json.dumps({"type": "response.output_audio.delta", "item_id": "item_A", "delta": base64.b64encode(a[i:i+4800]).decode()}))
    await ws.send(json.dumps({"type": "response.output_audio_transcript.done", "item_id": "item_A", "transcript": "Hi, I'm Mira. How's your day going?"}))
    log["t_audio_sent"] = time.monotonic()
    await asyncio.sleep(0.7)
    await ws.send(json.dumps({"type": "input_audio_buffer.speech_started", "item_id": "u1", "audio_start_ms": 0}))
    await ws.send(json.dumps({"type": "response.output_audio.delta", "item_id": "item_A", "delta": base64.b64encode(tone(500)).decode()}))  # late, must be dropped
    await ws.send(json.dumps({"type": "conversation.item.input_audio_transcription.completed", "item_id": "u1", "transcript": "Wait, quick question"}))
    await asyncio.sleep(0.3)
    b = tone(300, 880)
    log["b"] = b
    await ws.send(json.dumps({"type": "response.output_audio.delta", "item_id": "item_B", "delta": base64.b64encode(b).decode()}))
    await ws.send(json.dumps({"type": "error", "error": {"message": "test error is displayed"}}))
    await asyncio.sleep(0.6)
    await ws.close()

async def run(api, handler, headphones, seconds, speakers=False):
    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        rv.LIVE["url"] = f"ws://127.0.0.1:{port}/v1/live/sessions"
        rv.REALTIME["url"] = f"ws://127.0.0.1:{port}/v1/realtime?model={{model}}"
        args = types.SimpleNamespace(api=api, voice="marin", model=None, mic=None, speaker=None, headphones=headphones, speakers=speakers)
        task = asyncio.create_task(rv.main(args))
        await asyncio.sleep(seconds)
        if not task.done():
            task.cancel()  # what Ctrl+C does under asyncio.run
        try: await task
        except (asyncio.CancelledError, rv.ConnectionClosed) as e: print(f"\n[main ended: {type(e).__name__}]")

def nonzero_runs(b):
    return sum(1 for i in range(0, len(b), FRAME) if any(b[i:i+FRAME]))

print("=" * 30, "LIVE (headphones, real-time paced audio, Ctrl+C close)")
MIC_VOICE_SECONDS = 0.5
FakeStream.instances.clear()
asyncio.run(run("live", live_server, True, 3.0))
out = next(s for s in FakeStream.instances if s.kind == "out")
played = bytes(out.played).strip(b"\x00")
print("\npath:", log["path"], "| model:", log["start"]["session"]["model"], "| mic chunks sent:", log["mic_chunks"], "| other events:", log["other"])
print("played audio identical to sent audio:", played == log["sent_audio"].strip(b"\x00"), f"({len(played)} bytes)")

print("\n" + "=" * 30, "REALTIME (headphones, burst audio, barge-in at 0.7 s)")
MIC_VOICE_SECONDS = 0.0
FakeStream.instances.clear(); log.clear()
asyncio.run(run("realtime", realtime_server, True, 3.0))
out = next(s for s in FakeStream.instances if s.kind == "out")
print("\npath:", log["path"], "| session.update keys:", sorted(log["update"]["session"]), "| response.create has greeting:", "Greet" in log["create"]["response"]["instructions"])
tr, t_tr = log["truncate"]
heard = tr["audio_end_ms"]; elapsed = (t_tr - log["t_audio_sent"]) * 1000
print("truncate:", {k: tr[k] for k in ("item_id", "content_index", "audio_end_ms")}, f"(barge-in ~{elapsed:.0f} ms after audio arrived)")
played_ms = nonzero_runs(bytes(out.played)) * rv.CHUNK_MS
print(f"total model audio played: ~{played_ms} ms (expected ≈ {heard} ms of item_A + 300 ms of item_B, late item_A audio dropped)")
print("item_B played:", log["b"][:FRAME*5] in bytes(out.played))

print("\n" + "=" * 30, "REALTIME (--speakers -> echo guard)")
FakeStream.instances.clear(); log.clear()
MIC_VOICE_SECONDS = 99  # user is "loud" the whole time -> without the guard this would be echo
asyncio.run(run("realtime", realtime_server, False, 1.2, speakers=True))
z = log["mic_zero_while_playing"]
print(f"\nmic chunks sent: {len(z)}, silenced while model audio playing: {sum(z)}, first silenced at chunk #{z.index(True) if True in z else None}")
