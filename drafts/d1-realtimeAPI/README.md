# Realtime API quality experiment

`realtime_voice.py` is a standalone exploratory test for evaluating voice quality,
latency, and conversation behavior before implementing the application.
It connects your microphone and
headphones directly to OpenAI's Realtime API, greets you, and keeps a spoken
conversation going. You can interrupt it at any time. Ctrl+C stops the session.

Start from the project's `drafts/d1-realtimeAPI/` directory (its own `.venv` has the dependencies
installed):

```bash
.venv/bin/python realtime_voice.py
```

Enter your OpenAI API key at the hidden prompt, or set `OPENAI_API_KEY` in your
environment beforehand. The script does not save the key, audio, or conversation.
Microphone audio is streamed to OpenAI while the session is running; normal API
charges apply. Use an API project with billing and access to the selected model.

Use **headphones**, preferably wired/USB. This small Python client has no acoustic
echo cancellation; speakers can cause the model to hear and interrupt itself.
Bluetooth microphone mode can also lower sound quality and add latency. On macOS,
allow microphone access for your terminal when prompted.

For a fresh installation, use Python 3.11 or newer:

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install 'sounddevice>=0.5,<0.6' 'websockets>=15,<18'
.venv/bin/python realtime_voice.py
```

`python3.13` is used here because this machine's Python 3.14 installation has a
broken native XML library. The script itself supports Python 3.11+. If you use
`uv`, the file includes its dependencies, so `uv run --python 3.13 realtime_voice.py`
also works. On Linux you may need your distribution's PortAudio package
(`sudo apt install libportaudio2` on Debian/Ubuntu).

Useful options:

```bash
# Faster turn endings and a faster, smaller model:
.venv/bin/python realtime_voice.py --model gpt-realtime-2.1-mini --vad fast

# Alternative high-quality voice and German conversation:
.venv/bin/python realtime_voice.py --voice cedar --instructions 'Sprich Deutsch.'

# Find and select microphone/headphones (IDs or names):
.venv/bin/python realtime_voice.py --list-devices
.venv/bin/python realtime_voice.py --input-device 1 --output-device 2

# Override automatic microphone noise-filter selection if needed:
.venv/bin/python realtime_voice.py --noise-reduction far_field
.venv/bin/python realtime_voice.py --noise-reduction near_field

# Verify authentication, model access, configuration, and generated audio.
# Makes one short paid API request; does not open the microphone or play sound:
.venv/bin/python realtime_voice.py --check
```

The defaults use **`gpt-realtime-2.1`**, **`marin`**, minimal reasoning, semantic
turn detection with high eagerness, and uncompressed 24 kHz PCM audio. Microphone
chunks are 20 ms. Each reply starts playing once 200 ms of audio is queued (or the
whole reply has arrived). This jitter buffer absorbs irregular network delivery:
without it, a late audio delta leaves the player nothing to play, the gap is filled
with silence mid-word, and the abrupt jump to zero is heard as a click. If the
network still falls behind, the exit summary counts it as `playback gaps`. Output speed stays at
1.0 to preserve the voice's natural delivery. `--effort low` gives the model more
reasoning time for harder questions. `--vad fast` responds after 300 ms of silence,
but can interrupt your thinking pauses; semantic mode handles those more naturally.
Noise filtering automatically uses `far_field` for recognizable built-in microphone
names (including your MacBook), and `near_field` otherwise; either can be overridden.

On interruption, the script clears queued speech and truncates the server's
conversation to the audio already played, accounting for the device's output
clock. A small amount already handed to the hardware may still be audible.
Captions show generated speech and can run ahead of playback. Input transcription
is unnecessary: the model receives audio directly.

The printed first-audio timing starts when the client receives the server's
turn-end event. It **excludes** speech endpoint detection, upstream latency, the
jitter buffer (up to 200 ms), and device playback latency; it is not a claim of end-to-end conversational latency.
`--check` measures response-request to first received audio instead. Actual
responsiveness depends on your devices, network, and API load. Sessions last at
most 60 minutes; restart after expiry or a connection failure.

Research checked against official documentation on 2026-11-13:

- [Current Realtime model](https://developers.openai.com/api/docs/models/gpt-realtime-2.1)
  and [faster mini variant](https://developers.openai.com/api/docs/models/gpt-realtime-2.1-mini).
- [Audio formats, recommended voices, and interruption/truncation](https://developers.openai.com/api/docs/guides/realtime-conversations).
- [Semantic and server voice activity detection](https://developers.openai.com/api/docs/guides/realtime-vad).
- [Voice prompting and reasoning effort](https://developers.openai.com/api/docs/guides/voice-prompting).
- [Current client event schema](https://developers.openai.com/api/reference/resources/realtime/client-events).
- [WebSocket connection](https://developers.openai.com/api/docs/guides/voice-websockets?api=realtime).

OpenAI also offers [GPT-Live-1](https://developers.openai.com/api/docs/models/gpt-live-1)
for full-duplex voice conversations. It uses a separate API and session protocol;
this file specifically tests the Realtime API. For a future browser
version, use WebRTC for browser audio processing and transport.

Validation during implementation: 11 local tests passed for PCM playback order,
hardware playback timing, interruption/truncation, discarded late audio, resumed
conversation, error handling, and session setup over a local WebSocket server.
The actual MacBook microphone and output callbacks also passed a short local test
with silent playback and no network transmission. A live OpenAI request and voice
quality assessment remain unverified because no API key was available; run
`--check` and then a conversation with your key to complete those checks.
