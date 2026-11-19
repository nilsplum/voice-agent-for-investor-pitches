"""Logging setup: one line format for the whole backend, including uvicorn's own lines.

Every module logs through `logging.getLogger(__name__)` and writes its message as key=value pairs,
starting with the event: `event=login role=founder founder_id=...`. Only IDs, states, counts,
lengths and durations are logged, never what founders said (answers, transcripts), prompts, search
queries, secrets (including access codes and passwords) or the text of an exception.

`configure_logging` runs once in the app's lifespan and in the migrations. `basicConfig` leaves a
root logger alone that already has handlers, so pytest's log capture keeps working in the tests.
"""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    # uvicorn installs its own handlers before the app starts; hand its lines to the root logger
    # instead, so the whole backend shares one format.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
