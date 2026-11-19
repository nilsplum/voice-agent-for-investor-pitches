"""The voice conversation through the real app: a real Chrome plays a founder who signs up, passes the
tutorial and the device check, presses START and talks to the agent with recorded answers until the
conversation is complete. Runs only with ./scripts/test.sh --complete (compose service e2e), against
the running app and the real OpenAI and Serper; it costs a little per run.

- The founder: founder_script.json holds the signup details and the answers, in German, the default
  conversation language: an opening answer, one pitch that answers every topic question of the
  default catalog, a closing answer, and a fallback for every further turn, which also answers any
  follow-up, whether the agent asks it right away or in a follow-up round. clips.py turns them into
  speech at the start of each run.
- The microphone: an init script replaces getUserMedia with a Web Audio stream that the test plays
  the clips into. It always carries a faint noise floor, like a quiet room: the Live API starts
  only once input audio flows, and a stream without any audio never gets the greeting. The clips
  are served through `page.route`, so the app itself contains no test code.
- Turn taking: the test answers whenever the agent waits for the founder, that is when the status
  has shown „Hört zu" after a new agent message: for a moment if the message ends with a question,
  for longer otherwise. So it does not depend on the agent's wording, and it never talks into a
  short pause such as "one moment, I'm writing everything down".
- The result: every scripted answer was played, the success message in the browser and
  „Schreibt Ihre Antworten auf ..." on the way, then the stored conversation in the app's database:
  Completed, every answer and the summary, an answer to every follow-up the review selected (a
  follow-up round is optional, the review may select none), and a fact only the founder said (the
  co-founder's surname), so answers the agent invented can never pass.

Chrome runs in the frontend container's network, so http://localhost:5173 is a secure context for
the microphone. The test's founder and conversation stay in the database, like a real one.
"""

import json
import os
import time
import urllib.request
from pathlib import Path

import psycopg
import pytest
from playwright.sync_api import Page, expect

from clips import make_clips

APP = "http://localhost:5173"
DATABASE = "postgresql://postgres@db:5432/app"  # the app's database (DATABASE_* in backend/app/config.py)
TIME_LIMIT_S = 12 * 60
MAX_TURNS = 30
# How long „Hört zu" must show after a new agent message before the founder answers: briefly after
# a question, longer after anything else (the agent may only be pausing).
SETTLE_AFTER_QUESTION_S = 1.5
SETTLE_OTHERWISE_S = 8.0
POLL_MS = 250
SUCCESS = "Vielen Dank, Ihr Gespräch ist abgeschlossen."
UNFINISHED = "Dieses Gespräch wurde vor dem Abschluss beendet."
WRITING = "Schreibt Ihre Antworten auf ..."
FOUNDER_FACT = "Wagner"  # the co-founder's surname, said only in the pitch of founder_script.json
SCRIPTED = ["opening", "pitch", "closing"]  # in this order; then the fallback for every further turn

FAKE_MICROPHONE = """
(() => {
  const context = new AudioContext();
  const microphone = context.createMediaStreamDestination();
  const noise = context.createBuffer(1, context.sampleRate, context.sampleRate);
  const samples = noise.getChannelData(0);
  for (let i = 0; i < samples.length; i++) samples[i] = (Math.random() * 2 - 1) * 0.002;
  const floor = context.createBufferSource();
  floor.buffer = noise;
  floor.loop = true;
  floor.connect(microphone);
  floor.start();
  // A clone per request: the app stops the tracks it got, which must not silence the next request.
  navigator.mediaDevices.getUserMedia = async () => {
    await context.resume();
    return new MediaStream(microphone.stream.getAudioTracks().map((track) => track.clone()));
  };
  window.__fakeMic = {
    async play(url) {
      const clip = await context.decodeAudioData(await (await fetch(url)).arrayBuffer());
      const source = context.createBufferSource();
      source.buffer = clip;
      source.connect(microphone);
      await new Promise((resolve) => { source.onended = resolve; source.start(); });
    },
  };
})();
"""

SNAPSHOT = """() => ({
  status: document.querySelector('.status-pill')?.textContent ?? null,
  messages: [...document.querySelectorAll('.bubble')].map((bubble) => [
    bubble.classList.contains('bubble-agent') ? 'agent' : 'founder', bubble.querySelector('p').textContent]),
})"""


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict) -> dict:
    return {**browser_type_launch_args, "args": [
        "--use-fake-ui-for-media-stream",  # accepts the microphone permission prompt
        "--use-fake-device-for-media-stream",  # the device lists are not empty
        "--autoplay-policy=no-user-gesture-required",  # the fake microphone's audio runs from the start
    ]}


