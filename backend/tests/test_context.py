"""The context system: the shipped documents load, every prompt and text renders (so a misspelled
placeholder fails here and not at START), and a broken, missing or unknown document fails with a
message that names the file, also when the app starts."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager

from app import config
from app.context import (ENTRY_DOCUMENTS, ContextError, PromptsDocument, context, default_catalog, load_context, prompt,
                         render_faq, render_follow_ups, render_question_references, render_questionnaire,
                         render_search_results, text)
from app.conversations import new_questionnaire
from app.main import create_app
from app.schemas import FollowUp, SearchResult


@pytest.fixture
def documents(tmp_path: Path) -> Iterator[Path]:
    """A copy of the shipped documents to break; the cached context is reloaded afterwards."""
    copy = tmp_path / "documents"
    shutil.copytree(config.CONTEXT_DOCUMENTS_DIR, copy)
    yield copy
    context.cache_clear()


def test_the_shipped_documents_load():
    load_context(config.CONTEXT_DOCUMENTS_DIR)

    catalog = default_catalog()
    assert [question.id for question in catalog.questions] == list(range(1, 12))
    assert catalog.next_id == 12


# Every placeholder the code fills in. str.format fails on any other, so a misspelled placeholder
# in a document fails this test.
SAMPLE_VALUES = {
    "agent_name": "Mira", "founder_name": "Erika Muster", "company_name": "Nordlicht Robotics", "language": "German",
    "faq": "(faq)", "questionnaire": "(questionnaire)", "summary": "(summary)", "follow_ups": "(follow-ups)",
    "follow_up": "(follow-up)", "questions": "(questions)", "results": "(results)", "id": 5, "topic": "Traktion",
    "question": "(question)", "context": "(context)", "answer": "(answer)", "title": "(title)", "link": "(link)",
    "snippet": "(snippet)",
}


def test_every_prompt_and_text_renders_with_the_values_the_code_fills_in():
    documents = context()
    for name in PromptsDocument.model_fields:
        assert "{" not in prompt(name, **SAMPLE_VALUES)
    for document in ENTRY_DOCUMENTS:
        for entry in getattr(documents, document).entries:
            assert "{" not in text(f"{document}.{entry}", **SAMPLE_VALUES)


def test_the_render_functions_turn_lists_into_prompt_text():
    entries = new_questionnaire(default_catalog()).entries
    entries[4].follow_up = FollowUp(question="Wie viele Kunden?", explanation="Keine Zahlen.")

    assert render_questionnaire(entries).splitlines()[4].startswith("5. Traktion: Welche Traktion haben Sie bisher?")
    assert len(render_faq().splitlines()) == len(context().faq.faq)
    assert render_follow_ups(entries) == "- Question 5 (Traktion): Wie viele Kunden?"
    assert "\n- Question 5 (Traktion): Wie viele Kunden?\n" in text("messages.follow_up_round",
                                                                    follow_ups=render_follow_ups(entries))
    assert render_search_results([SearchResult(title="Nordlicht Robotics", link="https://nordlicht.example",
                                               snippet="Lagerroboter.")]) == (
        "- Nordlicht Robotics (https://nordlicht.example): Lagerroboter.")
    assert render_question_references(entries[4:6]) == "question 5 (Traktion), question 6 (Zielmarkt)"


def test_a_prompt_naming_a_missing_entry_is_refused(documents):
    (documents / "prompts.json").write_text((documents / "prompts.json").read_text().replace(
        "voice_agent.style", "voice_agent.stlye"))

    with pytest.raises(ContextError, match="prompts.json: voice_instructions names voice_agent.stlye"):
        load_context(documents)


@pytest.mark.parametrize(("content", "message"), [
    ("{", "catalog.json is not valid JSON"),
    ('{"default_questions": []}', "catalog.json at default_questions"),
    ('{"default_questions": [{"id": 1, "topic": "A", "question": "B?", "context": ""}]}',
     "catalog.json at default_questions.0.context"),
    ('{"default_questions": [{"id": 1, "topic": "A", "question": "B?", "context": "C"},'
     ' {"id": 1, "topic": "D", "question": "E?", "context": "F"}]}', "catalog.json at the top level"),
])
def test_a_broken_document_names_the_file_and_the_problem(documents, content, message):
    (documents / "catalog.json").write_text(content)

    with pytest.raises(ContextError, match=message):
        load_context(documents)


def test_a_missing_or_unknown_document_is_named(documents):
    (documents / "catalog.json").rename(documents / "katalog.json")

    with pytest.raises(ContextError, match="katalog.json"):
        load_context(documents)

    (documents / "katalog.json").unlink()
    with pytest.raises(ContextError, match="catalog.json is missing"):
        load_context(documents)


async def test_a_broken_document_stops_the_app(documents, secrets, monkeypatch):
    (documents / "catalog.json").write_text("{")
    monkeypatch.setattr(config, "CONTEXT_DOCUMENTS_DIR", documents)
    context.cache_clear()

    with pytest.raises(ContextError, match="catalog.json"):
        async with LifespanManager(create_app()):
            pass
