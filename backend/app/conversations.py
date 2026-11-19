"""Conversations: their states, their questionnaire, their transcript and what the views show (the
founder's, and the team's list and detail, which read only from here, without live updates).

States: Ready (unlocked, not started) -> In progress (the voice session runs) -> Completed (the
answers were written down: every one, or as far as the founder went when they ended early) or
Unfinished (ended any other way; final). A failed start goes back to Ready.
- A conversation is created only by `access_codes.redeem_access_code`, in state Ready; unlocking
  here ("Neues Gespräch") goes through that same redemption step as the signup does.
- `claim_start` is the one way into In progress. It copies the team's current settings and catalog
  into the conversation (the questionnaire), so later edits never change it.
- Every later write is conditional on In progress, so whichever comes first wins: the store steps
  of the tools, `finish_conversation` (Unfinished) and `revert_start` (back to Ready). The call
  (app/ai/live.py) writes before it closes a session itself, so the stored state never lags behind.
- A call's writes are also conditional on its own START (`started_at`, the attempt's token). After a
  failed start the founder may press START again while the old call is still cleaning up; the old
  call's writes then match nothing, so they can never reset or fill the new attempt.
- Completed is reached only in the step that stores the last answers: `store_initial` when the
  founder ended early, `store_review` when the review selected no follow-ups, otherwise
  `store_follow_up_answers`.
- `save_message` never writes for a Ready conversation, so a message flushed after a failed start
  is dropped instead of reappearing in the next attempt.

Every function that takes a session is a database step for `db.run_db` and runs in a worker
thread; none of them waits on anything outside the database.
"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.access_codes import redeem_access_code
from app.context import text
from app.errors import AppError
from app.models import Conversation, Founder, TranscriptMessageRow, utcnow
from app.schemas import (Catalog, ConversationSummary, ConversationView, EndReason, FollowUp, Questionnaire,
                         QuestionnaireEntry, ReviewFollowUp, Settings, StartedConversation, TeamConversationDetail,
                         TeamConversationRow, TranscriptMessage)
from app import team_values
from app.security import LOGIN_REQUIRED

logger = logging.getLogger(__name__)

NOT_FOUND = "Dieses Gespräch gibt es nicht."
CANNOT_START = "Dieses Gespräch kann nicht mehr gestartet werden."


# --- The founder's list and new conversations ---------------------------------------------
def list_founder_conversations(session: Session, founder_id: UUID) -> list[ConversationSummary]:
    """The founder's conversations, newest first."""
    rows = session.scalars(select(Conversation).where(Conversation.founder_id == founder_id)
                           .order_by(Conversation.created_at.desc()))
    return [ConversationSummary.model_validate(row) for row in rows]


def unlock_conversation(session: Session, founder_id: UUID, code: str) -> ConversationSummary:
    founder = session.get(Founder, founder_id)
    if founder is None:  # the cookie outlived its founder, for example after a database reset
        raise AppError(LOGIN_REQUIRED, "reason=founder_missing", status_code=401)
    return ConversationSummary.model_validate(redeem_access_code(session, code, founder))


def _founders_conversation(session: Session, founder_id: UUID, conversation_id: UUID) -> Conversation:
    """The conversation, if it belongs to this founder; another founder's is answered like a missing one."""
    row = session.get(Conversation, conversation_id)
    if row is None or row.founder_id != founder_id:
        raise AppError(NOT_FOUND, f"reason=conversation_not_found conversation_id={conversation_id}", status_code=404)
    return row


def check_owner(session: Session, founder_id: UUID, conversation_id: UUID) -> None:
    _founders_conversation(session, founder_id, conversation_id)


# --- START and a failed start -------------------------------------------------------------
def new_questionnaire(catalog: Catalog) -> Questionnaire:
    """The conversation's own copy of the catalog, with nothing written down yet."""
    return Questionnaire(entries=[QuestionnaireEntry(id=question.id, topic=question.topic, question=question.question,
                                                     context=question.context, answer=None, follow_up=None,
                                                     follow_up_answer=None) for question in catalog.questions],
                         summary=None, reviewed=None)


