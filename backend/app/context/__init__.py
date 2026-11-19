"""The context system: every text the AI reads, and the default question catalog, as validated JSON
documents.

Each document in `config.CONTEXT_DOCUMENTS_DIR` (app/context/documents) has one purpose and its own
Pydantic model: the fields of `Context`, named like the files.
- Entry documents (voice_agent, note_taker, writer, reviewer, messages) hold named texts:
  `{"entries": {"name": "text"}}`. A text is addressed as `document.entry`, for example
  `messages.goodbye`.
- prompts.json says which entries, in which order, make up each prompt. So any piece (the
  conversation rules, the FAQ) can be part of any prompt without being written twice.
- tools.json, faq.json and catalog.json have their own shapes.

`context()` loads and validates all documents once. The app's lifespan calls it at startup, before
anything else uses it, so a broken document stops the app with one message that names the file and
the problem; that every entry named in prompts.json exists is checked then too.

Texts are rendered with `str.format`: `{name}` is a placeholder, and literal braces are written
`{{` and `}}`. The values filled in are never parsed again, so founders' words cannot break a
prompt. The render functions below are the one place where lists (the questionnaire, the FAQ, the
follow-ups, the search results) become prompt text. Prompts are rendered once, when a conversation
starts; the messages of app/ai/tools.py when they are sent.

The documents are never written at runtime. The team's catalog in the database is seeded from
`default_catalog()` and reset to it (app/team_values.py), and the app reads only the database.

Runs wherever it is called; its only file work is the one cached load at startup.
"""

import json
from functools import cache
from pathlib import Path
from typing import Annotated, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

from app import config
from app.schemas import Catalog, CatalogQuestion, QuestionnaireEntry, SearchResult, ToolName, check_unique_ids

Text = Annotated[str, StringConstraints(min_length=1)]
ENTRY_DOCUMENTS = ("voice_agent", "note_taker", "writer", "reviewer", "messages")


class ContextError(RuntimeError):
    """A document is missing, unknown or broken. The message names the file and the problem."""


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EntryDocument(Document):
    """voice_agent.json, note_taker.json, writer.json, reviewer.json and messages.json: named texts."""

    entries: dict[str, Text]


class PromptsDocument(Document):
    """prompts.json: the entries (`document.entry`) each prompt consists of, in order."""

    voice_instructions: list[str] = Field(min_length=1)
    voice_kickoff: list[str] = Field(min_length=1)
    note_taker_instructions: list[str] = Field(min_length=1)
    note_taker_kickoff: list[str] = Field(min_length=1)
    writer_answers: list[str] = Field(min_length=1)
    writer_round: list[str] = Field(min_length=1)
    reviewer_instructions: list[str] = Field(min_length=1)


class ToolText(Document):
    description: Text
    fields: dict[str, Text]  # the descriptions of the tool's fields; empty for a tool without input


class ToolsDocument(Document):
    """tools.json: each tool's description and the descriptions of its fields (app/ai/tools.py)."""

    tools: dict[ToolName, ToolText]

    @model_validator(mode="after")
    def check_tools(self) -> Self:
        if missing := set(get_args(ToolName)) - set(self.tools):
            raise ValueError(f"tools missing: {', '.join(sorted(missing))}")
        return self


class FaqEntry(Document):
    question: Text
    answer: Text


class FaqDocument(Document):
    """faq.json: the answers to questions about this process, the only source the agent answers them
    from."""

    faq: list[FaqEntry] = Field(min_length=1)


