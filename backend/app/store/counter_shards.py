"""Чтение шардированного счётчика голосов в Redis.

Шард — это один hash-ключ `results:{question_id}:{номер}`. Голоса одного
опроса размазаны по нескольким таким ключам, чтобы Redis не сериализовал
миллионы HINCRBY в одну запись. Чтобы показать итог, читаем все шарды
и складываем одинаковые варианты: yes из шарда 0 + yes из шарда 1 + ...
"""

from typing import cast

from redis.asyncio import Redis

from app.store.keys import result_counter_keys


async def read_counter_shards(
    redis: Redis,
    question_id: int,
    shard_count: int,
) -> list[dict[str, str]]:
    """Забрать все шарды одним pipeline (пачка команд без кругосветки на каждый ключ).

    Транзакцию не открываем: нам важна скорость live-табло, а не идеальный
    снимок в одну миллисекунду. Пока читаем шард 0, в шард 1 может прилететь
    ещё один голос — на экране это расхождение на единицу, это нормально.

    Если ключа нет, Redis отдаёт пустой словарь `{}`.
    """
    pipeline = redis.pipeline(transaction=False)
    for key in result_counter_keys(question_id, shard_count):
        pipeline.hgetall(key)
    return cast(list[dict[str, str]], await pipeline.execute())


def aggregate_counter_shards(shards: list[dict[str, str]]) -> dict[str, int]:
    """Сложить числа одного и того же варианта по всем шардам.

    Redis отдаёт значения строками (`"1200"`), поэтому приводим к int.
    """
    totals: dict[str, int] = {}
    for shard in shards:
        for option_key, count in shard.items():
            totals[option_key] = totals.get(option_key, 0) + int(count)
    return totals


def counter_shards_have_votes(shards: list[dict[str, str]]) -> bool:
    """Был ли уже хотя бы один настоящий голос.

    Пустой hash или поле со значением 0 — это ещё не голоса. Нужно, чтобы
    админ мог поменять варианты у только что опубликованного опроса,
    пока никто не кликнул.
    """
    return any(int(count) > 0 for shard in shards for count in shard.values())
