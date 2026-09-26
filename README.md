# Минутный ТВ-опрос

Бэкенд для анонимного голосования со ссылки на QR в минутном телеролике. Админ заводит один вопрос с любым числом вариантов и смотрит обезличенные суммы. Зритель регистрироваться не обязан и с одного браузера отвечает один раз.

Ниже сохранено исходное условие. Дальше — как устроен сервис, почему выбран такой контур и как его поднять. Подробности лежат в [`docs/`](docs/).

## Условие задачи

Мы - национальная компания по проведению опросов, запускаем минутные ролики на крупнейших тв канал, где показываем опрос (1 вопрос любого типа: multiple choice, a/b, ...) и просим зрителей пройти по куар коду / ссылке и проголосовать. Опросы не требуют регистрации, но надо предусмотреть дедупликацию базовую (не слишком защищенную от обхода, достаточную на уровне обычных, не технически подкованных пользователей), чтоб не накручивали голоса.
Каждый ролик смотрит примерно 100М человек (все из них голосуют), длится он около минуты, в течении которой они могут голосовать.

На нашей стороне мы хотим иметь возможность создавать опросы и смотреть обезличенные результаты.

Что должно быть результатом решения задачи.
Бэкенд сервис (опционально - с фронтенд составляющей), который предоставляет возможность:

- анонимно проголосовать
- создать опрос (админка)
- посмотреть результаты опроса (админка)

Использование ИИ поощряется.

Что должно быть при сдаче задания:

1. Описание сервиса, как его запустить локально и протестировать
2. Обоснование выбранной архитектуры и технологий
3. Все артифакты работы с ИИ должны быть в сдаваемом репозитории, не надо их скрывать

Формат сдачи: публичный репозиторий на гитхабе / гитлабе.

## Что делает сервис

В ролике всегда один вопрос. В админке это одна запись с динамическим списком вариантов: два пункта для A/B или от 2 до 10 для multiple choice. Ссылка с QR — `/questionnaire/{id}`. Голосовать можно только пока серверное время внутри `[show_time, show_time + duration_seconds)`. По умолчанию окно — 60 секунд. Время телефона зрителя не используется.

Три возможности из условия:

| Кто | Действие | Как |
| --- | --- | --- |
| Зритель | Открыть вопрос и проголосовать без регистрации | `GET /questionnaire/{id}`, `POST /questionnaire/{id}/votes` |
| Админ | Создать и менять опрос | `POST/GET/PUT/DELETE /questions`, заголовок `Authorization: Bearer <токен>` |
| Админ | Смотреть обезличенный итог | `GET /questions/{id}/results` — суммы по вариантам, без IP и без идентификаторов зрителей |

Повторный голос с того же браузера не считается. Другой браузер с того же IP считается: домашний NAT и адрес оператора не должны склеивать разных людей. Обход через инкогнито, другой браузер или сброс cookie принимается: условие просит защиту от обычного зрителя, не от бота.

Админ в тестовом — статический токен, не полноценный IAM. Черновик зрителю не виден. Вопрос, по которому уже есть голоса, нельзя удалить и нельзя поменять у него набор вариантов.

Полное ТЗ, коды ошибок и критерии приёмки: [`docs/01-specification.md`](docs/01-specification.md). Контракт запросов: [`docs/05-api.md`](docs/05-api.md).

## Почему такая архитектура

Нагрузка из условия — около 100 млн голосов за минуту, то есть порядка 1,7 млн запросов в секунду на один вопрос, если явка близка к 100%. Админка при этом — единицы запросов в минуту. Поэтому горячий путь и CRUD разведены.

На голосе сервер по порядку:

1. Берёт карточку вопроса из Redis, не из PostgreSQL.
2. Проверяет, что вопрос опубликован и серверное время внутри окна.
3. Проверяет, что ключ варианта существует.
4. Атомарно ставит отметку «этот cookie уже голосовал» (`SET NX`). Не вышло — `409`, счётчик не растёт.
5. Увеличивает счётчик варианта (`HINCRBY` по шарду) и отвечает зрителю.
6. Пишет строку в журнал `vote` отдельно от ответа: синхронно на малых объёмах или пачкой при `VOTE_ASYNC=true`.

