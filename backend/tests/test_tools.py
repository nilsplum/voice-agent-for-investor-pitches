"""The note-taker's tools through the one runner. The web search (results, nothing found, failed)
goes back to the note-taker, whose reply carries it to the voice agent, the startup lookup like
every other search. The writing down with its outcomes (missing answers, the early end, success),
the review and the follow-up round with its tool swap, the completion and the goodbye close reach
the voice agent as backend messages, and the note-taker gets „OK" afterwards; so does every
failure of a handler."""

import asyncio
import json
import logging

from app import config
from app.ai import tools
from app.context import render_follow_ups, render_search_results, text
from app.schemas import SearchResult
from fakes import SUMMARY, TIMEOUT, written_down

MARKER = "SECRET-MARKER-91be"  # stands for something a founder said
OK = text("messages.tool_done")
FOLLOW_UP_5 = {"question_id": 5, "question": "Wie viele zahlende Kunden haben Sie?", "explanation": "Keine Zahlen genannt."}
FOLLOW_UP_8 = {"question_id": 8, "question": "Wofür genau setzen Sie das Kapital ein?",
               "explanation": "Die Verwendung des Kapitals fehlt."}
FINAL_SUMMARY = "Nordlicht baut Roboter für Lager und hat zwölf zahlende Kunden."
RESULT = {"title": "Nordlicht Robotics", "link": "https://nordlicht.example", "snippet": "Lagerroboter.", "position": 1}


def every_answer_but(*missing: int) -> dict:
    return written_down({question_id: "" if question_id in missing else f"Antwort {question_id}"
                         for question_id in range(1, 12)})


# --- web_search ---------------------------------------------------------------------------
async def test_web_search_gives_the_note_taker_the_results_or_why_not_to_pass_on(start, fake, caplog):
    caplog.set_level(logging.INFO)
    call = await start()
    fake.searches += [[RESULT], [], 500]

    outputs = [await call.call_tool("web_search", {"query": f"Nordlicht {MARKER}"}),
               await call.call_tool("web_search", {"query": "nichts"}, call_id="call_2"),
               await call.call_tool("web_search", {"query": "kaputt"}, call_id="call_3")]

    found = render_search_results([SearchResult(title="Nordlicht Robotics", link="https://nordlicht.example",
                                                snippet="Lagerroboter.")])
    assert outputs == [text("messages.search_results", results=found), text("messages.search_empty"),
                       text("messages.search_failed")]
    # The note-taker's reply carries every search's result, so the backend tells the voice agent
    # nothing, and the reply is never a bare „OK", also not for the startup lookup during the greeting.
    assert call.told() == [] and OK not in outputs
    assert [command["type"] for command in call.session.commands] == ["response.item.create", "response.create"] * 3
    assert fake.search_requests[0] == {"q": f"Nordlicht {MARKER}", "num": config.SEARCH_RESULT_COUNT, "hl": "de"}
    assert fake.search_keys[0] == "serper-test"
    assert "tool=web_search outcome=results" in caplog.text and "tool=web_search outcome=empty" in caplog.text
    assert "outcome=unavailable" in caplog.text and "reason=search_failed type=HTTPStatusError status=500" in caplog.text
    assert MARKER not in caplog.text


async def test_the_message_goes_out_before_the_note_taker_gets_its_ok(start, fake):
    call = await start()
    fake.responses.append(every_answer_but(5))

    await call.call_tool("submit_initial")

    assert [command["type"] for command in call.session.commands] == [
        "session.commentary.append", "response.item.create", "response.create"]


async def test_an_unexpected_error_in_a_handler_tells_the_generic_message_and_logs_only_its_type(start, monkeypatch, caplog):
    caplog.set_level(logging.INFO)

    async def explode(call, arguments):
        raise RuntimeError(f"the founder said {MARKER}")

    monkeypatch.setitem(tools.HANDLERS, "web_search", explode)
    call = await start()

    output = await call.call_tool("web_search", {"query": "Nordlicht"})

    assert (output, call.told()) == (OK, [text("messages.generic_error")])
    assert "tool=web_search outcome=failed" in caplog.text and "type=RuntimeError" in caplog.text
    assert MARKER not in caplog.text


