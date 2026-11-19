"""Pydantic models: the one home of every shape the backend exchanges.

API requests and responses live here, and through FastAPI's OpenAPI schema they become the
generated TypeScript types of the frontend (frontend/src/api/types.ts). Every model and field that
crosses into the frontend has a description, because the descriptions become the comments of the
generated types. A change here means regenerating those types (./scripts/start.sh and
./scripts/test.sh do it) and committing them with the change.

The `Literal` types are the only definition of their values: the database stores them as plain
strings, and the frontend's labels (frontend/src/labels.ts) are typed with them. `Language`,
`ModelName` and `ThinkingLevel` are built from the config module's options, which stay their only
source (their labels come from there too, through `SettingsPage`).

The team-editable values (`Settings`, `Catalog`) are stored as JSON and always read and written
through these models (app/team_values.py), so a stored value is validated like an API request.
"""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app import config

Role = Literal["founder", "team"]
ConversationState = Literal["ready", "in_progress", "completed", "unfinished"]
AccessCodeState = Literal["unused", "used", "expired"]
Language = Literal[*config.LANGUAGES]
ModelName = Literal[*config.MODELS]
ThinkingLevel = Literal[*config.THINKING_LEVELS]
# How an Unfinished conversation ended. Decided by who ended it, never by OpenAI's close reasons:
# STOPP, our own time limit, or every end we did not cause.
EndReason = Literal["stopped", "time_limit", "connection_lost"]
Speaker = Literal["founder", "agent"]
ToolName = Literal["web_search", "submit_initial", "submit_follow_up"]

# Types the browser needs although no route carries them: the note-taker's tool names reach the
# browser in OpenAI's data channel events, where they decide the status and the tags of the live
# chat („Sucht im Internet ...").
# app/main.py adds them to the OpenAPI schema, so the generated frontend types include them.
BROWSER_TYPES = {"ToolName": ToolName}

# Input texts: surrounding whitespace removed, never empty, bounded. Emails are normalized further
# (lowercased) by security.normalize_email, the one place that does it.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")]
Password = Annotated[str, StringConstraints(min_length=1, max_length=200)]
AccessCodeInput = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
AgentName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Topic = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
QuestionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
ContextText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class AppConfig(BaseModel):
    """Values the frontend needs from the backend's config module. Loading it also proves that the
    server is reachable."""

    access_code_valid_hours: int = Field(description="How many hours a new access code stays valid.")
    openai_reachability_url: str = Field(description=(
        "What the device check requests to see whether the browser reaches OpenAI."))
    connection_check_timeout_ms: int = Field(description="How long each request of the device check may take.")
    ice_gathering_timeout_ms: int = Field(description=(
        "How long START waits for the browser's network addresses before it sends the offer."))
    speaking_level_threshold: float = Field(description=(
        "The agent's audio level (RMS, 0 to 1) above which the status shows that it speaks."))
    speaking_hold_ms: int = Field(description=(
        "How long the status keeps showing that the agent speaks after its level dropped."))


class Me(BaseModel):
    """Who is logged in."""

    role: Role = Field(description="Founder or team; decides the area the user sees.")
    name: str = Field(description="The founder's name, or the team's email for the team.")
    company_name: str | None = Field(description="The founder's company; null for the team.")


class SignupRequest(BaseModel):
    """A founder's signup: creates the account and its first conversation, unlocked by an access code."""

    name: Name = Field(description="The founder's name; the agent greets the founder with it.")
    email: Email = Field(description="Must be the email the access code was created for.")
    password: Password = Field(description="The founder's password; stored only as a hash.")
    company_name: Name = Field(description="The startup's name; the agent mentions it and looks it up.")
    code: AccessCodeInput = Field(description="The access code from the team; letter case does not matter.")


class SignupResponse(BaseModel):
    """The new founder, now logged in, and the conversation the code unlocked."""

    me: Me = Field(description="The founder who is now logged in.")
    conversation_id: UUID = Field(description="The new conversation, in state Ready.")


class LoginRequest(BaseModel):
    """The one login for founders and the team; the email decides which of the two it is."""

    email: str = Field(min_length=1, max_length=254, description="The email of the account.")
    password: Password = Field(description="The account's password.")


