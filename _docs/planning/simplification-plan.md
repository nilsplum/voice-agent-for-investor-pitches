# Voice Agent for Investor Pitches: Simplification Plan

This plan turns the findings of `_docs/planning/prompt-robustness-analysis.md` into changes. The goal: a codebase that gets simpler, and prompts that shrink, because the backend takes over the jobs a small model does unreliably. Every proposal below replaces rules with structure; none adds a mechanism the codebase does not already use.

**Order of authority:** the requirements, the high-level plan, the audit resolution plan, then this plan. The behaviour those documents describe stays the same for founders and the team; only *who enforces it* changes. Where this plan changes a described mechanism (for example the four tools), the high-level plan is updated with it. The implementation plan stays the record of how the app was built; where it disagrees, the high-level plan wins (it says so itself).

**How to work with this plan**
- Read `AGENTS.md`, the README, the high-level plan, the analysis above and this whole plan first.
- One commit per change, in the order of section 3, on the branch `simplification`, committed locally only (developer decision). Each commit carries its tests and docs and ends green with `./scripts/test.sh`.
- The real checks of section 4 run in `./scripts/test.sh --complete` and in three scenario runs of the analysis's throwaway harness (developer decision: stopper, asker, pitcher; never committed).

---

## 1. The Idea

**Today** the two models do three jobs the backend could do: the voice agent tracks the interview's whole flow from its prompt, the note-taker writes all answers into eleven tool fields, and the two talk to each other in free text, which the voice agent reads out.

**After this plan** one rule holds everywhere: *the models talk and trigger; the backend writes, decides and says what comes next.*

```
 TODAY                                              AFTER THIS PLAN
 voice agent ─ hand-over ─► note-taker              voice agent ─ hand-over ─► note-taker
   (1,823-word prompt)        (614 words, 4 tools,     (about 1,150 words)        (about 90 words, 3 tools,
                               11 answer fields)                                    no fields: it only triggers)
        ▲                          │                       ▲                          │
        │ free-text script         ▼                       │ backend messages         ▼
        └──────────────────── backend                      └──────────────────── backend
          (summary only)       stores, reviews               (every result and     writes the answers
                                                              every next step)     from the transcript,
                                                                                    reviews, decides
```

---

## 2. Decisions

