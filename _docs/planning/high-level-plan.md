# Voice Agent for Investor Pitches: High-Level Plan

This plan describes what we build for the requirements (`_docs/_requirements.md`), how it behaves for the people who use it, and how it works on a high level. It is based on the requirements and on a lot of decisions and back and forth, and it contains every decision made along the way.

---

## 1. Goal

- A web-based voice agent that conducts the first conversation (Erstgespräch) between an investor and a startup founder.
- The founder talks to the agent in the browser. The agent looks up the startup on the web, asks the questions of a question catalog one at a time, follows up once right away when an answer stays vague, answers the founder's questions from a FAQ or with a quick web search, and writes down the founder's answers in the founder's own words.
- The agent summarizes the answers, a reviewer AI checks them against the conversation, the agent asks the follow-ups that are still needed in a short round (none if nothing is missing; at most one follow-up per question in the whole conversation), and the result is stored in a structured way.
- The investment team invites founders with access codes, reviews all conversations and adjusts the agent in a separate Team area.
- It is a local MVP: simple, well architected and easy to explain, but built in a professional way so it can be turned into a real tool effortlessly.

---

## 2. Guidelines
The real guidelines are in the AGENTS.md file. These are just summaries. Read the AGENTS.md file.

- Simplicity: the requirements are the core. Everything on top of them must earn its place.
- Uniformity: similar things work the same way everywhere (one login, one error type, one API client, one rule for every value the team can edit).
- Single source of truth: nothing is defined twice or mapped manually (see section 10).
- Performance: low response latency in the conversation, and the server never waits on slow work without a timeout.
- Comments in the code should be wisely phrased: they explain the why and the how, not the obvious things. They should be used to provide context that is not clear by reading the code.

---

## 3. Requirements Coverage

| Requirement | How it is met |
|---|---|
| The founder talks in the browser, the agent answers by voice | OpenAI Live API, connected directly from the browser |
| Low latency (ideally under 1 to 2 seconds) | Full-duplex voice model, audio goes straight between browser and OpenAI, every reply is measured |
| Natural speech output | `gpt-live-1` voices, one matching voice per language |
| Start/stop by button | One START/STOP button: START after the device check, STOP at any time (with confirmation) |
| The agent asks instead of only answering, follows up once if vague | The agent leads through the catalog, always returns to it and follows up once right away when an answer stays vague or incomplete; the reviewer reads the answers and the transcript and selects follow-ups at the end only for what is still missing, never for a question the agent already followed up on |
| Common thread, no repetition | The agent keeps the whole conversation in mind, skips questions already answered in full and never repeats itself unless the founder asks; the reviewer never asks about a question the agent already followed up on |
| Transcript visible (who said what) | Live transcript in chat style in the conversation view |
| Past conversations with timestamps | "My conversations" for founders, a searchable conversation list for the team |
| At least 2 settings | Language, agent name, question catalog, model, thinking level |
| Summarize at the end and store the result in a structured way | When the agent hands the writing down over, the backend writes every answer and the summary from the saved transcript with one schema-enforced call; the summary is read aloud while the answers are checked; a follow-up round writes the final summary, which replaces it without being read aloud, so the success message and the Team area always show the final facts; the questionnaire is stored per conversation |
| Result fields: startup, sector, stage, team, traction, funding need, next step | Startup name from the signup, all others are catalog questions |
| Bonus: tool calling | `web_search` (which also looks up the named startup), `submit_initial` and `submit_follow_up` (their call has the backend store the result in a structured way) |
| Bonus: streaming | Voice and transcript stream live |
| Bonus: good UI/UX | Welcome letter, short tutorial, device check, clear status indicators, an outcome message below the conversation |

---

## 4. Tech Stack

- Voice: OpenAI Live API with `gpt-live-1` (full duplex: it listens while it talks).
- Note-taker: a text model attached to the same Live session through OpenAI's "Responses delegation". It is the only AI that calls our tools, and it only triggers them.
- Writing down and review: two OpenAI Responses API calls with a strict structured output, made by our backend.
- Web search: Serper (Google search results through an API).
- Frontend: React with TypeScript.
- Backend: FastAPI (Python).
- Types: Pydantic for uniform, single-source-of-truth types across frontend and backend, exported to the frontend as generated TypeScript types.
- Database: PostgreSQL with SQLAlchemy.
- Environment: Docker Compose is the only environment. The app, the tests and all tools run in containers. No venv.

---

## 5. How It Works

```
  Browser (React)                              OpenAI
 +------------------+   audio + events    +------------------------------+
 |  Founder area    |<----- WebRTC ------>|  Live session                |
 |  Team area       |                     |   voice agent (gpt-live-1)   |
 +--------+---------+                     |   note-taker (delegation)    |
          | HTTP (one API client)         +--------------+---------------+
 +--------v---------+     sideband: tools, transcript,   |
 |  Backend         |<------------- session control -----+
 |  (FastAPI)       |------> Writing down, review (OpenAI Responses API)
 |                  |------> Serper (web search)
 +--------+---------+
 +--------v---------+
 |  PostgreSQL      |
 +------------------+
```

- The browser talks to OpenAI directly over WebRTC, the technology video calls use. This is the shortest possible audio path, and it brings the browser's built-in echo cancellation and noise suppression: laptop speakers work, headphones are optional.
- The same connection carries events: the transcript text, what the note-taker is doing, and the session's updates (`session.updated`, which marks the switch to the follow-up round's tools). Whether the agent is speaking is measured from its audio in the browser. The founder's conversation view is built live from these, so our server needs no streaming to the browser.
- Our backend controls every session. It creates the session (the OpenAI key never reaches the browser), sets the instructions and tools, and stays connected to it through a second connection, the "sideband". Through the sideband it runs the tools, tells the voice agent their results and every next step, saves the transcript and ends the session.
- Everything else is plain request and response between the browser and the backend. No streaming and no polling. The team, and a founder reopening a past conversation, see the same conversation view filled from the database, with a Refresh button for running conversations.