class CatalogDocument(Document):
    """catalog.json: the default question catalog, in German, because the team reads and edits it."""

    default_questions: list[CatalogQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def check_ids(self) -> Self:
        check_unique_ids([question.id for question in self.default_questions])
        return self


class Context(Document):
    """All documents, one field per file (`catalog` is catalog.json)."""

    prompts: PromptsDocument
    voice_agent: EntryDocument
    note_taker: EntryDocument
    writer: EntryDocument
    reviewer: EntryDocument
    messages: EntryDocument
    tools: ToolsDocument
    faq: FaqDocument
    catalog: CatalogDocument

    @model_validator(mode="after")
    def check_prompt_entries(self) -> Self:
        for prompt_name, keys in self.prompts:
            for key in keys:
                document, _, entry = key.partition(".")
                if document not in ENTRY_DOCUMENTS or entry not in getattr(self, document).entries:
                    raise ValueError(f"prompts.json: {prompt_name} names {key}, which does not exist")
        return self


def load_context(directory: Path) -> Context:
    """Reads and validates every document of `directory`; raises ContextError naming the file."""
    names = set(Context.model_fields)
    present = {path.stem for path in directory.glob("*.json")}
    if unknown := sorted(present - names):
        raise ContextError(f"Unknown context document {unknown[0]}.json in {directory}: every document "
                           "needs its field in app.context.Context.")
    raw = {}
    for name in names:
        path = directory / f"{name}.json"
        try:
            raw[name] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ContextError(f"The context document {path.name} is missing in {directory}.") from None
        except json.JSONDecodeError as error:
            raise ContextError(f"The context document {path.name} is not valid JSON: {error.msg} "
                               f"(line {error.lineno}, column {error.colno}).") from None
    try:
        return Context.model_validate(raw)
    except ValidationError as error:
        # The first part of an error location is the document's name, the rest the place in it. A
        # check across documents (prompts.json's entries) has no location and names the file itself.
        problems = "; ".join(
            f"{e['loc'][0]}.json at {'.'.join(map(str, e['loc'][1:])) or 'the top level'}: {e['msg']}"
            if e["loc"] else e["msg"] for e in error.errors())
        raise ContextError(f"A context document is invalid: {problems}") from None


@cache
def context() -> Context:
    """The validated documents, loaded once per process."""
    return load_context(config.CONTEXT_DOCUMENTS_DIR)


# --- Rendering --------------------------------------------------------------------------
def text(key: str, **values: object) -> str:
    """One entry (`document.entry`) with its placeholders filled in."""
    document, _, entry = key.partition(".")
    return getattr(context(), document).entries[entry].format(**values)


def prompt(name: str, **values: object) -> str:
    """A prompt of prompts.json: its entries joined with blank lines, placeholders filled in."""
    keys = getattr(context().prompts, name)
    return "\n\n".join(text(key, **values) for key in keys)


def render_questionnaire(entries: list[QuestionnaireEntry]) -> str:
    return "\n".join(text("voice_agent.questionnaire_item", id=entry.id, topic=entry.topic, question=entry.question,
                          context=entry.context) for entry in entries)


def render_faq() -> str:
    return "\n".join(text("voice_agent.faq_item", question=item.question, answer=item.answer)
                     for item in context().faq.faq)


def render_follow_ups(entries: list[QuestionnaireEntry]) -> str:
    """The selected follow-ups in questionnaire order, as the agent gets them for the follow-up round."""
    return "\n".join(text("messages.follow_up_item", id=entry.id, topic=entry.topic, follow_up=entry.follow_up.question)
                     for entry in entries if entry.follow_up)


def render_search_results(results: list[SearchResult]) -> str:
    return "\n".join(text("messages.search_result_item", title=result.title, link=result.link, snippet=result.snippet)
                     for result in results)


def render_question_references(entries: list[QuestionnaireEntry]) -> str:
    """For example "question 5 (Traktion), question 8 (Finanzierungsbedarf)" in an AI message."""
    return ", ".join(text("messages.question_reference", id=entry.id, topic=entry.topic) for entry in entries)


def default_catalog() -> Catalog:
    """The shipped default catalog. `next_id` is derived, never written by hand."""
    questions = context().catalog.default_questions
    return Catalog(questions=questions, next_id=max(question.id for question in questions) + 1)
