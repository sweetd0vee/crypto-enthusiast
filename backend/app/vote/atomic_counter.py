"""Atomic Redis operation used by the vote hot path."""

from redis.asyncio import Redis

ACCEPT_VOTE_SCRIPT = """
if redis.call("EXISTS", KEYS[1]) == 1 then
    return 0
end

local counter_type = redis.call("TYPE", KEYS[2])
if counter_type["ok"] ~= "none" and counter_type["ok"] ~= "hash" then
    return redis.error_reply("vote counter key has an unexpected type")
end

redis.call("SET", KEYS[1], "1", "EX", ARGV[1])
redis.call("HINCRBY", KEYS[2], ARGV[2], 1)
return 1
"""


async def reserve_viewer_and_increment_counter(
    redis: Redis,
    *,
    dedup_key: str,
    counter_key: str,
    ttl: int,
    option_key: str,
) -> bool:
    """Reserve a viewer and increment one option as a single Redis operation."""
    result = await redis.eval(
        ACCEPT_VOTE_SCRIPT,
        2,
        dedup_key,
        counter_key,
        ttl,
        option_key,
    )
    return result == 1
