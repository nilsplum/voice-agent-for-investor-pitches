"""The reviewer against the fake Responses API: the request carries the strict schema, the
conversation's settings, the answers and the transcript, the result holds at most one follow-up per
known question, and failed attempts are retried after the configured pause up to the configured
attempts."""

import json
from collections.abc import AsyncIterator

import pytest

from app import config, http
from app.ai.reviewer import review
from app.context import default_catalog, prompt
from app.conversations import new_questionnaire
from app.schemas import ReviewOutput, Settings, TranscriptMessage
from fakes import TIMEOUT

SETTINGS = Settings.model_validate({**config.DEFAULT_SETTINGS, "reviewer_model": "gpt-6.1-terra",
                                    "reviewer_thinking": "high"})


@pytest.fixture
async def reviewer(fake, secrets) -> AsyncIterator[None]:
    async with http.open_client():
        yield


def answered():
    questionnaire = new_questionnaire(default_catalog())
    for entry in questionnaire.entries:
        entry.answer = f"Antwort {entry.id}"
    return questionnaire


TRANSCRIPT = [TranscriptMessage(speaker="agent", text="Welche Traktion haben Sie bisher?", start_ms=1000, end_ms=2000),
              TranscriptMessage(speaker="founder", text="Es läuft gut.", start_ms=2500, end_ms=3500)]


def follow_up(question_id: int, question: str = "Rückfrage?") -> dict:
    return {"question_id": question_id, "question": question, "explanation": "Fehlt."}


async def test_the_request_carries_the_strict_schema_the_settings_the_answers_and_the_transcript(reviewer, fake):
    fake.responses.append({"follow_ups": []})

    assert await review(answered(), TRANSCRIPT, SETTINGS) == ([], True)

    request = fake.response_requests[0]
    assert (request["model"], request["reasoning"]) == ("gpt-6.1-terra", {"effort": "high"})
    assert request["instructions"] == prompt("reviewer_instructions")
    assert request["text"]["format"] == {"type": "json_schema", "name": "review", "strict": True,
                                         "schema": ReviewOutput.model_json_schema()}
    review_input = json.loads(request["input"])
    assert set(review_input) == {"questionnaire", "transcript"}
    assert review_input["questionnaire"][4] == {
        "id": 5, "topic": "Traktion", "question": "Welche Traktion haben Sie bisher?",
        "context": default_catalog().questions[4].context, "answer": "Antwort 5"}
    assert review_input["transcript"] == [{"speaker": "agent", "text": "Welche Traktion haben Sie bisher?"},
                                          {"speaker": "founder", "text": "Es läuft gut."}]


async def test_only_the_first_follow_up_per_known_question_is_kept_in_questionnaire_order(reviewer, fake):
    fake.responses.append({"follow_ups": [follow_up(11, "Noch etwas?"), follow_up(5, "Erste?"), follow_up(5, "Zweite?"),
                                        follow_up(99), follow_up(3, "  ")]})

    follow_ups, reviewed = await review(answered(), TRANSCRIPT, SETTINGS)

    assert reviewed is True
    assert [(f.question_id, f.question) for f in follow_ups] == [(5, "Erste?"), (11, "Noch etwas?")]


async def test_a_second_message_item_does_not_break_the_review(reviewer, fake):
    fake.responses.append({"output": [
        {"type": "message", "content": [{"type": "output_text", "text": "Thinking about it ..."}]},
        {"type": "message", "content": [{"type": "output_text", "text": json.dumps({"follow_ups": [follow_up(2)]})}]},
    ]})

    follow_ups, reviewed = await review(answered(), TRANSCRIPT, SETTINGS)

    assert ([f.question_id for f in follow_ups], reviewed) == ([2], True)


async def test_failed_attempts_are_retried_up_to_the_configured_attempts(reviewer, fake, monkeypatch):
    monkeypatch.setattr(config, "STRUCTURED_CALL_TIMEOUT_S", 0.2)
    monkeypatch.setattr(config, "STRUCTURED_CALL_ATTEMPTS", 3)
    fake.responses += [TIMEOUT, 500, {"follow_ups": [follow_up(8)]}]

    follow_ups, reviewed = await review(answered(), TRANSCRIPT, SETTINGS)

    assert ([f.question_id for f in follow_ups], reviewed) == ([8], True)
    assert len(fake.response_requests) == 3

    fake.responses += [TIMEOUT, 429, {"output": []}]
    assert await review(answered(), TRANSCRIPT, SETTINGS) == ([], False)
    assert len(fake.response_requests) == 6
