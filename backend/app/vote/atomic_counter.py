"""Одна атомарная операция Redis: «запомнить зрителя» и «прибавить голос».

Почему нельзя двумя командами подряд (SET, потом HINCRBY):

    запрос A: EXISTS? нет
    запрос B: EXISTS? нет     ← оба решили, что это первый голос
    запрос A: SET + HINCRBY
    запрос B: SET + HINCRBY   ← один зритель посчитался дважды

Redis выполняет Lua как одну команду: пока скрипт бежит, другой клиент
эти ключи не изменит. Либо оба шага произошли, либо ни одного.
"""

from redis.asyncio import Redis

ACCEPT_VOTE_SCRIPT = """
-- Что приходит из Python:
--   KEYS[1]  ключ дедупа, например vote:42:abc...  («этот зритель уже голосовал»)
--   KEYS[2]  шард счётчика, например results:42:0  (hash: поле = вариант, значение = число)
--   ARGV[1]  сколько секунд жить ключу дедупа
--   ARGV[2]  какой вариант нажали (yes / no / ...)

-- Повторный клик: ключ уже стоит. Счётчик не увеличиваем, говорим Python «это не первый голос».
if redis.call("EXISTS", KEYS[1]) == 1 then
    return 0
end

-- Счётчик должен быть либо hash, либо ещё не существовать.
-- Если на этом ключе случайно лежит строка/список — лучше упасть, чем молча испортить данные.
local counter_type = redis.call("TYPE", KEYS[2])
if counter_type["ok"] ~= "none" and counter_type["ok"] ~= "hash" then
    return redis.error_reply("vote counter key has an unexpected type")
end

-- Первый голос этого зрителя:
-- 1) помечаем его, чтобы второй клик увидел EXISTS;
-- 2) прибавляем 1 к выбранному варианту в hash счётчика.
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
    """Выполнить скрипт выше и перевести ответ Redis на bool.

    True  — скрипт вернул 1: зрителя ещё не было, голос засчитан.
    False — скрипт вернул 0: этот зритель уже голосовал, счётчик не менялся.

    `eval(..., 2, ...)` — число 2 значит «первые два аргумента после него
    это KEYS, остальные ARGV». Так Redis отличает ключи от обычных строк.
    """
    result = await redis.eval(
        ACCEPT_VOTE_SCRIPT,
        2,
        dedup_key,
        counter_key,
        ttl,
        option_key,
    )
    return result == 1
