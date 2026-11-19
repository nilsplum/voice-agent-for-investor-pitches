"""The team-editable values (settings and catalog): seeded once and never overwritten afterwards,
validated on save, new questions numbered without ever reusing an ID, and „Auf Standard
zurücksetzen" restoring the shipped default."""

import pytest

from app import config
from app.context import default_catalog
from app.db import run_db
from app.errors import INVALID_INPUT
from app.team_values import seed_all

DEFAULT_CATALOG = default_catalog().model_dump(mode="json")


def new_question(topic: str) -> dict:
    return {"id": None, "topic": topic, "question": f"Frage zu {topic}?", "context": f"Kontext zu {topic}."}


async def test_the_first_start_seeds_both_values_and_a_later_start_keeps_the_teams_version(team):
    page = (await team.get("/api/team/settings")).json()
    assert page["settings"] == config.DEFAULT_SETTINGS
    assert (await team.get("/api/team/catalog")).json() == DEFAULT_CATALOG
    assert DEFAULT_CATALOG["next_id"] == 12 and len(DEFAULT_CATALOG["questions"]) == 11

    await team.put("/api/team/settings", json={**config.DEFAULT_SETTINGS, "agent_name": "Lena"})
    await team.put("/api/team/catalog", json={"questions": DEFAULT_CATALOG["questions"][:3]})
    await run_db(seed_all)  # what every later launch (and a software update) does

    assert (await team.get("/api/team/settings")).json()["settings"]["agent_name"] == "Lena"
    assert len((await team.get("/api/team/catalog")).json()["questions"]) == 3


async def test_the_settings_page_offers_the_choices_of_the_config_module(team):
    page = (await team.get("/api/team/settings")).json()

    assert page["languages"] == [{"value": code, "label": language.label} for code, language in config.LANGUAGES.items()]
    assert page["models"] == [{"value": value, "label": label} for value, label in config.MODELS.items()]
    assert page["thinking_levels"] == [{"value": value, "label": label}
                                       for value, label in config.THINKING_LEVELS.items()]


async def test_saving_settings_stores_and_returns_them_trimmed(team):
    changed = {"language": "en", "agent_name": "  Lena ", "note_taker_model": "gpt-6.1-terra",
               "note_taker_thinking": "medium", "reviewer_model": "gpt-6.1-terra", "reviewer_thinking": "high"}

    saved = (await team.put("/api/team/settings", json=changed)).json()

    assert saved["settings"] == {**changed, "agent_name": "Lena"}
    assert (await team.get("/api/team/settings")).json() == saved


@pytest.mark.parametrize("change", [
    {"note_taker_model": "gpt-unknown"},
    {"reviewer_thinking": "extreme"},
    {"language": "fr"},
    {"agent_name": "   "},
    {"agent_name": "x" * 41},
])
async def test_invalid_settings_are_refused(team, change):
    response = await team.put("/api/team/settings", json={**config.DEFAULT_SETTINGS, **change})

    assert (response.status_code, response.json()) == (422, {"detail": INVALID_INPUT})
    assert (await team.get("/api/team/settings")).json()["settings"] == config.DEFAULT_SETTINGS


@pytest.mark.parametrize("questions", [
    [],                                                              # an empty catalog
    [{**new_question("Team"), "question": "  "}],                    # an empty question
    [{**new_question("Team"), "topic": ""}],                         # an empty topic
    [{**DEFAULT_CATALOG["questions"][0]}, {**DEFAULT_CATALOG["questions"][1], "id": 1}],  # duplicate IDs
])
async def test_an_invalid_catalog_is_refused(team, questions):
    response = await team.put("/api/team/catalog", json={"questions": questions})

    assert (response.status_code, response.json()) == (422, {"detail": INVALID_INPUT})
    assert (await team.get("/api/team/catalog")).json() == DEFAULT_CATALOG


async def test_new_questions_get_new_ids_and_no_id_is_ever_handed_out_twice(team):
    questions = DEFAULT_CATALOG["questions"]

    # Remove the last two questions, add one, and move question 3 to the front.
    saved = (await team.put("/api/team/catalog", json={
        "questions": [questions[2], *questions[:2], *questions[3:9], new_question("Patente")]})).json()
    assert [q["id"] for q in saved["questions"]] == [3, 1, 2, 4, 5, 6, 7, 8, 9, 12]
    assert saved["next_id"] == 13

    # Remove the new question again and add another one: it does not get 12 back.
    saved = (await team.put("/api/team/catalog", json={
        "questions": [*saved["questions"][:-1], new_question("Standort"), new_question("Exit")]})).json()
    assert [q["id"] for q in saved["questions"]][-2:] == [13, 14]
    assert [q["topic"] for q in saved["questions"]][-2:] == ["Standort", "Exit"]
    assert saved["next_id"] == 15
    assert (await team.get("/api/team/catalog")).json() == saved


async def test_both_resets_restore_the_defaults_and_the_catalog_keeps_its_counter(team):
    await team.put("/api/team/settings", json={**config.DEFAULT_SETTINGS, "agent_name": "Lena", "language": "en"})
    await team.put("/api/team/catalog", json={"questions": [new_question("Patente")]})

    settings = (await team.post("/api/team/settings/reset")).json()
    catalog = (await team.post("/api/team/catalog/reset")).json()

    assert settings["settings"] == config.DEFAULT_SETTINGS
    assert catalog["questions"] == DEFAULT_CATALOG["questions"]
    assert catalog["next_id"] == 13  # question 12 existed, so its ID is never handed out again
    added = (await team.put("/api/team/catalog", json={"questions": [*catalog["questions"], new_question("Neu")]})).json()
    assert added["questions"][-1]["id"] == 13


async def test_anything_else_is_an_ordinary_question(team):
    *others, anything_else = DEFAULT_CATALOG["questions"]
    assert anything_else["topic"] == "Sonstiges"

    edited = {**anything_else, "question": "Möchten Sie noch etwas ergänzen?"}
    saved = (await team.put("/api/team/catalog", json={"questions": [edited, *others]})).json()
    assert saved["questions"][0] == edited  # edited and moved to the front, keeping its ID

    saved = (await team.put("/api/team/catalog", json={"questions": others})).json()
    assert 11 not in [q["id"] for q in saved["questions"]]
