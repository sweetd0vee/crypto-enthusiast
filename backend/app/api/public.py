from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Request, Response, status
from pydantic import BaseModel, Field

from app.api.deps import DatabaseDep, RedisDep, SettingsDep, VoteJournalDep
from app.vote.models import PublicQuestion
from app.vote.service import accept_vote, get_public_question

router = APIRouter(tags=["public"])

VIEWER_COOKIE_MAX_AGE = 86_400


class VoteRequest(BaseModel):
    option: str = Field(min_length=1, max_length=64)


class VoteResponse(BaseModel):
    status: Literal["accepted"]
    question_id: int
    option: str


def _viewer_id(cookie_value: str | None) -> tuple[str, bool]:
    if cookie_value is not None:
        try:
            return str(UUID(cookie_value)), False
        except ValueError:
            pass
    return str(uuid4()), True


def _set_viewer_cookie(response: Response, viewer_id: str) -> None:
    response.set_cookie(
        key="vid",
        value=viewer_id,
        max_age=VIEWER_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.get("/questionnaire/{question_id}", response_model=PublicQuestion)
async def questionnaire(
    question_id: int,
    response: Response,
    database: DatabaseDep,
    redis: RedisDep,
    vid: Annotated[str | None, Cookie()] = None,
) -> PublicQuestion:
    viewer_id, is_new = _viewer_id(vid)
    result = await get_public_question(
        database,
        redis,
        question_id,
        viewer_id,
    )
    if is_new:
        _set_viewer_cookie(response, viewer_id)
    return result


@router.post(
    "/questionnaire/{question_id}/votes",
    response_model=VoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def vote(
    question_id: int,
    data: VoteRequest,
    request: Request,
    response: Response,
    database: DatabaseDep,
    redis: RedisDep,
    journal: VoteJournalDep,
    settings: SettingsDep,
    vid: Annotated[str | None, Cookie()] = None,
) -> VoteResponse:
    viewer_id, is_new = _viewer_id(vid)
    await accept_vote(
        database,
        redis,
        journal,
        question_id=question_id,
        option_key=data.option,
        viewer_id=viewer_id,
        client_ip=request.client.host if request.client is not None else "",
        ip_hash_salt=settings.ip_hash_salt,
        counter_shards=settings.counter_shards,
        asynchronous_journal=settings.vote_async,
    )
    if is_new:
        _set_viewer_cookie(response, viewer_id)
    return VoteResponse(status="accepted", question_id=question_id, option=data.option)
