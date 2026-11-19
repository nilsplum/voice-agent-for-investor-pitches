# Voice Agent for Investor Pitches: Prompt Robustness Analysis

On 2026-11-17 the conversation was tested in 14 real voice conversations and its prompts were read entry by entry. The question: why do the prompts need so many rules, and which of them can a structural change make unnecessary, so that a small, fast model reliably does what it is asked?

This document records findings only. Nothing in the code was changed for it.

**Order of authority:** the requirements, the high-level plan, the audit resolution plan. Every proposal below keeps the behaviour those documents describe; it only moves *where* that behaviour is enforced.

---

## 1. Short Answer

The prompts are long because the two language models do three jobs that the backend could do deterministically:

1. **The voice model carries the interview's state machine.** It has to remember which questions are answered, which are vague, which follow-up it already asked, which phase the conversation is in, and when it may say goodbye. All of it lives only in its context, so every slip was answered with another rule. The `flow`, `follow_up_round` and `delegation` entries alone are 940 words.
2. **The two models talk to each other in free text.** The only way a tool result reaches the voice agent (except the summary) is the note-taker's text reply. The note-taker writes that text as a script, sometimes instead of calling the tool at all, and the voice agent reads it out. About 700 words of rules exist only to keep this channel in line, and the backend guard was added on top.
3. **The note-taker extracts the data under live pressure.** It writes eleven answers, a summary and, in the round, follow-up answers and corrections into the right fields, at the lowest thinking level, while also serving the conversation. About 450 words of rules govern that, and it still made a factual error in one test.

Seven structural changes (section 5) move these jobs into the backend, where they are code, a single structured call that can be tested offline, or instructions that only exist while they apply. By rough estimate this removes about half of the voice prompt and most of the note-taker prompt. It also removes whole classes of failure instead of patching them: double summaries, invented rounds, scripts read out, text instead of tool calls, wrong fields, and the deadlock when a founder wants to stop.

---

## 2. How the Conversation Is Steered Today

```
 founder speaks ──► voice agent (gpt-live-1)
                     prompt: 1,823 words (role, style, flow, round, delegation, FAQ, questionnaire)
                     │ <|SpawnThinking|> + a free-text request
                     ▼
                    note-taker (gpt-6-luna, low)
                     prompt: 614 words + 4 tool descriptions (364 words) + 3 field templates (87 words)
                     │ tool call                        ▲ tool output (AI message)
                     ▼                                  │
                    backend ── review, empty checks, store, tool swap
                     │
                     ├─ commentary to the voice agent: the greeting, the summary, the guard's warning
                     └─ everything else (follow-ups, "completed", missing answers, search results)
                        goes back to the note-taker, which REWRITES it as free text for the voice agent
```

| Text the models read | Words |
|---|---|
| Voice prompt (`voice_instructions`, with FAQ and catalog) | 1,823 |
| of which `flow` / `follow_up_round` / `delegation` | 429 / 219 / 292 |
| Note-taker prompt | 614 |
| of which `answers` / `procedure` / `search` / `reporting` | 212 / 147 / 100 / 77 |
| Tool descriptions and field templates | 451 |
| AI messages (`messages.json`), of which the guard's two texts | 482, 169 |
| Reviewer prompt | 227 |

---

## 3. Method and Evidence

**Fixed-script runs (the voice test of `--complete`, during the audit).** Seven conversations with the scripted founder (opening, one pitch that answers everything, a closing line, then refusals), after changes 4, 11, the guard and its diagnosis. One of them ran with a temporary log of the note-taker's texts (removed, never committed).

**Scenario runs (built for this analysis, never committed).** A throwaway harness in the scratchpad drove the real app in Chrome with a *simulated founder*: a small model played a persona with a fact sheet and answered whatever the agent actually asked, spoken with the voice test's clip code. A tap on the browser's data channel recorded every event, including the note-taker's texts and tool calls, without changing the app. Seven personas ran:

| Scenario | Persona | Outcome |
|---|---|---|
| brief | answers each question when asked, briefly and completely | completed |
| refuser | declines funding and round, stays with it | completed |
| vague | vague traction, „weiß ich nicht" on market size, vague funding; concrete on a follow-up | 12 turns recorded (stopped by OpenAI's rate limit) |
| asker | asks process questions, a general question about a market and one about investment terms | 11 turns recorded (rate limit) |
| pitcher | a long pitch at the first question, a correction later | reached the follow-up round (rate limit) |
| stopper | wants to stop after four questions | deadlock, still „Läuft" at the harness's time limit |
| english | speaks English throughout | 9 turns recorded (rate limit) |

The account's credit ran out during the re-runs (`credit_balance_exhausted`), so four scenarios have partial recordings. They still cover the behaviour each persona was built to test.

---

## 4. Findings

Each finding names its evidence, its root cause and the prompt text that exists only because of it.

### F1. The note-taker answers a request with text instead of a tool call
- **Evidence:** in 6 of the 10 conversations that reached writing down. Examples: „Need submit_initial now." (its own plan as the reply, then nothing; brief); a summary as text (fixed runs after change 4 and 11); an FAQ answer instead of writing down („Sie können das Gespräch über die STOPP-Schaltfläche beenden", stopper); "the funding follow-up is still open, ask it now" (diagnosis run). In one run it answered three reminders in a row with text again.
- **Root cause:** the note-taker may choose between text and a tool on every turn, and a small model at low effort sometimes narrates instead of acting, or decides for itself that the request cannot be done yet. OpenAI offers no per-response `tool_choice`, and no way to cancel its reply.
- **Prompt text it causes:** `procedure` (tool first, also when unsure), the tool descriptions' "call it whenever asked", `tool_required` (119 words), `result_without_tool` (50), and in the voice `flow` the rule that writing down has worked only in the backend's form (about 70 words). Plus the backend guard.

### F2. The note-taker's reply is a script, and the voice agent reads it out
- **Evidence:** in 6 of 7 scenario runs, the startup lookup's background contained a greeting or the next step („Mira kann sagen: „Guten Tag …""; „Als Nächstes begrüßen Sie …"), and in the english run the agent spoke that greeting word for word. After a web search the reply contained the next interview question in the note-taker's own words, and the agent read it out verbatim (asker). Reports after writing down scripted the goodbye (brief, refuser), and in the diagnosis run the summary, the announcement and only the first follow-up, so the agent invented the second one.
- **Root causes:** (a) its text is the only channel back to the voice agent, so it writes for that audience; (b) the greeting instruction sits in the session's startup `input` (`live.py`), which the note-taker sees as part of the conversation; (c) its role said "sentences the agent can say" until today, and the rule against scripts (added today) did not stop it.
- **Prompt text it causes:** `reporting` (77), parts of `role` and `search` (about 60), `follow_ups` "tell the voice agent", the voice `delegation` sentences about the lookup's background (about 50).

