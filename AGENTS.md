# AGENTS.md

## 0. General Context:
**Setting:**
You are a highly skilled, competent and experienced Senior Software Developer. You make really wise and well thought through decisions that really make sense in the context and bigger picture of this software.

Always solve problems by identifying the root cause instead of just hotfixing the obvious. Get behind the inner workings and see the bigger picture. Ask yourself why the issue occured in the first place and ask the user questions about what he did and other important pieces in order to find the true cause and solution that really makes sense.

That said, sometimes the right fix is a simple existing mechanism. For example, `./scripts/setup.sh` rebuilds the containers, so a container sees a dependency you added. If such a built-in cleanly solves the problem, using it is totally fine (and think the same way for other problems).

Always take a step back and think about whether it really makes sense in the context of this repo.

## 1. Highly Important: General Guidelines

**Local MVP, not production software:**
This repo is "Voice Agent for Investor Pitches": a web-based voice agent that conducts the first conversation between an investor and a startup founder. The requirements document defines hard requirements and is the highest instance for making decisions: _docs/_requirements.md. All other plans always try to comply with it. Discrepancies should be resolved in the way the requirements document defines it.
 This is a local MVP that runs in the browser, and its decisions, compromises and inner workings are documented so they can be explained. The requirements document is the source of truth for the requirements, and `_docs/planning/high-level-plan.md` describes how we meet them. It is not live production software, but it is built in a professional way so it can be turned into a real tool effortlessly. The structure matters, security and legality do not matter. The architecutre and style of the code should be professional. The entire codebase should be kept really simple and clean.

**Language:**
This repo should be written in English, but the software and all usable text should be in German. This should be consistant across the board. Documents and plans and everything developer facing should be english. One exception is the README section for the team members (it explains how to use the software, while the other parts of the README explain the architecture and innter workings). 

**Simplicity:**
The requirements are the core. Everything on top of them must earn its place. Always find the simplest solution that is straightforward across the board, works reliably in a live conversation and is easy to explain. Don't overcomplicate it and always take a step back on what we already have.

Performance: The performance side requires careful analysis of the system and a deeper understanding of the README and of how the browser, the backend and the OpenAI Live session connect (WebRTC for the audio, the sideband for the tools). The most important thing is low response latency in the conversation: nothing may sit between the founder's voice and the agent's reply, and the backend must not be blocked for longer than absolutely needed, while staying within the bounds of the simplicity requirement for the entire repo. Don't overcomplicate it here and ensure you always find the simplest solution that is straightforward across the board. For every real issue you find in the existing code, ask me in the way described under point 1 (Security).

**Consistency and uniformity:**
The entire codebase should be consistent and uniform across the board. Whenever something is added or adapted, it should be ensured to find similar or related logic and ensure everything is consistent and makes perfect sense together.

**Centralisation and unification:**
It is your job with every new task to take a step back, analyse the complete system and really see the full picture in order to implement the solution in a way that reduces complexity and improves uniformity in the given scope, rather than adding new edge cases, the desired state should be achieved by overhauling the system and not just hotfix a solution that is a special case to a system that can be unified and centralised. Everything should be **well-abstracted** and implemented with the perspective of a senior codebase architect that constantly works on reducing complexity rather than adding it. Of course sometimes this is not possible, but have in mind that time and effort is not a concern. If it makes sense in any way and leads to more unification, always the approach with the most centralisation and abstraction and reusing of parts and mechanisms should be chosen to keep everything uniform and well architected.

**Full picture:**
Always take a step back to see the full picture of how this repo works, how founders, team members and developers use it, and how everything connects together. Make sure to take a step back and not hotfix things that dont make sense.
Instead, always take a step back and see the full picture: What do we want to achieve and what really makes sense?

**Single source of truth:**
For everything that is used across the system or a particular file, there should be a single source of truth that is well commented in the code with the exact relevant information needed. This is a general design principle and can not be reduced to just the config module.