async def test_an_unknown_tool_or_invalid_arguments_tell_the_generic_message(start, caplog):
    caplog.set_level(logging.INFO)
    call = await start()

    await call.call_tool("get_questionnaire", {"ids": []})
    await call.call_tool("web_search", {"query": 42, "extra": MARKER}, call_id="call_2")

    assert call.told() == [text("messages.generic_error")] * 2
    assert "reason=tool_not_available" in caplog.text and "reason=invalid_arguments fields=extra,query" in caplog.text
    assert MARKER not in caplog.text


# --- submit_initial ---------------------------------------------------------------------
async def test_submit_initial_with_missing_answers_names_them_and_stores_nothing(start, fake):
    call = await start()
    fake.responses.append(every_answer_but(5, 8))

    output = await call.call_tool("submit_initial")

    assert output == OK
    assert call.told() == [text("messages.missing_answers",
                                questions="question 5 (Traktion), question 8 (Finanzierungsbedarf)")]
    assert call.questionnaire().summary is None
    assert all(entry.answer is None for entry in call.questionnaire().entries)
    assert len(fake.response_requests) == 1  # no review


async def test_submit_initial_says_when_writing_down_failed_and_stores_nothing(start, fake, monkeypatch):
    monkeypatch.setattr(config, "STRUCTURED_CALL_TIMEOUT_S", 0.2)
    call = await start()
    fake.responses += [500, TIMEOUT]

    await call.call_tool("submit_initial")

    assert call.told() == [text("messages.write_down_failed")]
    assert call.questionnaire().summary is None and call.stored()["state"] == "in_progress"


async def test_submit_initial_with_follow_ups_reads_the_summary_reviews_and_starts_the_round(start, fake):
    call = await start()
    duplicate = {**FOLLOW_UP_5, "question": "Eine zweite Rückfrage zu 5?"}
    unknown = {**FOLLOW_UP_5, "question_id": 99}
    fake.responses += [every_answer_but(), {"follow_ups": [FOLLOW_UP_8, FOLLOW_UP_5, duplicate, unknown]}]

    output = await call.call_tool("submit_initial")

    questionnaire = call.questionnaire()
    assert (questionnaire.summary, questionnaire.entries[4].answer, questionnaire.reviewed) == (SUMMARY, "Antwort 5", True)
    selected = {entry.id: entry.follow_up for entry in questionnaire.entries if entry.follow_up}
    assert sorted(selected) == [5, 8]
    assert selected[5].question == FOLLOW_UP_5["question"]  # the first one per question
    assert call.stored()["state"] == "in_progress"

    round_message = text("messages.follow_up_round", follow_ups=render_follow_ups(questionnaire.entries))
    assert (output, call.told()) == (OK, [text("messages.summary", summary=SUMMARY), round_message])
    assert round_message.index("Question 5 (Traktion)") < round_message.index("Question 8 (Finanzierungsbedarf)")
    kinds = [command["type"] for command in call.session.commands]
    assert kinds == ["session.commentary.append", "session.update", "session.commentary.append",
                     "response.item.create", "response.create"]
    phase_2 = call.session.commands_of("session.update")[0]["session"]["delegation"]["responses"]["tools"]
    assert phase_2 == tools.tool_definitions(2)
    assert [tool["name"] for tool in phase_2] == ["web_search", "submit_follow_up"]


async def test_submit_initial_writes_down_and_reviews_the_same_saved_transcript(start, fake, caplog):
    caplog.set_level(logging.INFO)
    call = await start()
    await call.say("agent", "Welche Traktion haben Sie bisher?", 1000, 2000)
    await call.say("founder", f"Noch keine Kunden, {MARKER}.", 2500, 3500)
    # The agent's handover starts a new message, which saves the founder's answer before the tool call.
    await call.say("agent", "Ich schreibe alles auf, einen Moment.", 4000, 5000)
    fake.responses += [every_answer_but(), {"follow_ups": []}]

    await call.call_tool("submit_initial")

    writing, reviewing = fake.response_requests
    assert (writing["model"], writing["reasoning"]) == (config.DEFAULT_SETTINGS["note_taker_model"],
                                                        {"effort": config.DEFAULT_SETTINGS["note_taker_thinking"]})
    assert (reviewing["model"], reviewing["reasoning"]) == (config.DEFAULT_SETTINGS["reviewer_model"],
                                                            {"effort": config.DEFAULT_SETTINGS["reviewer_thinking"]})
    said = [{"speaker": "agent", "text": "Welche Traktion haben Sie bisher?"},
            {"speaker": "founder", "text": f"Noch keine Kunden, {MARKER}."}]
    assert json.loads(writing["input"])["transcript"] == json.loads(reviewing["input"])["transcript"] == said
    assert json.loads(reviewing["input"])["questionnaire"][4]["answer"] == "Antwort 5"
    assert "event=review messages=2" in caplog.text and "tool=submit_initial outcome=completed" in caplog.text
    assert MARKER not in caplog.text