def claim_start(session: Session, founder_id: UUID, conversation_id: UUID) -> StartedConversation:
    """Ready -> In progress in one conditional update, with the copies of settings and catalog.

    Only one of two simultaneous STARTs (two tabs) can match `state = 'ready'`; the other gets 409.
    """
    settings = team_values.read(session, team_values.TEAM_SETTINGS)
    questionnaire = new_questionnaire(team_values.read(session, team_values.TEAM_CATALOG))
    started_at = utcnow()
    claimed = session.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id, Conversation.founder_id == founder_id,
               Conversation.state == "ready")
        .values(state="in_progress", started_at=started_at, settings=settings.model_dump(mode="json"),
                questionnaire=questionnaire.model_dump(mode="json"))
        .returning(Conversation.id)
    ).first()
    if claimed is None:
        row = _founders_conversation(session, founder_id, conversation_id)
        raise AppError(CANNOT_START, f"reason=not_ready conversation_id={conversation_id} state={row.state}",
                       status_code=409)
    founder = session.get(Founder, founder_id)
    logger.info("event=start_claimed conversation_id=%s questions=%d", conversation_id, len(questionnaire.entries))
    return StartedConversation(started_at=started_at, settings=settings, questionnaire=questionnaire,
                               founder_name=founder.name, company_name=founder.company_name)


def _this_start(conversation_id: UUID, started_at: datetime | None) -> list:
    """The conditions of a write for the running attempt that started at `started_at` (any running
    attempt if None, for an end reported without a call)."""
    conditions = [Conversation.id == conversation_id, Conversation.state == "in_progress"]
    if started_at is not None:
        conditions.append(Conversation.started_at == started_at)
    return conditions


def revert_start(session: Session, conversation_id: UUID, started_at: datetime) -> None:
    """A failed start: In progress -> Ready, with the copies and any saved message (a greeting)
    removed, so the access code is not lost. Leaves every other state, and every other attempt, alone."""
    reverted = session.execute(
        update(Conversation).where(*_this_start(conversation_id, started_at))
        .values(state="ready", started_at=None, settings=None, questionnaire=None)
    ).rowcount
    if reverted:
        session.execute(delete(TranscriptMessageRow).where(TranscriptMessageRow.conversation_id == conversation_id))
        logger.info("event=start_reverted conversation_id=%s", conversation_id)


# --- The questionnaire, written by the tools ------------------------------------------------
def _in_progress(session: Session, conversation_id: UUID, started_at: datetime) -> tuple[Conversation, Questionnaire]:
    """The running attempt, locked until the step ends, and its questionnaire."""
    row = session.get(Conversation, conversation_id, with_for_update=True)
    if row is None or row.state != "in_progress" or row.started_at != started_at:
        raise AppError.for_ai(f"reason=conversation_ended conversation_id={conversation_id}",
                              text("messages.conversation_ended"))
    return row, Questionnaire.model_validate(row.questionnaire)


def _complete(row: Conversation) -> None:
    row.state = "completed"
    row.ended_at = utcnow()
    logger.info("event=conversation_completed conversation_id=%s", row.id)


def store_initial(session: Session, conversation_id: UUID, started_at: datetime, answers: dict[int, str],
                  summary: str, ended_early: bool) -> Questionnaire | None:
    """The first writing down's answers and summary, only once: a second one changes nothing and
    returns None, so the summary is never read twice and two reviews never race. An empty answer is
    stored as unanswered (null). When the founder ended early, the conversation is complete at once:
    no review and no follow-up round, so `reviewed` stays null."""
    row, questionnaire = _in_progress(session, conversation_id, started_at)
    if questionnaire.summary is not None:
        return None
    for entry in questionnaire.entries:
        entry.answer = answers[entry.id] or None
    questionnaire.summary = summary
    row.questionnaire = questionnaire.model_dump(mode="json")
    if ended_early:
        _complete(row)
    return questionnaire


def store_review(session: Session, conversation_id: UUID, started_at: datetime, follow_ups: list[ReviewFollowUp],
                 reviewed: bool) -> Questionnaire:
    """The review's follow-ups. Without any (none selected, or the review failed), the conversation
    is complete: there is no follow-up round."""
    row, questionnaire = _in_progress(session, conversation_id, started_at)
    selected = {follow_up.question_id: follow_up for follow_up in follow_ups}
    for entry in questionnaire.entries:
        if follow_up := selected.get(entry.id):
            entry.follow_up = FollowUp(question=follow_up.question, explanation=follow_up.explanation)
    questionnaire.reviewed = reviewed
    row.questionnaire = questionnaire.model_dump(mode="json")
    if not follow_ups:
        _complete(row)
    return questionnaire


def store_follow_up_answers(session: Session, conversation_id: UUID, started_at: datetime,
                            answers: dict[int, str], summary: str) -> Questionnaire:
    """The follow-up round: every non-empty answer (to a follow-up, or an addition to another
    question) goes into its entry, the final summary replaces the first one, and the conversation
    is complete. So the success message and the team see the facts of the whole conversation."""
    row, questionnaire = _in_progress(session, conversation_id, started_at)
    for entry in questionnaire.entries:
        if answers.get(entry.id):
            entry.follow_up_answer = answers[entry.id]
    questionnaire.summary = summary
    row.questionnaire = questionnaire.model_dump(mode="json")
    _complete(row)
    return questionnaire