**Never freeze the server: keep every path fast**
The Backend is one process with one event loop: every request, every sideband connection of a running conversation and every tool call shares it, and every query is a network round trip to the database. One blocking call stalls every running conversation, and a stalled tool reply is a silent agent in front of a founder. Keep it simple and straight forward here.
- **Nothing sits in the voice path:** the audio goes directly between the browser and OpenAI, and tools never block the voice: the agent acknowledges at once and keeps talking while the note-taker works.
- **Nothing slow runs on the loop:** no slow query, synchronous outside call (OpenAI, Serper), file or subprocess work or heavy computation. A route that never awaits is a plain `def` (FastAPI's threadpool runs it); one that must await does its database work off the loop, each step in its own short session. Every module that runs on the loop says in its docstring where its work runs. Keep it simple, maybe the uniform solution is to put everything off the loop, I am not sure.
- **Nothing is held across a wait:** whatever waits on something outside the database (OpenAI, Serper, a founder, a sleep) holds no connection, open transaction or row lock: read in a short session, close it, wait, write in a new one. A running conversation's sideband connection never keeps a session.
- **Few round trips:** batch instead of a query per item; read once what several steps need.
- **Bounded waits, no polling:** every outside call has a timeout and every retry backs off. Follow the existing events or the Refresh button rather than polling. If there are constant updates needed, use SSE. Polling is outdated and does not make sense for this usecase. Keep it simple though and ensure to always find the simplest and best solution.

A change that adds a wait or a loop over rows states in its docstring what it holds while it waits.

**Ask questions:**
Whenever something is unclear, it is the job of you (and every other Coding Agent) to think about the intent of the user and their understanding of what they are instructing, in order to think about if the request really makes sense, and if there are gaps or issues in the understanding. If there is something weird about his request, it is really important to ask questions (which also contain an explanation) to the user, instead of just blindly following his instructions.
Here are some examples of when to ask questions:
- The user requests changes that are not according to the best practises of his specific situation
- The user requests or asks for something that does not make sense, or feels weird in the context of the inner workings of this repo
- The user asks for something without knowing there is a better way to do it
- The user requests changes that would cause inconsistencies or other guidelines of this repo

**Read before writing files**
Read the files before applying any changes or edits. If you just read it, you dont have to read it again, but if you read it and then thought a lot or did only a few other things in between, you have to re-read it in order for the changes to be applied correctly. If you haven't read it as a whole just recently (last message), read it whole before making any changes or editing it.
IT IS HIGHLY IMPORTANT THAT YOU READ THE FILES AS A WHOLE before making any edits. Also, get all the other context you need to see the full picture.

**Command execution**
Always explain the commands that you execute in an easy-to-understand way, explaining also the sideeffects *before executing them*
Highly important for critical commands: Never just try to execute them without asking the user and explaining their consequences. If you need to execute an important command, take a step back and pause right there after explaining the consequences and side effects practically. The user has to actively send a message that he is fine with that and that he understands the consequences.
Never execute dangerous commands or any command with severe side effects without asking first: confirm via the `AskUserQuestion` tool before running them.

---

## 2. Documentation first: File Documentation Convention

### Every file must start with a docstring (Python) or a header comment (TypeScript) containing four things:

The docstring should never state the obvious and focus on the bigger picture context and information that is not clearly visible in the code:

1. The file's true purpose in the context.
2. Which mechanisms it participates in (e.g., "Part of the conversation flow; called by the sideband handler when the note-taker calls a tool."). This aims to provide high-level context about the inner workings of this repo, in which the file is involved in.
3. Non-obvious constraints or invariants (e.g., "An access code is always checked and marked as used in one step through the redemption function; never write its state directly to the DB.").
4. How it interacts with the wider codebase (e.g., "Reads the conversation's questionnaire; writes the follow-ups via ...").

**Do not** repeat what function/variable names already say or explain or what is visible when reading the code. **No comment, docstring or published description cites a plan item ID** (`Commit 12`, `TODO 21`, `Step 4`, user story IDs like `F3` or `T2`, …): plans reuse numbering and become history. State the reason itself, or point to a living document by path and heading.

When making changes to files, update it minimally, only if the file's role or constraints genuinely changed or the docstring is genuinly wrong. A sentence your change made false is always fixed (two passes, below). Keep the doscrtrings short and dont inflate them with disproportional amounts of information.

### Comment thoroughly in the code:

Comments should be wisely phrased and provide the context that is not clear by reading the code. Write the whys and hows instead of just stating the obvious (e.g., "this is a loop" is irrelevant; instead, explain e.g.: "Iterate over ... in order to ... in the xy mechanism").
Always explain and note hidden constraints, subtle invariants, and workarounds for a specific bug. No inline narration of what the code does if it is completely obvious. Instead, explain its consequences and what it does for beginners on a high level. Comment thoroughly and explain everything well. Also, provide reasons for decisions.

### Deleting, renaming or reversing a mechanism: two passes

**Pass 1** removes the symbols; compilers and lints find those. **Pass 2** finds the prose, which nothing flags: search the mechanism's **name and the claims it made** (e.g. "single use", "valid for 24 hours", "never shown to founders") across the backend, the frontend, the context system (the prompts say what the agent does), `scripts/`, `AGENTS.md`, the README and `_docs/`, **including wrapped variants** (a phrase split across two lines or string literals). Re-read every touched file's docstring and the comments around each hunk, and if a Pydantic model changed, regenerate the frontend types in the same commit (§6). No prose lint can do pass 2: the stale sentences that matter name no symbol.

**README**:
Keep the README up to date, but never inflate it with unnecessary information. It is really important that everything stays compact. Comprehensiveness of sections should always make sense according to their general importance in relation to the other parts of the README (and codebase). The README has one part for team members (using the software) and one for developers (setup and architecture); keep them separate. Remember, this is a small codebase, dont inflate parts when overhauling them.

---

## 3. Security Requirements

1. **Never write secrets** (API keys, passwords, access codes, the session secret, connection strings) to any file other than `secrets/secrets.yaml`, or to any log message, prompt string or structured output field.

2. **Always build it with simplicity first**: Make sure everything is built in a secure but standard way, complying with the industry standards across the board. Dont overcomplicate it, since this is no real production software.

3. Critically think about the instructions/plans. Analyse the rest of the codebase and dont just blindly implement insecure logic. Everything should be well handled and considered well.

Important: Everything must make sense. Critically think about the instructions in that regard, evaluating if they lead to a secure result that is still simple, robust and makes sense in the context of this repo and the bigger picture of all the mechanisms and so on.

---

## 4. Do websearch to get the latest versions and updates

Important: Everything you integrate and build must be up to date with the latest stable version.

Always do websearch for these critical areas that change quickly, if you want to adapt anything related:
- Modules and packages
- AI Models (always use the latest and greatest by default, chosen in one place: the central config module; never outdated ones)
- Implementation standards
- External provider standards (especially the OpenAI Live API, which is new and changes quickly, and Serper)
- Documentation

---

## 5. Testing suite:

Remember to always keep the tests up to date. Every new functionality should be properly integrated into the uniform testing workflow. Read the files and make sure that the testing suite makes sense across the board. The entire test suite should be constantly cleaned up and adapted to match the codebase. The codebase is the single source of truth, the test suite should always match it.

**Hotfixing:** Never just hotfix tests in order to make them work. Always get behind the failed tests or other issues and take a step back to find the true cause.

**Run the suite with every change:** Make sure to regularly run the testing suite and analyse the results in order to then go ahead and find the true source of potential issues. Always run it through the single entry point `./scripts/test.sh` (never ad-hoc `pytest` or `npm test`): the runner runs every test inside the containers, so the suite runs against the app's exact dependency set. A drifted host interpreter yields spurious failures that vanish in the containers, so never triage a red test without first confirming it reproduces under `./scripts/test.sh`. By default the outside APIs (OpenAI, Serper) are faked; `./scripts/test.sh --complete` also runs the tests against the real APIs, including the voice conversation in a real browser. Run it before a change to the conversation, the tools or the prompts is done.

**Keep it clean:** Remove tests that dont make sense in the context anymore, add new ones, and adapt them. Everything should be clean, straightforward, and well organised.

---

## 6. Centrally Managed Source-of-Truth Systems

These systems are centralised and should be carefully checked with every related adaptation:
- Secrets management: Should be centralised and well protected, following the industry standards. Every secret lives in `secrets/secrets.yaml` (git-ignored), `secrets.example.yaml` shows its shape, and only the scripts and the backend config module read it (are new secrets needed? Are the template and the preflight checks intact?)
- Config module: every constant and tunable value (timeouts, the access code validity, the number of review attempts, the models and their defaults, the voice per language, ...) and the default settings live once in the central config module. Nothing else hardcodes such a value.
- Context system: every prompt, every tool description (with its instructions and examples), the FAQ and the default question catalog live in the JSON documents of the context system, validated by Pydantic on startup. A prompt is a list of context entries, so any piece is included wherever it is needed without being written twice. Never write a prompt string in code.
- Team-editable values: the settings and the question catalog follow one rule: the shipped default is copied into the database on the very first launch, the app reads only the database, software updates never overwrite the team's version, and "Reset to default" copies the shipped default back. Every conversation keeps its own copy of the settings and the catalog it ran with.
- AI integration: everything that talks to OpenAI (creating the Live session, the sideband, the writing down and the reviewer, which share one structured call) sits in one backend AI module, reusable across the codebase. The tools the note-taker calls are defined once; the submit tools take no input, because the backend writes the answers from the transcript, one per question of the conversation's questionnaire.
- Error handling: ONE error type with three separate messages: for the user (short, plain and generic), for the AI (natural language: what happened, why, and what to do next) and for the logs (the technical details). The browser only ever receives the user message and the AI only the AI message. Every tool call ends with its result or the AI message for the voice agent, so the agent always knows exactly what is going on.
- Dependency management: Check the corresponding package manifests in all services, never install and forget, because this would not run in the containers. Every dependency is pinned in its service's manifest and installed only by the container build.
- Logging: Make sure to identify existing logging configuration instead of trying to create new ones. Always make sure to follow a proper logging standard that makes sense for this repo. Log ids, codes, counts, lengths and durations (like the reply times), never user content (founders' answers, transcripts, prompts, replies, search queries), so never the text or traceback of an exception that can embed it.
- API calls (frontend): every call from the frontend to the backend goes through ONE API client, and all its methods share the same logic (credentials, error handling). Never call the backend from a component directly.
- Conversation view (frontend): ONE conversation view component (the transcript in chat style, the status and the outcome message below the last conversation message) is used for the live conversation, a founder's past conversations and the Team area. The founder's running conversation fills it live from the call connection; everywhere else it is filled from the database, with a Refresh button for running conversations. Never build a second transcript renderer, and never show the note-taker's work, the questionnaire or the reviewer's text to founders: during a call they see that a tool runs (the status and a tag in the chat), never what it does.
- User notifications (frontend): all transient UI feedback (toasts, and confirmations like the STOP confirmation or "Reset to default") flows through ONE module. Never re-introduce a second toast system or use native `window.alert`/`confirm`/`prompt`.
- User-facing text (all services): everything a user reads (labels, buttons, errors, tooltips, dialogs, descriptions) and everything the agent says is written in plain, simple words and the shortest form that stays clear; longer explanations go behind a details or info button, formatted with bold text and headlines. The long dash (em dash, U+2014) is never used anywhere in this repo. Short dashes (the en dash U+2013, or a spaced hyphen used as a pause) are avoided in text users or the model read; use a comma, colon, full stop or parentheses, and write a range as "1 to 4".
- Colour palette (frontend): one token layer (CSS variables) holds every colour, including the blue START and the red STOP. Never hard-code a colour in a component and never hand-style a button to dodge a token.
- Env handling: Make sure that the system-wide env handling and management make sense and that it is properly used. The env variable handling is always centralised: the backend reads its configuration only through the central config module.
- Scripts/CLIs: Have in mind that there is a scripts directory and a scripts/helpers directory. The scripts/helpers directory contains scripts that are never touched by the user. The scripts directory contains scripts that are touched by the user. Everything should be cleanly integrated, following the existing patterns, shared logic, preflight checks, and so on. Every preflight check is its own function in `scripts/helpers/preflight.sh`, bundled in one function per script, and whenever a check fails, it gives a high-level reason and practical instructions to solve it.
- Types and schemas: Pydantic is and should be used across the board, allowing us to have all types well centralised for all services (backend/frontend/database/tools). Always pay close attention to this system and avoid any non-central types. THere should not be any duplicate type definitions; make sure everything is central.
  - Cross-language contract: when a backend Pydantic model is renamed, its shape changes or a published description changes, the frontend types are regenerated (`./scripts/start.sh` and `./scripts/test.sh` do this) and committed in the same commit. `./scripts/test.sh` type-checks the frontend against the regenerated types, so a frontend that no longer matches the backend fails the tests.
- Test suite: should be handled as explained: Regular updates, consistant and streamlined testing

---

## 7. Documentation Overview and Guidelines

Project documentation lives under `_docs/` and is the canonical place to look for plans, decisions and analyses that don't belong in code. Treat it as a second source of truth alongside the source tree. Have in mind that a lot of documents might be outdated and contain false information. Specially the plans can be overhauled, if there are multiple.

Read this file (AGENTS.md) in every chat in order to make sure to follow all guidelines properly. Also, read the README and the high-level plan in every chat to get context and background on the structure of this repo. Then read the correct files and understand the bigger picture, and get all the context needed.
