"""The writing down: turns the saved conversation into the founder's answers, the summary, and whether
the founder wants to stop. Called by the submit tools (app/ai/tools.py), which the note-taker calls
without any input when the voice agent hands the writing down over.

- One structured call (app/ai/structured.py) with the note-taker's model and thinking level from the
  conversation's settings: the settings' „Protokollant" is the AI that writes the answers down. The
  instructions come from the context system (`writer_answers` after the questions, `writer_round`
  after the follow-up round); the rules both share live once, in `writer.rules`.
- After the questions, the input is the questionnaire (IDs, topics, questions, contexts) and the
  whole transcript, so an answer collects everything the founder said about its question, wherever
  it was said. After the follow-up round, it is the questionnaire with the answers and follow-ups,
  the earlier summary, and only the transcript since the round began.
- Whatever the model returns, the result has exactly one answer per question of the questionnaire,
  in its order: unknown IDs are dropped, the first entry per ID counts, and a missing one is empty.
  So the callers' empty checks can rely on every question being present.
- A summary that is empty or longer than `SUMMARY_MAX_CHARS` (it is read aloud from one commentary)
  is refused and counts as a failed attempt. When every attempt failed, the result is None.

Runs on the event loop: the awaited structured call holds no database session.
"""

import logging

from app import config
from app.ai import structured
from app.context import prompt
from app.schemas import Questionnaire, Settings, TranscriptMessage, WrittenAnswer, WrittenDown

logger = logging.getLogger(__name__)


async def write_down(questionnaire: Questionnaire, transcript: list[TranscriptMessage], settings: Settings,
                     follow_up_round: bool) -> WrittenDown | None:
    """The written answers, one per question in questionnaire order, or None after failed attempts."""
    fields = {"id", "topic", "question", "answer", "follow_up"} if follow_up_round else {"id", "topic", "question", "context"}
    payload: dict = {"questionnaire": [entry.model_dump(include=fields, exclude_none=True) for entry in questionnaire.entries]}
    if follow_up_round:
        payload["summary"] = questionnaire.summary
    payload["transcript"] = [message.model_dump(include={"speaker", "text"}) for message in transcript]
    language = config.LANGUAGES[settings.language].name
    written = await structured.call(
        "write_down", settings.note_taker_model, settings.note_taker_thinking,
        prompt("writer_round" if follow_up_round else "writer_answers", language=language), payload, WrittenDown,
        accept=lambda output: 0 < len(output.summary.strip()) <= config.SUMMARY_MAX_CHARS)
    if written is None:
        return None
    texts: dict[int, str] = {}
    for answer in written.answers:
        texts.setdefault(answer.question_id, answer.text.strip())
    answers = [WrittenAnswer(question_id=entry.id, text=texts.get(entry.id, "")) for entry in questionnaire.entries]
    logger.info("event=written_down round=%s answered=%d of=%d wants_to_stop=%s", follow_up_round,
                sum(1 for answer in answers if answer.text), len(answers), written.founder_wants_to_stop)
    return WrittenDown(answers=answers, summary=written.summary.strip(),
                       founder_wants_to_stop=written.founder_wants_to_stop)
