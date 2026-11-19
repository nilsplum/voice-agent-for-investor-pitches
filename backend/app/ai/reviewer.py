"""The reviewer: reads all answers against their questions, against each other and against the
conversation, and selects the follow-ups of the follow-up round. Called by `submit_initial` while
the voice agent reads the summary aloud.

- One structured call (app/ai/structured.py) with the reviewer's model and thinking level from the
  conversation's settings and the instructions `reviewer_instructions` from the context system. The
  input is the questionnaire (IDs, topics, questions, contexts, answers) and the saved transcript
  (speaker and text of each message). The transcript shows which questions the voice agent already
  followed up on during the questions, so the review never asks about them again. Selecting nothing
  is normal: then there is no follow-up round.
- Whatever the model returns, only follow-ups for questions of this questionnaire are kept, and only
  the first one per question, so "at most one per question" always holds.
- When every attempt failed, the result is "no follow-ups, not reviewed", and the conversation
  completes without a follow-up round. The log line counts the transcript's messages and the
  follow-ups, never their text.

Runs on the event loop: the awaited structured call holds no database session.
"""

import logging

from app.ai import structured
from app.context import prompt
from app.schemas import Questionnaire, ReviewFollowUp, ReviewOutput, Settings, TranscriptMessage

logger = logging.getLogger(__name__)


async def review(questionnaire: Questionnaire, transcript: list[TranscriptMessage],
                 settings: Settings) -> tuple[list[ReviewFollowUp], bool]:
    """The selected follow-ups in questionnaire order, and whether the review succeeded."""
    payload = {
        "questionnaire": [entry.model_dump(include={"id", "topic", "question", "context", "answer"})
                          for entry in questionnaire.entries],
        "transcript": [message.model_dump(include={"speaker", "text"}) for message in transcript],
    }
    output = await structured.call("review", settings.reviewer_model, settings.reviewer_thinking,
                                   prompt("reviewer_instructions"), payload, ReviewOutput)
    if output is None:
        return [], False
    follow_ups = _selected(output, questionnaire)
    logger.info("event=review messages=%d follow_ups=%d", len(transcript), len(follow_ups))
    return follow_ups, True


def _selected(output: ReviewOutput, questionnaire: Questionnaire) -> list[ReviewFollowUp]:
    """Only questions of this questionnaire, the first follow-up per question, none without text."""
    known = {entry.id for entry in questionnaire.entries}
    selected: dict[int, ReviewFollowUp] = {}
    for follow_up in output.follow_ups:
        if follow_up.question_id in known and follow_up.question_id not in selected and follow_up.question.strip():
            selected[follow_up.question_id] = follow_up
    return [selected[entry.id] for entry in questionnaire.entries if entry.id in selected]