class CodeRequest(BaseModel):
    """Unlocks a further conversation with a new access code ("Neues Gespräch")."""

    code: AccessCodeInput = Field(description="The access code from the team; letter case does not matter.")


class ConversationSummary(BaseModel):
    """A row of the founder's list "Meine Gespräche"."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="The conversation's ID.")
    state: ConversationState = Field(description="Where the conversation stands.")
    created_at: datetime = Field(description="When the access code unlocked it.")
    started_at: datetime | None = Field(description="When START was pressed; null while Ready.")


class AccessCodeCreate(BaseModel):
    """Creates an access code for one founder's email."""

    email: Email = Field(description="The founder's email; only the account with this email can use the code.")


class CreatedAccessCode(BaseModel):
    """A new access code. The only time the plain code exists outside the founder's hands: only its
    hash is stored."""

    code: str = Field(description="The plain code, to copy and send to the founder.")
    email: str = Field(description="The email the code is bound to.")
    expires_at: datetime = Field(description="When the code expires if it is not used.")


class AccessCodeRow(BaseModel):
    """An access code in the team's list. The plain code is never part of it."""

    id: UUID = Field(description="The code's ID.")
    email: str = Field(description="The email the code is bound to.")
    created_at: datetime = Field(description="When the team created the code.")
    expires_at: datetime = Field(description="When the code expires if it is not used.")
    state: AccessCodeState = Field(description="Computed from the stored times: unused, used or expired.")
    conversation_id: UUID | None = Field(description="The conversation the code unlocked, once it is used.")


# --- Settings and question catalog (team-editable, see app/team_values.py) ---------------------
class Settings(BaseModel):
    """The agent's settings: the team's current ones, and the copy every conversation keeps from its
    START."""

    language: Language = Field(description="The language the agent speaks; it also chooses the voice.")
    agent_name: AgentName = Field(description="The name the agent introduces itself with.")
    note_taker_model: ModelName = Field(description=(
        "The note-taker's model: the AI in the background that looks things up and writes the answers down."))
    note_taker_thinking: ThinkingLevel = Field(description="How much the note-taker thinks; higher is slower.")
    reviewer_model: ModelName = Field(description=(
        "The reviewer's model: the AI that checks the answers and selects the follow-ups."))
    reviewer_thinking: ThinkingLevel = Field(description="How much the reviewer thinks; higher is slower.")


def check_unique_ids(ids: list[int]) -> None:
    """Question IDs identify the answers, also in the writing down's output, so a catalog never holds
    one twice."""
    if len(set(ids)) != len(ids):
        raise ValueError("the question IDs are not unique")


class CatalogQuestion(BaseModel):
    """A question of the catalog. The agent uses the context to explain or rephrase the question and
    to notice a partly answered one; the reviewer uses it to judge whether an answer is complete.
    Written in German, because the team reads and edits it; the agent asks it in the conversation
    language."""

    id: int = Field(ge=1, description="Unique; assigned automatically and never handed out twice.")
    topic: Topic = Field(description="A short name of the topic, for example Traktion.")
    question: QuestionText = Field(description="The question as the agent asks it.")
    context: ContextText = Field(description="What the question is about and what a complete answer covers.")


class Catalog(BaseModel):
    """The question catalog: the questions every new conversation copies at START, in this order."""

    questions: list[CatalogQuestion] = Field(min_length=1, description="The questions in the order the agent asks them.")
    next_id: int = Field(description=(
        "The ID the next new question gets. It only grows, so no ID is ever handed out twice."))

    @model_validator(mode="after")
    def check_ids(self) -> Self:
        check_unique_ids([question.id for question in self.questions])
        if self.next_id <= max(question.id for question in self.questions):
            raise ValueError("next_id must be above every question ID")
        return self


class CatalogQuestionEdit(BaseModel):
    """A question as the team saves it: an existing one keeps its ID, a new one has none yet."""

    id: int | None = Field(ge=1, description="The question's ID, or null for a new question.")
    topic: Topic = Field(description="A short name of the topic.")
    question: QuestionText = Field(description="The question as the agent asks it.")
    context: ContextText = Field(description="What the question is about and what a complete answer covers.")


