"""Ctrl+C on a running Live session sends session.close, waits for session.closed and exits cleanly."""
import asyncio, json, os, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # folder containing realtime_voice.py
from websockets.asyncio.server import serve
WRAP = r'''
import asyncio, sys, threading, time, types
sys.path.insert(0, sys.argv[2])
import realtime_voice as rv
class Fake:
    def __init__(self, device=None, callback=None, **kw): self.cb, self.latency, self.on = callback, 0.01, False
    def start(self):
        self.on = True
        threading.Thread(target=self.run, daemon=True).start()
    def close(self): self.on = False
    def run(self):
        while self.on:
            buf = memoryview(bytearray(960)); self.cb(buf, 480, None, None); time.sleep(0.02)
rv.sd.RawInputStream = rv.sd.RawOutputStream = Fake
rv.api_key = lambda: "sk-test"
rv.LIVE["url"] = sys.argv[1]
args = types.SimpleNamespace(api="live", voice="marin", model=None, mic=None, speaker=None, headphones=True, speakers=False)
try:
    asyncio.run(rv.main(args))
except KeyboardInterrupt:
    print("[KeyboardInterrupt]")
print("Bye.")
'''
log = []
async def handler(ws):
    await ws.recv(); await ws.send(json.dumps({"type": "session.started"}))
    try:
        async for raw in ws:
            t = json.loads(raw)["type"]
            if t != "session.input_audio.append": log.append(t)
            if t == "session.close": await ws.send(json.dumps({"type": "session.closed", "reason": "close_requested"}))
    except Exception as e: log.append(f"exc {e}")
    log.append(f"close code {ws.close_code}")
async def main():
    async with serve(handler, "127.0.0.1", 0) as srv:
        port = srv.sockets[0].getsockname()[1]
        p = await asyncio.create_subprocess_exec(sys.executable, "-c", WRAP, f"ws://127.0.0.1:{port}/v1/live/sessions", str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        await asyncio.sleep(2); p.send_signal(signal.SIGINT)
        out, _ = await asyncio.wait_for(p.communicate(), 10)
        print(out.decode()[-300:]); print("exit code", p.returncode); await asyncio.sleep(0.2); print("server saw:", log)
asyncio.run(main())
