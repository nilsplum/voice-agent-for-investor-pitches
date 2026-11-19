# d3: Live API spike (note-taker, tools, sideband)

`spike.py` runs a real GPT-Live session the way the app will: a voice agent, a note-taker
(Responses delegation) with fake tools that carry the app's real names, and a sideband that
answers the tools. It answers the open points of section 17 of
[`_docs/planning/high-level-plan.md`](../../_docs/planning/high-level-plan.md) before any app code
depends on them. The terminal plays the browser (microphone, speaker, transcript), and the
sideband plays our backend. How the script works is in its docstring.

## Setup (once)

```bash
cd drafts/d3-liveDelegation
python3.13 -m venv .venv && .venv/bin/pip install websockets==17.4 sounddevice==0.5.6
```

Use Python 3.13 (the Homebrew Python 3.14 on this machine cannot create venvs). The key comes from
`OPENAI_API_KEY` or from a `.env` file next to the script (`OPENAI_API_KEY=sk-...`, git-ignored).
It needs access to `gpt-live-1`, `gpt-6-luna` and `gpt-6.1-sol`.

## Runs

Wear **headphones**. On laptop speakers the microphone is muted while the agent talks (as in d2),
so you cannot interrupt it. Every run writes `events-<timestamp>.jsonl` next to the script
(git-ignored) and ends with a summary: the session limit, the reply times and the received
event types per connection. Cost: `gpt-live-1` is $0.05 per minute, so the whole plan below
costs well under $1.

1. **Thinking levels** (question 10, no audio, about 2 minutes):
   `.venv/bin/python spike.py --probe-efforts`
2. **The conversation** (questions 1 to 5, 7 and 8, about 6 minutes): `.venv/bin/python spike.py`
   - After the greeting, say you have no questions.
   - Answer the three questions (product, traction, funding). Give the traction **without numbers**.
   - Listen: the summary should be read while the fake review runs (8 seconds).
   - The follow-up asks for traction numbers. Answer it **and add something new about your
     product** ("Und zum Produkt noch: ...").
   - After the goodbye the session should end by itself, about 2.5 seconds after the last word.
3. **Kickoff** (question 6, short runs, Ctrl+C after the greeting):
   `--kickoff input`, then `--kickoff commentary` (the default `both` is run 2).
4. **Voices** (question 9, short runs, Ctrl+C after the greeting):
   `--voice nuri`, `--voice flitz` (run 2 used `juni`), then
   `--language en --voice marin`, and for example `--voice gleam` and `--voice meridian`.

Other options: `--effort`, `--founder`, `--company`, `--devices`, `--mic`, `--speaker`
(see `--help`).

## Findings

The "Docs" column is what OpenAI's documentation and the official SDK (`openai` 3.51.0) said on
2026-11-16. The "Run" column is filled in from the runs above, with the log events as evidence.