Итог для админки — сумма шардов Redis, не `COUNT(*)` по миллионам строк. Журнал нужен, чтобы один раз пересчитать цифры, если Redis пуст, и положить снимок в `question_result`. Пока идёт эфир, дашборд этот пересчёт не запускает.

Дедуп — cookie `vid`, которую выставляет сервер. В журнал пишутся хеш cookie и хеш IP. Сырой IP в ответах API не появляется. Два одновременных `POST` с одним `vid` дают ровно один голос.

Счётчики шардируются (`COUNTER_SHARDS`): один ключ Redis не выдерживает пик целой страны, а чтение результата — это несколько `HGETALL` и сумма в процессе API. У процесса API своего состояния нет, поэтому несколько реплик делят один Redis.

Если Redis в минуту эфира недоступен, голосование останавливается (`503`). Писать каждый голос сразу в PostgreSQL в этот момент нельзя: дедуп разъедется.

Подробнее, с оценкой памяти и моделью таблиц: [`docs/02-architecture.md`](docs/02-architecture.md).

## Стек

Узкое место — Redis и журнал в PostgreSQL, не язык HTTP-слоя. Python здесь уместен: тот же горячий путь (разобрать JSON, сходить в Redis, ответить), а вакансия — backend на Python.

| Слой | Выбор | Зачем |
| --- | --- | --- |
| API | Python 3.12, FastAPI, Uvicorn, Pydantic v2 | Тонкий JSON API, async-обработчик, схемы запроса и OpenAPI на `/docs` |
| Вопросы и журнал | PostgreSQL 16, SQLAlchemy 2 Core, asyncpg, Alembic | Источник правды для админки и пересчёта. Партиции журнала по вопросу |
| Горячий путь | Redis 7 | `SET NX`, шарды счётчиков, кэш карточки вопроса |
| Фронт, если останется время | React 18, TypeScript, Vite | Форма по QR и таблица админки. В условии фронт необязателен |
| Локально | Docker Compose | Postgres, Redis и API одной командой |

Django не берём: его админка и сессии расходятся с этим контрактом. Flask не берём: несколько обращений в Redis и ответ без ожидания пачки `INSERT` естественно ложатся на `async def`. Elasticsearch не берём: итог — суммы по 2–10 ключам, не поиск. Отдельный брокер не поднимаем: пачка журнала живёт в `asyncio.Queue` внутри процесса. Kubernetes в сдачу не входит; локально достаточно Compose, в проде тот же процесс без состояния кладётся в несколько реплик.

Обоснование по библиотекам и от чего отказались: [`docs/06-stack.md`](docs/06-stack.md).

## Локальный запуск и проверка

Контур: PostgreSQL 16, Redis 7, API на порту 8080. Секреты только из окружения.

```bash
cd backend
docker compose up --build
```

Фронтенд запускается отдельно во втором терминале:

```bash
cd frontend
npm install
npm run dev
```

Vite откроет интерфейс на `http://localhost:5173`: форма зрителя — `/q/<id>`,
админка — `/admin`. Для локального входа используйте токен
`dev-admin-token`. Запросы к API проксируются на `localhost:8080`.

Переменные сервиса `api`:

| Переменная | Смысл |
| --- | --- |
| `DATABASE_URL` | PostgreSQL |
| `REDIS_URL` | Redis |
| `ADMIN_TOKEN` | токен админки, локально `dev-admin-token` |
| `IP_HASH_SALT` | соль хеша IP в журнале |
| `COUNTER_SHARDS` | локально `1` |
| `VOTE_ASYNC` | `true` — журнал пишется пачкой после ответа зрителю |

`GET /healthz` отвечает `200`, когда оба хранилища доступны. Миграции применяются до приёма трафика.

### Десять сценариев приёмки

Команды ниже рассчитаны на чистую базу, но не зависят от того, какой `id` выдал PostgreSQL. Нужны `curl` и `python3`. Каждый вызов печатает HTTP-код.

1. Создать опубликованный вопрос. Старт будет через 10 секунд, окно — 30 секунд:

