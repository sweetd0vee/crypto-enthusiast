from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

metadata = MetaData()

question = Table(
    "question",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column("name", Text, nullable=False),
    Column("status", String(16), nullable=False),
    Column("show_time", DateTime(timezone=True)),
    Column("duration_seconds", Integer, nullable=False, server_default="60"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("status IN ('draft', 'published', 'cancelled')", name="ck_question_status"),
    CheckConstraint(
        "duration_seconds BETWEEN 10 AND 3600",
        name="ck_question_duration_seconds",
    ),
)

question_option = Table(
    "question_option",
    metadata,
    Column("id", BigInteger, primary_key=True),
    Column(
        "question_id",
        BigInteger,
        ForeignKey("question.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("key", String(64), nullable=False),
    Column("label", Text, nullable=False),
    Column("position", Integer, nullable=False),
    UniqueConstraint("question_id", "key", name="uq_question_option_question_key"),
    UniqueConstraint("question_id", "position", name="uq_question_option_position"),
)

vote = Table(
    "vote",
    metadata,
    Column("id", BigInteger),
    Column(
        "question_id",
        BigInteger,
        ForeignKey("question.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("option_key", String(64), nullable=False),
    Column("dedup_key", String(64), nullable=False),
    Column("ip_hash", String(64), nullable=False),
    Column("voted_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    PrimaryKeyConstraint("question_id", "id", name="vote_pkey"),
    UniqueConstraint("question_id", "dedup_key", name="uq_vote_question_dedup"),
)
Index("ix_vote_question_option", vote.c.question_id, vote.c.option_key)

question_result = Table(
    "question_result",
    metadata,
    Column(
        "question_id",
        BigInteger,
        ForeignKey("question.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("option_key", String(64), primary_key=True),
    Column("count", BigInteger, nullable=False),
    Column("rebuilt_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("count >= 0", name="ck_question_result_count"),
)
