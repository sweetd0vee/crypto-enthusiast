# Контракт API

Базовый URL локально: `http://localhost:8080`. Готовая коллекция запросов — в [`postman/`](../postman/).

Тело — JSON, время — ISO-8601 UTC. Ошибки всегда одного вида:

```json
{"error": "window_closed", "message": "Время голосования истекло"}
```

`error` стабилен для фронта. `message` можно показать человеку.

Админские маршруты: заголовок `Authorization: Bearer dev-admin-token`.

## Зритель

### Получить форму

`GET /questionnaire/{id}`

Успех `200`:

```json
{
  "id": 1,
  "name": "What is 100+8?",
  "closes_at": "2026-09-24T18:01:00Z",
  "options": [
    {"key": "a", "label": "108"},
    {"key": "b", "label": "102"},
    {"key": "c", "label": "303"},
    {"key": "d", "label": "20"}
  ]
}
```

Если cookie `vid` не было, ответ содержит `Set-Cookie`.

Ошибки: `404 not_found`, `403 window_not_started`, `403 not_published`,
`410 window_closed`, `409 already_voted`.

### Проголосовать

`POST /questionnaire/{id}/votes`

```json
{"option": "a"}
```

Успех `201`:

```json
{"status": "accepted", "question_id": 1, "option": "a"}
```

Ошибки те же, плюс `422 invalid_option` и `503 unavailable`, если Redis не
отвечает.

```bash
curl -sS -c /tmp/vid.txt -b /tmp/vid.txt \
  http://localhost:8080/questionnaire/1

curl -sS -c /tmp/vid.txt -b /tmp/vid.txt \
  -H 'content-type: application/json' \
  -d '{"option":"a"}' \
  http://localhost:8080/questionnaire/1/votes
```

Повтор той же пары команд с тем же файлом cookie даёт `409`.

## Админ: вопросы

### Создать

`POST /questions`

```json
{
  "name": "What is 100+8?",
  "show_time": "2026-09-24T18:00:00Z",
  "duration_seconds": 60,
  "status": "published",
  "options": [
    {"key": "a", "label": "108"},
    {"key": "b", "label": "102"},
    {"key": "c", "label": "303"},
    {"key": "d", "label": "20"}
  ]
}
```

Ответ `201` — карточка:

```json
{
  "id": 1,
  "name": "What is 100+8?",
  "status": "published",
  "effective_status": "scheduled",
  "show_time": "2026-09-24T18:00:00Z",
  "duration_seconds": 60,
  "options": [
    {"key": "a", "label": "108", "position": 0},
    {"key": "b", "label": "102", "position": 1},
    {"key": "c", "label": "303", "position": 2},
    {"key": "d", "label": "20", "position": 3}
  ]
}
```

Для локальной проверки `show_time` ставят на несколько секунд вперёд или
`duration_seconds` увеличивают до 300. A/B — тот же метод с двумя элементами
в `options`.

### Список

`GET /questions` → `200` и массив карточек.

### Карточка

`GET /questions/{id}` → `200` карточка или `404`.

### Изменить

`PUT /questions/{id}` — то же тело, что у создания. Ответ `200` — обновлённая
карточка.

Если по вопросу уже есть голоса и в теле другой набор `options` →
`409 options_locked`.

### Удалить

`DELETE /questions/{id}`.

- черновик без голосов → `204`;
- есть голоса или статус не `draft` → `409 delete_forbidden`.

Опубликованный вопрос отменяют через `PUT` со `"status": "cancelled"`.

## Админ: результат

`GET /questions/{id}/results`

```json
{
  "question_id": 1,
  "name": "What is 100+8?",
  "effective_status": "closed",
  "total": 9001500,
  "counts": [
    {"key": "a", "label": "108", "count": 600},
    {"key": "b", "label": "102", "count": 900},
    {"key": "c", "label": "303", "count": 9000000},
    {"key": "d", "label": "20", "count": 8100}
  ]
}
```

`total` равен сумме `count`. Вариант с нулём голосов всё равно присутствует.

`POST /questions/{id}/results/rebuild` → `200` и тот же объект, цифры заново
собраны из таблицы `vote`.

## Коды ошибок

| Код | `error` | Когда |
| --- | --- | --- |
| 401 | `unauthorized` | нет или неверный токен админа |
| 404 | `not_found` | нет вопроса |
| 409 | `already_voted` | этот `vid` уже ответил |
| 409 | `options_locked` | нельзя менять варианты после голосов |
| 409 | `delete_forbidden` | нельзя удалить не-черновик или вопрос с голосами |
| 410 | `window_closed` | `now` больше или равен концу окна |
| 403 | `window_not_started` | `now` меньше `show_time` |
| 403 | `not_published` | `draft` или `cancelled` |
| 422 | `invalid_option` | ключа нет среди вариантов |
| 422 | `invalid_body` | пустое имя, меньше двух вариантов, битый JSON |
| 503 | `unavailable` | Redis недоступен на голосе |