@pytest.fixture(scope="session")
def script() -> dict[str, str]:
    return json.loads(Path(__file__).with_name("founder_script.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def clips(script: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return make_clips({name: script[name] for name in [*SCRIPTED, "fallback"]}, tmp_path_factory.mktemp("clips"))


def wait_for_app() -> None:
    """compose up --wait waited for the backend; the frontend's dev server may need a moment more."""
    deadline = time.monotonic() + 60
    while True:
        try:
            urllib.request.urlopen(f"{APP}/api/app-config", timeout=2)
            return
        except OSError:
            assert time.monotonic() < deadline, "the app does not answer at http://localhost:5173"
            time.sleep(1)


def talk(page: Page) -> tuple[int, set[str]]:
    """Answers whenever the agent waits, until the conversation has ended; returns how many answers
    were played and every status seen."""
    statuses: set[str] = set()
    turn = 0
    answered: list | None = None  # the agent's message the founder answered last
    waiting_for: list | None = None  # the agent's message the founder is about to answer
    waiting_since = 0.0
    deadline = time.monotonic() + TIME_LIMIT_S
    while not page.get_by_text(SUCCESS).is_visible():
        assert not page.get_by_text(UNFINISHED).is_visible(), "the conversation ended before it was complete"
        assert time.monotonic() < deadline, f"no success message after {TIME_LIMIT_S // 60} minutes"
        snapshot = page.evaluate(SNAPSHOT)
        statuses.add(snapshot["status"])
        last = snapshot["messages"][-1] if snapshot["messages"] else None
        if snapshot["status"] != "Hört zu" or not last or last[0] != "agent" or last == answered:
            waiting_for = None
        elif last != waiting_for:
            waiting_for, waiting_since = last, time.monotonic()  # a new message: wait until it settles
        elif time.monotonic() - waiting_since >= (
                SETTLE_AFTER_QUESTION_S if last[1].rstrip().endswith("?") else SETTLE_OTHERWISE_S):
            assert turn < MAX_TURNS, f"no success message after {MAX_TURNS} answers"
            clip = SCRIPTED[turn] if turn < len(SCRIPTED) else "fallback"
            print(f"voice test: answer {turn + 1}: {clip}", flush=True)
            page.evaluate("url => window.__fakeMic.play(url)", f"{APP}/__e2e/clips/{clip}")
            answered, waiting_for, turn = last, None, turn + 1
        page.wait_for_timeout(POLL_MS)
    return turn, statuses


def test_a_founder_completes_a_conversation_by_voice(page: Page, script: dict[str, str], clips: dict[str, Path]):
    wait_for_app()
    page.add_init_script(FAKE_MICROPHONE)
    page.route("**/__e2e/clips/*",
               lambda route: route.fulfill(path=clips[route.request.url.rsplit("/", 1)[1]], content_type="audio/wav"))

    # Signup leads straight into the new conversation.
    page.goto(f"{APP}/signup")
    page.get_by_label("Name", exact=True).fill(script["founder_name"])
    page.get_by_label("E-Mail").fill(os.environ["E2E_EMAIL"])
    page.get_by_label("Passwort").fill("e2e-password")
    page.get_by_label("Firmenname").fill(script["company_name"])
    page.get_by_label("Zugangscode").fill(os.environ["E2E_CODE"])
    page.get_by_role("button", name="Registrieren").click()
    page.get_by_role("button", name="Tutorial überspringen").click()
    conversation_id = page.url.rsplit("/", 1)[1]

    # The device check, then START.
    page.get_by_role("button", name="Mikrofon erlauben").click()
    page.get_by_role("button", name="Testton abspielen").click()
    page.get_by_role("button", name="Ich habe ihn gehört").click()
    start = page.get_by_role("button", name="START")
    expect(start).to_be_enabled(timeout=15_000)
    start.click()

    answers, statuses = talk(page)
    print(f"voice test: statuses seen: {', '.join(sorted(filter(None, statuses)))}", flush=True)
    assert answers >= len(SCRIPTED), f"the conversation ended after {answers} of the founder's scripted answers"
    assert WRITING in statuses, "„Schreibt Ihre Antworten auf ...\" never showed"

    page.get_by_role("button", name="Zusammenfassung anzeigen").click()
    expect(page.locator(".outcome-summary")).not_to_be_empty()

    with psycopg.connect(DATABASE) as connection:
        state, questionnaire = connection.execute(
            "SELECT state, questionnaire FROM conversations WHERE id = %s", (conversation_id,)).fetchone()
    entries = questionnaire["entries"]
    assert state == "completed"
    assert questionnaire["summary"].strip()
    assert all((entry["answer"] or "").strip() for entry in entries), "a question has no answer"
    selected = [entry for entry in entries if entry["follow_up"]]
    assert all((entry["follow_up_answer"] or "").strip() for entry in selected), "a follow-up has no answer"
    # Only the pitch names the co-founder, so this fact in the answers proves they come from the founder.
    assert FOUNDER_FACT in json.dumps(entries, ensure_ascii=False), "the answers do not contain what the founder said"
    follow_up_round = f"a follow-up round of {len(selected)} follow-ups" if selected else "no follow-up round"
    print(f"voice test: completed with {follow_up_round} (conversation {conversation_id})", flush=True)
