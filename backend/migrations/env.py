"""Alembic's environment: runs the migrations in versions/ against the app's database.

Runs at every backend start (the Dockerfile's command, before uvicorn) and in the test setup, which
points the config module at the test database first. The URL comes from the config module, so all
of them always agree. New migrations are written with
`alembic revision --autogenerate --rev-id <next number> -m "..."` in the backend container, then
reviewed by hand; tests/test_database.py fails if the models and the migrations drift apart.
"""

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app import config
from app.logs import configure_logging
from app.models import Base

configure_logging()

engine = create_engine(config.database_url(), poolclass=NullPool)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
engine.dispose()