```bash
SHOW_TIME=$(python3 -c 'from datetime import datetime,timezone,timedelta; print((datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat())')
curl -sS -o /tmp/question.json -w '\nHTTP %{http_code}\n' \
  -X POST http://localhost:8080/questions \
  -H 'authorization: Bearer dev-admin-token' \
  -H 'content-type: application/json' \
  -d "{
    \"name\":\"What is 100+8?\",
    \"show_time\":\"$SHOW_TIME\",
    \"duration_seconds\":30,
    \"status\":\"published\",
    \"options\":[
      {\"key\":\"a\",\"label\":\"108\"},
      {\"key\":\"b\",\"label\":\"102\"},
      {\"key\":\"c\",\"label\":\"303\"},
      {\"key\":\"d\",\"label\":\"20\"}
    ]
  }"
cat /tmp/question.json
QID=$(python3 -c 'import json; print(json.load(open("/tmp/question.json"))["id"])')
```

Ожидание: `HTTP 201`.

2. Сразу открыть форму до начала:

```bash
curl -sS -w '\nHTTP %{http_code}\n' -c /tmp/vid-1 -b /tmp/vid-1 \
  "http://localhost:8080/questionnaire/$QID"
```

Ожидание: `HTTP 403`, `error=window_not_started`.

3. Дождаться окна и получить только публичные поля:

```bash
sleep 11
curl -sS -w '\nHTTP %{http_code}\n' -c /tmp/vid-1 -b /tmp/vid-1 \
  "http://localhost:8080/questionnaire/$QID"
```

Ожидание: `HTTP 200`; в JSON есть `id`, `name`, `closes_at`, `options`, но нет `status` и внутренних хешей.

4. Проголосовать и повторить запрос с тем же cookie:

```bash
curl -sS -w '\nHTTP %{http_code}\n' -c /tmp/vid-1 -b /tmp/vid-1 \
  -H 'content-type: application/json' -d '{"option":"a"}' \
  "http://localhost:8080/questionnaire/$QID/votes"
curl -sS -w '\nHTTP %{http_code}\n' -c /tmp/vid-1 -b /tmp/vid-1 \
  -H 'content-type: application/json' -d '{"option":"a"}' \
  "http://localhost:8080/questionnaire/$QID/votes"
```

Ожидание: сначала `201`, затем `409 already_voted`; голос `a` учтён один раз.

5. Второй браузер с того же IP:

```bash
curl -sS -w '\nHTTP %{http_code}\n' -c /tmp/vid-2 -b /tmp/vid-2 \
  -H 'content-type: application/json' -d '{"option":"b"}' \
  "http://localhost:8080/questionnaire/$QID/votes"
```

Ожидание: `HTTP 201`. IP не является ключом дедупликации.

6. Передать отсутствующий ключ:

```bash
curl -sS -w '\nHTTP %{http_code}\n' -c /tmp/vid-invalid -b /tmp/vid-invalid \
  -H 'content-type: application/json' -d '{"option":"missing"}' \
  "http://localhost:8080/questionnaire/$QID/votes"
```

Ожидание: `HTTP 422`, `error=invalid_option`.

7. Дождаться закрытия и попробовать проголосовать:

```bash
sleep 31
curl -sS -w '\nHTTP %{http_code}\n' -c /tmp/vid-late -b /tmp/vid-late \
  -H 'content-type: application/json' -d '{"option":"a"}' \
  "http://localhost:8080/questionnaire/$QID/votes"
```

Ожидание: `HTTP 410`, `error=window_closed`.

8. Прочитать суммы:

```bash
curl -sS -w '\nHTTP %{http_code}\n' \
  -H 'authorization: Bearer dev-admin-token' \
  "http://localhost:8080/questions/$QID/results"
```

Ожидание: `a=1`, `b=1`, остальные варианты равны нулю, `total=2`. Если Redis очистить, закрытый вопрос один раз пересчитывается из журнала. Принудительный пересчёт: `POST /questions/$QID/results/rebuild`.

9. Проверить изменение и удаление черновика, затем запрет удаления вопроса с голосами:

