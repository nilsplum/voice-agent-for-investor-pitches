"""Strictly validate every event realtime_voice.py sends against the official OpenAI SDK schemas (needs `pip install openai`)."""
import asyncio, json, sys, types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # folder containing realtime_voice.py
sys.path.insert(0, str(ROOT))
import realtime_voice as rv
from pydantic import BaseModel, TypeAdapter
from openai.types.live.client_event import ClientEvent as LiveClientEvent
from openai.types.realtime.realtime_client_event import RealtimeClientEvent

class FakeWS:
    def __init__(self, replies): self.sent, self.replies = [], replies
    async def send(self, s): self.sent.append(json.loads(s))
    def __aiter__(self): return self
    async def __anext__(self):
        if not self.replies: raise StopAsyncIteration
        return json.dumps(self.replies.pop(0))

def extras(obj, path="event"):
    """Recursively collect fields the SDK model does not know (openai models silently allow extras)."""
    found = []
    if isinstance(obj, BaseModel):
        for k in (obj.model_extra or {}): found.append(f"{path}.{k}")
        for k in type(obj).model_fields: found += extras(getattr(obj, k), f"{path}.{k}")
    elif isinstance(obj, list):
        for i, x in enumerate(obj): found += extras(x, f"{path}[{i}]")
    return found

def check(adapter, event):
    model = adapter.validate_python(event)
    bad = extras(model)
    print(("OK  " if not bad else "BAD ") + event["type"], bad or "", f"-> {type(model).__name__}")
    return not bad

args = types.SimpleNamespace(model=None, voice="marin")
ok = True
live, rt = TypeAdapter(LiveClientEvent), TypeAdapter(RealtimeClientEvent)

ws = FakeWS([{"type": "session.started", "session": {}}])
asyncio.run(rv.start_live(ws, args))
live_events = ws.sent + [
    {"type": "session.commentary.append", "delegation_id": None, "content": rv.GREETING},
    {"type": "session.input_audio.append", "audio": "AAAA"},
    {"type": "session.close"},
]
print("== Live API"); ok &= all(check(live, e) for e in live_events)

ws = FakeWS([])
asyncio.run(rv.start_realtime(ws, args))
rt_events = ws.sent + [
    {"type": "input_audio_buffer.append", "audio": "AAAA"},
    {"type": "conversation.item.truncate", "item_id": "item_1", "content_index": 0, "audio_end_ms": 1234},
]
print("== Realtime API"); ok &= all(check(rt, e) for e in rt_events)
print(json.dumps(live_events[0], indent=1)[:1500])
sys.exit(0 if ok else 1)