| # | Question | Docs | Run | Consequence for the app |
|---|---|---|---|---|
| 1 | Does the note-taker see the whole conversation? (compare the `submit_initial` arguments with what was said) | Implied: only client delegation has to collect the transcripts itself; the suggested backend prompt says the conversation arrives as live transcripts. | Verified in the app's voice test runs (2026-11-16): `submit_initial` held every answer from the founder's spoken pitch, in the founder's words. | Yes: as planned. No: the backend writes the answers from its saved transcript with one Responses call using the same tool model. |
| 2 | Does the `session.update` tool swap work mid-session, and does the addition about question 1 land in `question_1`? | `session.update` may change `delegation.responses` (tools included); omitted settings stay; a rejected setting arrives later as an `error` with `responses_validation_failed`. | Verified in the app's voice test runs: after the `session.update`, the note-taker called `submit_follow_up`, and the late `submit_initial` path is no longer offered. | Yes: as planned. No: the session starts with all four tools, and the tool of the wrong phase returns an AI message. |
| 3 | Does the primary (the browser's data channel) receive `session.delegation.created` and nested `response.event`s, and which nested events start and end a tool's work? | The data channel carries "nested `response.event` messages"; its permissions (`session.client.data_channel`) allow every event when omitted. A function call arrives as nested `response.output_item.done`; the end event is not documented. | Verified in the app's browser call (2026-11-16): the data channel carried `session.started`, the transcript deltas and the nested `response.event`s; "Schlägt nach ..." showed during the startup lookup and cleared with the next `response.created`. | Yes: the status shows "Schlägt nach ..." and "Schreibt Ihre Antworten auf ..." from these events. No: the agent's spoken notice is the only indicator. |
| 4 | Is the commentary summary read aloud while `submit_initial` is pending, and does the follow-up wait until it is finished? | Commentary is "information to speak aloud" that the model may paraphrase; its acknowledgment confirms neither wording nor playback. At most 500 tokens per append. | Verified in the app's voice test runs: the agent read the stored summary aloud while the review ran and asked the follow-ups only afterwards. It reads it as a whole and paraphrases little. | Yes: as planned. No: the `follow_ups` text starts with the summary, so the agent reads it after the review. |
| 5 | Are input and output transcript times on the same clock, and does `agent.start_ms - founder.end_ms` match the felt delay (`[heard after ...]`)? How often do backchannels split agent messages? | `start_ms`/`end_ms` are milliseconds from the session start, approximate fragment times; no item IDs and no turn-done event. Primary output audio has no timing; the sideband's reflected `session.output_audio.delta` has `start_ms`/`end_ms`. | Plausible in the app's voice test runs: medians of 0.6 to 1.2 seconds per conversation. Speech of the founder over the agent's (the test answering too early) split the agent's messages, as decision 7 of the implementation plan expects. | Yes: reply times from the transcript. No: the agent's start from the reflected output audio on the sideband. |
| 6 | Does the agent speak first with the `input` kickoff alone, the commentary alone, or only both? | OpenAI's recipe uses both: a developer message in `input`, and the same text as `session.commentary.append` (`delegation_id: null`) after `session.started`, with input audio flowing. | Answered with the app and a probe (2026-11-16): `input` alone gives no greeting; the commentary makes the agent speak, reliably when it holds only the words to say (an instruction-style text, which the app first sent, left the agent silent in one of two probes). The voice model hands work over (<|SpawnThinking|>) only in its replies to the founder, never in the commentary-driven greeting, so a lookup the greeting announces never starts by itself. A stream without any input audio gets no greeting and expires after about 30 seconds. | The app uses the smallest combination that works, rechecked over WebRTC once the browser call exists. |
| 7 | Is the output transcript produced at speaking speed, and how long is the pause between the last words before `submit_follow_up` returns and the goodbye? | Not documented. | Answered in the app's voice test runs: the pause before the goodbye includes the note-taker's report of the completion (1 to 7 seconds), longer than 2.5 seconds, so a goodbye watch that started right away closed the session before the goodbye. The app's watch now waits for that report first. | `GOODBYE_SILENCE_S` (2.5 s) must stay clearly above that pause. If the transcript runs ahead of the voice, the goodbye watch uses the reflected output audio's `end_ms`. |
| 8 | What is the session's duration limit (`expires_at` in `session.started`)? | `session.expires_at` is a Unix timestamp; the close reason `expired` exists; no number is documented. | Pending | `CONVERSATION_TIME_LIMIT_S` (30 minutes) must stay below it. |
| 9 | Which German and English voices sound most natural? | German: `juni`, `nuri` (feminine), `flitz` (masculine). English: `marin` (default) and the natural voices `gleam`, `meridian`, `willow`, `stone`, `vesper`, `ripple`. | Pending | The two choices go into `LANGUAGES` in the config module. |
| 10 | Which `reasoning.effort` values do `gpt-6-luna` and `gpt-6.1-sol` accept, in delegation and in the Responses API? | Model pages: `none`, `low`, `medium` (default), `high`, `xhigh`, `max`. The SDK's delegation type: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`. `gpt-6-sol` is superseded by `gpt-6.1-sol`. | Pending | The levels both models accept in both places become `THINKING_LEVELS`, the lowest one the default. |

Also recorded by every run: whether the sideband may attach to a WebSocket session at all. The
docs describe the sideband for WebRTC and SIP sessions only. If the attach is refused, the
primary handles the tools (the summary says "sideband not attached"), the questions above are
still answered, and the sideband itself is first checked with the app's real browser call (WebRTC).
