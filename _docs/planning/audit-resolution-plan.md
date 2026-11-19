# Voice Agent for Investor Pitches: Audit Resolution Plan

On 2026-11-17 every sentence of the requirements (`_docs/_requirements.md`) was checked against the code, the UI and a real conversation. This plan records the result, the developer's decisions on every gap, and the changes that resolve them.

**Order of authority:** the requirements, then the high-level plan, then this plan. The implementation plan stays the record of how the app was built; where it disagrees, the high-level plan wins (it says so itself).

**How to work with this plan**
- Read `AGENTS.md`, the README and the high-level plan first, then the files named in each change (whole files, before editing).
- Keep it simple: every change below reuses an existing mechanism. No new tables, routes, constants or modules.
- Code, prompts and docs are English; everything a user reads is German. No comment, docstring or prompt cites this plan or its numbers.
- Two commits fit: the conversation flow (changes 1 to 5), then the interface and the models (changes 7 to 12). The demo guide (change 6) comes last. The plan is done when the checks in "Done when" pass.

---

## 1. Audit Result

**Evidence used**
- The code: backend, context documents, frontend, scripts, tests and the voice test.
- `./scripts/test.sh` on 2026-11-17: 103 backend tests passed (the 4 real-API tests skipped as intended), the frontend type check passed and 9 Vitest tests passed. The regenerated types were unchanged.
- The developer's latest real conversation in the local database ("HiveDone", 2026-11-16 23:18), with its transcript, questionnaire and backend log lines.
- OpenAI's Live API documentation, checked on 2026-11-17.

| Requirement sentence (exact wording) | Status | Evidence, and what changes |
|---|---|---|
| „Ein web-basierter Voice-Agent, der ein Erstgespräch mit einem Startup führt." | Met | React frontend, FastAPI backend, the founder area and the Team area. |
| „Der Nutzer spricht über das Mikrofon im Browser, der Agent versteht das Gesprochene, generiert per KI eine Antwort und spricht sie zurück." | Met | WebRTC between the browser and `gpt-live-1`; the backend creates the session and runs the tools. |
| „…der Agent führt durch das Gespräch und fragt nach, bis er ein belastbares Bild hat." | **Change** | The agent never followed up during the questions. In HiveDone it accepted „Also die Software ist gebaut so", „Ich weiß es nicht" and „N8N oder Zapier" and moved on. Then the reviewer selected 8 follow-ups at the end, and the founder quit after the second. See changes 1 to 3. |
| „Also Team, Produkt und Stand der Entwicklung, Traktion, Markt und Wettbewerb, Finanzierungsbedarf und geplante Runde." | Met | Default catalog questions 2 to 9, plus Branche, Nächster Schritt and Sonstiges. |
| „Am Ende fasst der Agent zusammen und legt das Ergebnis strukturiert ab." | **Change** | The result is stored per conversation (one answer per question, the summary, the follow-ups). But the summary is written before the follow-up round and never updated, so the success message and the team view can show outdated facts. See change 4. |
| „Geringe Latenz: …idealerweise unter 1 bis 2 Sekunden vom Ende der Eingabe bis zum Beginn der Audioantwort." | Met | Nothing sits between the voice and the reply. HiveDone: 17 replies, median 0.6 s, max 2.4 s. The measurement also counts backchannels („Mhm."); it stays as it is, and the README says so (change 5). |
| „Natürliche Sprachausgabe: TTS soll sich möglichst wenig nach Maschine anhören." | Met by design | `gpt-live-1` with the voice `juni` (German) or `marin` (English). Only a person can judge how natural it sounds (operator to-do, section 5). |
| „Start/Stopp-Steuerung: Gespräch per Button starten und beenden." | Met | Blue START after the device check, red STOPP with a confirmation. STOPP stays an abort: only the transcript is kept (decision 7). |
| „Der Agent fragt nach, statt nur zu antworten." | Met | The agent leads through the catalog and always returns to it after answering a founder's question. |
| „Wenn eine Angabe fehlt oder vage bleibt, hakt er einmal nach." | **Change** | Today the agent only follows up at the end, after a review, and the review can fail and leave no follow-ups at all. See changes 1 and 2. |
| „Roter Faden: Der Agent behält im Gespräch, was schon geklärt ist, und wiederholt sich nicht." | **Change** | The reviewer always selected „Sonstiges" again as a closing round, so the founder heard nearly the same question twice. With follow-ups during the questions, the reviewer could also ask about a topic a second time. See changes 2 and 3. |
| „Gesprächsverlauf sichtbar (wer hat was gesagt)." | Met | Live chat transcript („Sie" and the agent's name); the same view for past conversations and the Team area. |
| „Vergangene Gespräche mit Zeitstempel einsehbar." | Met | „Meine Gespräche" and the team list show date and time; the team detail shows when the conversation was created, started and ended. |
| „Mind. 2 Einstellungen anpassbar (z. B. Name des Agents, Tonalität, Sprache, System-Prompt, Fragenkatalog)." | Met | Agent name, conversation language, question catalog, and the model and thinking level of the note-taker and the reviewer. |
| Bonus: „Tool Calling: …das Gesprächsergebnis strukturiert speichern (Startup, Sektor, Stage, Team, Traktion, Finanzierungsbedarf, nächster Schritt) oder eine Websuche zum genannten Startup." | Met | The submit tools hold one field per question; `web_search` looks up the startup during the greeting. „Stage" is covered by Entwicklungsstand plus Geplante Runde (decision 2). |
| Bonus: „Streaming-Antworten." | Met | The voice and the transcript stream live. |
| Bonus: „Gutes UI/UX." | Met, improved | Welcome page, tutorial, device check, status pill, outcome message and Team area. One tutorial slide changes with change 1. Changes 7 to 11 show more on the screen, keep the header in view, mark tool calls and the follow-up round in the live chat, and add a mute button. |

---

## 2. Decisions (the developer, 2026-11-17)

1. **Follow-ups: both right away and at the end.** The end-of-conversation logic is not removed. In addition, the agent is told not to accept a vague answer and to ask again. In the developer's words: "If the answer is 'I don't know', this is fine but depending on the situation, there can be another question asked to get a result that is also workable."
2. **How often, right away: exactly once.** A vague or incomplete answer, or „Ich weiß es nicht", gets exactly one more question aimed at something workable (a rough estimate, a range, a best guess). The agent then accepts whatever comes and moves on. An explicit refusal („Das möchte ich nicht sagen") is accepted at once.
3. **The reviewer gets the transcript** and never selects a follow-up for a question the agent already followed up on. In the developer's words: "just ensure that it is possible to have no follow up."
4. **Final summary:** the follow-up round writes the final summary, which replaces the earlier one. The agent does not read it aloud again.
5. **The closing question becomes the follow-up round's own check**, clearly different from „Sonstiges". The round starts with an announcement that the first round of collecting answers is finished and a short follow-up round follows. It ends with a check about correcting the earlier answers. The developer left the design to this plan ("Think about what makes most sense in order to be well distinguishable from each other").
6. **No follow-ups, no round.** If the reviewer selects nothing, the agent goes straight from the summary to the goodbye. There is no closing check then.
7. **Kept as it is:**
   - **„Stage":** explained as Entwicklungsstand plus Geplante Runde.
   - **The note-taker's remarks inside answers** (for example „…wurden nicht genannt"): left in.
   - **The reply time measurement:** it keeps counting backchannels, and only the README note is added.
   - **STOPP:** an abort that keeps only the transcript. A founder who says „Ich möchte aufhören" gets a proper end with a result.