---

## 6. People, Login and Access

### Roles
- Founder (applicant): signs up once and can have several conversations, each unlocked by its own access code.
- Team member: logs into the Team area, invites founders, reviews conversations and changes the settings.

### Team members
- The team has one shared login: an email and a password that the developer writes into the secrets file. It exists for basic authorization and nothing else.
- Nothing is stored for the team: no profiles, no roles, no ownership. Everyone on the team uses the same login, and all conversations, access codes and settings are shared.

### Login
- One login for both roles: email plus password, then a session cookie that carries the role. The team's email logs into the Team area; every other email belongs to a founder.
- Founders' passwords are stored only as hashes in the database. The team's password sits in plain text in the secrets file, next to the other secrets.
- Founder signup asks for: name, email (unique), password and company name. Name and company name go into the agent's instructions.

### Access codes
- A team member creates a code for one founder's email. The code is shown once, to copy and send.
- A code is valid for 24 hours, can be used once, and only by the account with that email.
- One code unlocks exactly one conversation. It is used either at signup (which creates the account and the first conversation together) or later under "New conversation".
- Both ways use the same single step: it checks the code and marks it as used at once, then creates the conversation. A rejected code creates nothing. Codes are stored only as hashes, like passwords.
- The Team area lists every code with its email, its creation time and its state: unused, used or expired.

### Conversation states
- Ready: unlocked by a code, not started yet. It can be started at any time, also after a failed start. A start has failed when the session could not be opened or the connection broke before the founder said anything; the conversation then goes back to Ready.
- In progress: the voice session is running.
- Completed: the answers were written down: the follow-up answers, or the first answers if the review selected no follow-ups, or what the founder said before asking to stop (the early end, section 7). These are the only ways to reach Completed.
- Unfinished: the conversation started but ended in any other way (STOP button, lost connection, closed tab, session time limit). This is final: another try needs a new code. Everything said up to that point is kept.

---

## 7. The Conversation

### Three AI roles
- Voice agent (`gpt-live-1`): talks and listens. It greets, asks the questions (following up once right away on a vague answer) and answers the founder's questions. After the questions it follows the backend's messages: it reads the summary aloud, runs the follow-up round and says goodbye when the backend tells it to. It cannot call tools itself: when work is needed, it hands the work to the note-taker. While a search runs it keeps talking; while the answers are written down it waits for the result, because there is nothing to say yet that it would not have to invent. It can hand work over only in reply to something the founder said, so the startup lookup at the start is started by the backend (see "Startup lookup and founders' questions").
- Note-taker (text model from the settings): takes over the handed work and calls our tools (looking things up, writing everything down). It only triggers them and then replies as the tool's output says. After writing down it replies only "OK": the backend tells the voice agent the result itself, so the note-taker's own words can never become a script, a summary or a question the agent reads out. After a search it passes the results on as plain information, because its reply always reaches the voice agent as the hand-over's result (see "Startup lookup and founders' questions"). Its model and thinking level also write the answers down: one structured call by our backend inside the submit tools, which writes every answer in the founder's own words from the saved transcript, plus the summary and whether the founder wants to stop.
- Reviewer (text model from the settings): called by our backend inside `submit_initial`. It reads all answers against their questions, against each other and against the transcript, and selects follow-ups only where something is still missing, never for a question the agent already followed up on.

### Question catalog and questionnaire
- The question catalog is the current list of questions. Every question has a unique number (its ID), a short topic, the question as the agent asks it, and a context: a short explanation of what the question is about and what a complete answer covers. The agent uses the context to explain or rephrase a question and to notice a partly answered one; the reviewer uses it to judge whether an answer is complete.
- Default catalog:
  1. **Sector:** "In which sector or industry is your startup active?"
     Context: the market category, for example health tech, B2B software or climate tech. One or two words are enough; if the startup spans several sectors, which one comes first.
  2. **Team:** "Who is on your founding team, and what roles and experience do you bring?"
     Context: the number of founders and employees, who is responsible for what, and the experience that makes this team able to build the company.
  3. **Product:** "What problem do you solve, and how does your product solve it?"
     Context: the customer's problem, the solution in plain words, and what makes it better than the way the problem is solved today.
  4. **Stage of development:** "How far along is your product today?"
     Context: idea, prototype, MVP, pilot or live product, plus what is already built and what is still missing.
  5. **Traction:** "What traction do you have so far?"
     Context: measurable progress such as users, paying customers, revenue, growth, pilots or letters of intent, with numbers where possible. "None yet" is a valid answer.
  6. **Target market:** "Who are your target customers, and how big is your market?"
     Context: the customer segment, the region the startup starts in, and the market size (for example the number of potential customers or the market volume).
  7. **Competition and positioning:** "Who are your main competitors, and how do you stand out from them?"
     Context: direct competitors and the alternatives customers use today, and the startup's advantage over them.
  8. **Funding need:** "How much funding do you need, why, and what will you use it for?"
     Context: the amount, the reason for raising now, and the main uses of the money (for example hiring, product development or sales).
  9. **Planned round:** "What financing round are you planning, and when?"
     Context: the round type (pre-seed, seed, Series A, ...) and the planned timing.
  10. **Next step:** "What is your startup's next big milestone?"
      Context: the next concrete goal the startup is working towards (for example a launch, the first paying customers or a key hire) and when it should be reached.
  11. **Anything else:** "Is there anything else you'd like to tell us?"
      Context: room for anything important the other questions did not cover.
