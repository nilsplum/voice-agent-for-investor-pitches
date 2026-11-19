"""The writing down against the fake Responses API: the request carries the note-taker's model and
thinking level, the prompt of its phase and the right input (the whole transcript after the
questions; the answers, follow-ups, earlier summary and the round's transcript after the round),
the result has exactly one answer per question in questionnaire order, and an unusable summary
counts as a failed attempt."""

import json
from collections.abc import AsyncIterator

import pytest

from app import config, http
from app.ai.writer import write_down
from app.context import default_catalog, prompt
from app.conversations import new_questionnaire
from app.schemas import FollowUp, Settings, TranscriptMessage, WrittenDown
from fakes import SUMMARY, written_down

SETTINGS = Settings.model_validate({**config.DEFAULT_SETTINGS, "note_taker_model": "gpt-6.1-terra",
                                    "note_taker_thinking": "medium"})
TRANSCRIPT = [TranscriptMessage(speaker="agent", text="Welche Traktion haben Sie bisher?", start_ms=1000, end_ms=2000),
              TranscriptMessage(speaker="founder", text="Drei zahlende Piloten.", start_ms=2500, end_ms=3500)]


@pytest.fixture
async def writer(fake, secrets) -> AsyncIterator[None]:
    async with http.open_client():
        yield


async def test_after_the_questions_the_request_carries_the_questions_and_the_whole_transcript(writer, fake):
    fake.responses.append(written_down({5: "Drei zahlende Piloten."}))

    result = await write_down(new_questionnaire(default_catalog()), TRANSCRIPT, SETTINGS, follow_up_round=False)

    request = fake.response_requests[0]
    assert (request["model"], request["reasoning"]) == ("gpt-6.1-terra", {"effort": "medium"})
    assert request["instructions"] == prompt("writer_answers", language="German")
    assert request["text"]["format"]["schema"] == WrittenDown.model_json_schema()
    payload = json.loads(request["input"])
    assert payload["questionnaire"][4] == {"id": 5, "topic": "Traktion", "question": "Welche Traktion haben Sie bisher?",
                                           "context": default_catalog().questions[4].context}
    assert payload["transcript"] == [{"speaker": "agent", "text": "Welche Traktion haben Sie bisher?"},
                                     {"speaker": "founder", "text": "Drei zahlende Piloten."}]
    assert result.summary == SUMMARY


async def test_after_the_round_the_request_carries_the_answers_follow_ups_and_earlier_summary(writer, fake):
    questionnaire = new_questionnaire(default_catalog())
    for entry in questionnaire.entries:
        entry.answer = f"Antwort {entry.id}"
    questionnaire.entries[4].follow_up = FollowUp(question="Wie viel Umsatz?", explanation="Keine Zahlen.")
    questionnaire.summary = "Die erste Zusammenfassung."
    fake.responses.append(written_down({5: "48.000 Euro."}, summary="Die finale Zusammenfassung."))

    await write_down(questionnaire, TRANSCRIPT, SETTINGS, follow_up_round=True)

    request = fake.response_requests[0]
    assert request["instructions"] == prompt("writer_round", language="German")
    payload = json.loads(request["input"])
    assert payload["summary"] == "Die erste Zusammenfassung."
    assert payload["questionnaire"][4] == {"id": 5, "topic": "Traktion", "question": "Welche Traktion haben Sie bisher?",
                                           "answer": "Antwort 5",
                                           "follow_up": {"question": "Wie viel Umsatz?", "explanation": "Keine Zahlen."}}
    assert "context" not in payload["questionnaire"][0] and "follow_up" not in payload["questionnaire"][0]


async def test_every_question_gets_exactly_one_answer_in_questionnaire_order(writer, fake):
    fake.responses.append(written_down({11: "Nein.", 5: "  Erste.  ", 99: "Unbekannt."}, stop=True))
    fake.responses[-1]["answers"].append({"question_id": 5, "text": "Zweite."})

    result = await write_down(new_questionnaire(default_catalog()), TRANSCRIPT, SETTINGS, follow_up_round=False)

    assert [answer.question_id for answer in result.answers] == list(range(1, 12))
    texts = {answer.question_id: answer.text for answer in result.answers}
    assert texts[5] == "Erste." and texts[11] == "Nein." and texts[1] == ""
    assert result.founder_wants_to_stop is True


async def test_an_empty_or_too_long_summary_is_a_failed_attempt(writer, fake, monkeypatch):
    monkeypatch.setattr(config, "STRUCTURED_CALL_ATTEMPTS", 3)
    fake.responses += [written_down({}, summary=" "), written_down({}, summary="x" * (config.SUMMARY_MAX_CHARS + 1)),
                       written_down({}, summary="Passt.")]

    result = await write_down(new_questionnaire(default_catalog()), TRANSCRIPT, SETTINGS, follow_up_round=False)

    assert result.summary == "Passt." and len(fake.response_requests) == 3

    fake.responses += [written_down({}, summary=" ")] * 3
    assert await write_down(new_questionnaire(default_catalog()), TRANSCRIPT, SETTINGS, follow_up_round=False) is None
