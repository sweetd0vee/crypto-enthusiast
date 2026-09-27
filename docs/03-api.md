# Контракт API

Базовый URL локально: `http://localhost:8080`. Коллекция запросов —
в [`postman/`](../postman/).

Тело — JSON, время — ISO-8601 UTC. Ошибка всегда одна и та же формы:

```json
{"error": "window_closed", "message": "Время голосования истекло"}
```

`error` стабилен для клиента. `message` можно показать человеку.

Админские маршруты требуют `Authorization: Bearer dev-admin-token`.

## Зритель

### `GET /questionnaire/{id}`

Успех `200`:

```json
{
  "id": 1,
  "name": "Какой привод практичнее?",
  "closes_at": "2026-09-24T18:01:00Z",
  "options": [
    {"key": "a", "label": "Передний"},
    {"key": "b", "label": "Задний"}
  ]
}
```

В ответе нет `status`, `show_time` и хешей. Если cookie `vid` не было и
обработчик дошёл до ответа, приходит `Set-Cookie`: `HttpOnly`,
`SameSite=Lax`, `Path=/`, сутки. Ошибка до этого cookie не ставит.

Ошибки: `404 not_found`, `403 not_published`, `403 window_not_started`,
`410 window_closed`, `409 already_voted`, `503 unavailable`.

### `POST /questionnaire/{id}/votes`

```json
{"option": "a"}
```

`option` — ключ варианта, не подпись. Успех `201`:

```json
{"status": "accepted", "question_id": 1, "option": "a"}
```

Ошибки те же, плюс `422 invalid_option`. Неизвестный ключ проверяется до
изменения Redis.

```bash
curl -sS -c /tmp/vid.txt -b /tmp/vid.txt \
  http://localhost:8080/questionnaire/1

curl -sS -c /tmp/vid.txt -b /tmp/vid.txt \
  -H 'content-type: application/json' \
  -d '{"option":"a"}' \
  http://localhost:8080/questionnaire/1/votes
```

Повтор с тем же файлом cookie даёт `409`.

## Админ: вопросы

### `POST /questions`

Создание. `status` — `draft` или `published`. Для `published` нужен
`show_time`. По умолчанию статус — `draft`, длительность — 60 секунд.

```json
{
  "name": "Какой привод практичнее?",
  "show_time": "2026-09-24T18:00:00Z",
  "duration_seconds": 60,
  "status": "published",
  "options": [
    {"key": "a", "label": "Передний"},
    {"key": "b", "label": "Задний"},
    {"key": "c", "label": "Полный"},
    {"key": "d", "label": "Подключаемый"}
  ]
}
```

Ответ `201` — карточка с `id`, сохранённым `status`, `effective_status` и
вариантами, у каждого есть `position`. A/B — тот же метод с двумя
элементами в `options`.

### `GET /questions`

`200` и массив карточек. Пагинации нет.

### `GET /questions/{id}`

`200` и карточка, либо `404`. Интерфейс этот маршрут не вызывает: список
уже содержит карточки.

### `PUT /questions/{id}`

Тело как у создания, но `status` может быть ещё и `cancelled`. Ответ `200` —
обновлённая карточка.

Если голоса уже есть и набор `options` изменился — `409 options_locked`.
Имя, время, длительность и статус при том же наборе кнопок менять можно.

### `DELETE /questions/{id}`

Черновик без голосов — `204`. Иначе `409 delete_forbidden`. Опубликованный
вопрос снимают через `PUT` со `"status": "cancelled"`.

## Админ: результат

### `GET /questions/{id}/results`

```json
{
  "question_id": 1,
  "name": "Какой привод практичнее?",
  "effective_status": "closed",
  "total": 2,
  "counts": [
    {"key": "a", "label": "Передний", "count": 1},
    {"key": "b", "label": "Задний", "count": 1},
    {"key": "c", "label": "Полный", "count": 0},
    {"key": "d", "label": "Подключаемый", "count": 0}
  ]
}
```

`total` равен сумме `count`. Нулевой вариант присутствует. Пока вопрос
`live` и счётчиков Redis нет, ответ — нули, без сканирования журнала.

### `POST /questions/{id}/results/rebuild`

`200` и тот же объект. Цифры заново собраны из `vote`, снимок записан в
`question_result`, счётчики Redis заменены. В интерфейсе вызова нет.

## Служебное

`GET /healthz` — `200 {"status":"ok"}`, если PostgreSQL и Redis отвечают.
Иначе `503` с обычным телом ошибки.

## Коды

| Код | `error` | Когда |
| --- | --- | --- |
| 401 | `unauthorized` | нет или неверный токен |
| 404 | `not_found` | нет вопроса |
| 409 | `already_voted` | этот `vid` уже ответил |
| 409 | `options_locked` | варианты после голосов |
| 409 | `delete_forbidden` | не черновик или уже есть голоса |
| 410 | `window_closed` | `now` больше или равен концу окна |
| 403 | `window_not_started` | `now` меньше `show_time` |
| 403 | `not_published` | `draft` или `cancelled` |
| 422 | `invalid_option` | ключа нет среди вариантов |
| 422 | `invalid_body` | пустое имя, меньше двух вариантов, битый JSON, `published` без `show_time` |
| 503 | `unavailable` | Redis недоступен на публичном пути или при чтении счётчиков |
