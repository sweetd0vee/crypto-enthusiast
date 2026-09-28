"""HTTP-ручки зрителя: открыть форму и отправить голос.

Кто такой зритель: браузер без логина. Мы клеим ему cookie `vid` (случайный
UUID) и по нему понимаем «этот телефон уже голосовал». Это не защита от
хакера с DevTools, а от обычного двойного клика и повторного захода по QR.
"""

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
    """Тело POST: какой вариант нажали. Строка должна совпасть с `key` варианта."""

    option: str = Field(min_length=1, max_length=64)


class VoteResponse(BaseModel):
    """Ответ после успешного голоса. Сами итоги зрителю не отдаём."""

    status: Literal["accepted"]
    question_id: int
    option: str


def _viewer_id(cookie_value: str | None) -> tuple[str, bool]:
    """Понять, кто пришёл, по cookie `vid`.

    Возвращает (uuid, нужно_ли_записать_cookie):
    - cookie есть и это нормальный UUID → берём его, cookie не трогаем;
    - cookie нет или это мусор → генерируем новый UUID и потом запишем его.

    Битый cookie нельзя оставлять: иначе человек навсегда застрял бы
    с идентификатором, который сервер не понимает.
    """
    if cookie_value is not None:
        try:
            return str(UUID(cookie_value)), False
        except ValueError:
            pass
    return str(uuid4()), True


def _set_viewer_cookie(response: Response, viewer_id: str) -> None:
    """Положить `vid` в ответ. httponly — JS страницы cookie не прочитает.

    SameSite=Lax: cookie уйдёт при обычном переходе по ссылке с QR,
    но не уйдёт с чужого сайта скрытым POST. Живёт сутки, путь `/`.
    """
    response.set_cookie(
        key="vid",
        value=viewer_id,
        max_age=VIEWER_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _remember_viewer(response: Response, viewer_id: str, is_new: bool) -> None:
    """Записать новый cookie только после успешного ответа.

    Если поставить cookie на ошибке (окно закрыто, уже голосовал), зритель
    получил бы новый UUID, обновил бы страницу и обошёл бы дедуп.
    Поэтому вызываем это в конце обработчика, когда сервис уже не бросил исключение.
    """
    if is_new:
        _set_viewer_cookie(response, viewer_id)


@router.get("/questionnaire/{question_id}", response_model=PublicQuestion)
async def questionnaire(
    question_id: int,
    response: Response,
    database: DatabaseDep,
    redis: RedisDep,
    vid: Annotated[str | None, Cookie()] = None,
) -> PublicQuestion:
    """GET формы: текст вопроса и кнопки вариантов.

    FastAPI сам достаёт cookie `vid` из запроса. Дальше сервис проверяет
    окно эфира и дедуп. Cookie нового зрителя ставится только если форма
    реально отдалась (не 403/409/410).
    """
    viewer_id, is_new = _viewer_id(vid)
    result = await get_public_question(database, redis, question_id, viewer_id)
    _remember_viewer(response, viewer_id, is_new)
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
    """POST голоса: один клик → 201 accepted.

    IP берём из TCP-сокета только чтобы захешировать его в журнал.
    На «можно ли голосовать ещё раз» IP не влияет: два человека за одним
    NAT не должны блокировать друг друга.

    Настройки (соль IP, число шардов, писать журнал сразу или в очередь)
    приходят из окружения через Settings.
    """
    viewer_id, is_new = _viewer_id(vid)
    client_ip = request.client.host if request.client is not None else ""
    await accept_vote(
        database,
        redis,
        journal,
        question_id=question_id,
        option_key=data.option,
        viewer_id=viewer_id,
        client_ip=client_ip,
        ip_hash_salt=settings.ip_hash_salt,
        counter_shards=settings.counter_shards,
        asynchronous_journal=settings.vote_async,
    )
    _remember_viewer(response, viewer_id, is_new)
    return VoteResponse(status="accepted", question_id=question_id, option=data.option)