async def test_submit_initial_without_follow_ups_completes_and_closes_after_the_goodbye(start, fake):
    call = await start()
    fake.responses += [every_answer_but(), {"follow_ups": []}]

    await call.call_tool("submit_initial")

    assert call.told() == [text("messages.summary", summary=SUMMARY), text("messages.goodbye")]
    assert call.stored()["state"] == "completed"
    assert call.questionnaire().reviewed is True
    assert call.session.commands_of("session.update") == []
    await call.say("agent", "Vielen Dank und auf Wiedersehen!", 90_000, 92_000)
    await call.session.next_command("session.close")


async def test_a_review_that_fails_twice_completes_without_follow_ups(start, fake, monkeypatch):
    monkeypatch.setattr(config, "STRUCTURED_CALL_TIMEOUT_S", 0.2)
    call = await start()
    fake.responses += [every_answer_but(), 500, TIMEOUT]

    await call.call_tool("submit_initial")

    assert call.told()[-1] == text("messages.goodbye")
    assert len(fake.response_requests) == 1 + config.STRUCTURED_CALL_ATTEMPTS
    questionnaire = call.questionnaire()
    assert questionnaire.reviewed is False and not any(entry.follow_up for entry in questionnaire.entries)
    assert call.stored()["state"] == "completed"


async def test_a_second_submit_initial_changes_nothing_and_says_nothing(start, fake):
    call = await start()
    fake.responses += [every_answer_but(), {"follow_ups": [FOLLOW_UP_5]}]
    await call.call_tool("submit_initial")
    told = call.told()
    fake.responses.append(written_down(summary="Eine andere Zusammenfassung."))

    again = await call.call_tool("submit_initial", call_id="call_2")

    assert (again, call.told()) == (OK, told)
    assert call.questionnaire().summary == SUMMARY
    assert len(fake.response_requests) == 3  # the second writing down, but no second review


async def test_a_founder_who_wants_to_stop_ends_with_what_is_there_and_no_review(start, fake):
    call = await start()
    early = {question_id: f"Antwort {question_id}" if question_id <= 4 else "" for question_id in range(1, 12)}
    fake.responses.append(written_down(early, summary="Vorzeitig beendet.", stop=True))

    await call.call_tool("submit_initial")

    assert call.told() == [text("messages.goodbye")]
    questionnaire = call.questionnaire()
    assert [entry.answer for entry in questionnaire.entries[3:6]] == ["Antwort 4", None, None]
    assert (questionnaire.summary, questionnaire.reviewed) == ("Vorzeitig beendet.", None)
    assert call.stored()["state"] == "completed"
    assert len(fake.response_requests) == 1  # no review
    await call.say("agent", "Danke, auf Wiedersehen!", 90_000, 92_000)
    await call.session.next_command("session.close")


# --- submit_follow_up -------------------------------------------------------------------
async def in_follow_up_round(start, fake):
    call = await start()
    await call.say("agent", "Welche Traktion haben Sie bisher?", 1000, 2000)
    await call.say("founder", "Noch keine Kunden.", 2500, 3500)
    await call.say("agent", "Ich schreibe alles auf.", 4000, 5000)
    fake.responses += [every_answer_but(), {"follow_ups": [FOLLOW_UP_5, FOLLOW_UP_8]}]
    await call.call_tool("submit_initial", call_id="call_initial")
    return call


def round_written(**answers: str) -> dict:
    return written_down({question_id: answers.get(f"question_{question_id}", "") for question_id in range(1, 12)},
                        summary=FINAL_SUMMARY)


async def test_submit_follow_up_names_missing_follow_ups_but_not_empty_additions(start, fake):
    call = await in_follow_up_round(start, fake)
    fake.responses.append(round_written(question_5="Zwölf Kunden."))

    await call.call_tool("submit_follow_up")

    assert call.told()[-1] == text("messages.missing_answers", questions="question 8 (Finanzierungsbedarf)")
    assert call.stored()["state"] == "in_progress"
    assert all(entry.follow_up_answer is None for entry in call.questionnaire().entries)


