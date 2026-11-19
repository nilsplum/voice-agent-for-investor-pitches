"""Create the transcript messages of the conversations.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transcript_messages",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("speaker", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"],
                                name=op.f("fk_transcript_messages_conversation_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transcript_messages")),
    )
    op.create_index(op.f("ix_transcript_messages_conversation_id"), "transcript_messages", ["conversation_id"],
                    unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_transcript_messages_conversation_id"), table_name="transcript_messages")
    op.drop_table("transcript_messages")
