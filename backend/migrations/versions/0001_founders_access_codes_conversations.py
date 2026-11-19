"""Create the founders, the conversations and the access codes.

The conversation's columns for the running conversation (times, end reason, the copies of the
settings and the questionnaire) exist from the start, because its states and fields are known; they
stay empty until a conversation is started.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "founders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("company_name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_founders")),
        sa.UniqueConstraint("email", name=op.f("uq_founders_email")),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("founder_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(), nullable=True),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("questionnaire", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["founder_id"], ["founders.id"], name=op.f("fk_conversations_founder_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(op.f("ix_conversations_founder_id"), "conversations", ["founder_id"], unique=False)
    op.create_table(
        "access_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"],
                                name=op.f("fk_access_codes_conversation_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_codes")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_access_codes_code_hash")),
    )


def downgrade() -> None:
    op.drop_table("access_codes")
    op.drop_index(op.f("ix_conversations_founder_id"), table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("founders")