# --- Transcript and the end -------------------------------------------------------------
def save_message(session: Session, conversation_id: UUID, started_at: datetime, message: TranscriptMessage) -> None:
    """A message of the attempt that started at `started_at`; also after it ended (the goodbye),
    never after it went back to Ready. FOR SHARE waits for a revert_start running at the same
    moment, so the check stays true until the message is written."""
    row = session.execute(select(Conversation.state, Conversation.started_at)
                          .where(Conversation.id == conversation_id).with_for_update(read=True)).first()
    if row is None or row.state == "ready" or row.started_at != started_at:
        return
    session.add(TranscriptMessageRow(conversation_id=conversation_id, speaker=message.speaker, text=message.text,
                                     start_ms=message.start_ms, end_ms=message.end_ms))


def read_transcript(session: Session, conversation_id: UUID) -> list[TranscriptMessage]:
    """The saved messages in conversation order: the one reader of the transcript, for the
    conversation view, the writing down and the review. A message in progress is not saved yet."""
    rows = session.scalars(select(TranscriptMessageRow).where(TranscriptMessageRow.conversation_id == conversation_id)
                           .order_by(TranscriptMessageRow.id))
    return [TranscriptMessage(speaker=row.speaker, text=row.text, start_ms=row.start_ms, end_ms=row.end_ms)
            for row in rows]


def finish_conversation(session: Session, conversation_id: UUID, reason: EndReason,
                        started_at: datetime | None) -> None:
    """In progress -> Unfinished with its reason. Leaves every other state alone: a Completed
    conversation stays Completed whatever is reported afterwards."""
    finished = session.execute(
        update(Conversation).where(*_this_start(conversation_id, started_at))
        .values(state="unfinished", end_reason=reason, ended_at=utcnow())
    ).rowcount
    if finished:
        logger.info("event=conversation_unfinished conversation_id=%s reason=%s", conversation_id, reason)


def sweep_after_restart(session: Session) -> None:
    """At startup: no call survives a restart (the call registry is in memory), so every conversation
    still In progress ended with a lost connection."""
    swept = session.execute(
        update(Conversation).where(Conversation.state == "in_progress")
        .values(state="unfinished", end_reason="connection_lost", ended_at=utcnow())
    ).rowcount
    if swept:
        logger.info("event=sweep_after_restart conversations=%d", swept)


# --- What the conversation view shows --------------------------------------------------------
def conversation_view(session: Session, row: Conversation) -> ConversationView:
    """The one builder of the conversation view: the transcript, the state and the outcome. The
    summary is part of it only when Completed; the questionnaire and the settings never are."""
    settings = Settings.model_validate(row.settings) if row.settings else None
    questionnaire = Questionnaire.model_validate(row.questionnaire) if row.questionnaire else None
    return ConversationView(
        id=row.id, state=row.state, agent_name=settings.agent_name if settings else None, created_at=row.created_at,
        started_at=row.started_at, ended_at=row.ended_at, end_reason=row.end_reason,
        transcript=read_transcript(session, row.id),
        summary=questionnaire.summary if row.state == "completed" and questionnaire else None,
    )


def founder_view(session: Session, founder_id: UUID, conversation_id: UUID) -> ConversationView:
    return conversation_view(session, _founders_conversation(session, founder_id, conversation_id))


# --- The team's review ----------------------------------------------------------------------
def list_team_conversations(session: Session) -> list[TeamConversationRow]:
    """Every conversation with its founder, newest first, in one query. The team's page searches and
    filters them in the browser."""
    rows = session.execute(select(Conversation, Founder).join(Founder, Conversation.founder_id == Founder.id)
                           .order_by(Conversation.created_at.desc()))
    return [TeamConversationRow(id=conversation.id, created_at=conversation.created_at,
                                started_at=conversation.started_at, state=conversation.state,
                                founder_name=founder.name, founder_email=founder.email,
                                company_name=founder.company_name) for conversation, founder in rows]


def team_detail(session: Session, conversation_id: UUID) -> TeamConversationDetail:
    """One conversation for the team. Its view is built by the same function as the founder's, so
    both see the same thing; the questionnaire and the settings are the team-only details."""
    row = session.get(Conversation, conversation_id)
    if row is None:
        raise AppError(NOT_FOUND, f"reason=conversation_not_found conversation_id={conversation_id}", status_code=404)
    founder = session.get(Founder, row.founder_id)
    return TeamConversationDetail(
        view=conversation_view(session, row), founder_name=founder.name, founder_email=founder.email,
        company_name=founder.company_name,
        settings=Settings.model_validate(row.settings) if row.settings else None,
        questionnaire=Questionnaire.model_validate(row.questionnaire) if row.questionnaire else None,
    )
