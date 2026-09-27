"""Shared Redis operations for sharded vote counters."""

from typing import cast

from redis.asyncio import Redis

from app.store.keys import result_counter_keys


async def read_counter_shards(
    redis: Redis,
    question_id: int,
    shard_count: int,
) -> list[dict[str, str]]:
    """Read every counter shard in one non-transactional pipeline."""
    pipeline = redis.pipeline(transaction=False)
    for key in result_counter_keys(question_id, shard_count):
        pipeline.hgetall(key)
    return cast(list[dict[str, str]], await pipeline.execute())


def aggregate_counter_shards(shards: list[dict[str, str]]) -> dict[str, int]:
    """Sum option counters across shards."""
    totals: dict[str, int] = {}
    for shard in shards:
        for option_key, count in shard.items():
            totals[option_key] = totals.get(option_key, 0) + int(count)
    return totals


def counter_shards_have_votes(shards: list[dict[str, str]]) -> bool:
    """Return whether any shard contains a positive counter."""
    return any(int(count) > 0 for shard in shards for count in shard.values())