- The startup name is not asked. It comes from the founder's signup.
- When a conversation starts, it gets its own copy of the catalog: the questionnaire. Per question, it holds the answer, the follow-up question with its explanation (if one was selected) and the follow-up answer: what the founder said about this question in the follow-up round, whether it answers the selected follow-up or is something the founder added or corrected on their own. It also holds the summary: written at the first submit and replaced by the final one when the follow-up round is written down. Later catalog edits never change a running or past conversation.
- "Anything else?" is a normal catalog question: the team can edit, move or remove it like any other, and no code or prompt treats it specially. The reviewer may select a follow-up for it like for any other question. It never sounds like the follow-up round's own closing check (Flow step 6), which exists only when there is a follow-up round and is always worded as the end of that round.

### Tools

| Tool | Available in | What it does |
|---|---|---|
| `web_search` | Both phases | Searches the web through Serper: the startup at the start, and general information the founder asks about |
| `submit_initial` | Phase 1 | Writes everything down: the backend writes one answer per catalog question and a short summary from the saved transcript, checks and stores them |
| `submit_follow_up` | Phase 2 | Writes the follow-up round down: the backend writes what the founder said in the round per question (the follow-up answers, additions and corrections) and the final summary |

- The questionnaire (questions and contexts) is part of the agent's instructions from the start, and the follow-up round's questions come with the round's message, so nothing needs to be reread.
- When phase 2 begins, the backend swaps the tools: `submit_initial` disappears and `submit_follow_up` appears. The agent only ever sees tools that apply.
- The submit tools take no input: their call has the backend write the answers itself, with a strict structured output (one answer per question of the conversation's questionnaire), so a new catalog question automatically gets its answer, and the note-taker cannot put an answer into the wrong question.
- The follow-up round is written down per question, from the transcript since the round began. If the founder adds or corrects something about another question during the round, also at its closing check, it is written into that question, not into whichever follow-up was just being asked.
- Every result and every next step of writing down reaches the voice agent as a message from the backend: the summary to read, missing questions, the follow-up round, the goodbye, and what failed. A search's result reaches it as the note-taker's reply.

### Flow

[Note: This is after the signup/login, initial setup, preflight checks and everything else that happens when the user first starts the app. Also its of course just for the applicants]
1. **Start:** the backend assembles the instructions (agent name, language, founder name, company name, questionnaire with contexts, FAQ, rules) and starts the session. The agent greets the founder by name and explains how the conversation works (about 10 to 15 minutes, one question at a time, a short follow-up question when something stays unclear). It says it is quickly looking up the startup online, and the search really runs while it greets. Meanwhile it asks whether the founder has any important questions before starting and answers them (see "Startup lookup and founders' questions"). Then it asks the first question.
2. **Phase 1, questions:** the agent asks the questions in order, one at a time. It skips any question the founder has already answered in full, which rarely happens. If a question is partly answered, the agent mentions this and asks only for the rest of it. It does not repeat itself unless the founder explicitly asks it to. If an answer leaves out what the question's context asks for, stays vague, or the founder does not know, it asks exactly one follow-up right away, aimed at something workable (a rough estimate, a range or a best guess), then accepts whatever the founder says and moves on; it never follows up on the same question twice. An explicit refusal ("I'd rather not say") is accepted at once. It never just answers: it always comes back to asking, to reach the goal of completing the questionnaire. It only rephrases a question the founder did not understand.
3. **Submit initial:** when every question has an answer, the agent says it is writing everything down, hands over and waits, and the screen shows "Writing down your answers...". It never summarizes, says that something is written down or says goodbye on its own: what comes next is told to it in messages from the backend. The note-taker calls `submit_initial`, and the backend writes every answer from the saved transcript in the founder's own words, cleaned of fillers and repetitions, plus a short summary of all answers. Everything the founder said about a question counts, wherever it was said, and a later correction replaces what it corrects. Nothing is invented, and a declined question is written down as declined.
4. **Empty check and summary:** the backend checks that every answer is filled in and that the summary is short enough to be read aloud. If answers are missing, the agent is told which questions are missing, asks them and writes everything down again; a summary that is missing or too long counts as a failed attempt and is written again. Otherwise the backend stores the answers and the summary and immediately tells the voice agent to read the summary aloud as a statement ("Here is what I've written down: ...") while the review runs. Without a follow-up round, the spoken summary is the one shown in the success message; a follow-up round replaces it with the final summary (step 7).
5. **Review:** the reviewer reads the answers and the saved transcript and selects at most one follow-up per question, each with an explanation of what is missing or unclear, never one for a question the agent already followed up on. Selecting none is normal. The backend stores the follow-ups in the questionnaire, swaps the tools and sends the agent the follow-up round: its rules and its questions, in one message. If the review selected no follow-ups, there is no phase 2: the conversation becomes Completed at once and continues with the goodbye (step 8).
6. **Phase 2, the follow-up round:** once the summary has been read, the agent says in one sentence that the first round of questions is complete and a few short follow-up questions follow. It asks each follow-up naturally ("Coming back to your traction: ..."), one at a time, in questionnaire order, and only the selected ones; it accepts whatever the founder answers and never follows up on a follow-up's answer. If the founder adds or corrects something about another question, the agent accepts it and moves on. As the round's last question, it asks once whether the founder would like to correct anything in the answers given so far, clearly as the end of the follow-up round and different from "Anything else?". These rules arrive with the round's message from the backend, so the closing check exists exactly when a follow-up round exists.
7. **Submit follow-up:** the agent says it is writing everything down, and the screen shows the same "Writing down your answers..." indicator as in step 3 (one shared mechanism). The note-taker calls `submit_follow_up`, and the backend writes the round down from the transcript since the round began: every follow-up answer and everything the founder added or corrected about other questions (also at the closing check), each in the question it belongs to. The empty check confirms that every selected follow-up has an answer (if not, the agent asks the missing ones). It also writes the final summary: the first one updated with everything the founder answered, added or corrected in the round, with the same checks as in step 4. It replaces the first summary and is not read aloud; the backend tells the agent to say goodbye. The conversation becomes Completed.
8. **Goodbye:** the agent thanks the founder and says the team will be in touch. After the goodbye has been spoken, the backend ends the session, and the success message appears below the last conversation message.
- **Early end:** if the founder says they want to stop, the agent writes everything down at once, in either phase. The writing down notices it: the backend stores what was said, leaves the rest as not answered, skips the review, and the conversation becomes Completed; the agent says goodbye. STOP stays an abort that keeps only the transcript.

### Startup lookup and founders' questions
- At the start, the startup (the company name from the signup) is looked up with `web_search` while the agent greets the founder and tells them it is doing so. The voice agent can hand work over only in reply to the founder, and the greeting is not a reply, so the backend asks the note-taker for this search itself when the session starts. Like every search, its result reaches the voice agent as the note-taker's reply: one or two sentences of plain information, never a greeting or other words to say, which the agent takes as background, never as something to answer; the greeting never waits for it. The note-taker always passes something on, also when the search found nothing or failed, because its reply reaches the voice agent in any case, and a bare "OK" in the middle of the greeting made the agent say "OK" and greet twice. The agent uses the results only as background for the conversation and ignores them if they seem to describe a different company. It never writes them into the answers, which are always the founder's own words.
- Also at the start, the agent asks whether the founder has any important questions before beginning. Founders can ask questions at any later point as well.
- The agent answers only valid questions: questions related to the conversation, the startup, the investor or the process. It politely declines anything else.
- Questions about this process and this application (for example what happens next, who reads the answers or how long the conversation takes) are answered only from the FAQ. The FAQ is part of the agent's instructions, so these answers come at once. Default FAQ:
  - "How long does this conversation take?" About 10 to 15 minutes.
  - "What happens with my answers?" They are written down in your own words, checked for completeness and stored for the investment team, who review them.
  - "What happens after this conversation?" The investment team reviews your conversation and gets in touch with you.
  - "Who sees my answers?" The investment team.
  - "Can I correct something I said?" Yes, just say so at any time during the conversation.
  - "What if I don't know an answer or don't want to share it?" Just say so. If you don't know, I may ask once for a rough estimate; otherwise it is noted, and the conversation continues.
  - "Why do you ask follow-up questions?" To make sure every topic is complete: when an answer stays open, I ask once right away, and if something is still missing at the end, a few short follow-up questions follow. There is at most one follow-up per question.
  - "Can I stop the conversation?" Yes. Just tell me, and I write down what you said so far and we finish here. STOP also ends it at any time, but then the conversation is saved as unfinished, and a new attempt needs a new access code from the team.
  - "Is the conversation recorded?" The transcript is stored, the audio is not.
- General information (for example public facts about a market or a company) is looked up with `web_search`. The agent says "Let me look that up", hands over, and answers from the results only, naming the source. The prompts explain that the web search tool is versatile: for the startup, for public information about markets and companies, and for any valid general question.
- If the FAQ (for questions about the process and the application) or the search results (for general questions) do not contain the answer, the agent is instructed "to not make anything up and rather be honest and truthful to the user and state that you cannot provide the information or do not know the information."
- The search is built for speed: one search per question, result snippets only (no page loading), a short timeout.
- After answering, the agent always returns to the questionnaire. It never puts confidential details from the conversation into a search, never promises anything on the investor's behalf and never rates the startup.

### Common thread and natural conversation
- The voice agent keeps the whole conversation in mind for its entire length. Together with the fixed question order, this is the common thread: the agent does not repeat itself unless the founder asks it to, it follows up on a question at most once, right away, and the reviewer never selects a follow-up for a question the agent already followed up on.
- The founder can interrupt at any time. The agent stops and listens.
- The agent speaks the configured language. If the founder switches language, it follows.

---

## 8. Screens

All interface text is German (AGENTS.md). The texts quoted in this plan give their meaning in English.

The header shows the app's name with the area (Team area or Founder area) as a small blue pill below it, the team's navigation, and on the right the user's name and Log out; on phone width the navigation gets its own line and the name is hidden. Every page keeps the header in view, and the window itself never scrolls. On a page whose main content is a list or the chat, only that scrolls inside its card, while the title, the filters, the forms, the conversation's bar and its outcome message stay visible.

### Founder area
- **Welcome page:** a welcome letter ("Welcome to the Voice Agent for Investor Pitches"), what the agent is for, and Log in / Sign up.
- **Sign up:** name, email, password, company name and the access code. It leads straight into the new conversation.
- **My conversations:** own conversations with date, time and state. "New conversation" with a code field, which also leads straight into the new conversation. A past conversation opens in the conversation view (transcript and outcome message), filled from the database; one running in another tab shows "This conversation is running right now." with a Refresh button.
- **Tutorial** (before each conversation, skippable): a few slides with as little text as possible and simple visuals. Find a quiet place. Headphones are optional. Talk naturally, one question at a time. You can ask questions too. If an answer is unclear, the agent asks once more. The agent ends the call when everything is written down. STOP ends the conversation for good.
- **Device check** (before each conversation): connection (our server and OpenAI reachable), microphone (permission, selection, live level meter), speaker (selection where the browser allows it, a test sound, "I heard it"). START is enabled once everything passes. After a failed start the founder is back here with everything passed and the same microphone.
- **Conversation view:** the transcript in chat style (founder and agent, streaming live), the status (Connecting, Listening, Speaking, Microphone muted, Ending, and while a tool of the note-taker runs: Searching the web, Writing down your answers) and the START/STOP button (blue START at the end of the device check, red STOP during the call; STOP asks for confirmation). The bar with the status and STOP sits at the top of the conversation's card and the outcome message below the messages; only the messages scroll, and they follow new text while the reader is at the bottom. During the call, each tool call of the note-taker appears as a small coloured tag between the messages (with a spinner while it runs, then a check: "Searched the web", "Answers written down", "Follow-ups written down"), and the follow-up round sits in its own section, which starts with a "Follow-up questions" divider at the switch to the round's tools. Both exist only live: past conversations and the Team area show the stored messages alone. Apart from that, only what was said is shown. The note-taker's work, the questionnaire and the reviewer's text are never shown to founders. Reply times are not shown. During the call the header offers no links and no log out but a mute button ("Mute"): it silences the microphone the call sends, and while muted the status shows "Microphone muted" instead of "Listening", so a founder who talks and gets no answer sees why. Closing the tab asks first, and leaving the page anyway ends the call like a lost connection.
- **Outcome message:** when a conversation ends, a message appears below the last conversation message and stays there permanently: also when the conversation is reopened later, and in the Team area's view.
  - Success message (Completed): "Thank you, your conversation is complete.", the summary behind a prominent, expandable "Show summary" button, and what happens next ("The team will review your answers and get in touch.").
  - Unfinished message (Unfinished): "This conversation ended before it was complete.", the reason in plain words (stopped, connection lost, time limit reached), that the answers could not be submitted, and that a new attempt needs a new access code from the team. No summary.

### Team area
- **Conversations:** newest first, with date and time, founder, company and state. Search by founder, email or company, filter by state. Clicking a company shows all of its conversations.
- **Conversation detail:** most relevant first. The facts side by side: state and times (with the reason of an unfinished conversation), founder and company, and the settings used. Then the questionnaire: a "not reviewed" note if the review failed and the summary on top, then the questions with their answers, follow-up questions with their explanations and follow-up answers, which scroll in their own pane. Last, the same conversation view the founders see (transcript and outcome message), filled from the database, in a collapsible card that is closed when the page opens and shows the state and the number of messages in its title. Details that do not exist yet show "Not available yet"; a question still without an answer once everything is written down (an early end) shows "Not answered". A Refresh button reloads everything from the database, also while the conversation is running, and keeps the conversation open.
- **Access codes:** create a code for an email, list all codes with their state.
- **Settings:** see section 9.

---

## 9. Settings and Question Catalog

- The team can change: the conversation language (German or English, each with one matching voice; the interface itself is always German), agent name, question catalog, model and thinking level (both for the note-taker and the reviewer). The default language is German.
- Catalog editing: add, edit, remove and reorder questions (each with its question text and context). IDs are assigned automatically and never reused.
- One rule for every value the team can edit: the shipped default (in the repo) is copied into the database on the very first launch. From then on the app reads only the database. Software updates never overwrite the team's version. "Reset to default" in the Team area copies the current shipped default back, after a confirmation.
- Changes apply from the next conversation. Each conversation stores the settings and the catalog it ran with.
- The voice model is fixed. The offered models are `gpt-6-luna` (fast) and `gpt-6.1-terra` (OpenAI's fast and efficient model between Luna and Sol, more thorough), with the thinking levels low, medium, high and very high (the levels both models accept everywhere). The voices are `juni` for German and `marin` for English. The spike confirms or corrects these choices (section 17).
- An offered option can only be removed while no stored conversation and no team setting uses it, because their stored copies are checked against the offered options when they are read.
- The default for model and thinking is fast (`gpt-6-luna`, OpenAI's recommended delegation model, with thinking at the lowest offered level, low), because the note-taker decides how fast a founder's question gets answered and how long the "writing down" wait takes.

---

## 10. Centralisation and Single Source of Truth

| What | Its one home |
|---|---|
| Prompts, tool descriptions with their instructions and examples, FAQ, default catalog | The central context system |
| Every constant and tunable value, and the default settings (language, agent name, model, thinking level) | The central config module |
| Types (API, database, tool arguments, the writing down's and the reviewer's output) | Pydantic models; the frontend types are generated from them |
| Current catalog and settings | The database (seeded from the context system and the config module) |
| Secrets | `secrets/secrets.yaml` |
| OpenAI integration | One backend AI module, reusable across the codebase |
| Calls from the frontend to the backend | One frontend API client; all methods share its logic (credentials, errors) |
| Errors | One error type |

### Config module
- The central config module is the defaults file: every constant and tunable value lives there once, so the system can be tweaked in one place. Examples: timeouts, the access code validity (24 hours), the number of review attempts, the number of search results, the available models and the default model, the default thinking level, the voice per language, the latency target.
- Nothing else hardcodes such a value. The frontend gets what it needs from the backend.

### Context system
- JSON documents, each with one purpose (voice agent, note-taker, writing down, reviewer, the backend's messages, tools, FAQ, default catalog), split into named entries so specific parts can be extracted (as in the context system of an earlier project).
- Every prompt is defined in the context system as a list of entries. Any piece, for example the conversation rules or a tool's examples, can be included in any prompt without being written twice.
- Pydantic validates all documents on startup. A broken document stops the app with a clear message.
- Prompts are assembled once, when a conversation starts; the backend's messages to the voice agent (the summary, the follow-up round, the goodbye, ...) are rendered when they are sent.

---

## 11. Error Handling and Feedback for the Agent

- One error type with three separate messages:
  - for the user: short, plain and generic;
  - for the AI: natural language, saying what happened, why, and what to do next;
  - for the logs: the technical details.
- The browser only ever receives the user message, the AI only the AI message, and only the logs see the details.
- Every tool call ends with its result or the AI message for the voice agent, so the agent always knows exactly what is going on (for example: "Nothing was written down yet, because these questions have no answer: question 5 (Traktion), question 8 (Finanzierungsbedarf). Ask the founder about them, then write everything down again."). The backend sends it as a message, and the note-taker then gets "OK"; only a search's result, also "nothing found" or "not available", goes back to the note-taker, which passes it on.
- The note-taker answers every request with a tool call and then replies as the tool's output says; the voice agent names that tool in its hand-over. The note-taker's text still reaches the voice agent as a result, and OpenAI's API can neither force a tool call per response nor stop that text, so the backend guards the procedure: when a request ends with text alone, the voice agent is told to ignore that text, and the note-taker gets explicit instructions naming the request's tool and tries again (at most a few times per call).
- Every call to an outside service (OpenAI, Serper) has a timeout.
- If the writing down fails twice, nothing is stored, and the agent says it takes a moment longer and hands it over once more.
- If the review fails twice, there is no follow-up round: the conversation is completed right away and marked "not reviewed" for the team. If a search fails, the agent says it cannot look that up right now. If the startup lookup fails, the agent simply continues without it.
- A failed start leaves the conversation Ready, so the code is not lost.
- Logs contain IDs, codes and durations, never what the founder said.

---

## 12. Latency

- Reply time is measured from the moment the founder stops speaking until the agent's voice starts. Target: median under 1.5 seconds, almost never above 2 seconds.
- Why it is fast: a full-duplex voice model, audio straight between the browser and OpenAI with no hop through our server, and tools that never block the voice (the agent acknowledges at once and keeps talking while a search runs).
- Measured by the backend in the simplest way: OpenAI attaches timestamps to the transcript, and the backend takes the time between the end of the founder's words and the start of the agent's reply. It logs one line per reply, and one line with the median and the maximum when the conversation ends. Nothing is shown in the UI.
- Web searches and the "writing down" waits are covered by the agent's immediate acknowledgment and the summary. Their durations are measured and logged as well.

---

## 13. Developer Workflow

### Scripts
- `scripts/` contains everything developers run:
  - `setup.sh`: checks Docker, creates `secrets/secrets.yaml` from its template if it does not exist yet (internal values such as the session secret are generated), runs the secrets check and builds the containers. If a value is missing, it points the developer to the secrets file and says which values to fill in.
  - `start.sh`: preflight checks, then `docker compose up`.
  - `test.sh`: preflight checks, then the test suite in containers. With `--complete`, the tests against the real APIs run as well.
- `scripts/helpers/` is never used by developers directly. It contains the helpers the scripts use:
  - `preflight.sh` holds every check as its own function (Docker running, secrets complete, internet connectivity, OpenAI key valid, Serper key valid) and bundles them in one function per script (for example, `start()` calls the checks `start.sh` needs). The key checks run for `test.sh` only with `--complete`.
  - Whenever a check fails, it gives a high-level reason and practical instructions to solve it (for example: "The Serper key is missing. Get one at serper.dev and add it as serper_api_key in secrets/secrets.yaml.").
  - Shared helpers for running the backend's commands and for generating the frontend types.
- The frontend types are regenerated by `start.sh` and `test.sh`, and `test.sh` type-checks the frontend against them, so a frontend that no longer matches the backend fails the tests. The regenerated file is committed with the change.

### Secrets
- `secrets/secrets.yaml` (git-ignored) holds the OpenAI key, the Serper key, the session secret and the team login (email and password). A committed `secrets.example.yaml` shows its shape with empty values. The developer fills in the keys and the team login; `setup.sh` generates the session secret.
- The database needs no password: it runs only inside the app's containers and cannot be reached from outside them.
- Only the scripts and the backend config module read it.

### Tests
- Integration tests with a real PostgreSQL, faking as little as possible.
- Backend: login, access codes (expiry, single use, email binding, one redemption step for signup and new conversations), conversation states, empty checks, the tool swap, and error messages never leaking log details.
- AI: the writing down on recorded conversations (complete, declined, a later correction, an early stop), the reviewer on prepared questionnaires with their transcripts (complete, vague, declined, and a vague answer the agent already followed up on, which gets no second follow-up; at most one follow-up per question) and web search answers.
- Voice conversation, only with `--complete`: a real Chrome (Playwright) runs a full conversation through the real app. Its founder signs up with a new code and answers from a short script (an opening answer, one pitch that answers every topic question, a closing answer, then a fallback for every further turn), spoken by OpenAI's audio model at the start of each run and played into a fake microphone whenever the agent waits. It checks the success message and the summary in the browser, and in the database the Completed state, every answer, the summary, an answer to every follow-up the review selected (a follow-up round is optional), and a fact only the founder said, so answers the agent invented never pass; `test.sh` then prints the backend's reply times.
- Tests against the real APIs cost a small amount per run and need the keys. These tests should be optional with a --complete flag. If this flag is not provided, they should be faked. The voice conversation is the exception: it is not faked but runs only with `--complete`, because faking it would mean building a fake voice server.

### AGENTS.md
- Carried over from an earlier project of the developer, keeping the exact phrasing where possible: general context, root cause instead of hotfix, consistency and uniformity, centralisation and unification, full picture, single source of truth, performance (adapted: never block the server's event loop, a timeout on every outside call), asking questions with the ask user question tool, reading before writing, explaining commands, documentation first (module docstrings with purpose, mechanisms, constraints and interactions; comments explain the why), two passes for renames, a compact README, security, web search for the latest versions, the test suite through `scripts/test.sh`, the centrally managed systems, and the rules for user-facing text.
- Adapted: "live production software" becomes "a local MVP built to production standards". The model rule becomes "the latest models by default, chosen in one place".
- Dropped: everything that only applies to that project (Fly.io, the Daemon, the desktop client, the legal documents pipeline, Sentry, MCP servers, admin scripts).

---

## 14. README

The README stays compact and has two clearly separated parts. The team part is in German, like the app itself; the developer part is in English.

### For team members: using the software
- What the voice agent does and what a founder experiences, in a few sentences: welcome, signup with an access code, tutorial, device check, conversation, outcome message.
- Logging into the Team area (with the team login a developer sets in the secrets file).
- Inviting a founder: creating an access code for an email and sending it (valid for 24 hours, single use).
- Reviewing conversations: the list, search and filter, the conversation view, Refresh, and what the questionnaire shows (answers, summary, follow-ups with their explanations, "not reviewed").
- Changing the settings and the question catalog, and "Reset to default".

### For developers: setup and architecture
- Requirements: Docker, an OpenAI key and a Serper key.
- Setup, start and tests: `setup.sh`, `start.sh`, `test.sh` (and `--complete`), and what to do when a preflight check fails.
- The secrets file.
- Architecture overview: the diagram from section 5, the three AI roles, the two phases and the tools.
- Where things live: the context system, the central config module, the Pydantic types and the generated frontend types, the AI module, the API client and the error type.
- Deliberate trade-offs (section 16).

---

## 15. User Stories

These user stories should be carefully taken into account during every step of the implementation. Don't miss out on any detail and ensure this is taken care of uniformly and in the simple way that makes sense in combination with the planned functionality in this entire document.

### Team member

**T1. Invite a founder**
As a team member, I want to invite a founder, so that only people we choose talk to the agent.
- I log into the Team area and create an access code for the founder's email.
- The code is shown once. I copy it and send it to the founder myself (the app sends no emails).
- The code list shows the code as unused, then as used (linked to the conversation), or as expired after 24 hours without use.
- The system stores only a hash of the code, binds it to the email, and accepts it once, within 24 hours, and only for that email.

**T2. Review conversations**
As a team member, I want to find and read conversations, so that I can decide how to continue with a startup.
- I open Conversations, search for a company or a founder, and/or filter by state.
- I open a conversation and see the transcript and the outcome message, plus the questionnaire with answers, summary, follow-ups and their explanations, and the settings used. [NOTE: For this, the same UI should be reused that the applicants receive]
- For a running conversation, I press Refresh to see the latest transcript and, after the first submit, the answers. The other "details" should be shown in their current state from the db or placeholders with "not available yet" flag if and where it makes sense
- The system reads everything from the database. There are no live updates. [NOTE: If there is streaming in the user's conversation UI, the team's view reuses the same functionality, but fills it from the database and updates it with Refresh, because the live stream only exists in the founder's own call connection]

**T3. Adjust the agent**
As a team member, I want to change the language, the agent's name, the questions and the model, so that the conversation fits our needs.
- I change a setting or edit the catalog and save. The next conversation uses it; running and past conversations keep theirs.
- "Reset to default" restores the shipped default after a confirmation.
- The system validates every change (for example, no empty question) and assigns IDs to new questions.

### Founder

**F1. Sign up and get ready**
As a founder, I want to get into my conversation quickly and know what to expect.
- I open the website, read the welcome letter and sign up with my name, email, password, company name and the access code from the team.
- The system checks the code (it exists, is unused, has not expired and belongs to my email). It creates my account and my first conversation (Ready) and invalidates the code at once. If the code is wrong, expired or meant for another email, I am told so plainly, and nothing is created.
- I see the short tutorial (or skip it), then the device check: I allow the microphone, select my microphone and speaker, see the level meter move when I talk, hear the test sound and confirm it.
- If the microphone is blocked, I see how to allow it in my browser. If our server or OpenAI cannot be reached, I see that and can retry. START stays disabled until everything passes.

**F2. Have the conversation**
As a founder, I want a natural conversation that does not waste my time.
- I press START. The agent greets me by name, mentions my company, explains the process, tells me it is quickly looking up my startup online, and asks whether I have any important questions before we begin. Then it asks the first question.
- I answer naturally. If I already answered a later question in full, the agent skips it; if I answered it partly, the agent says so and asks only for the rest. I can interrupt the agent at any time.
- If my answer stays vague or I say I don't know, the agent asks once right away for something workable, such as a rough estimate or a range, and then moves on, whatever I say. If I decline a question, it accepts that at once.
- I ask: "What happens after this conversation?". The agent answers at once from its FAQ. I ask something general, for example about a market. The agent says it will look it up and answers from the search results, naming the source. If neither the FAQ nor the search has the answer, it honestly says it cannot provide or does not know this information. Then it continues with the questions.
- I see the transcript as we talk and the current status.
- The system sends the audio directly between my browser and OpenAI, and the backend saves the transcript through the sideband. Only the conversation transcript is visible, in a typical chat style. The sideband text and review text are never visible to the founders.

**F3. Finish and have the result stored**
As a founder, I want my answers written down correctly, and I want to know when I am done.
- After the last question ("Anything else?"), the agent says it is writing everything down, and the screen shows "Writing down your answers...". A few seconds later, the agent reads the summary aloud.
- If something is still missing, the agent then says that the first round is complete and a few short follow-up questions follow, asks the follow-ups the review selected (at most one per question, never about a topic it already followed up on) and finally whether I'd like to correct anything in my answers so far. After a second short "writing down" moment (the same indicator) it thanks me and says goodbye. If nothing is missing, it says goodbye right after the summary. The call ends by itself, and the success message appears below the last conversation message.
- In the system: `submit_initial`, the backend writes the answers and the summary from the transcript, empty check, summary read aloud while the review (answers and transcript) runs; with follow-ups: follow-ups stored, tools swapped, the round's message, then `submit_follow_up` writes down the round and the final summary, empty check, Completed; without: Completed at once; then the backend's goodbye message, and the backend ends the session after the goodbye.
- The success message stays below the last conversation message: "Thank you, your conversation is complete.", a prominent, expandable "Show summary" button with the summary, and what happens next. It looks the same when I reopen the conversation later and in the Team area.

**F4. The conversation stops early**
As a founder, I want to be able to stop, and I want to know what happens if something breaks.
- I press STOP and confirm ("Stop now? The conversation will be saved as unfinished and can't be submitted."). The session ends, and the unfinished message appears below the last conversation message, in contrast to the success message described in F3.
- If my connection drops or I close the tab, the conversation is Unfinished as well.
- If I tell the agent that I want to stop, it writes down what I said so far and says goodbye. The conversation is Completed with my answers so far (the rest is marked as not answered for the team), and the success message appears.
- If the start itself fails, or the connection breaks before I said anything, the conversation stays Ready, and I can try again.
- OpenAI reports every session end to the backend. Every conversation that started but did not reach Completed becomes Unfinished, and its transcript is kept for the team. A new attempt needs a new code.
- The unfinished message stays below the last conversation message: "This conversation ended before it was complete.", the reason in plain words (stopped, connection lost, time limit reached), that the answers could not be submitted, and that a new attempt needs a new access code from the team. No summary is shown.

**F5. Come back for another conversation**
As a founder, I want to see my past conversations and start a new one when the team invites me again.
- I log in, see my conversations with date, time and state, and can read their transcripts.
- With a new code from the team, I start a new conversation under "New conversation".
- The new code is marked as already used immediately as I submit the new conversation. This should happen uniformly with when entering the code in the signup and clicking on signup because both start a new conversation, and the responsible method always checks the provided code and marks it as used in the same step. This is the kind of uniformity and anti-fragility I want.

### Developer

**D1. Set up, start and test**
As a developer, or someone trying the app, I want to run it in as few steps as possible.
- I run `setup.sh` once. It creates the secrets file, runs the secrets check and, if something is missing, tells me which values to fill in `secrets/secrets.yaml`: the two API keys and the team login.
- I run `start.sh`. The preflight checks Docker, the secrets, the internet connection and both keys, and if something fails, tells me the reason and how to fix it. Then the app starts.
- I run `test.sh`. All tests run in containers, with the outside APIs faked. With `--complete`, they run against the real services, including the voice conversation and the latency measurement.

---

## 16. Deliberately Out of Scope

These are conscious trade-offs for a local MVP:
- Password reset, email verification and sending emails (the team sends codes itself).
- Continuing an unfinished conversation (a new attempt needs a new code).
- Storing audio recordings (only transcripts are stored).
- Any AI judgment or scoring of startups.
- Live updates in the Team area (Refresh instead).
- Hosting and deployment, several investors per installation, separate team accounts or roles.
- Mobile apps (desktop browser; Chrome recommended, since not every browser lets a website choose the speaker).
- Privacy and Legal consideration: Dropped because it is not needed for a local MVP. Same goes for fact checking, monitoring and prompt analysis via Langfuse.
- RAG System for having a knowledge base about the investor, in order to actually answer questions about the investor in a more fact based manner.

---

## 17. To Verify First

The first implementation step is a small spike against the real APIs to confirm what the documentation leaves open. The spike is `drafts/d3-liveDelegation/spike.py`; its README holds the findings table with what the documentation says about each point. The app's real voice conversations (the browser calls and the voice test of `./scripts/test.sh --complete`, 2026-11-16) settled most points; the rest stay open until the spike or a person's conversation answers them:
- Verified: the note-taker sees the whole conversation. Its `submit_initial` held every answer from the founder's spoken pitch, in the founder's words.
- Verified: the tools can be swapped mid-session. After the `session.update`, the note-taker called `submit_follow_up`.
- Verified in the app's browser call (2026-11-16): the browser's connection receives the note-taker's tool activity (the nested `response.event`s), and "Looking it up" showed during the startup lookup.
- Verified in a real voice test (2026-11-17): the browser's data channel also receives `session.updated` after the backend's `session.update`, with the tool names in `session.delegation.responses.tools[].name`, so the switch to `submit_follow_up` marks the start of the follow-up round in the live chat. The transcript deltas carry no turn ID (`type`, `start_ms`, `end_ms`, `delta`, `event_id`).
- Verified: the backend can hand the stored summary to the voice agent, which reads it aloud while the review runs.
- Verified: the transcript timestamps give plausible reply times (median about 1 to 1.2 seconds per conversation).
- Found on the way: the voice agent hands work over only in its own replies to the founder, so the startup lookup is started by the backend (section 7), and the greeting text must be words to say, not instructions, or the greeting sometimes does not start.
- The German voices sound natural, and the session time limit comfortably exceeds a 15-minute conversation.