```bash
curl -sS -o /tmp/draft.json -w '\nHTTP %{http_code}\n' \
  -X POST http://localhost:8080/questions \
  -H 'authorization: Bearer dev-admin-token' \
  -H 'content-type: application/json' \
  -d '{"name":"Draft","status":"draft","duration_seconds":60,"options":[{"key":"yes","label":"Yes"},{"key":"no","label":"No"}]}'
DRAFT_ID=$(python3 -c 'import json; print(json.load(open("/tmp/draft.json"))["id"])')
curl -sS -w '\nHTTP %{http_code}\n' -X PUT \
  -H 'authorization: Bearer dev-admin-token' \
  -H 'content-type: application/json' \
  -d '{"name":"Edited draft","status":"draft","duration_seconds":60,"options":[{"key":"yes","label":"Yes"},{"key":"no","label":"No"}]}' \
  "http://localhost:8080/questions/$DRAFT_ID"
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' -X DELETE \
  -H 'authorization: Bearer dev-admin-token' \
  "http://localhost:8080/questions/$DRAFT_ID"
curl -sS -w '\nHTTP %{http_code}\n' -X DELETE \
  -H 'authorization: Bearer dev-admin-token' \
  "http://localhost:8080/questions/$QID"
```

Ожидание: `201`, `200`, `204`, затем `409 delete_forbidden`.

10. Машинно проверить отсутствие идентификаторов зрителя в результате:

```bash
curl -sS -H 'authorization: Bearer dev-admin-token' \
  "http://localhost:8080/questions/$QID/results" |
python3 -c 'import json,sys; value=json.load(sys.stdin); text=json.dumps(value); assert all(word not in text for word in ("ip_hash","dedup","cookie","vid")); assert value["total"] == sum(row["count"] for row in value["counts"]); print("OK")'
```

### Автотесты

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

### Локальный нагрузочный прогон

Включить четыре шарда и пакетную запись журнала, создать живой вопрос и передать его id скрипту:

```bash
VOTE_ASYNC=true COUNTER_SHARDS=4 docker compose up --build -d --force-recreate api
.venv/bin/python scripts/load_test.py 1 --requests 2000 --concurrency 100
```

Контрольный прогон на локальном Docker Desktop: 2000 принятых голосов, 1149,5 RPS, p95 117,2 мс, p99 170,3 мс. После прогона сумма Redis и число строк журнала были равны 2000. Это цифры одного ноутбука, а не обещание 1,7 млн RPS.

### Что не влезает в один процесс

- API не хранит локального состояния и масштабируется несколькими репликами за балансировщиком.
- Дедуп для 100 млн cookie требует порядка 8–16 ГБ с учётом накладных расходов; в проде нужен Redis Cluster.
- `COUNTER_SHARDS` разносит запись одного эфира по ключам; чтение результата складывает все шарды.
- Журнал `vote` разбит на 16 hash-партиций по `question_id`. Для изоляции и быстрого удаления отдельных крупных эфиров следующий шаг — выделенные list-партиции.
- `VOTE_ASYNC=true` пишет журнал пачками до 1000 строк или раз в 50 мс. Очередь процесса ограничена; промышленный вариант заменяет её внешним брокером и отдельными воркерами.
- PostgreSQL хранит журнал и снимки пересчёта, но дашборд не выполняет `GROUP BY` на горячем пути.

Фронт в Compose не входит. Когда API уже отвечает, каталог `frontend/` поднимается отдельно (`npm run dev`), прокси Vite смотрит на `localhost:8080`, чтобы cookie была same-site.

Порядок сборки по шагам: [`docs/07-short-plan.md`](docs/07-short-plan.md), бэкенд — [`docs/03-backend-plan.md`](docs/03-backend-plan.md), фронт — [`docs/04-frontend-plan.md`](docs/04-frontend-plan.md).

## Документы

| Файл | О чём |
| --- | --- |
| [`docs/01-specification.md`](docs/01-specification.md) | ТЗ, скоуп, критерии приёмки |
| [`docs/02-architecture.md`](docs/02-architecture.md) | Горячий путь, модель данных, дедуп, счётчики |
| [`docs/03-backend-plan.md`](docs/03-backend-plan.md) | Порядок реализации API |
| [`docs/04-frontend-plan.md`](docs/04-frontend-plan.md) | Экраны зрителя и админки |
| [`docs/05-api.md`](docs/05-api.md) | Контракт и коды ошибок |
| [`docs/06-stack.md`](docs/06-stack.md) | Библиотеки и от чего отказались |
| [`docs/07-short-plan.md`](docs/07-short-plan.md) | Короткий план работ |

Спецификация собрана вместе с ИИ и лежит в репозитории открыто: скрывать эти документы не нужно.
