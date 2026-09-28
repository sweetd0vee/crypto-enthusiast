"""Как называются ключи в Redis. Формат один, чтобы сервисы не разъехались.

Три семейства:
- question:{id}              JSON карточки опроса (кэш формы)
- vote:{id}:{хеш_зрителя}    «этот браузер уже голосовал» (ставится Lua)
- results:{id}:{номер_шарда} hash со счётчиками вариантов (yes=1200, no=800)
"""


def question_cache_key(question_id: int) -> str:
    """Ключ кэша карточки. Значение — JSON QuestionOutput целиком."""
    return f"question:{question_id}"


def vote_dedup_key(question_id: int, dedup_hash: str) -> str:
    """Ключ-флаг: если он есть, этот зритель по этому вопросу уже голосовал.

    `dedup_hash` — SHA-256 от «id вопроса | cookie vid», не сам UUID.
    TTL (сколько жить) выставляет Lua-скрипт при первом голосе.
    """
    return f"vote:{question_id}:{dedup_hash}"


def result_counter_key(question_id: int, shard: int) -> str:
    """Один кусок счётчика. Это Redis hash: поле = ключ варианта, значение = число.

    Пример: HGETALL results:42:0  →  {yes: "500", no: "300"}
    Голос конкретного зрителя всегда пишется в один и тот же шард.
    """
    return f"results:{question_id}:{shard}"


def result_counter_keys(question_id: int, shard_count: int) -> list[str]:
    """Имена всех шардов подряд: 0, 1, … N-1. Нужно, чтобы сложить итог или rebuild."""
    return [result_counter_key(question_id, shard) for shard in range(shard_count)]
