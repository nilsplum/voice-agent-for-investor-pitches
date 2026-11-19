"""The migrations create exactly the schema the models describe, so neither can change without the
other (a model change needs a new migration in migrations/versions)."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app import db
from app.models import Base


def test_the_migrations_match_the_models():
    with db.get_engine().connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert differences == []
