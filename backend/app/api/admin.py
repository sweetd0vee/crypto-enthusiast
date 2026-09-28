"""Админские HTTP-ручки. Без верного Bearer ни одна сюда не попадёт.

`require_admin` висит на всём роутере: сравнивает заголовок Authorization
с ADMIN_TOKEN. Сами правила (нельзя менять варианты после голосов и т.д.)
живут в сервисах, здесь только «принять JSON и вызвать функцию».
"""

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CounterShardsDep, DatabaseDep, RedisDep, require_admin
from app.question.models import QuestionCreate, QuestionOutput, QuestionUpdate
from app.question.service import (
    create_question,
    delete_question,
    get_question,
    list_questions,
    update_question,
)
from app.result.models import QuestionResult
from app.result.service import get_results, rebuild_results

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])


@router.post(
    "/questions",
    response_model=QuestionOutput,
    status_code=status.HTTP_201_CREATED,
)
async def create_question_route(
    data: QuestionCreate,
    database: DatabaseDep,
    redis: RedisDep,
) -> QuestionOutput:
    """Создать опрос. Пишется в PostgreSQL, карточка сразу кладётся в Redis."""
    return await create_question(database, redis, data)


@router.get("/questions", response_model=list[QuestionOutput])
async def list_questions_route(database: DatabaseDep) -> list[QuestionOutput]:
    """Таблица всех опросов. Читаем из базы, не из кэша — админке нужна правда."""
    return await list_questions(database)


@router.get("/questions/{question_id}", response_model=QuestionOutput)
async def get_question_route(question_id: int, database: DatabaseDep) -> QuestionOutput:
    """Один опрос по id. Нет строки → 404 not_found."""
    return await get_question(database, question_id)


@router.get("/questions/{question_id}/results", response_model=QuestionResult)
async def get_results_route(
    question_id: int,
    database: DatabaseDep,
    redis: RedisDep,
    counter_shards: CounterShardsDep,
) -> QuestionResult:
    """Текущие цифры: во время эфира — сумма Redis, после — при необходимости пересчёт из журнала."""
    return await get_results(database, redis, question_id, counter_shards)


@router.post("/questions/{question_id}/results/rebuild", response_model=QuestionResult)
async def rebuild_results_route(
    question_id: int,
    database: DatabaseDep,
    redis: RedisDep,
    counter_shards: CounterShardsDep,
) -> QuestionResult:
    """Принудительно пересчитать итоги из таблицы vote и записать их в Redis."""
    return await rebuild_results(database, redis, question_id, counter_shards)


@router.put("/questions/{question_id}", response_model=QuestionOutput)
async def update_question_route(
    question_id: int,
    data: QuestionUpdate,
    database: DatabaseDep,
    redis: RedisDep,
    counter_shards: CounterShardsDep,
) -> QuestionOutput:
    """Изменить опрос. Если уже есть голоса, сменить варианты нельзя (409)."""
    return await update_question(database, redis, question_id, data, counter_shards)


@router.delete(
    "/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_question_route(
    question_id: int,
    database: DatabaseDep,
    redis: RedisDep,
    counter_shards: CounterShardsDep,
) -> Response:
    """Удалить опрос. Только черновик без голосов, иначе 409. Тело ответа пустое."""
    await delete_question(database, redis, question_id, counter_shards)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