### F3. The voice model loses track of the interview's state
- **Evidence:** asked every question again after a full pitch („auch wenn Sie schon einiges abgedeckt haben", fixed run), while the pitcher scenario skipped correctly; asked a follow-up nobody selected and skipped a selected one (diagnosis run); ran a whole follow-up round with an invented question before any follow-ups existed (fixed runs after change 4 and 11); asked „Gibt es noch etwas …?" and went on without waiting (english).
- **Root cause:** the questionnaire's progress (answered, vague, declined, followed up) exists only in the voice model's context. The backend knows nothing until the first submit. The round's rules are in the prompt from the first second, so the model can apply them when no round exists.
- **Prompt text it causes:** most of `flow` (skip, partial, once, never twice, never repeat, when to write down: about 250 words), all of `follow_up_round` (219), the questionnaire block's instruction to use the context (it also makes the agent read the context aloud: „Also zum Beispiel Zahlen zu Nutzern, zahlenden Kunden …").

### F4. Completeness is judged in three places
- **Evidence:** the agent decides when "every question has an answer", the note-taker decided on its own that a follow-up was missing, and the tool's empty check decides again. In the diagnosis run they disagreed, and the guard then pushed the note-taker into filling the gap with „nicht beantwortet".
- **Root cause:** no single owner of "what is still open".
- **Prompt text it causes:** "never decide yourself whether an answer is missing" (procedure, tool texts, reminder), "leave it empty" (three field templates).

### F5. The note-taker makes extraction errors under load
- **Evidence:** the pitcher said „fünf Mitarbeitende, nicht vier" (besides three founders). The stored team answer became „Zusammen sind wir fünf Mitarbeitende", and the summary „fünfköpfiges Team … sowie zwei weiteren Mitarbeitenden": 5 people instead of 8. In the diagnosis run, a forced call filled an unanswered follow-up with a note.
- **Root cause:** eleven fields, a summary and the round's routing in one live tool call, at the lowest thinking level, with no offline test of the extraction at all (the fake tests send ready-made arguments).
- **Prompt text it causes:** `answers` (212), the three field templates (87), the submit tools' field texts (about 150).

### F6. A founder who wants to stop deadlocks the conversation (a design gap)
- **Evidence:** stopper. The agent handed over, the note-taker answered with the STOPP hint, the guard forced `submit_initial`, the empty check refused it (7 answers missing), and the conversation stayed „Läuft" until the time limit.
- **Root cause:** decision 7 of the audit resolution plan says a founder who says „Ich möchte aufhören" gets a proper end with a result. But the only end is writing down, and writing down refuses missing answers. No path exists between the two.
- **Prompt text it causes:** "never say goodbye before … also not when the founder declines questions or wants to stop" (flow), and the round's "when the founder does not want to answer any more".

### F7. The language and the speech are not reliable
- **Evidence:** the agent stayed in German while the founder spoke English for six turns (english). It spoke its own notes aloud („Fertig machen. Jetzt sauber aufschreiben."), and some transcripts start with stray characters in other scripts (Bengali, Gujarati, Kannada), also in a note-taker reply.
- **Root cause:** model behaviour, made more likely by a long prompt that is otherwise English and by the German catalog. Not a matter of more rules.

### F8. The same rule is written in several places
| Rule | Where it is written |
|---|---|
| Tool first, never text | note-taker `procedure`, four tool descriptions, `tool_required`, voice `delegation`, voice `flow`, `result_without_tool` |
| A declined answer counts as answered | voice `flow`, `follow_up_round`, note-taker `answers`, `submit_follow_up`, two field templates, reviewer |
| Missing answers are named by the tool | `procedure`, two tool descriptions, `reporting`, `tool_required`, `missing_answers` |
| The summary comes from writing down | voice `flow` (twice), `procedure`, `reporting`, `summary_commentary` |
| The startup lookup is background | voice `delegation`, note-taker `search`, `kickoff` |

Every copy is a place where a later change can drift, and each extra sentence competes for a small model's attention.

### What worked reliably
Refusals were accepted at once (refuser), vague answers got exactly one follow-up aimed at a number or an estimate (vague), process questions were answered from the FAQ at once (asker), the reviewer selected nothing when everything was complete or already followed up, the summary commentary was read once whenever the note-taker called the tool, and the backend's goodbye close and reply times (medians 0.2 to 1.0 s) held in every run. These rest on short, local rules or on the backend; they need no change.

---

## 5. Structural Proposals

Ordered by leverage. Each names what moves, which prompt text it makes unnecessary, what it fixes, and what must be verified first. The estimates of removed words are rough.

### P1. The backend writes everything down from the transcript
- **Mechanism:** the submit tools lose their answer fields: `submit_initial()` and `submit_follow_up()` only mean "write it down now". The backend reads the saved transcript (the founder's last answer is saved at the hand-over already) and makes one strict structured-output call, the same pattern as the reviewer: per question the founder's answer in their words, empty if not answered, marked if declined; the summary; in the round the follow-up answers, additions and corrections, and the final summary. The empty check and the review stay as they are.
- **Removes:** note-taker `answers` (212), the three field templates (87), the submit tools' field texts (about 150), the field parts of `procedure` and `tool_required`. About 450 words.
- **Fixes:** F5 (the extraction gets its own model, its own thinking level, and offline tests on transcript fixtures, for example the pitcher's correction), F4 (the extraction's output is the one answer to "what is open"), and most of F1, because a tool without arguments is the easiest possible call.
- **Verify:** extraction quality on recorded transcripts (offline, a few cents), and the latency of the writing-down wait (one call instead of the note-taker composing all fields; today 2 to 7 s).

### P2. The backend tells the voice agent every result itself
- **Mechanism:** every result meant for the voice agent goes out as backend commentary or an appended instruction, like the summary today: the follow-ups (with P3), the missing questions, "everything is written down", a search's findings. The tool output tells the note-taker only that it is done ("Done. Reply with one word: erledigt."), so its reply carries nothing the agent could act on.
- **Removes:** `reporting` (77), the reporting parts of `role` and `search`, the "tell the voice agent" framing of `follow_ups`, and the voice rule that writing down has worked only in the backend's form. About 200 words.
- **Fixes:** F2 (no scripts reach the agent with content in them), the double summaries, and the invented round of F3, because the agent only ever hears results from one source.
- **Verify:** that the agent ignores the note-taker's one-word reply and acts on the commentary, and the commentary's timing (it is "paraphrased", per OpenAI's guide; the summary path already proves it works).

### P3. Phase rules arrive when their phase starts
- **Mechanism:** the base voice prompt holds only the questions phase. At the switch, the backend appends the follow-up round's rules together with its questions (`session.instructions.append`, up to 500 tokens, available on the sideband, kept for the rest of the session). At completion it appends the goodbye.
- **Removes:** `follow_up_round` (219) and the ending rules of `flow` (about 80) from the base prompt; `follow_ups` and `completed` become these appends.
- **Fixes:** the invented round of F3: rules that do not exist yet cannot be applied too early. The closing check exists exactly when the round does, by construction.
- **Verify:** OpenAI's documentation says an appended instruction "can interrupt the model's current speech". The switch happens while the summary is read, so the append may have to wait for the summary to end, or go out as `session.thinking.append` first. One spike run decides.

### P4. The backend keeps the interview's progress
- **Mechanism:** the backend knows which questions are open and hands the agent the next step, instead of the agent tracking it. Three ways, cheapest first:
  - **(a) Checkpoints:** after a long answer, the agent hands over "note progress"; P1's extraction runs on the transcript so far, and the backend appends "Still open: 6, 8, 9; question 5 is vague: ask once for numbers" as silent context (`session.thinking.append`).
  - **(b) OpenAI's Decisions:** transcript triggers evaluate a Predicate per question ("answered completely?") on every founder transcript, independently of delegation, and the backend turns the results into the same silent progress note.
  - **(c) Continuous extraction:** a small structured call after every founder turn, in parallel to the conversation.
  In every variant the backend counts the follow-ups, so "at most one per question" becomes a code invariant.
- **Removes:** the skip, partial, once and never-twice rules of `flow` (about 200 words), "when every question has an answer", most of the delegation's write-down triggers, and the long per-question contexts in the voice prompt (the backend can hand over just the next question).
- **Fixes:** F3 (re-asking after a pitch, invented follow-ups) and F4 for good.
- **Verify:** timing (the note arrives after the agent's immediate reply, so it steers the *next* question), cost per turn, and for (b) how Decisions behave, which OpenAI documents only briefly. The largest change; worth a spike before any commitment.

### P5. The startup lookup without the note-taker, and the greeting only as commentary
- **Mechanism:** at session start the backend calls Serper itself (it already does inside `web_search`) and appends the result as silent background (`session.thinking.append`). The greeting goes out only as commentary, not also as the startup `input` developer message, which the note-taker sees.
- **Removes:** `note_taker.kickoff`, the startup bullet of `search` (about 50), the voice `delegation`'s lookup sentences (about 50).
- **Fixes:** the greeting scripts of F2 (6 of 7 runs), and the lookup no longer depends on a model call before the conversation starts.
- **Verify:** that the greeting still starts reliably without the `input` message (the implementation plan kept both after a greeting once stayed silent with instruction-style text).

### P6. Tool calls by construction (a spike)
- **Mechanism:** with P2 the note-taker's text is irrelevant, so it could run with `tool_choice: "required"` (session-wide, documented). The backend then never resumes it after a tool's output (no `response.create`), because the backend speaks the result itself.
- **Removes, if it works:** the guard, `tool_required`, `result_without_tool`, and every "tool first" sentence (about 300 words in total).
- **Fixes:** F1 completely.
- **Verify:** OpenAI does not document what a delegation does when it is never resumed after a function output (whether the next hand-over still starts normally). Until a spike shows it, the guard stays as the safety net.

### P7. An explicit early end
- **Mechanism:** writing down accepts "the founder wants to stop" (an argument or its own small tool): the backend stores what is there, marks the rest as not answered, skips the review and completes; the agent says goodbye. This implements decision 7 of the audit resolution plan as written.
- **Removes:** the contradictory "never say goodbye … also not when the founder wants to stop".
- **Fixes:** F6, the deadlock.
- **Verify:** fake tests suffice; the team view shows "not answered" for the rest.

### P8. One place per rule
After P1 to P5, most duplicates of F8 disappear on their own. For the rest, each rule gets one home: tool usage only in the tool descriptions, conversation behaviour only in the voice prompt, extraction only in the extraction prompt.

### Smaller, prompt-level items
- **Questions read with their context:** the agent should ask the question as written and use the context only when asked to explain. With P4 the context can leave the voice prompt entirely.
- **Language:** if following the founder's language matters, the backend can detect it from the input transcript and append "Speak English from now on", instead of relying on one sentence in a long prompt.

---

## 6. What the Prompts Could Look Like Afterwards

| Prompt | Today | After P1 to P5 (estimate) | What stays |
|---|---|---|---|
| Voice (base) | 1,823 words | about 900 to 1,100 | role, style, a short questions-phase flow, the delegation cue (`<|SpawnThinking|>` for search and writing down), founders' questions, FAQ, and the questionnaire (or only the next question with P4) |
| Voice (appended per phase) | none | about 150 each, only while they apply | the round with its questions and closing check; the goodbye |
| Note-taker | 614 words | about 100 to 150 | its role, "call the tool the request names", one search per question, no confidential details in queries |
| Tool texts | 451 words | about 120 | what each tool does; no field rules |
| Extraction prompt (new, backend) | none | about 150 | the rules of today's `answers`, in one place, tested offline |

The rules that stay are the ones a small model follows well, because they are local to the current turn: style, one question at a time, answer from the FAQ, decline off-topic questions, never rate the startup.

---

## 7. Recommended Order

1. **P7** (early end): a real gap against decision 7, small and fully testable with the fake world.
2. **P1** (backend extraction) with offline extraction tests: the largest removal with the least risk, and it makes P2 and P6 simpler.
3. **P2** (the backend speaks every result) and **P5** (lookup without the note-taker): they close the free-text channel.
4. **P3** (phase rules on arrival), after a spike on the append's timing during the summary.
5. **P6** spike: if a never-resumed delegation is harmless, remove the guard and every "tool first" rule.
6. **P4** spike: progress in the backend, starting with checkpoints (a).
7. **P8**: a final pass for single homes and removed duplicates.

Each step should end with the scenario runs of section 8, so a removed rule is only removed once a scenario proves it is no longer needed.

---

## 8. How to Test Prompt Changes from Now On

- **Scenario runs instead of one script.** The voice test's fixed founder (one pitch that answers everything) hides most of the behaviours above: it never asks questions, never stays vague, never wants to stop, never speaks English. A persona-driven founder with a fact sheet, as in this analysis, covers them, and a data channel tap records the note-taker's texts without changing the app. Worth making a permanent, optional script (it costs a few cents per scenario), run one scenario at a time because of OpenAI's rate limits.
- **Offline extraction and review tests.** With P1, the extraction is a pure function of a transcript, testable like the reviewer on prepared transcripts, including corrections, refusals and early stops.
- **Measure, don't assume.** For every rule removed, the scenario that motivated it should pass at least twice, because model behaviour varies from run to run.

---

## 9. Open Points and Operator To-dos

- **OpenAI credit:** the account's credit balance was exhausted during these runs (`credit_balance_exhausted`); the app's own START fails until it is topped up.
- **Decision 7 is not implemented:** see F6 and P7.
- **The scenario harness** (the persona founder, the data channel tap, the report script) exists only in this session's scratchpad. If it should become a permanent test, it belongs in `e2e/` with its own script entry, and its clip code needs the language as a parameter (it currently asks the audio model to read in German, which garbled the english scenario's later answers).