async def test_submit_follow_up_writes_down_only_the_round(start, fake):
    call = await in_follow_up_round(start, fake)
    await call.say("agent", " Wie viele zahlende Kunden haben Sie?", 20_000, 21_000)
    await call.say("founder", "Zwölf.", 21_500, 22_000)
    await call.say("agent", "Ich schreibe das auf.", 22_500, 23_000)
    fake.responses.append(round_written(question_5="Zwölf.", question_8="Vertrieb."))

    await call.call_tool("submit_follow_up")

    round_input = json.loads(fake.response_requests[-1]["input"])
    # From the agent's handover on: the first round's messages are written down already.
    assert round_input["transcript"] == [
        {"speaker": "agent", "text": "Ich schreibe alles auf. Wie viele zahlende Kunden haben Sie?"},
        {"speaker": "founder", "text": "Zwölf."}]
    assert round_input["summary"] == SUMMARY


async def test_submit_follow_up_stores_answers_and_additions_completes_and_closes(start, fake):
    call = await in_follow_up_round(start, fake)
    fake.responses.append(round_written(question_5="Zwölf zahlende Kunden.", question_8="Für den Vertrieb.",
                                        question_3="Ergänzung: Wir haben auch eine App."))

    await call.call_tool("submit_follow_up")

    entries = {entry.id: entry for entry in call.questionnaire().entries}
    assert entries[5].follow_up_answer == "Zwölf zahlende Kunden."
    assert entries[3].follow_up_answer == "Ergänzung: Wir haben auch eine App."  # an addition, no follow-up
    assert entries[3].follow_up is None and entries[9].follow_up_answer is None
    assert call.questionnaire().summary == FINAL_SUMMARY  # replaces the first one, and is not read aloud
    assert call.told()[-1] == text("messages.goodbye") and len(call.told()) == 3
    assert call.stored()["state"] == "completed"
    await call.say("agent", "Vielen Dank!", 200_000, 201_000)
    await call.session.next_command("session.close")


async def test_a_founder_who_wants_to_stop_in_the_round_ends_with_what_is_there(start, fake):
    call = await in_follow_up_round(start, fake)
    fake.responses.append({**round_written(question_5="Zwölf."), "founder_wants_to_stop": True})

    await call.call_tool("submit_follow_up")

    assert call.told()[-1] == text("messages.goodbye")
    assert call.questionnaire().entries[7].follow_up_answer is None  # follow-up 8 stays unanswered
    assert call.stored()["state"] == "completed"


async def test_the_goodbye_close_waits_for_the_agent_to_speak_after_the_goodbye_went_out(start, fake):
    call = await in_follow_up_round(start, fake)
    await call.say("agent", "Einen Moment, ich schreibe das mit.", 300_000, 301_000)  # the handover
    fake.responses.append(round_written(question_5="Zwölf.", question_8="Vertrieb."))
    await call.call_tool("submit_follow_up", call_id="call_follow_up")

    # A pause longer than the goodbye silence: no close, because the agent has not spoken since the
    # goodbye went out; its handover never counts.
    await asyncio.sleep(config.GOODBYE_SILENCE_S * 2)
    assert call.session.commands_of("session.close") == []

    await call.say("agent", " Vielen Dank, auf Wiedersehen!", 304_000, 305_000)
    await call.session.next_command("session.close")


async def test_founder_speech_after_the_goodbye_delays_the_close_until_both_are_silent(start, fake):
    call = await in_follow_up_round(start, fake)
    fake.responses.append(round_written(question_5="Zwölf.", question_8="Vertrieb."))
    await call.call_tool("submit_follow_up", call_id="call_follow_up")
    loop = asyncio.get_running_loop()

    await call.say("agent", "Vielen Dank, auf Wiedersehen!", 300_000, 301_000)
    await asyncio.sleep(config.GOODBYE_SILENCE_S / 2)
    await call.say("founder", "Ach, eine Sache noch", 301_500, 302_000)
    await asyncio.sleep(config.GOODBYE_SILENCE_S / 2)
    last_spoken = loop.time()
    await call.say("founder", " zum Schluss.", 302_000, 302_500)
    await call.session.next_command("session.close")

    assert loop.time() - last_spoken >= config.GOODBYE_SILENCE_S
