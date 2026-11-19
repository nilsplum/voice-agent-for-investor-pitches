"""The SQLAlchemy tables. The schema itself is created and changed only by the Alembic migrations
in migrations/versions, and a test checks that these models and the migrations never drift apart.

Every row is written by a database step through `db.run_db`. The JSONB columns are always read and
written through their Pydantic models (`schemas.py`), never as loose dicts. The team is not stored
here: its one shared login lives in the secrets file.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Identity, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """The one clock of the backend: every stored time is timezone-aware UTC."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    # Explicit constraint names, so the migrations name everything the same way the models do.
    metadata = MetaData(naming_convention={
        "pk": "pk_%(table_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
    })
    type_annotation_map = {datetime: DateTime(timezone=True)}


class Founder(Base):
    __tablename__ = "founders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)  # stored trimmed and lowercased (security.normalize_email)
    password_hash: Mapped[str]                       # argon2; the password itself is never stored
    company_name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Conversation(Base):
    """One conversation, unlocked by one access code. `state` is a `schemas.ConversationState`."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    founder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("founders.id"), index=True)
    state: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    started_at: Mapped[datetime | None]
    ended_at: Mapped[datetime | None]           # set when the conversation becomes Completed or Unfinished
    end_reason: Mapped[str | None]              # a schemas.EndReason, only for Unfinished
    # The copies made at START (schemas.Settings and schemas.Questionnaire), SQL NULL while Ready;
    # none_as_null makes None mean SQL NULL, not the JSON value null.
    settings: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    questionnaire: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))


class AccessCode(Base):
    """An access code for one email. Its state (unused, used, expired) is computed from the columns
    by `access_codes.access_code_state` and never stored."""

    __tablename__ = "access_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str]                                     # normalized like the founders' emails
    code_hash: Mapped[str] = mapped_column(unique=True)    # SHA-256; the plain code is never stored
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"))


class TeamValueRow(Base):
    """A team-editable value (`settings` or `catalog`), one row each, stored as the JSON of its
    Pydantic model. Seeded once with the shipped default and from then on changed only by the team
    (app/team_values.py)."""

    __tablename__ = "team_values"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)


class TranscriptMessageRow(Base):
    """One finished transcript message (`schemas.TranscriptMessage`), in conversation order by `id`.
    Saved by the call's sideband on every speaker change and at the end; a Ready conversation never
    has messages."""

    __tablename__ = "transcript_messages"

    id: Mapped[int] = mapped_column(Identity(), primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    speaker: Mapped[str]   # a schemas.Speaker
    text: Mapped[str]
    start_ms: Mapped[int]
    end_ms: Mapped[int]
