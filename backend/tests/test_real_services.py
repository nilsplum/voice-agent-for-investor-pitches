"""Against the real OpenAI and Serper APIs (marker `real`; only with ./scripts/test.sh --complete):
the writing down on recorded conversations (tests/data/transcripts.json: a simulated founder of a
fictional startup, cut where the agent hands the writing down over), the reviewer on the prepared
questionnaires in tests/data/ (answers in German, as founders give them), each with the transcript
of a conversation that asked every question once and with every offered model (so OpenAI's strict
structured output is confirmed for each), and a real web search. They use the keys in secrets/secrets.yaml and cost a little per run. The model's choices
vary, so the checks are the rules the review must always keep; selecting nothing is allowed."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app import config, http
from app.ai.reviewer import review
from app.ai.writer import write_down
from app.context import default_catalog
from app.conversations import new_questionnaire
from app.schemas import Questionnaire, Settings, TranscriptMessage
from app.search import search

pytestmark = pytest.mark.real

DATA = Path(__file__).parent / "data"
TEAM, TRACTION, FUNDING, ROUND = 2, 5, 8, 9
DEFAULTS = Settings.model_validate(config.DEFAULT_SETTINGS)
# The voice agent's follow-up right away on the vague traction answer, and the founder's reply,
# which stays vague: the review must not ask about traction a second time.
TRACTION_FOLLOW_UP = ("Können Sie das an Zahlen festmachen, zum Beispiel an zahlenden Kunden oder am Umsatz?",
                      "Genaue Zahlen möchte ich dazu gerade noch nicht nennen.")


@pytest.fixture
async def outside_world() -> AsyncIterator[None]:
    async with http.open_client():
        yield


@pytest.fixture(params=list(config.MODELS))
def settings(request: pytest.FixtureRequest) -> Settings:
    """The default settings with each offered model as the reviewer."""
    return Settings.model_validate({**config.DEFAULT_SETTINGS, "reviewer_model": request.param})


def prepared(name: str) -> Questionnaire:
    answers = json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))["answers"]
    questionnaire = new_questionnaire(default_catalog())
    for entry in questionnaire.entries:
        entry.answer = answers[str(entry.id)]
    return questionnaire


def recorded(name: str) -> list[TranscriptMessage]:
    messages = json.loads((DATA / "transcripts.json").read_text(encoding="utf-8"))["transcripts"][name]
    return [TranscriptMessage(speaker=m["speaker"], text=m["text"], start_ms=0, end_ms=0) for m in messages]


async def written(name: str) -> dict[int, str]:
    result = await write_down(new_questionnaire(default_catalog()), recorded(name), DEFAULTS, follow_up_round=False)
    assert result is not None and result.summary
    return {answer.question_id: answer.text for answer in result.answers} | {0: str(result.founder_wants_to_stop)}


async def test_the_writer_writes_every_answer_of_a_complete_conversation(outside_world):
    answers = await written("complete")
    assert all(answers[question_id] for question_id in range(1, 12)) and answers[0] == "False"


async def test_the_writer_keeps_refusals_as_answers(outside_world):
    answers = await written("declined")
    assert all(answers[question_id] for question_id in range(1, 12)) and answers[0] == "False"


async def test_the_writer_applies_a_later_correction(outside_world):
    # The founder said "vier Mitarbeitende" in the pitch and later corrected it to five.
    assert "fünf" in (await written("correction"))[TEAM].lower()


async def test_the_writer_notices_that_the_founder_wants_to_stop(outside_world):
    answers = await written("stop")
    assert answers[0] == "True"
    assert all(answers[question_id] for question_id in range(1, 5))
    assert not any(answers[question_id] for question_id in range(5, 12))


def conversation(questionnaire: Questionnaire,
                 followed_up: dict[int, tuple[str, str]] | None = None) -> list[TranscriptMessage]:
    """The transcript of a conversation that asked every question once and got its written-down
    answer, plus the voice agent's follow-ups right away (question ID -> follow-up and reply)."""
    said: list[tuple[str, str]] = []
    for entry in questionnaire.entries:
        said += [("agent", entry.question), ("founder", entry.answer)]
        if follow_up := (followed_up or {}).get(entry.id):
            said += [("agent", follow_up[0]), ("founder", follow_up[1])]
    return [TranscriptMessage(speaker=speaker, text=text, start_ms=index * 1000, end_ms=index * 1000 + 900)
            for index, (speaker, text) in enumerate(said)]


async def reviewed_ids(questionnaire: Questionnaire, transcript: list[TranscriptMessage], settings: Settings) -> list[int]:
    follow_ups, reviewed = await review(questionnaire, transcript, settings)
    assert reviewed
    ids = [follow_up.question_id for follow_up in follow_ups]
    assert len(set(ids)) == len(ids)  # at most one per question
    return ids


async def test_complete_answers_get_few_follow_ups(outside_world, settings):
    questionnaire = prepared("complete")
    assert len(await reviewed_ids(questionnaire, conversation(questionnaire), settings)) <= 2


async def test_a_vague_traction_answer_gets_a_traction_follow_up(outside_world, settings):
    questionnaire = prepared("vague_traction")
    assert TRACTION in await reviewed_ids(questionnaire, conversation(questionnaire), settings)


async def test_declined_answers_get_no_follow_up(outside_world, settings):
    questionnaire = prepared("declined")
    ids = await reviewed_ids(questionnaire, conversation(questionnaire), settings)
    assert FUNDING not in ids and ROUND not in ids


async def test_a_question_the_agent_already_followed_up_on_gets_no_follow_up(outside_world, settings):
    questionnaire = prepared("vague_traction")
    transcript = conversation(questionnaire, {TRACTION: TRACTION_FOLLOW_UP})
    traction = questionnaire.entries[TRACTION - 1]
    traction.answer = f"{traction.answer} {TRACTION_FOLLOW_UP[1]}"  # the note-taker writes down both replies

    assert TRACTION not in await reviewed_ids(questionnaire, transcript, settings)


async def test_a_real_search_finds_results(outside_world):
    results = await search("Venture Capital", "de")

    assert results and all(result.link.startswith("http") for result in results)
