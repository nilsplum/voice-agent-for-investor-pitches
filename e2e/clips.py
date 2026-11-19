"""The founder's voice for the voice test: each text of founder_script.json becomes a WAV clip at the
start of every run, in a temporary folder.

This test calls OpenAI directly because it plays the founder, not the app; the app's own OpenAI
calls all go through the backend. The key comes from OPENAI_API_KEY, which ./scripts/test.sh reads
through the backend's CLI and passes in; it is never written to a file.

OpenAI's dedicated speech models (`/v1/audio/speech`) are deprecated, so the clips come from the
current audio model through Chat Completions with audio output. That model is conversational: it is
told to read each text verbatim, and the transcript of what it said is compared with the text. Now
and then it answers a short, reply-like text instead of reading it, so each clip gets a few
attempts; a clip that is never read verbatim fails the run instead of confusing the conversation.
"""

import base64
import os
import re
from difflib import SequenceMatcher
from pathlib import Path

import httpx

SPEECH_MODEL = "gpt-audio-1.5"
VOICE = "cedar"  # a voice clearly different from the agent's
READ_ALOUD = ("You are a text-to-speech voice. Read the user's message aloud in German, word for word, exactly "
              "as written, at a natural speaking pace. Do not answer it, comment on it or add anything.")
MIN_SIMILARITY = 0.8  # how closely the spoken words must match the text (0 to 1)
ATTEMPTS = 3  # how often each clip is asked for before the run fails
TIMEOUT_S = 120


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def make_clips(texts: dict[str, str], folder: Path) -> dict[str, Path]:
    """One WAV clip per text, named after its key; returns the clips' paths by key."""
    clips = {}
    with httpx.Client(base_url="https://api.openai.com/v1", timeout=TIMEOUT_S,
                      headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}) as client:
        for name, text in texts.items():
            similarities = []
            for _ in range(ATTEMPTS):
                response = client.post("/chat/completions", json={
                    "model": SPEECH_MODEL,
                    "modalities": ["text", "audio"],
                    "audio": {"voice": VOICE, "format": "wav"},
                    "messages": [{"role": "system", "content": READ_ALOUD}, {"role": "user", "content": text}],
                })
                response.raise_for_status()
                audio = response.json()["choices"][0]["message"]["audio"]
                similarities.append(SequenceMatcher(None, _words(text), _words(audio["transcript"])).ratio())
                if similarities[-1] >= MIN_SIMILARITY:
                    break
            assert similarities[-1] >= MIN_SIMILARITY, (
                f"The speech model did not read the clip '{name}' verbatim in {ATTEMPTS} attempts "
                f"(similarities {', '.join(f'{value:.2f}' for value in similarities)}).")
            clips[name] = folder / f"{name}.wav"
            clips[name].write_bytes(base64.b64decode(audio["data"]))
    return clips
