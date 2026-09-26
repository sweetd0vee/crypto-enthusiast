from fastapi import APIRouter, Depends, Response, status

from app.api.deps import DatabaseDep, RedisDep, SettingsDep, require_admin
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
    return await create_question(database, redis, data)


@router.get("/questions", response_model=list[QuestionOutput])
async def list_questions_route(database: DatabaseDep) -> list[QuestionOutput]:
    return await list_questions(database)


@router.get("/questions/{question_id}", response_model=QuestionOutput)
async def get_question_route(question_id: int, database: DatabaseDep) -> QuestionOutput:
    return await get_question(database, question_id)


@router.get("/questions/{question_id}/results", response_model=QuestionResult)
async def get_results_route(
    question_id: int,
    database: DatabaseDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> QuestionResult:
    return await get_results(
        database,
        redis,
        question_id,
        settings.counter_shards,
    )


@router.post("/questions/{question_id}/results/rebuild", response_model=QuestionResult)
async def rebuild_results_route(
    question_id: int,
    database: DatabaseDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> QuestionResult:
    return await rebuild_results(
        database,
        redis,
        question_id,
        settings.counter_shards,
    )


@router.put("/questions/{question_id}", response_model=QuestionOutput)
async def update_question_route(
    question_id: int,
    data: QuestionUpdate,
    database: DatabaseDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> QuestionOutput:
    return await update_question(
        database,
        redis,
        question_id,
        data,
        settings.counter_shards,
    )


@router.delete(
    "/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_question_route(
    question_id: int,
    database: DatabaseDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> Response:
    await delete_question(
        database,
        redis,
        question_id,
        settings.counter_shards,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
