import asyncio
from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import pytest

from app.api.errors import AppError
from app.question.service import OptionOutput, QuestionOutput
from app.vote.service import VoteEvent, VoteJournal, accept_vote, get_public_question


class MemoryJournal:
    def __init__(self) -> None:
        self.events: list[VoteEvent] = []

    async def write(self, event: VoteEvent) -> None:
        self.events.append(event)

    def enqueue(self, event: VoteEvent) -> None:
        self.events.append(event)


class RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[object] = []

    async def execute(self, statement: object) -> None:
        self.statements.append(statement)


class TransactionContext:
    def __init__(self, connection: RecordingConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> RecordingConnection:
        return self.connection

    async def __aexit__(self, *_args) -> None:
        return None


class RecordingEngine:
    def __init__(self) -> None:
        self.connection = RecordingConnection()

    def begin(self) -> TransactionContext:
        return TransactionContext(self.connection)


def live_question(now: datetime) -> QuestionOutput:
    return QuestionOutput(
        id=1,
        name="A or B?",
        status="published",
        effective_status="live",
        show_time=now - timedelta(seconds=10),
        duration_seconds=60,
        options=[
            OptionOutput(key="a", label="A", position=0),
            OptionOutput(key="b", label="B", position=1),
        ],
    )


async def test_public_question_rejects_viewer_who_already_voted(monkeypatch) -> None:
    now = datetime(2026, 9, 26, 12, tzinfo=UTC)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def load_question(*_args) -> QuestionOutput:
        return live_question(now)

    monkeypatch.setattr("app.vote.service._load_question", load_question)
    first = await get_public_question(object(), redis, 1, "viewer", now=now)
    assert first.name == "A or B?"

    from app.vote.service import dedup_hash

    await redis.set(f"vote:1:{dedup_hash(1, 'viewer')}", "1")
    with pytest.raises(AppError) as exc:
        await get_public_question(object(), redis, 1, "viewer", now=now)
    assert exc.value.error == "already_voted"


async def test_parallel_votes_from_same_viewer_count_once(monkeypatch) -> None:
    now = datetime(2026, 9, 26, 12, tzinfo=UTC)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    journal = MemoryJournal()

    async def load_question(*_args) -> QuestionOutput:
        return live_question(now)

    monkeypatch.setattr("app.vote.service._load_question", load_question)

    async def cast() -> str:
        try:
            await accept_vote(
                object(),
                redis,
                journal,
                question_id=1,
                option_key="a",
                viewer_id="same-viewer",
                client_ip="192.0.2.1",
                ip_hash_salt="salt",
                counter_shards=1,
                asynchronous_journal=False,
                now=now,
            )
        except AppError as exc:
            return exc.error
        return "accepted"

    outcomes = await asyncio.gather(cast(), cast())
    assert sorted(outcomes) == ["accepted", "already_voted"]
    assert await redis.hget("results:1:0", "a") == "1"
    assert len(journal.events) == 1


async def test_two_viewers_on_same_ip_are_both_counted(monkeypatch) -> None:
    now = datetime(2026, 9, 26, 12, tzinfo=UTC)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    journal = MemoryJournal()

    async def load_question(*_args) -> QuestionOutput:
        return live_question(now)

    monkeypatch.setattr("app.vote.service._load_question", load_question)
    for viewer_id in ("viewer-1", "viewer-2"):
        await accept_vote(
            object(),
            redis,
            journal,
            question_id=1,
            option_key="b",
            viewer_id=viewer_id,
            client_ip="192.0.2.1",
            ip_hash_salt="salt",
            counter_shards=1,
            asynchronous_journal=False,
            now=now,
        )

    assert await redis.hget("results:1:0", "b") == "2"
    assert len(journal.events) == 2
    assert journal.events[0].ip_hash == journal.events[1].ip_hash


async def test_invalid_option_does_not_reserve_viewer(monkeypatch) -> None:
    now = datetime(2026, 9, 26, 12, tzinfo=UTC)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    journal = MemoryJournal()

    async def load_question(*_args) -> QuestionOutput:
        return live_question(now)

    monkeypatch.setattr("app.vote.service._load_question", load_question)
    with pytest.raises(AppError) as exc:
        await accept_vote(
            object(),
            redis,
            journal,
            question_id=1,
            option_key="missing",
            viewer_id="viewer",
            client_ip="192.0.2.1",
            ip_hash_salt="salt",
            counter_shards=1,
            asynchronous_journal=False,
            now=now,
        )
    assert exc.value.error == "invalid_option"
    assert await redis.keys("vote:*") == []


async def test_async_journal_flushes_events_in_one_batch() -> None:
    engine = RecordingEngine()
    journal = VoteJournal(engine)
    now = datetime(2026, 9, 26, 12, tzinfo=UTC)
    journal.start()
    for dedup_key in ("first", "second"):
        journal.enqueue(
            VoteEvent(
                question_id=1,
                option_key="a",
                dedup_key=dedup_key,
                ip_hash="hash",
                voted_at=now,
            )
        )

    await journal.close()
    assert len(engine.connection.statements) == 1
