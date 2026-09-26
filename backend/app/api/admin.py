from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import require_admin
from app.config import Settings, get_settings
from app.question.service import (
    QuestionCreate,
    QuestionOutput,
    QuestionUpdate,
    create_question,
    delete_question,
    get_question,
    list_questions,
    update_question,
)
from app.result.service import QuestionResult, get_results, rebuild_results
from app.store.db import get_engine
from app.store.redis import get_redis

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])


@router.post(
    "/questions",
    response_model=QuestionOutput,
    status_code=status.HTTP_201_CREATED,
)
async def create_question_route(data: QuestionCreate) -> QuestionOutput:
    return await create_question(get_engine(), get_redis(), data)


@router.get("/questions", response_model=list[QuestionOutput])
async def list_questions_route() -> list[QuestionOutput]:
    return await list_questions(get_engine())


@router.get("/questions/{question_id}", response_model=QuestionOutput)
async def get_question_route(question_id: int) -> QuestionOutput:
    return await get_question(get_engine(), question_id)


@router.get("/questions/{question_id}/results", response_model=QuestionResult)
async def get_results_route(
    question_id: int,
    settings: Annotated[Settings, Depends(get_settings)],
) -> QuestionResult:
    return await get_results(
        get_engine(),
        get_redis(),
        question_id,
        settings.counter_shards,
    )


@router.post("/questions/{question_id}/results/rebuild", response_model=QuestionResult)
async def rebuild_results_route(
    question_id: int,
    settings: Annotated[Settings, Depends(get_settings)],
) -> QuestionResult:
    return await rebuild_results(
        get_engine(),
        get_redis(),
        question_id,
        settings.counter_shards,
    )


@router.put("/questions/{question_id}", response_model=QuestionOutput)
async def update_question_route(
    question_id: int,
    data: QuestionUpdate,
    settings: Annotated[Settings, Depends(get_settings)],
) -> QuestionOutput:
    return await update_question(
        get_engine(),
        get_redis(),
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
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    await delete_question(
        get_engine(),
        get_redis(),
        question_id,
        settings.counter_shards,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