8. **This plan lives in `_docs/planning/`.** In the developer's words: "Ensure that it is not overcomplicated and implementing it keeps the repo simple and well structured."
9. **A short demo guide is written last** (change 6).
10. **The interface, the developer's six further points** (changes 7 to 12):
    - in-component scrolling with the header always in view, and a denser, reordered Team detail;
    - the area label as a blue pill under the app's name;
    - coloured tags for tool calls in the founder's chat;
    - a separated follow-up section;
    - a mute button in the header;
    - Terra instead of Sol.
11. **Tags and the separator are live only.** They are shown during the call. After it, in past conversations and in the Team area, the chat shows the stored transcript as today; no backend or database change.
12. **The separator starts at the switch to the follow-up tools** (the `session.updated` event on the browser's data channel), after one check in a real call that the browser receives it. If it does not, the developer is asked again before anything is built.
13. **The interface says „Rückfragen"** everywhere, as today; the new tags and the separator use it too.
14. **Terra replaces Sol, and the config comment is corrected.** The comment's wrong claim that removing a model leaves past conversations untouched becomes the true rule. No code is added for removed models.

**How decision 5 is built.** The closing check moves out of the reviewer and into the follow-up round's own rules in the context system. Today the reviewer has to select „Sonstiges" every time to create the closing round, and that forces a follow-up round in every conversation, which decision 6 rules out. With the closing check in the round's rules:
- it exists exactly when a follow-up round exists;
- it is always worded the same way, so it never sounds like „Sonstiges";
- no code or prompt depends on a particular catalog question, and „Sonstiges" becomes a truly ordinary question that the reviewer may or may not select.

---

## 3. Changes

### Change 1: The agent follows up once, right away
- **`backend/app/context/documents/voice_agent.json`, `flow`:**
  - Replace "Never ask follow-up questions of your own and never summarize the answers yourself: the summary and the follow-up questions come from writing everything down." with two rules. The first: "Never summarize the answers yourself: the summary comes from writing everything down."
  - The second, the new rule: if an answer leaves out what the question's context asks for, stays vague, or the founder says they do not know, ask exactly one follow-up right away, aimed at something workable (for example a rough estimate, a range or a best guess). Then accept whatever the founder says and go on, and never ask about the same question a second time. This applies to the questionnaire's questions; the answers in the follow-up round are accepted as they are.
  - The existing rule "A question the founder declines counts as answered" stays and now reads as the counterpart: an explicit refusal is accepted at once.
  - Describe the intent; do not quote example sentences (the agent once copied an English example word for word).
- **`voice_agent.json`, `kickoff`:** "follow-up questions at the end" becomes: a short follow-up question when something stays unclear.
- **`backend/app/context/documents/faq.json`:**
  - "What if I don't know an answer or don't want to share it?" → "Just say so. If you don't know, I may ask once for a rough estimate; otherwise it is noted, and the conversation continues."
  - "Why do you ask follow-up questions?" → "To make sure every topic is complete: when an answer stays open, I ask once right away, and if something is still missing at the end, a few short follow-up questions follow. There is at most one follow-up per question."
  - "Can I correct something I said?" → "Yes, just say so at any time during the conversation." There may be no follow-up round (decision 6).
- **`frontend/src/pages/founder/Tutorial.tsx`, slide 4:** „Rückfragen kommen am Ende." → „Ist eine Antwort unklar, fragt der Agent einmal nach."

**Status: completed on 2026-11-17.** `./scripts/test.sh` passes (103 backend tests, 4 real ones skipped; type check; 9 Vitest tests). The real voice test runs after change 4 (decision 3 below).

**Decision log**
1. **One commit per change, change 6 last.** The developer asked for one commit per change in the document's order, instead of the two commits "How to work with this plan" suggests. The demo guide (change 6) still comes last, because its own text says it is written after changes 7 to 12.
2. **"Never follow up on the same question a second time"** instead of "never ask about the same question a second time". After a pitch, the agent may still ask the missing part of a partly answered question (an existing flow rule); that is the question itself, not a follow-up, so the limit names the follow-up.
3. **`--complete` after changes 4, 11 and 12** (developer decision). Changes 1 to 4 together form the new conversation flow, so the real voice test checks them once, after change 4.
4. **Docs in the commit of their change.** This commit updates what change 1 made false: the README (both parts) and the high-level plan sections 1, 3, 7 (roles, Flow steps 1 to 3, FAQ, common thread), 8 (tutorial) and 15 (F2). The reviewer, the round and the summary follow with changes 2 to 4.

**Inconsistency noted:** the FAQ's "at most one follow-up per question" holds fully only once the reviewer reads the transcript (change 2). Between the two commits, the reviewer could still select a follow-up for a question the agent already followed up on.

### Change 2: The reviewer reads the conversation, and a follow-up round happens only when needed
- **`backend/app/conversations.py`:** add `read_transcript(session, conversation_id) -> list[TranscriptMessage]`, the one reader of the saved messages. `conversation_view` uses it instead of its own query.
- **`backend/app/ai/tools.py`, `submit_initial`:** after `store_initial`, run `transcript = await run_db(conversations.read_transcript, call.conversation_id)`, then `review(call.questionnaire, transcript, call.settings)`. The founder's last answer is already saved, because the agent's handover reply started a new message. Nothing is held while the review waits (say so in the docstring).
- **`backend/app/ai/reviewer.py`:**
  - The signature becomes `review(questionnaire, transcript, settings)`.
  - The input becomes one JSON object: `{"questionnaire": [...as today...], "transcript": [{"speaker": ..., "text": ...}, ...]}`.
  - The log line gets the message count only, never text.
  - Update the docstring.
- **`backend/app/context/documents/reviewer.json`, `rules`:**
  - The input description names the transcript.
  - New rule: never select a follow-up for a question the voice agent already followed up on in the conversation.
  - Remove the rule that always selects the add-anything question (the closing check now belongs to the follow-up round, change 3).
  - Keep the rest: at most one per question, few in total, never for a declined answer, German, never judge.
  - Selecting nothing is normal when every answer is complete or was already followed up.
- **No code change for the empty case:** `store_review` already completes the conversation when there are no follow-ups, and the goodbye follows (decision 6).
- **„Nicht geprüft" note** (`frontend/src/pages/team/ConversationDetailCards.tsx` and the README's team part): „…deshalb gab es keine Rückfragen." → „…deshalb gab es keine Rückfragerunde." Follow-ups during the questions may still have happened.

**Status: completed on 2026-11-17.** `./scripts/test.sh` passes (104 backend tests, 5 real ones skipped; type check; 9 Vitest tests). The real reviewer tests run with `--complete` after change 4.

**Decision log**
1. **The transcript is read after the summary commentary is sent.** The agent starts reading the summary at once; the read is one short step of its own while the agent talks. The message still in progress (the agent's handover) is not saved yet and not part of the review, which it does not need.
2. **The reviewer's rules say how to use the transcript:** to see how each question was asked and answered, keeping in mind that it can contain transcription mistakes. The answers it judges are the written-down ones. Its log line gets `messages=` (the count).
3. **`messages.already_submitted` lost "Corrections come in the closing round at the end."** A follow-up round no longer always exists, so the sentence would promise something that may not come.
4. **Test data:** the fake tests' "closing round" follow-up for question 11 became an ordinary follow-up for question 8, because no prompt creates closing rounds any more. A new fake test checks that `submit_initial` sends the saved transcript to the review, with the founder's last answer, and that the log has only the count.
5. **The real reviewer tests build each transcript from the prepared answers** (every question asked once and answered). The new case adds the agent's follow-up on traction with a reply that stays vague, and the written-down answer contains both replies, as the note-taker would write it. Complete answers may get at most 2 follow-ups (the former 3 without the closing round), and 0 is fine.
6. **The high-level plan's "Anything else?" paragraph and Flow step 6** lost the closing round in this commit; change 3 adds the round's own closing check.

### Change 3: The follow-up round, with its announcement and closing check
- **New entry `voice_agent.follow_up_round`**, listed in `prompts.json` `voice_instructions` right after `flow`. It is the one home of the round's rules:
  1. When the follow-up questions arrive (after the summary), say in one sentence that the first round of questions is complete and that a few short follow-up questions follow.
  2. Ask them one at a time, in the given order, each introduced by coming back to its topic. A declined follow-up counts as answered. Accept additions or corrections about other questions briefly. Never follow up on a follow-up's answer.
  3. As the last question of the round, ask once whether the founder would like to correct anything in the answers given so far. Ask it clearly as the end of the follow-up round, different from the questionnaire's question whether there is anything else.
  4. Then write everything down.
- **Remove those lines from `flow`,** so the round's rules exist only once.
- **`backend/app/context/documents/messages.json`, `follow_ups`:** shorten it to the trigger: the answers are checked; once the summary has been read, the voice agent runs the follow-up round with these questions, in this order: `{follow_ups}`. No rules are repeated there.
- **Where corrections go:** a correction from the closing check goes into the field of the question it concerns (`submit_follow_up` already has an optional field per question). The closing check has no field and is not part of the empty check.
- **Expected German wording** (the agent speaks the conversation language; nothing is hardcoded):
  - the announcement: „Damit ist die erste Runde abgeschlossen. Ich habe noch ein paar kurze Rückfragen."
  - the closing check: „Zum Abschluss der Rückfragen: Möchten Sie an Ihren bisherigen Antworten noch etwas korrigieren?"

**Status: completed on 2026-11-17.** `./scripts/test.sh` passes (105 backend tests, 5 real ones skipped; type check; 9 Vitest tests). The real voice test runs after change 4.

**Decision log**
1. **One home for the round's rules.** `flow` keeps one sentence that leads into the round ("go on with what writing everything down returned: the follow-up round below, or the goodbye"). Change 1's scope clause now says the immediate follow-up rule applies only to the questionnaire's questions and that the round has its own rules below. So "never follow up on a follow-up's answer" is written only in `follow_up_round`.
2. **The round starts only with follow-ups.** The entry's heading says "only when writing everything down returned follow-up questions", so the agent never announces a round or asks the closing check without one (decision 6).
3. **The hand-over trigger moved to the end of the round.** The delegation policy said "every follow-up question has an answer"; it now says "the follow-up round is finished", so the agent asks the closing check before it writes everything down. The early exit stays: when the founder does not want to answer any more, the agent writes everything down at once.
4. **Corrections from the closing check are named twice in the note-taker's texts.** The note-taker's answers rule and the `submit_follow_up` description say that a correction made at the closing check goes into the field of the question it concerns. This is the reply most likely to land in the wrong field, and both texts are where the note-taker decides that.
5. **Test:** `test_context.py` checks that the rendered voice prompt holds the round's entry right after the flow, and that `follow_ups` ends with the rendered list.

### Change 4: The follow-up round writes the final summary
- **`backend/app/ai/tools.py`:**
  - `phase_2_tools` adds the `summary` field.
  - One shared check, `_checked_summary(arguments) -> str`, refuses an empty summary (`missing_summary`) or one that is too long (`summary_too_long`, `SUMMARY_MAX_CHARS`), and both submit handlers use it.
  - `submit_follow_up` passes the summary to `store_follow_up_answers`.
- **`backend/app/conversations.py`:** `store_follow_up_answers(..., answers, summary)` also replaces `questionnaire.summary`.
- **`backend/app/context/documents/tools.json`:**
  - The `submit_follow_up` description mentions the final summary.
  - New `fields.summary`: the earlier summary updated with everything the founder answered, added or corrected in the follow-up round, in four to six sentences, in the conversation language, without judgement; it replaces the earlier summary and is not read aloud.
- **`note_taker.json`, `answers`:** one line saying that writing down the follow-up round includes the final summary.
- **Not read aloud:** no commentary is sent, and the `completed` message is unchanged.
- **`backend/app/schemas.py`, `Questionnaire.summary` description:** "written at the first submit, replaced by the final one when the follow-up round is written down; null before the first submit." Regenerate `frontend/src/api/types.ts` (`./scripts/test.sh` does it) and commit it with the change.
- **The second „writing down" wait** grows by one field; the voice test log shows it (`event=note_taker_finished`).

**Status: completed on 2026-11-17.** `./scripts/test.sh` passes (106 backend tests, 5 real ones skipped; type check; 9 Vitest tests), and `./scripts/test.sh --complete` passes (111 backend tests with the 5 real ones; the voice conversation). This real run covers changes 1 to 4 together (decision 3 of change 1).

**Decision log**
1. **One summary check, in the same order in both tools:** the missing answers first, then `_checked_summary`, so the note-taker gets one message at a time.
2. **The final summary keeps the same limit** (`SUMMARY_MAX_CHARS`), because it replaces the first one in the same places (the success message and the Team area). The config comment and `messages.summary_too_long` no longer say "to be read aloud", since the final summary is not.
3. **The trigger does not repeat the earlier summary.** The note-taker wrote it in its own `submit_initial` call, which is part of its context; the field description says to update it.
4. **The first real run found a gap in the prompts (developer decision: harden and re-run).** The note-taker answered the agent's "write everything down" request with text and no tool call (the log: `note_taker_reported`, no `tool_call`). The agent read that text out as the summary and then ran a follow-up round on its own: the announcement, a follow-up of its own and the closing check. Only its second hand-over reached `submit_initial`, so the real summary was read a second time. The stored result was correct and the test passed, but the founder heard two summaries. The implementation plan saw the same note-taker failure once before (commit 6, decision 7). The fix, in the context system only:
   - `voice_agent.flow`: writing down has worked only when its result arrives in the backend's form (first the summary message, after the round the message that everything is written down). Anything else means nothing was written down: the agent never reads it out or acts on it, and hands over once more. Without the retry the agent would wait forever, because the note-taker's turn has ended.
   - `voice_agent.delegation`: that retry is one more trigger, and the round's heading says it starts only after the summary.
   - `note_taker.procedure`: a request to write everything down is always the submit tool, never text, and it never writes answers, a summary or follow-up questions of its own, with the reason (the agent would take them for written down).
   - The re-run followed every rule: a follow-up right away on traction after the pitch, one hand-over with `submit_initial`, the summary read once, no follow-ups selected (traction was already followed up), and the goodbye straight after the summary. Reply times: median 1.0 s, max 1.6 s (first run: median 0.8 s, max 1.0 s).
5. **The high-level plan's Flow step 3** describes the safeguard in one sentence.

**Known limit (unchanged):** that the agent and the note-taker follow these rules stays prompt-only by nature. The voice test checks the stored result on every `--complete` run, and a person's conversation checks what it sounds like (section 5).

### Change 5: README note on reply times
- In the developer part's "Reply times" bullet, add that every switch from the founder to the agent counts, also a short backchannel such as „Mhm".

**Status: completed on 2026-11-17.** `./scripts/test.sh` passes. No decisions were needed: the measurement stays as it is (decision 7), so only the README changes, and the high-level plan's latency section stays untouched.

### Change 6: Demo guide
- **`_docs/demo-guide.md`** (English, about one page, for the developer only). Written after every other change, including changes 7 to 12, so it matches the final state.
- **The demo path:**
  1. the team login;
  2. creating an access code;
  3. the founder signup, the tutorial and the device check;
  4. a conversation that shows a follow-up right away, the tool tags, the „Rückfragen" section and the mute button;
  5. the team detail, Refresh and the settings, including a catalog edit.
- **Talking points:**
  - the architecture in three sentences (WebRTC, sideband, three AI roles);
  - the key decisions: the backend owns the session, the context system, one rule for team values, follow-ups right away and in a review round, why the startup lookup is started by the backend;
  - the compromises (the README's trade-offs);
  - the decisions of section 2;
  - the known limits:
    - prompt-only behaviours;
    - stray characters in OpenAI's transcript;
    - backchannels in the reply times;
    - remarks in the answers;
    - `--reload` ends running conversations;
    - OpenAI's session limit is undocumented: it closes with `expired`, which the app shows as „Die Verbindung wurde unterbrochen.", and our own limit is 30 minutes.

### Change 7: One scroll model, with the header always in view
**Why:** today the whole window scrolls. On long pages the header with the team's navigation scrolls away. The chat's auto-scroll uses `scrollIntoView`, which also scrolls the window, so the page jumps while someone reads; that is the root cause of the broken auto-scroll. One rule fixes both.

**The rule:**
- The window itself never scrolls. The shell is exactly as high as the screen (`100dvh`): the header stays at the top, and `main` below it is the page's one scroll area.
- **Fill pages** are pages whose main content is one list or the chat: „Gespräche" and „Zugangscodes" (team), „Meine Gespräche" and the founder's conversation.
  - The page is exactly as high as `main`, and its fixed parts stay in view: the title row, the filters, the forms, the conversation's bar and the outcome message.
  - Only the list (or the messages) scrolls, inside its card. The card grows with its content and starts to scroll once it reaches the bottom of the screen; it never stretches into an empty box.
  - On a screen too low for that (a phone in landscape), the scrolling part keeps a minimum height of about 10rem, and `main` scrolls as a whole.
- **Every other page** (settings, tutorial, device check, login, signup, Team detail) scrolls inside `main` as a whole; the header still stays.

**CSS (`frontend/src/styles/base.css`, the one home of these classes):**
- **The shell:** `.shell` gets `height: 100dvh` as a flex column, `.header` gets `flex: none`, and `main` gets `flex: 1; min-height: 0; overflow-y: auto`. `main` spans the full width, so its scrollbar sits at the screen's edge; `.content` inside stays centered.
- **`.page-fill`:** a flex column as high as `main`. The card that holds the list is a flex column that may shrink (`min-height: 0`).
- **`.scroll-pane`:** `overflow: auto; overscroll-behavior: contain`, so scrolling a pane never scrolls the page behind it.
  - In a fill page it takes the remaining height.
  - Elsewhere, `.scroll-pane-limited` caps it at about `min(60dvh, 40rem)`.
- **Tables in a pane:** a sticky header row (`thead th { position: sticky; top: 0; background: var(--color-surface) }`). `.table-wrap` becomes the pane.
- **More on the screen:**
  - `.content` top padding 2rem → 1.25rem, and 0.75rem on phones;
  - `h1` 1.6rem → 1.35rem;
  - card spacing 1.25rem → 1rem.
- **Width:** the team area gets a wider page (`.content-wide`, about 1100px, set by `PageShell` for the team role). It replaces the `.content:has(.detail-layout)` rule; the founder area stays at 760px.
- **One title row, `.page-head`:** the back link, the `h1` and either a short detail (the date) or the page's action button (right), on one line that wraps on narrow screens. It replaces `.page-actions` and the back link's own margin. Pages without a back link keep a plain `h1`.

**Pages:**
- **„Gespräche":** `h1`, then one card with the filters (in view) and the table in the pane.
- **„Zugangscodes":** `h1`, the „Code erstellen" card (in view, including the code box), then the list card with the table in the pane.
- **„Meine Gespräche":** `h1`, the „Neues Gespräch" card, then the list in the pane.
- **The founder's conversation:** see change 8.
- **The Team detail:** see change 9.

**Docs:**
- the header comments of `PageShell`, `ConversationView` and `base.css`;
- high-level plan section 8, one sentence: the header stays, and lists and the chat scroll inside their card.

**Status: completed on 2026-11-17.** `./scripts/test.sh` passes. A throwaway Playwright check in Chrome (an isolated compose project with test secrets and its own database, removed afterwards; nothing of it is committed) seeded 25 founders, 30 codes and a founder with 15 conversations, then measured every page at desktop width (1280×800), phone width (375×667) and a phone in landscape (667×375). The window never scrolls, nothing scrolls horizontally, the header stays at the top, and the list pages scroll only inside their card, below a sticky table header.

**Decision log**
1. **One invisible `.fill-area` around the list card (deviation).** The plan's "the card may shrink (`min-height: 0`)" squeezed the code list to 0 px on a phone right after creating a code, because the code box makes the fixed parts taller than the screen. Plain CSS cannot give a card "its content height, at most the space left, at least about 10rem" in one box (`calc-size()` could, but only Chrome has it). So the fill page ends with an invisible area that takes the height left and is at least 18rem high, and the card inside keeps its content height up to 100% of that area:
   - a short list never stretches into an empty box (the rest of the area is page background);
   - a long list scrolls inside the card;
   - on a screen too low for both (a phone in landscape, or a phone with the code box), `main` scrolls as a whole and the list keeps about 9 to 16rem.
   This one rule also covers the plan's "phone in landscape" case, so no height media query is needed. The measured panes: 15.7rem for the code list on the phone with the code box, 9.3rem for „Gespräche" in landscape (its filters sit in the card).
2. **No `.scroll-pane-limited` class.** A `.scroll-pane` is capped at `min(60dvh, 40rem)` everywhere, and inside a `.card-fill` it takes the height left instead. The context decides, so the one conversation view needs no extra prop when the Team detail shows it in a limited pane (change 9).
3. **The bottom padding of `.content` shrank too** (4rem to 1.25rem, 3rem to 0.75rem on phones, like the top), so a fill page's card ends just above the screen's edge instead of 4rem higher.
4. **One title row everywhere.** The settings page's `.page-title` (a title with an info button) became `.page-head` as well, so there is one class for a page's title row. The Team detail's back link, title and „Aktualisieren", and the founder's back link and title (with the date of a stored conversation), moved into `.page-head` in this commit, because it removes `.page-actions` and the back link's own margin. Change 8 completes the founder's row (the call).
5. **The sticky table header draws its line as a shadow**, because the border of a sticky cell scrolls away in a table with collapsed borders.

### Change 8: The founder's conversation page, compact and always complete on the screen
- **One title row** (`frontend/src/pages/founder/ConversationPage.tsx`):
  - before the call: `← Meine Gespräche`, then „So läuft das Gespräch" (tutorial) or „Gerätetest" (device check);
  - a stored conversation: `← Meine Gespräche`, then „Ihr Gespräch", then its date (muted);
  - during the call: „Ihr Gespräch" and the date, without the back link, because the call offers no way out but STOPP, as today.
  On phone width the row wraps and nothing else changes.
- **The conversation is a fill page:** the conversation card takes the rest of the screen.
  - At the top, the bar: the status pill, and STOPP or „Aktualisieren".
  - In the middle, the messages, the only part that scrolls.
  - Below them, the outcome message.
  The bar and the outcome are always visible, so the bar no longer needs `position: sticky`.
- **Auto-scroll** (in `frontend/src/conversation/ConversationView.tsx`, so it is the same everywhere): the messages pane scrolls, never the window.
  - When new text arrives and the pane was at its bottom (within about 3rem), it scrolls to the bottom (`pane.scrollTop = pane.scrollHeight`, in a layout effect).
  - If the reader scrolled up to reread, it stays where it is.
  - A stored conversation opens at its beginning.
  - This one rule replaces `scrollIntoView` and also serves the team's „Aktualisieren".

**Status: completed on 2026-11-17.** `./scripts/test.sh` passes. The throwaway Chrome check (isolated compose project, as in change 7) opened a stored conversation of 44 messages and a running one of 30:
- at desktop and phone width the title row, the bar, the messages and the outcome fit the screen, and only the messages scroll;
- a stored conversation opens at its beginning;
- with „Aktualisieren", new messages are followed while the reader is at the bottom, and a reader who scrolled up stays where they are;
- the window never moves.

**Decision log**
1. **The view renders into the card its page gives it.** `ConversationView` returns its three parts (the bar, the messages pane, the outcome) instead of its own card. The founder's page wraps them in the fill card; the Team area wraps them in its card (change 9: the collapsible „Gesprächsverlauf"). So there is never a card inside a card, and the messages pane is "fill" or "capped" by its place alone (change 7, decision 2). Until change 9, the Team detail puts it in a plain card.
2. **One view element before and after the call.** The page renders the live and the stored view at the same place, so React keeps the element, and the reader stays where they were when the call ends and the outcome appears.
3. **The date during the call is when START was pressed** (`useCall` keeps it as `startedAt`). The page's stored conversation still says Ready until the call ends; afterwards the stored start time, seconds apart, replaces it.
4. **The pane also follows when the outcome appears.** The outcome takes height from the pane, so the auto-scroll rule runs on it too, and a reader at the bottom keeps the last message in view.

**Known limit:** on a phone in landscape after the call, the outcome message needs its room, so the messages pane keeps about 4.5rem and `main` scrolls as a whole. During the call, without the outcome, the pane keeps about 12rem.

### Change 9: Gesprächsdetails: the facts first, then the questionnaire, then the conversation
In `frontend/src/pages/team/ConversationDetailPage.tsx` and `ConversationDetailCards.tsx`, top to bottom:
1. **Title row:** `← Zurück zu den Gesprächen`, „Gesprächsdetails", and „Aktualisieren" on the right.
2. **Facts:** three compact cards side by side on wide screens (`grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr))`), one below the other on narrow ones, most relevant first:
   - „Gespräch": the state badge, the reason if unfinished, created, started, ended;
   - „Gründer": name, email, company;
   - „Verwendete Einstellungen".
3. **„Fragebogen":** one full-width card.
   - At its top, always visible: the „Nicht geprüft" note and the summary.
   - Below them, the questions with their answers and follow-ups in a limited scroll pane.
4. **„Gesprächsverlauf":** one collapsible card (`<details>`), closed when the page opens.
   - Its summary line is always visible: a chevron, „Gesprächsverlauf", the state badge (the existing labels and colours: Läuft, Abgeschlossen, Nicht abgeschlossen, Bereit) and the number of messages.
   - Opened, it shows the one `ConversationView`: the messages in a limited scroll pane, and the outcome message below them.
   - „Aktualisieren" keeps it open, because React keeps the element.
- Remove the two-column `.detail-layout` and `.detail-cards` styles, and update the header comments of both files.
- The README's team part („Gespräche prüfen") describes the new order in one sentence.

**Status: completed on 2026-11-17.** `./scripts/test.sh` passes. The throwaway Chrome check (isolated compose project) at desktop, phone and landscape width confirmed:
- the facts sit side by side on wide screens and one below the other on narrow ones;
- the questions scroll in their capped pane below the always visible summary;
- „Gesprächsverlauf" is closed when the page opens, opens with a click and stays open after „Aktualisieren";
- the window never scrolls, and nothing scrolls horizontally.

**Decision log**
1. **`TranscriptCard` joins the other cards** in `ConversationDetailCards.tsx`, so the page only arranges cards. It shows the one `ConversationView`, which renders into it (change 8, decision 1).
2. **A hidden pane is not measured.** While „Gesprächsverlauf" is closed, the view is rendered but has no size, and it would count as "at the bottom". So the auto-scroll skips a pane that is not visible (`checkVisibility()`), and an opened conversation starts at its beginning and never jumps to its end on „Aktualisieren".
3. **The three fact cards keep one height per row** (the grid's default stretch), so they line up.
4. **The message count says „1 Nachricht" or „n Nachrichten".**
5. **Two README lines that the change 1 commit left over-long** were re-wrapped together with the new sentence.

### Change 10: The header: brand and area together, and the mute button
- **Brand and area** (`frontend/src/layout/PageShell.tsx`): a new wrapper `.brand-block` (a flex column) holds two lines.
  - „Voice Agent for Investor Pitches": a link, or plain text during a call, as today.
  - Below it, when logged in, the area („Teambereich" or „Gründerbereich", from `ROLE_AREAS`) as a small pill: background `--color-primary`, text `--color-on-primary`, small font, rounded.
- **The header row:** the brand block, the team's navigation, and on the right the mute button (during a call), the user's name and „Abmelden" (not during a call). On phone width the navigation wraps onto its own line and the user's name is hidden; „Abmelden" stays.
- **Mute** (only during a call):
  - **`frontend/src/AppProvider.tsx`:** `muted` and `setMuted` next to `callActive`, the app-wide call state the header reads. Update its header comment.
  - **`PageShell`:** a toggle button with `aria-pressed`.
    - Unmuted: the `Mic` icon and „Stummschalten".
    - Muted: the `MicOff` icon and „Stumm", in `--color-warning` on `--color-warning-soft`, so it stands out.
  - **`frontend/src/call/useCall.ts`:** whenever `muted` changes during a call, it sets `enabled = !muted` on the microphone tracks the call sends.
    - A disabled track sends only silence, so OpenAI hears and transcribes nothing; the session and the connection stay as they are, so unmuting works at once.
    - When the call ends, the tracks are enabled again and `muted` resets, because the page reuses the microphone for a retry.
    - The call keeps the microphone stream in its `Connection` for this.
  - **The status pill:** while muted, it shows „Mikrofon stumm" (`MicOff` icon, warning colours) instead of „Hört zu", so a founder who talks and gets no answer sees why. A running tool and „Spricht" still come first.
  - The voice test never mutes, and „Hört zu" stays its signal to answer.
- **Docs:**
  - the README's team part („Was Gründer erleben") gets one sentence about „Stummschalten";
  - high-level plan section 8 gets the header and the mute button.

**Status: completed on 2026-11-17.** `./scripts/test.sh` passes (the Vitest test of the status order includes „Mikrofon stumm"). The throwaway Chrome check (isolated compose project) showed the header at desktop width (the name with the blue area pill, the navigation, the user's name and „Abmelden") and at phone width (the navigation on its own line, the name hidden, „Abmelden" kept), with no horizontal scrolling. The mute button needs a real call, so the real run after change 11 checks it (see there).

**Decision log**
1. **The user's name stays in the header during the call**, as before. "(not during a call)" refers to „Abmelden", which matches the existing rule that the header offers no links and no log out during a call.
2. **Every way out of a call restores the microphone.** The end of a call (`handleEnd`) and a failed START enable the tracks again, and `muted` resets in the same effect that clears `callActive`. So a retry after a failed start always begins with a live microphone and an unpressed button.
3. **The mute works as soon as the call exists** (from START on, while connecting too), because the button shows whenever `callActive` is set and the call applies `muted` to its connection's tracks.
4. **No new colours:** the pressed button (`.button-muted`) and the muted pill (`.status-muted`) use the warning tokens.

### Change 11: Tool tags and the „Rückfragen" section in the live chat
**One definition per tool.** It lives in `frontend/src/labels.ts`, the home of the German labels of the backend's values: `TOOL_LABELS: Record<ToolName, { running, done, tone }>`. It is typed with the generated `ToolName`, so a new tool fails the type check until it has an entry.

| Tool | Status pill while it runs | Tag in the chat | Tone (existing tokens) |
|---|---|---|---|
| `get_questionnaire` | „Liest die Fragen nach ..." | „Fragen nachgelesen" | reading: `--color-muted` on `--color-bg` |
| `web_search` | „Sucht im Internet ..." | „Im Internet gesucht" | search: `--color-primary` on `--color-primary-soft` |
| `submit_initial` | „Schreibt Ihre Antworten auf ..." | „Antworten aufgeschrieben" | writing: `--color-success` on `--color-success-soft` |
| `submit_follow_up` | „Schreibt Ihre Antworten auf ..." | „Rückfragen aufgeschrieben" | writing |

- One `.tone-reading`, `.tone-search` and `.tone-writing` class each in `base.css`, used by both the pill and the tag. No new colour tokens.
- „Schreibt Ihre Antworten auf ..." stays word for word, because the voice test waits for it. „Schlägt nach ..." becomes „Sucht im Internet ...".
- Every tool call now shows, including `get_questionnaire` (uniform). Founders see only that a tool runs, never what it does.

**State: one list of tool calls instead of one activity** (`frontend/src/conversation/status.ts`, pure and unit tested):
- `reduceToolCalls(calls, event, messageCount)`:
  - A nested `response.output_item.added` or `.done` whose item is a function call adds the call once, keyed by its `call_id`, with its tool, its delegation, `running: true` and its position `at`, the number of messages so far.
  - The next nested `response.created` of the same delegation marks that delegation's running calls as done (the same rule that ends the activity today).
- `displayStatus(calls, speaking, muted)`: the latest running call's tool (its running label and tone), else „Spricht", else „Mikrofon stumm" when muted (change 10), else „Hört zu". „Verbinde ..." and „Wird beendet ..." stay as they are.
- `Activity` and `TOOL_ACTIVITIES` disappear.
- `useCall` keeps the calls and passes them to the view.
- `ChannelEvent` gains the item's `call_id` and the session's tool names (for the separator below).

**The tags in the chat** (`ConversationView`, new optional prop `toolCalls`, live only):
- Each call is a small centered pill between the messages, at its position: right after the message that was last when the call started (that message may still grow).
- While running: a spinner and the running label. When done: a check and the done label.
- A tag is not a `.bubble`, because the voice test reads only `.bubble` elements as messages.

**The „Rückfragen" section:**
- **First, the check:** in one real call, confirm that the browser's data channel receives `session.updated` after the backend switches to the follow-up tools, and in which shape its tool names arrive. Do it with a temporary log in the browser that is never committed. If the event does not arrive, stop and ask the developer.
- **`startsFollowUpRound(event)`** (in `status.ts`, unit tested): true for a `session.updated` whose delegation tools include `submit_follow_up`. When it is true for the first time, `useCall` stores `followUpFrom`, the number of messages at that moment.
- **`ConversationView`** (new optional prop `followUpFrom`, live only):
  - The messages from that position on, and the tags placed there, sit in one section that starts with a divider line carrying a centered „Rückfragen" pill (`--color-primary` fill and `--color-on-primary` text, like the area pill).
  - The section's background is `--color-bg`, so the white agent bubbles and the blue founder bubbles stay readable. It has rounded corners and a little padding.
  - The round's announcement (change 3) is then the first message inside the section.
  - A conversation without follow-ups has no section.
- **After the call** (decision 11), the page shows the stored conversation as today: no tags and no section, also in past conversations and in the Team area.

**Docs:**
- the header comments of `status.ts`, `StatusPill.tsx`, `ConversationView.tsx`, `useCall.ts` and `labels.ts`;
- `AGENTS.md` section 6, conversation view: founders see that a tool runs, as a tag, never what it does;
- high-level plan section 5 (the data channel also carries `session.updated`) and section 8 (the status list, the tags, the section);
- high-level plan section 17: record the result of the check;
- the README's team part („Was Gründer erleben"), one sentence.

**Tests** (`frontend/src/conversation/status.test.ts`, rewritten):
- a call starts on `added` or `done` and is added only once;
- it ends with the next `response.created` of its delegation, and other delegations are ignored;
- its position is the message count;
- the display order: a running tool, then speaking, then muted, then listening;
- `startsFollowUpRound` is true only for a `session.updated` with `submit_follow_up`.

**Status: completed on 2026-11-17.** `./scripts/test.sh` passes (the rewritten `status.test.ts` covers every case above), and `./scripts/test.sh --complete` passes. The check of `session.updated` ran in that real run (the developer approved one run for it), with temporary instrumentation that was removed afterwards and never committed:
- a browser log of the `session.updated` event (prompt texts left out) and of a transcript delta's field names;
- a forced follow-up, only for the voice test's company, so the switch really happened (since change 1 a follow-up round is rare in the voice test);
- screenshots at every new status and turn;
- one press of „Stummschalten" at the first „Hört zu".

**Result of the check:**
- **The event arrives** on the browser's data channel. The tool names sit in `session.delegation.responses.tools[].name`, the shape `startsFollowUpRound` reads.
- **The live chat showed** the tags „Im Internet gesucht" (blue) and „Antworten aufgeschrieben" (green), the „Rückfragen" divider at the switch with the round's closing check inside the section, and after the call the stored conversation without tags.
- **The mute check (change 10):** „Hört zu", then „Mikrofon stumm" with `aria-pressed=true`, then „Hört zu" again, with the button in the warning colours.
- **The transcript deltas carry no turn ID** (`type`, `start_ms`, `end_ms`, `delta`, `event_id`).

**Decision log**
1. **The section's start holds two counts (deviation).** `followUpFrom` is `{messages, toolCalls}`, the numbers of messages and of tool calls at the switch, instead of the number of messages alone. The agent reads the summary in the same message as its hand-over, so `submit_initial`'s tag sits at the same message count as the switch. With the message count alone, „Antworten aufgeschrieben" would fall into the „Rückfragen" section; with the call count it stays above the divider (seen in the real run).
2. **One live reducer in `useCall`** (`reduceChat`) feeds the messages (`appendDelta`), the tool calls (`reduceToolCalls`) and the round's start (`startsFollowUpRound`) from each event. It only glues the three tested pure functions, so it stays private to `useCall`.
3. **The status is the running tool's name.** `CallStatus` is the call's own states (`CallState`) or a `ToolName`, and `StatusPill` takes the label, the icon (one per tone) and the colour from `TOOL_LABELS`, so each tool is defined once in `labels.ts`.
4. **One blue label class.** The header's area pill and the section's „Rückfragen" pill share `.label-pill` (renamed from `.area-pill`).
5. **A tag keeps its place when its message has no words yet**, so a call that starts while the agent's next message is still only whitespace is not lost.

**Known limit:** the announcement opens the section only when the founder speaks between the summary and the announcement. One message is a run of deltas from one speaker, and the deltas carry no turn ID. So when the agent goes straight from the summary into the announcement and the first follow-up, all three are one message above the divider, and the section starts with the founder's first answer (seen in the real run).

**Found in the same run:** the note-taker again answered the agent's "write everything down" with text and no tool call (as in the first run after change 4), and the agent read that text out. The developer decided on a backend guard and on naming the tools in the hand-over; see "Additional fix: the note-taker guard" below.

### Additional fix: the note-taker guard (developer decision, 2026-11-17)
**Why:** in 2 of the 3 real runs after change 4, the note-taker answered the voice agent's "write everything down" with text and no tool call. Its procedure says that every request is done with a tool call first. The voice agent took that text for the result: it read out a summary nothing was written down for, and ran a closing check of its own. Only its next hand-over reached `submit_initial`. The stored result was correct every time, but the founder heard two summaries. The prompt hardening of change 4 did not hold. OpenAI's API offers no per-response `tool_choice` (only a session-wide one, which would also force a tool call on the note-taker's report) and no command to cancel the note-taker's answer, so the text cannot be stopped before the agent hears it. The developer decided on a backend guard with explicit instructions for the note-taker, and on naming the tools in the hand-over.

**What it does:**
- **The sideband detects the broken procedure.** It notes every delegation in which the note-taker called a tool (`LiveCall.delegations_with_tools`). A response that completes a delegation without any tool call is a request answered with text alone.
- **`tools.remind_to_use_tools` recovers the flow:**
  1. a commentary to the voice agent (`messages.result_without_tool`): nothing was written down or looked up yet, so do not read that text out or act on it, and wait for the real result;
  2. a developer message to the note-taker (`messages.tool_required`) with explicit instructions: which tool each request needs (`submit_initial`, after the follow-up questions `submit_follow_up`, `web_search`, `get_questionnaire`), and never answers, a summary or follow-up questions in its text;
  3. a `response.create`, so it tries again.
  It sends at most `config.TOOL_REMINDERS_PER_CALL` (3) reminders per call, so a note-taker that keeps answering with text can never start an endless loop.
- **The hand-over names the tool.** The voice agent's delegation policy lists the tools by name and says which one each hand-over needs (only in the request, never aloud), so the note-taker gets an explicit request.

**Tests:**
- `test_sideband.py`: a request answered with text alone gets the warning, the reminder (with the agent's name) and a new response; a request answered with a tool gets none; the reminders stop at the configured limit.
- The fake note-taker now answers a `response.create` with its report only after a tool's output, like the real one. Before, it also answered the opening's startup lookup with a report without a tool call, which the guard would have taken for a broken procedure.
- `e2e/clips.py`: the first real run for this fix failed before the conversation. The founder's audio model answered the reply-like opening line instead of reading it, and the clip check stopped the run on purpose. Developer decision: each clip gets up to 3 attempts, and the check stays.

**The first real run with the guard (developer decision: diagnose).** The guard's commentary worked: the voice agent waited instead of reading the note-taker's text out. But the note-taker answered all three reminders with text again, and only the voice agent's own new hand-over reached `submit_initial`, after about 25 s. One more real run with a temporary log of the note-taker's texts (only in the app's own database, removed afterwards, never committed) showed two root causes in its texts:
1. **It judged completeness itself.** In the follow-up round the agent handed over too early. Instead of calling `submit_follow_up`, the note-taker answered "the funding follow-up is still open, ask it now". That is useful guidance, but it is the job of the tool's empty check. The tool texts invited it ("once every question has an answer"). When the guard then forced the tool call, the note-taker filled the open field with "not answered", and the round ended before the founder was asked.
2. **It wrote scripts for the voice agent.** After `submit_initial` its report repeated the whole summary, the announcement and the first follow-up as words to say. The summary already reaches the agent as the backend's commentary, so that was a second source of double summaries; and because the script named only the first follow-up, the agent invented the second.

**The targeted fix (context system only):**
- The submit tools' descriptions and field templates: call the tool whenever asked to write everything down; leave an unanswered question's field empty; the tool checks itself what is missing and names it.
- The note-taker's procedure: never decide whether something is missing or whether the agent asked too early, and never fill a field with something the founder did not say (also in `answers`).
- Its role and reporting: report what a tool returned as information, never as a script; never repeat the summary; pass on all follow-up questions in order, and the missing questions a submit tool names.
- The guard's reminder says the same, so a forced tool call can no longer fill gaps.

**Verified (2026-11-17):** `./scripts/test.sh` passes (109 backend tests, 5 real ones skipped), and the real run passes. In it both hand-overs reached their tool directly (no reminder was needed), and the report after `submit_initial` passed on only "everything is written down, no follow-ups, say goodbye", so the summary was read once.

**Known limits seen in these runs (prompt-only by nature):**
- In one run the voice agent asked every question again after the founder's full pitch, against its rule to skip answered questions; the runs before followed it.
- The note-taker still adds a greeting to the startup lookup's background, because it sees the session's greeting instruction. That is harmless: the agent greets once.
- The guard is the safety net for the remaining text-only answers: the agent waits instead of reading them out, and the note-taker gets explicit instructions.

### Change 12: Terra replaces Sol
- **`backend/app/config.py`:**
  - `MODELS` offers `"gpt-6-luna": "GPT-6 Luna (schnell)"` and `"gpt-6.1-terra": "GPT-6.1 Terra (gründlicher)"`. OpenAI describes Terra as "a fast, efficient model", priced between Luna and Sol, accepting all four offered thinking levels, with function calling and structured outputs. The default stays Luna, OpenAI's recommended delegation model.
  - **The comment, made true:** a model or other option can only be removed while no stored conversation and no team setting uses it, because their stored copies are checked against these options when they are read. Checked on 2026-11-17: every stored conversation and the team's settings use Luna.
  - Drop the sentence about the spike probing these two models.
- **Types:** the generated frontend types change (`ModelName`); regenerate and commit them.
- **Tests:**
  - `backend/tests/test_team_values.py` and `test_reviewer.py` use `gpt-6.1-terra` instead of `gpt-6.1-sol`;
  - the real reviewer test (`backend/tests/test_real_services.py`) runs once with each offered model, which confirms the strict structured output with Terra.
- **Check:** OpenAI's Live delegation docs do not name Terra, so have one real conversation with „Protokollant: Modell" set to Terra in „Einstellungen", then set it back.
- **Docs:** high-level plan section 9 (the offered models). The README names no model, and `drafts/` stays as the record of the spike.

**Status: completed on 2026-11-17.** `./scripts/test.sh` passes, and the regenerated frontend types (`ModelName`) are committed. Before Sol was removed, the app's database was checked: all 15 stored conversations and the team's settings use Luna, so nothing stored refers to Sol.

**Decision log**
1. **No real Terra conversation (developer decision).** The developer decided not to test with the model. The real run with Terra as the note-taker and the real reviewer tests with both models (now parametrized over `config.MODELS`) stay open, see the operator to-dos.
2. **The config comment states the true rule**, without a date: an option can only be removed while no stored conversation and no team setting uses it. The high-level plan's section 9 says the same.

**Operator to-do:** run `./scripts/test.sh --complete` once. It runs the real reviewer tests with Luna and Terra, which confirms Terra's strict structured output. Optionally also have one conversation with „Protokollant: Modell" set to Terra in „Einstellungen", then set it back.

### Docs (pass 2, AGENTS.md section 2)
- **README:**
  - developer part, "Three AI roles" and "Two phases and four tools": the agent follows up once right away; the reviewer reads the answers and the transcript; phase 2 happens only when it selects follow-ups; `submit_follow_up` also writes the final summary;
  - team part, „Was Gründer erleben": the agent asks once more when an answer is unclear;
  - team part, „Gespräche prüfen": follow-ups during the questions are in the transcript; the summary is the final one;
  - the reply time note (change 5).
- **High-level plan:**
  - section 1 (Goal);
  - section 3 (the rows for following up, the common thread and the summary);
  - section 7 (the "Anything else?" paragraph, the Tools table, Flow steps 1 to 8, the FAQ list, Common thread);
  - section 8 (the tutorial slides);
  - section 13 (the voice test's checks);
  - section 15 (F2 and F3);
  - section 17 (the session limit: OpenAI's docs name no number, only the close reason `expired`; checked on 2026-11-17).
- **Docstrings** of `reviewer.py`, `tools.py`, `conversations.py`, the e2e test, and every touched file whose sentence became false.
- **Search for stale claims,** including wrapped lines:
  - "closing round", "Anything else", "always select";
  - "no second summary", "summary written at the first submit";
  - "follow-ups at the end", „Rückfragen kommen am Ende";
  - "never ask follow-up", "at most one follow-up".

### Tests
- **`backend/tests/test_reviewer.py`:** the request's input carries the questionnaire and the transcript, and the existing guarantees stay (only known questions, the first follow-up per question, retries).
- **`backend/tests/test_tools.py`:**
  - `submit_initial` sends the saved transcript to the reviewer: push transcript events first, then assert they are in the review request.
  - `submit_follow_up` refuses an empty or too long summary and stores nothing.
  - On success it replaces the stored summary.
  - The `follow_up_round` helper gains `summary`.
- **`backend/tests/test_context.py`:** the new entry renders, and `follow_ups` still renders the list.
- **`backend/tests/test_real_services.py`** (real reviewer, `--complete` only):
  - Drop the assertion that the closing round is always selected; the reviewer no longer selects it.
  - Pass a transcript to `review`.
  - Complete answers may now get no follow-up at all.
  - Add one prepared case: a vague traction answer whose transcript shows the agent already followed up on it gets no traction follow-up.
- **`e2e/test_voice_conversation.py`:**
  - Drop the "the review selected no follow-up" assertion, because a follow-up round is now optional.
  - Keep: Completed, every answer, the summary, every selected follow-up answered, and the fact only the founder said.
  - Print whether a follow-up round happened.
  - The founder script stays (the fallback answers any follow-up). Update the docstring.
- **Run order:** `./scripts/test.sh`, then `./scripts/test.sh --complete`, because the prompts and the tools changed. `--complete` uses the real APIs, costs a little, and needs a running `start.sh` stopped first.

---

## 4. Unchanged on Purpose
- **Stage, the note-taker's remarks, the latency measurement and STOPP:** decision 7.
- **„Tonalität" and „System-Prompt" as settings:** the requirements ask for at least 2 settings, and there are 5. Each further setting would have to earn its place.
- **Per-message timestamps in the transcript:** the requirements ask for past conversations with a timestamp, which they have.

---

## 5. Done When
- `./scripts/test.sh` and `./scripts/test.sh --complete` pass, and the frontend types are regenerated and committed.
- **A conversation in Chrome by a person** (it also judges how natural the voice sounds) shows:
  - a vague answer gets exactly one follow-up right away;
  - „Ich weiß es nicht" gets one ask for an estimate;
  - a refusal is accepted;
  - with nothing left to ask, the summary is followed directly by the goodbye;
  - otherwise the announcement, the follow-ups and the closing check follow, and the success message shows the final summary.
- The README, the high-level plan and every touched docstring describe the new behaviour, and `_docs/demo-guide.md` exists.
- **The interface, checked in Chrome at desktop width and at phone width (about 375px):**
  - the header with the blue area pill stays in view on every page;
  - the lists and the chat scroll inside their card, with no horizontal scrolling;
  - the chat's bar and outcome stay visible, and auto-scroll follows new messages without moving the page;
  - the Team detail shows the facts, then the questionnaire, then the collapsed „Gesprächsverlauf" with its badge;
  - during a call, the tool tags appear with their colours, the „Rückfragen" section starts at the follow-up round, and „Stummschalten" silences the microphone and shows „Mikrofon stumm".
- One real conversation runs with Terra as the note-taker.