1. **The backend writes the answers from the transcript.** The submit tools take no input. When the note-taker calls one, the backend reads the saved transcript and makes one strict structured-output call, the same pattern as the reviewer: the founder's answer per question in their own words (empty if not answered), the summary, and whether the founder wants to stop. The note-taker's model and thinking level from the settings („Protokollant") make this call, so the settings keep their meaning: the AI that writes the answers down.
2. **One channel to the voice agent: backend messages.** Every result and every next step reaches the voice agent as commentary from the backend, the channel the summary already uses reliably: the missing questions, the follow-up round, the goodbye, a web search's results. The note-taker's reply after a tool is only „OK", so its free text can no longer carry a script, a summary or a question. *Revised:* a search's result is the note-taker's reply (see C5).
3. **Each step's rules arrive with the step.** The follow-up round's rules (announcement, questions, closing check) and the goodbye come inside their backend messages, when the backend decides that step. The base voice prompt only holds what applies all the time. One mechanism (commentary), already proven, instead of a second one (`session.instructions.append`).
4. **The startup lookup stays a tool call, and its result arrives as silent background** (developer decision: the requirements name "a web search for the named startup" as a tool-calling example, and the greeting must never depend on it). At session start the backend sends the greeting and, at the same moment, asks the note-taker to call `web_search` for the startup; the voice agent greets while the search runs. The first search of a call is this lookup: its result goes to the voice agent as silent background (`session.thinking.append`), not as something to answer. The note-taker only replies „OK", so it can no longer turn the lookup into a greeting script. *Revised:* the lookup stays a tool call, but its result is the note-taker's reply, like every search's (see C5).
5. **The founder can end early with a result.** The writing-down call also says whether the founder wants to stop. Then the backend stores what was said, leaves the rest as not answered, skips the review and completes. This implements decision 7 of the audit resolution plan, which today deadlocks (analysis, F6).
6. **`get_questionnaire` is removed.** The questions are in the voice prompt, and the round's questions come with the round's message; nothing is left to reread. One tool, its label, its status and its tests go.
7. **The tool swap stays, with static tools.** Phase 1 offers `web_search` and `submit_initial`, phase 2 `web_search` and `submit_follow_up`, both without fields, so the note-taker can never pick the wrong write tool, and the browser keeps its verified signal for the „Rückfragen" section (`session.updated`). The tools no longer depend on the questionnaire.
8. **The guard stays as the safety net**, with shorter texts: a request answered with text alone still triggers nothing, so the reminder remains.
9. **The requirements still hold** (checked before implementing): "Am Ende fasst der Agent zusammen und legt das Ergebnis strukturiert ab" and the tool-calling bonus ("das Gesprächsergebnis strukturiert speichern … oder eine Websuche zum genannten Startup"). The agent still reads the summary; the submit tool call is what stores the result in a structured way, with the backend's schema-enforced call doing the writing (developer decision: "Backend writes"); the startup search stays a tool call (developer decision, decision 4).
10. **Not in this plan:** the backend tracking which questions are open (analysis P4), forcing tool calls with `tool_choice: "required"` (P6), and language detection. Each needs a real spike first and can follow once this plan is measured.

---

## 3. Changes

### C1. One structured call for the backend's AI work
- **New `backend/app/ai/structured.py`:** the one OpenAI Responses call with a strict JSON schema, moved out of `reviewer.py` unchanged in behaviour: model and thinking level from the settings, instructions from the context system, the input as one JSON object, retries with a pause, a timeout per attempt, the first valid output text, logs with type, status, duration and counts only. An optional check lets a caller refuse a valid but unusable result (the summary's length), which counts as a failed attempt.
- **`reviewer.py`:** `review()` keeps its signature and its filtering (only known questions, the first follow-up each) and calls `structured.call(...)`.
- **`config.py`:** `REVIEW_ATTEMPTS`, `REVIEW_TIMEOUT_S`, `REVIEW_RETRY_DELAY_S` become `STRUCTURED_CALL_ATTEMPTS`, `STRUCTURED_CALL_TIMEOUT_S`, `STRUCTURED_CALL_RETRY_DELAY_S`, shared by the review and the writing down.
- **Tests:** `test_reviewer.py` keeps its cases (they now cover the shared call); the fake world's `reviews` queue becomes `responses` (one queue for every structured call, in call order).

**Status: completed.** `./scripts/test.sh` passes. The shared call logs `event=structured_call` (name, attempt, duration); the review logs its counts (`event=review messages= follow_ups=`).

### C2. The backend writes the answers
- **New `backend/app/ai/writer.py`:** `write_down(questionnaire, transcript, settings, round)` returns the written answers or `None` after failed attempts.
  - Input: the questionnaire (IDs, topics, questions, contexts; in the round also the answers, the follow-ups and the earlier summary) and the transcript (speaker and text). In the round only the messages since the switch go in, so additions land in the round and never repeat the first answers.
  - Output (`schemas.WrittenDown`, strict): `answers` (`question_id`, `text`; empty text if nothing was said), `summary`, `founder_wants_to_stop`. One shape for both phases: in the round `answers` holds what the founder said in the round per question.
  - The summary's length is checked (`SUMMARY_MAX_CHARS`); a longer one is a failed attempt.
- **New context document `writer.json`** with one entry per phase (`answers`, `round`) and `prompts.json` entries `writer_answers` and `writer_round`. The rules of today's note-taker `answers` entry move here, once: the founder's own words, everything said about a question wherever it was said, never the agent's words, a refusal written as such, empty when not answered, four to six sentences of summary, the early stop said in the summary.
- **`LiveCall`** keeps `round_starts_at` (the number of saved messages when the round began).
- **Tests:** fake tests for the request's input and the filtering (unknown IDs, the first entry per ID); real tests (`--complete`) on prepared transcripts in `tests/data/`: complete, vague, declined, the pitcher's correction („fünf Mitarbeitende, nicht vier"), and an early stop.

**Status: completed.** `./scripts/test.sh` passes; the real writer tests run with `--complete` at the end of the plan.
- *Decision:* the writer's rules live once, in `writer.rules`, shared by `writer_answers` and `writer_round` (each adds only its task), so the two phases can never write by different rules.
- *Decision:* `write_down` returns exactly one answer per question in questionnaire order (unknown IDs dropped, the first entry per ID, a missing one empty), so the submit tools' empty checks rely on that shape instead of re-checking the model's output. An empty summary is refused like a too long one.
- *Deviation:* the prepared transcripts are four recorded conversations of the analysis's simulated founder (`tests/data/transcripts.json`: complete, declined, correction, stop), not five written by hand: they are real speech recognition output, which is what the writer reads. The vague case is covered by the complete one, where the agent's follow-ups are part of the transcript.
- *Deviation:* `LiveCall.round_starts_at` lands with C3, where it is first used.

### C3. Tools without fields, results from the backend
- **`tools.py`:**
  - Three static tools: `web_search(query)`, `submit_initial()`, `submit_follow_up()`. A small Pydantic model per tool (`query` for the search, no fields for the submits) gives the strict schema and parses the call. Gone: `tool_model`, `answer_field`, the field templates, building tools from the questionnaire, `_answers`, `_checked_summary`, `LiveCall.tool_models`.
  - `submit_initial()`: read the transcript, `write_down`. Then exactly one of:
    - answers missing and no stop: message `missing_answers` (the questions to ask), nothing stored;
    - the founder wants to stop: store what is there, complete without review, message `goodbye`;
    - otherwise: store answers and summary, message `summary` (read it now), review, then either swap to phase 2 and message `follow_up_round`, or complete and message `goodbye`.
  - `submit_follow_up()`: `write_down` on the round, then missing follow-ups (message `missing_follow_ups`), or store the round's answers and the final summary, complete, message `goodbye`.
  - `web_search(query)`: search, then message `search_results` (the results as text, answer from them and name the source) or `search_empty` / `search_failed`.
  - Every tool returns `tool_done` („OK") to the note-taker, after its messages went out, so the voice agent hears the result before anything the note-taker says.
  - `get_questionnaire` and its handler are removed; `ToolName` loses it.
  - The guard (`remind_to_use_tools`) stays, with the shorter `tool_required`.
- **`context/__init__.py`:** `ToolsDocument` loses the three field templates; a `render_search_results` joins the other render functions (the one place where lists become prompt text).
- **Tests:** `test_tools.py` is rewritten around the three outcomes of each submit (missing, stop, success), the messages and their order, the swap with static tools, and „OK" as every tool output.

**Status: completed**, together with C5 and C8 (see the deviations). `./scripts/test.sh` passes.
- *Decision:* every failure a handler raises (missing answers, a failed writing down, a failed search, the generic error) goes to the voice agent as its AI message, because the voice agent is the one who acts on it; the note-taker always gets „OK". Strict function calling makes invalid arguments and unknown tools practically impossible, so they also tell the voice agent the generic error instead of asking the note-taker to retry; `invalid_arguments` is removed.
- *Decision:* a second `submit_initial` stores nothing and says nothing (`store_initial` returns None). It can only come from a handover while the summary is read, and any message there would interrupt the reading.
- *Decision:* a writing down that fails after its attempts tells the voice agent `write_down_failed` (say it takes a moment, then write everything down once more), so a failed call never ends the conversation.
- *Decision:* the transcript is read once per submit and serves the writing down and the review. `round_starts_at` is the number of messages saved when the round began.
- *Deviation:* one `missing_answers` message serves both phases (the plan had `missing_follow_ups`): in the round the voice agent knows the follow-ups of the named topics from the round's message.
- *Deviation:* C5 is part of this change: with the startup lookup staying a tool call (developer decision), its only change is where `web_search` sends the lookup's result. The kickoff opens the call's first delegation (verified in a recorded session: the backend's `response.create` creates a `session.delegation.created` like a handover, and the voice agent delegates only in reply to the founder), so a search in that delegation is the lookup.
- *Deviation:* C8 is part of this change: the generated `ToolName` loses `get_questionnaire`, so the frontend labels change in the same commit (AGENTS.md section 6). Its „reading" tone and icon go with it.
- *Fix:* `read_questionnaire` was used only by `get_questionnaire` and is removed.
- *Fix:* the test that no founder's words reach the logs now captures at the app's own level, INFO (app/logs.py). At DEBUG it read the websocket library's frame dumps, which the app never turns on and which carry what is said by design; it passed before only because the marker was cut from the middle of a long frame.

### C4. The prompts, rewritten around the new roles
- **`voice_agent.json`:**
  - `flow` shrinks to the questions phase (target wording in section 5): ask in order, skip and partly answered, one follow-up right away, refusal counts, come back to the questionnaire, and at the end (or when the founder wants to stop) hand over writing everything down and wait. "What comes next is told to you by messages from the backend; follow them; never summarize, say that something is written down, or say goodbye on your own."
  - `follow_up_round` leaves the base prompt (it becomes the message `follow_up_round`).
  - `delegation` keeps the trained cue (`Generate <|SpawnThinking|>`), the two triggers (a general question the FAQ does not answer; writing everything down, naming the tool) and one sentence: results reach you as backend messages, the note-taker's own words are not for the founder.
  - `kickoff` stays the greeting; `style`, `role`, `founders_questions`, `faq`, `questionnaire` stay.
- **`note_taker.json`:** one short entry (target wording in section 5): call the tool the request names, `submit_*` take no input, one search per question without confidential details, after a tool reply only „OK". `kickoff` stays (C5).
- **`tools.json`:** three short descriptions, no field rules.
- **`messages.json`:** the step messages `missing_answers`, `summary`, `follow_up_round` (the round's rules with its questions), `missing_follow_ups`, `goodbye`, `search_results`, `startup_background`, `tool_done`, plus the errors. Removed: `follow_ups`, `completed`, `unknown_questions`, `already_submitted`, `invalid_arguments` for the submits. `tool_required` and `result_without_tool` get shorter.
- **Tests:** `test_context.py` renders every prompt and message with the values the code fills in.

**Status: completed.** `./scripts/test.sh` passes. Without the FAQ and questionnaire lists, the voice prompt went from 1,250 to 684 words (`flow` 429 to 226, `delegation` 292 to 148, `follow_up_round` 219 moved into its message) and the note-taker's from 614 to 104.
- *Decision:* the handover still names the tool (the developer's earlier decision): `submit_initial` in the flow, `submit_follow_up` in the round's message, `web_search` for a founder's question. The note-taker has only one write tool per phase, so the name only confirms it.
- *Decision:* the rule that the startup lookup's results are background only lives in their message (`startup_background`), not in the voice prompt.
- *Messages:* the step messages and their texts came with C3, where the code that sends them was written.

### C5. The opening: the greeting first, the lookup's result as silent background
- **`live.py`:** on `session.started` the backend sends the greeting (commentary, unchanged) and the note-taker's kickoff (unchanged), so the greeting never waits for the search. `LiveCall` marks the startup lookup as pending.
- **`tools.py` (`web_search`):** while the startup lookup is pending, the first search is it: its results go to the voice agent as silent background (`session.thinking.append` with `startup_background`), or nothing if the search found nothing or failed. Every later search is a founder's question and gets `search_results`.
- The session's startup `input` (the greeting) stays as it is; the note-taker only replies „OK", so it cannot turn it into a script.
- **Tests:** `test_sideband.py` (the opening unchanged) and `test_tools.py`: the first search becomes silent background, a later one an answer to give.

**Revised after the scenario runs.** The note-taker's reply to the lookup always reaches the voice agent, and it arrives while the agent greets. A bare „OK" there made the agent say „OK" and greet twice; not resuming the note-taker after the lookup left „Sucht im Internet ..." in the browser for the whole call, because the browser ends a tool's status with the note-taker's next response. So every search, the lookup and a founder's question alike, goes back to the note-taker as before this plan: the tool's output carries the results (or that nothing was found, or that the search failed) and says what to reply, and that reply is the voice agent's result, background for the lookup. The note-taker's one rule is „reply as the tool's output says"; writing down still ends with „OK". The rule that the lookup's result is background only lives in the voice prompt's `delegation` again, because that is where the agent takes a hand-over's result. Gone: `startup_background`, `session.thinking.append` (so its real check in section 4 is moot), `LiveCall.lookup_delegation` and the `delegation_id` the handlers carried for it.

### C6. The goodbye watch without the note-taker's report
- **`live.py`:** the goodbye message comes from the backend now, so the watch starts when it is sent: it closes once the agent has spoken *after* that moment and then nobody spoke for `GOODBYE_SILENCE_S`. The wait for the note-taker's report goes, and with it `responses_started`, `last_finished_response`, `last_finished_at` and the `responded` event. The note-taker's responses are still logged with their duration.
- **Tests:** the goodbye tests keep their cases (the handover's last words never count; founder speech after the goodbye delays the close).

**Status: completed.** `./scripts/test.sh` passes. The fake world's `reports` switch, which only the old wait used, is removed: the fake note-taker always answers a tool's output with its „OK" response.

### C7. The early end, shown to the team
- **`conversations.py`:** `store_initial` accepts unanswered questions (`None`) when the founder stops, and `store_review` completes with `reviewed` left empty when no review ran.
- **`ConversationDetailCards.tsx`:** an answer that is still empty once the summary exists shows „Nicht beantwortet" instead of „Noch nicht verfügbar".
- **Tests:** a stop during the questions and one during the round, both ending Completed with the summary.

**Status: completed.** The store part came with C3, where the submit tools need it (`store_initial` stores an empty answer as unanswered and completes at once when the founder ended early; `store_review` is not called then, so `reviewed` stays empty), together with its tests. This change adds „Nicht beantwortet" to the team's questionnaire card. The „Nicht geprüft" note stays only for a failed review: after an early end no review ran, and the summary says that the founder ended early. `./scripts/test.sh` passes.

### C8. The live chat follows the tools
- **`labels.ts`:** `TOOL_LABELS` loses `get_questionnaire` (the generated `ToolName` enforces it). The startup lookup keeps its tag „Sucht im Internet ...", because it stays a tool call.
- **`status.test.ts`:** cases without `get_questionnaire`.

### C9. Docs (two passes)
- **README:** "Three AI roles" (the note-taker triggers, the backend writes the answers and reviews them), "Two phases and four tools" becomes three tools, and the opening.
- **High-level plan:** sections 3, 4, 5, 7 (roles, tools table, flow steps, startup lookup), 10, 11 and 12; section 15 F3 for the early end.
- **AGENTS.md section 6, AI integration:** "their fields are generated from the conversation's questionnaire" becomes true for the writing-down schema, not the tools.
- **Pass 2:** search for "answer field", "get_questionnaire", "reread", "report", "follow_ups", "completed", "kickoff" across the repo.

**Status: completed.** README (team part: the early end, „Nicht beantwortet", no „nachliest"; developer part: roles, three tools, the writing down, logs), the high-level plan (sections 3 to 15, including the early end as a flow step and in F4), the two AGENTS.md lines of section 6 that described the old mechanism (AI integration, and "every tool reply" in error handling), and pass 2 (the `schemas.py` docstring on "tool fields", a test comment). The implementation plan stays the record of how the app was built.
- *Fix:* decision 7 of the audit resolution plan was never in the high-level plan's flow; it is now (the early end), and the FAQ's answer to "Can I stop the conversation?" names both ways: saying so keeps a result, STOPP is an abort.

---

## 4. Real Checks (after the credit is topped up)

Each check has a fallback that keeps the plan intact.

| Check | Why | Fallback |
|---|---|---|
| The round's message arrives while the summary is read: does the agent finish the summary, then run the round? | Commentary is appended mid-speech | The message says "once you have finished reading the summary" (as today's relayed text did); if needed, the backend sends it after the agent's summary ends (silence detection, as the goodbye watch) |
| `session.thinking.append` with `delegation_id: null` under Responses delegation | The startup lookup's background must stay silent | Commentary that says "background, do not read it out" |
| The agent ignores the note-taker's „OK" | It reaches the agent as the delegation's result | A tool output without `response.create` (spike of analysis P6) |
| The writing-down wait | One backend call replaces the note-taker's composing | Accept; it was 2 to 7 s before |

---

## 5. Target Wording (English, as the models read it)

**Voice agent, `flow`**
> Flow:
> - Ask the questions below in their order, one at a time. Skip a question the founder has already answered in full; if it is partly answered, ask only for the missing part.
> - If an answer stays vague, leaves out what the question's context asks for, or the founder does not know, ask one follow-up right away for something workable, such as a rough estimate or a range; then accept whatever comes. A refusal counts as an answer.
> - After answering a question of the founder, come back to the questionnaire.
> - When every question has an answer, or the founder wants to stop, say once that you are writing everything down, generate <|SpawnThinking|> to write it down, and wait in silence.
> - What comes next is told to you in messages from the backend: the summary to read, missing questions to ask, a short follow-up round, or the goodbye. Follow them. Never summarize, say that something is written down, or say goodbye on your own.

**Note-taker**
> You work in the background for {agent_name} in a first conversation between an investor and a startup founder. You only call tools; the backend handles their results.
> - Writing everything down: call the tool {agent_name} names, submit_initial or submit_follow_up. They take no input: the backend writes the answers from the conversation itself.
> - Looking something up: call web_search with a short query that contains no confidential details from the conversation; one search per question.
> - After a tool, reply only: OK.

---

## 6. Done When
- `./scripts/test.sh` passes, and `./scripts/test.sh --complete` (the writer and reviewer on prepared transcripts, a real search, the voice conversation).
- Three scenario runs of the analysis pass, one at a time (developer decision): stopper (ends Completed with a partial result), asker (answers from the backend's search results, no script read out) and pitcher (skips what the pitch answered, stores the correction right). In none of them the founder hears two summaries, a script of the note-taker or an invented round.
- The prompts are about the size of section 7, and the code is smaller (section 7).
- README, the high-level plan and every touched docstring describe the new roles.

---

## 7. What Gets Smaller

| | Today | After |
|---|---|---|
| Voice prompt | 1,823 words | about 1,150 (the round and the goodbye move into their messages) |
| Note-taker prompt | 614 words | about 90 |
| Tool texts | 451 words, 4 tools, 3 field templates | about 120 words, 3 tools |
| Rules written in several places (analysis F8) | 5 rules in 3 to 7 places each | each in one place |
| Code removed | tool fields built from the questionnaire, per-phase argument models, `get_questionnaire`, the goodbye watch's report counting | |
| Code added | `writer.py` (one function), `structured.py` (moved, not new), one flag for the startup lookup | |

**Measured after C1 to C8** (word counts without the FAQ and questionnaire lists; code without tests and generated types, against `main`):

| | Before | After |
|---|---|---|
| Voice prompt | 1,250 words | 684 |
| Note-taker prompt | 614 words | 104 |
| Tool texts | 451 words, 4 tools, 3 field templates | 131 words, 3 tools |
| Backend messages | 458 words | 600 (the round's rules moved here from the voice prompt) |
| Writer prompt | | 308 words (the rules of the note-taker's old `answers` entry, once, plus the two tasks) |
| All text the models read | 2,773 words | 1,827 |
| App code | | +461 / -389 lines: `writer.py` (54) and `structured.py` (80) are new, `tools.py`, `live.py` and `reviewer.py` lost 68 |

The code is not smaller, contrary to the estimate above: the writer and the shared structured call are new code that replaces prompt rules, and the early end is a new path. The text the models read shrank by about a third, and the note-taker's prompt by five sixths.

**What stays exactly as it is:** WebRTC, the sideband, START and the end of a call, the greeting and the startup lookup's start, the database and its states, the reviewer's rules, the summary commentary, the tool swap and the browser's „Rückfragen" section, the guard, the settings, the team area.
