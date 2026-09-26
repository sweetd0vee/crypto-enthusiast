"""Create questions, options, votes and result snapshots.

Revision ID: 001_init
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_init"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "question",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("show_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "duration_seconds",
            sa.Integer(),
            server_default=sa.text("60"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'cancelled')",
            name="ck_question_status",
        ),
        sa.CheckConstraint(
            "duration_seconds BETWEEN 10 AND 3600",
            name="ck_question_duration_seconds",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "question_option",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["question.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "question_id",
            "key",
            name="uq_question_option_question_key",
        ),
        sa.UniqueConstraint(
            "question_id",
            "position",
            name="uq_question_option_position",
        ),
    )
    op.create_table(
        "vote",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column("option_key", sa.String(length=64), nullable=False),
        sa.Column("dedup_key", sa.String(length=64), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "voted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["question_id"], ["question.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", "dedup_key", name="uq_vote_question_dedup"),
    )
    op.create_index(
        "ix_vote_question_option",
        "vote",
        ["question_id", "option_key"],
    )
    op.create_table(
        "question_result",
        sa.Column("question_id", sa.BigInteger(), nullable=False),
        sa.Column("option_key", sa.String(length=64), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False),
        sa.Column(
            "rebuilt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("count >= 0", name="ck_question_result_count"),
        sa.ForeignKeyConstraint(["question_id"], ["question.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("question_id", "option_key"),
    )


def downgrade() -> None:
    op.drop_table("question_result")
    op.drop_index("ix_vote_question_option", table_name="vote")
    op.drop_table("vote")
    op.drop_table("question_option")
    op.drop_table("question")