class CatalogEdit(BaseModel):
    """The whole catalog as the team saves it: removed questions are missing, new ones have no ID."""

    questions: list[CatalogQuestionEdit] = Field(min_length=1, description="The questions in their new order.")

    @model_validator(mode="after")
    def check_ids(self) -> Self:
        check_unique_ids([question.id for question in self.questions if question.id is not None])
        return self


class Option(BaseModel):
    """A choice of a select field: the stored value and its German label."""

    value: str = Field(description="The value stored in the settings.")
    label: str = Field(description="What the settings page shows.")


class SettingsPage(BaseModel):
    """The team's current settings and the choices the settings page offers (from the config module)."""

    settings: Settings = Field(description="The current settings; new conversations copy them at START.")
    languages: list[Option] = Field(description="The conversation languages.")
    models: list[Option] = Field(description="The models for the note-taker and the reviewer.")
    thinking_levels: list[Option] = Field(description="The thinking levels, lowest first.")


# --- The conversation -------------------------------------------------------------------------
class TranscriptMessage(BaseModel):
    """One message of the transcript: a run of consecutive transcript deltas from the same speaker.

    The Live API has no turn IDs, so this is the one definition of a message, for the backend
    (app/ai/transcript.py) and any live transcript in the browser alike: a speaker change starts a
    new message; the text is the deltas joined as received, trimmed when the message is finished; an
    empty message is dropped. Times are milliseconds from the start of the Live session."""

    speaker: Speaker = Field(description="Who spoke: the founder or the agent.")
    text: str = Field(description="What was said.")
    start_ms: int = Field(description="When the message started, in ms from the session start.")
    end_ms: int = Field(description="When the message ended, in ms from the session start.")


class FollowUp(BaseModel):
    """A follow-up the reviewer selected for a question, in German for the team."""

    question: str = Field(description="The follow-up question; the agent asks it in the conversation language.")
    explanation: str = Field(description="What is missing or unclear in the answer.")


class QuestionnaireEntry(BaseModel):
    """A question of the conversation's questionnaire, with what was written down for it."""

    id: int = Field(description="The question's ID in the catalog the conversation copied.")
    topic: str = Field(description="The question's topic.")
    question: str = Field(description="The question as the agent asks it.")
    context: str = Field(description="What the question is about and what a complete answer covers.")
    answer: str | None = Field(description="The founder's answer in their own words; null before the first submit.")
    follow_up: FollowUp | None = Field(description="The follow-up the reviewer selected; null if none.")
    follow_up_answer: str | None = Field(description=(
        "What the founder said about this question in the follow-up round: the answer to its follow-up, "
        "or an addition or correction; null if nothing."))


class Questionnaire(BaseModel):
    """The conversation's own copy of the catalog, made at START, with the answers, the summary and
    the follow-ups. Later catalog edits never change it."""

    entries: list[QuestionnaireEntry] = Field(description="The questions in the order the agent asks them.")
    summary: str | None = Field(description=(
        "The short summary: written at the first submit, replaced by the final one when the follow-up round is "
        "written down; null before the first submit."))
    reviewed: bool | None = Field(description=(
        "Whether the review succeeded; false means it failed and there were no follow-ups; null before it."))


class StartedConversation(BaseModel):
    """What claiming a conversation's START returns to the call: the copies it made and the founder's
    details for the prompts."""

    started_at: datetime  # the attempt's token: the call's writes are conditional on it
    settings: Settings
    questionnaire: Questionnaire
    founder_name: str
    company_name: str


class ReviewFollowUp(BaseModel):
    """A follow-up as the reviewer returns it. Strict for OpenAI's structured output: no extra fields
    and no defaults."""

    model_config = ConfigDict(extra="forbid")

    question_id: int = Field(description="The ID of the question the follow-up belongs to.")
    question: str = Field(description="The follow-up question, in German.")
    explanation: str = Field(description="In German: what is missing, vague or contradictory in the answer.")


