# d2 – Realtime voice test

Talk to OpenAI's newest speech-to-speech models from the terminal (mic in, speaker out).
One file: `realtime_voice.py`.

| `--api` | Model | What it is |
|---|---|---|
| `live` (default) | `gpt-live-1` | Live API (Sep 2026). Full duplex: listens while it talks, ~0.8 s turn-taking. $0.05/min. |
| `realtime` | `gpt-realtime-2.1` | Realtime API (Jul 2026). Turn-based, semantic VAD, low reasoning effort. |

## Setup (once)

```bash
cd drafts/d2-realtimeVoice
python3.13 -m venv .venv && .venv/bin/pip install websockets sounddevice
```

Use Python 3.13. The Homebrew `python3` (3.14.7) on this machine can't create venvs because its `pyexpat` is broken.

## Run

```bash
export OPENAI_API_KEY=sk-...          # or OPENAI_API_KEY=... in a .env file in this folder
.venv/bin/python realtime_voice.py    # then just talk; Ctrl+C to quit
```

| Option | Effect |
|---|---|
| `--api realtime` | Use gpt-realtime-2.1 instead of gpt-live-1 |
| `--voice cedar` | Other voice (default `marin`). German Live voices: `juni`, `nuri`, `flitz` |
| `--devices`, `--mic NAME`, `--speaker NAME` | List or pick audio devices (name substring) |
| `--headphones` / `--speakers` | Force full duplex / force the echo guard (normally auto-detected) |

After each answer, the measured delay from when you stopped talking until Mira's voice starts is shown dim, e.g. `[0.84 s]`.

Tips:
- **Headphones** let you interrupt the model mid-sentence. On an output whose name contains "speaker" (e.g. MacBook speakers), the mic is muted while the model talks so it doesn't hear itself.
- With AirPods, keep the MacBook mic as input. Using the AirPods mic switches them to low-quality call audio.
- The persona, voice and latency settings are constants at the top of the script (`INSTRUCTIONS`, `JITTER_MS`, `REALTIME["eagerness"]`, …).

## Tests (no API key, no sound)

```bash
.venv/bin/python tests/mock_conversation.py   # both protocols end to end against mock servers, incl. barge-in + echo guard
.venv/bin/python tests/mock_ctrl_c.py         # Ctrl+C closes the Live session cleanly
.venv/bin/python tests/mock_bad_key.py        # readable error on HTTP 401
.venv/bin/pip install openai && .venv/bin/python tests/check_schemas.py   # every sent event vs. the official SDK schemas
```

These tests don't call the real API. One untested assumption: the Live API sends audio at real-time speed. The docs imply it but don't state it. If interrupting feels laggy with `--api live`, check this first.
