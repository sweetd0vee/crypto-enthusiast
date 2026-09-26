def question_cache_key(question_id: int) -> str:
    return f"question:{question_id}"


def vote_dedup_key(question_id: int, dedup_hash: str) -> str:
    return f"vote:{question_id}:{dedup_hash}"


def result_counter_key(question_id: int, shard: int) -> str:
    return f"results:{question_id}:{shard}"


def result_counter_keys(question_id: int, shard_count: int) -> list[str]:
    return [result_counter_key(question_id, shard) for shard in range(shard_count)]