class ReviewOutput(BaseModel):
    """The reviewer's answer: the selected follow-ups, at most one per question."""

    model_config = ConfigDict(extra="forbid")

    follow_ups: list[ReviewFollowUp] = Field(description="The selected follow-ups, at most one per question.")


class WrittenAnswer(BaseModel):
    """What the founder said about one question, as the writing down returns it."""

    model_config = ConfigDict(extra="forbid")

    question_id: int = Field(description="The ID of the question.")
    text: str = Field(description="The founder's answer in their own words; empty if nothing was said about it.")


class WrittenDown(BaseModel):
    """The writing down's answer (app/ai/writer.py): the answers per question, the summary, and
    whether the founder wants to end the conversation now. Strict for OpenAI's structured output: no
    extra fields and no defaults."""

    model_config = ConfigDict(extra="forbid")

    answers: list[WrittenAnswer] = Field(description="One entry per question of the questionnaire.")
    summary: str = Field(description="A short statement of all answers, four to six sentences, without judgement.")
    founder_wants_to_stop: bool = Field(description="True only if the founder clearly wants to end the conversation now.")


class SearchResult(BaseModel):
    """One web search result: only what the search returns, no page is loaded."""

    title: str
    link: str
    snippet: str = ""  # a few results come without one


class StartRequest(BaseModel):
    """START: the browser's WebRTC offer for the call to OpenAI."""

    sdp: str = Field(min_length=1, max_length=100_000, description="The browser's SDP offer.")


class StartResponse(BaseModel):
    """The call is set up: the browser connects to OpenAI with this answer."""

    sdp: str = Field(description="OpenAI's SDP answer for the browser's peer connection.")
    agent_name: str = Field(description="The agent's name in this conversation.")


class EndRequest(BaseModel):
    """The browser reports the end of its call, once."""

    reason: Literal["stopped", "connection_lost"] = Field(description=(
        "stopped after the founder confirmed STOPP; connection_lost when the call ended by itself."))


class ConversationView(BaseModel):
    """What the conversation view shows, the same for the founder and the team: the transcript, the
    state and the outcome. Never the questionnaire, the settings or the reviewer's text."""

    id: UUID = Field(description="The conversation's ID.")
    state: ConversationState = Field(description="Where the conversation stands.")
    agent_name: str | None = Field(description="The agent's name in this conversation; null while Ready.")
    created_at: datetime = Field(description="When the access code unlocked it.")
    started_at: datetime | None = Field(description="When START was pressed; null while Ready.")
    ended_at: datetime | None = Field(description="When it became Completed or Unfinished.")
    end_reason: EndReason | None = Field(description="Why an Unfinished conversation ended; null otherwise.")
    transcript: list[TranscriptMessage] = Field(description="The saved messages, in order.")
    summary: str | None = Field(description="The summary, only when Completed.")


# --- The team's review of conversations --------------------------------------------------------
class TeamConversationRow(BaseModel):
    """A row of the team's conversation list."""

    id: UUID = Field(description="The conversation's ID.")
    created_at: datetime = Field(description="When the access code unlocked it.")
    started_at: datetime | None = Field(description="When START was pressed; null while Ready.")
    state: ConversationState = Field(description="Where the conversation stands.")
    founder_name: str = Field(description="The founder's name.")
    founder_email: str = Field(description="The founder's email.")
    company_name: str = Field(description="The founder's company.")


class TeamConversationDetail(BaseModel):
    """One conversation for the team: the same view the founder sees, plus the team-only details."""

    view: ConversationView = Field(description="Exactly what the founder sees: transcript, state and outcome.")
    founder_name: str = Field(description="The founder's name.")
    founder_email: str = Field(description="The founder's email.")
    company_name: str = Field(description="The founder's company.")
    settings: Settings | None = Field(description="The settings the conversation ran with; null while Ready.")
    questionnaire: Questionnaire | None = Field(description=(
        "The questionnaire with answers, summary and follow-ups; null while Ready."))


class ErrorResponse(BaseModel):
    """The body of every error response."""

    detail: str = Field(description="What went wrong, in plain German, ready to show to the user.")
