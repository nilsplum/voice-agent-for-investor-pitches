"""The one way to the database: short session scopes, run in worker threads through `run_db`.

The backend is one process with one event loop, and every query is a network round trip. So the
event loop never touches the database: every database step is a plain function
`step(session, ...)`, and `run_db` runs it in a worker thread inside its own short session scope
(one transaction). Steps return plain values or Pydantic models, never ORM objects, because the
session is closed once `run_db` returns. Password hashing runs inside such steps too, so it never
blocks the loop either.

Nothing holds a session across a wait on anything outside the database: a step reads or writes and
returns, and whatever waits (OpenAI, a founder) happens between two steps.
"""

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app import config


@cache
def get_engine() -> Engine:
    """Created on first use, so the tests can point the config at their own database first."""
    return create_engine(config.database_url(), pool_pre_ping=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """One transaction: commits when the block succeeds, rolls back when it raises."""
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


async def run_db[T](step: Callable[..., T], *args: object) -> T:
    """Run `step(session, *args)` in its own session scope in a worker thread and return its result."""

    def call() -> T:
        with session_scope() as session:
            return step(session, *args)

    return await asyncio.to_thread(call)
