"""The team-editable values, the agent's settings and the question catalog, under one rule:

- The shipped default (settings: `config.DEFAULT_SETTINGS`; catalog: the context system's
  catalog.json) is copied into the database on the very first launch (`seed_all`, run by the app's
  lifespan).
- From then on the app reads only the database, and later launches and software updates never
  overwrite the team's version.
- „Auf Standard zurücksetzen" (`reset`) copies the current shipped default back.
- Every conversation copies both values when it starts, so a change applies from the next
  conversation, and running and past conversations keep theirs.

Settings and catalog are two instances of this one mechanism (`TeamValue`). The catalog adds one
rule of its own: question IDs are never handed out twice, because a conversation's answers and tool
fields are keyed by them. Its `next_id` only grows: saving keeps the given IDs and numbers the new
questions from it, and a reset keeps it.

Every function that takes a session is a database step for `db.run_db` and runs in a worker
thread. Saving the catalog and resetting lock the value's row first, so two simultaneous saves
cannot hand out the same ID.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import config
from app.context import default_catalog
from app.models import TeamValueRow, utcnow
from app.schemas import Catalog, CatalogEdit, CatalogQuestion, Option, Settings, SettingsPage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TeamValue[M: BaseModel]:
    """A team-editable value: its database key, its model and its shipped default."""

    key: str
    model: type[M]
    shipped_default: Callable[[], M]
    # What „Auf Standard zurücksetzen" stores, given the shipped default and the current value.
    reset_value: Callable[[M, M], M] = lambda default, current: default


TEAM_SETTINGS = TeamValue("settings", Settings, lambda: Settings.model_validate(config.DEFAULT_SETTINGS))
TEAM_CATALOG = TeamValue(
    "catalog", Catalog, default_catalog,
    # The default questions come back with their own IDs, but the counter never goes back, so a
    # question added later never gets the ID of one added and removed before the reset.
    reset_value=lambda default, current: default.model_copy(
        update={"next_id": max(default.next_id, current.next_id)}),
)
TEAM_VALUES = (TEAM_SETTINGS, TEAM_CATALOG)


def seed_all(session: Session) -> None:
    """Copies each shipped default into the database once; an existing value is never touched."""
    for value in TEAM_VALUES:
        inserted = session.execute(
            insert(TeamValueRow)
            .values(key=value.key, value=value.shipped_default().model_dump(mode="json"), updated_at=utcnow())
            .on_conflict_do_nothing(index_elements=[TeamValueRow.key])
        )
        if inserted.rowcount:
            logger.info("event=team_value_seeded key=%s", value.key)


def read[M: BaseModel](session: Session, value: TeamValue[M], lock: bool = False) -> M:
    """The stored value; `lock` keeps its row locked until the step's transaction ends."""
    return value.model.model_validate(session.get(TeamValueRow, value.key, with_for_update=lock).value)


def save[M: BaseModel](session: Session, value: TeamValue[M], new: M) -> M:
    _store(session, value, new)
    logger.info("event=team_value_saved key=%s", value.key)
    return new


def reset[M: BaseModel](session: Session, value: TeamValue[M]) -> M:
    new = value.reset_value(value.shipped_default(), read(session, value, lock=True))
    _store(session, value, new)
    logger.info("event=team_value_reset key=%s", value.key)
    return new


def _store(session: Session, value: TeamValue, new: BaseModel) -> None:
    row = session.get(TeamValueRow, value.key)  # no second query when `read` loaded it in this step
    row.value = new.model_dump(mode="json")
    row.updated_at = utcnow()


def save_catalog(session: Session, edit: CatalogEdit) -> Catalog:
    """Stores the edited catalog: existing questions keep their IDs, new ones get the next free IDs."""
    current = read(session, TEAM_CATALOG, lock=True)
    given_ids = [question.id for question in edit.questions if question.id is not None]
    next_id = max([current.next_id, *(question_id + 1 for question_id in given_ids)])
    questions = []
    for question in edit.questions:
        question_id = question.id
        if question_id is None:
            question_id, next_id = next_id, next_id + 1
        questions.append(CatalogQuestion(id=question_id, topic=question.topic, question=question.question,
                                         context=question.context))
    return save(session, TEAM_CATALOG, Catalog(questions=questions, next_id=next_id))


def settings_page(settings: Settings) -> SettingsPage:
    """The settings with the choices the settings page offers, all from the config module."""

    def options(labels: dict[str, str]) -> list[Option]:
        return [Option(value=value, label=label) for value, label in labels.items()]

    return SettingsPage(
        settings=settings,
        languages=options({code: language.label for code, language in config.LANGUAGES.items()}),
        models=options(config.MODELS),
        thinking_levels=options(config.THINKING_LEVELS),
    )
