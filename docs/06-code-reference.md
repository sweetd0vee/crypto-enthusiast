# Справочник по коду

Этот документ описывает фактическую структуру приложения, назначение модулей,
основные функции и цепочки вызовов. Требования находятся в
[01-specification.md](01-specification.md), архитектурные решения — в
[02-architecture.md](02-architecture.md), HTTP-контракт — в
[03-api.md](03-api.md).

## Структура репозитория

```text
backend/
  app/
    api/            # HTTP-маршруты, зависимости, auth и ошибки
    question/       # модели, CRUD и кэш вопросов
    vote/           # публичная форма, Lua hot path и журнал
    result/         # чтение и пересчёт результатов
    store/          # PostgreSQL, Redis, ключи и таблицы
    config.py       # конфигурация из окружения
    main.py         # FastAPI и lifecycle
  migrations/       # Alembic
  scripts/          # seed и нагрузочный скрипт
  tests/
frontend/
  src/
    pages/
    components/
    styles/
    api.ts
    types.ts
    adminQuestions.ts
    ui.ts
  e2e/
docker/
  compose.yml
  compose.verify.yml
  backend.Dockerfile
  frontend.Dockerfile
  nginx.conf
scripts/verify.sh
```

## Backend: запуск и lifecycle

### `backend/app/main.py`

`create_app()` создаёт FastAPI, устанавливает обработчики ошибок, подключает
публичный и административный роутеры и регистрирует `/healthz`.

`lifespan()` управляет ресурсами:

1. получает закэшированный `Settings`;
2. создаёт SQLAlchemy engine;
3. создаёт Redis client;
4. создаёт `VoteJournal`;
5. при `VOTE_ASYNC=true` запускает worker журнала;
6. при остановке дожидается журнала и закрывает Redis и PostgreSQL.

Ресурсы хранятся как singleton внутри соответствующих модулей. Обработчики
получают их через FastAPI dependencies, а не создают на каждый запрос.

`healthz()` вызывает `ping_db()` и `ping_redis()`. Если оба хранилища
доступны, возвращается `200 {"status":"ok"}`; любая ошибка даёт `503`.

ASGI entrypoint — `app = create_app()`.

### `backend/app/config.py`

`Settings` читает:

- `DATABASE_URL`;
- `REDIS_URL`;
- `ADMIN_TOKEN`;
- `IP_HASH_SALT`;
- `COUNTER_SHARDS`;
- `VOTE_ASYNC`.

PostgreSQL URL нормализуется к asyncpg dialect. `counter_shards` не может
быть меньше единицы. `get_settings()` использует `lru_cache`, поэтому
конфигурация создаётся один раз на процесс.

## Backend: API-слой

### `backend/app/api/deps.py`

Aliases `DatabaseDep`, `RedisDep`, `SettingsDep` и `VoteJournalDep` связывают
обработчики с singleton-ресурсами.

`require_admin()`:

1. читает Bearer credentials через `HTTPBearer(auto_error=False)`;
2. сравнивает токен с настройкой через `hmac.compare_digest`;
3. при несовпадении выбрасывает `AppError(401, "unauthorized", ...)`.

Все административные маршруты подключают эту зависимость на уровне роутера.

### `backend/app/api/errors.py`

`AppError` переносит HTTP status, стабильный машинный `error` и сообщение.

`install_error_handlers()` регистрирует:

- преобразование `AppError` в `{"error", "message"}`;
- преобразование `RequestValidationError` в `422 invalid_body`.

Сервисный слой не формирует `JSONResponse`: он выбрасывает доменную ошибку,
которую единообразно переводит API-слой.

### `backend/app/api/public.py`

`_viewer_id(cookie_value)` валидирует UUID из cookie `vid`. Валидное значение
используется повторно; отсутствующее или испорченное заменяется новым
`uuid4()`. Функция также сообщает, нужно ли поставить cookie в ответ.

`_set_viewer_cookie()` создаёт `vid` с параметрами:

- `Max-Age=86400`;
- `HttpOnly`;
- `SameSite=Lax`;
- `Path=/`.

`questionnaire()` обслуживает `GET /questionnaire/{question_id}`:

```text
cookie → _viewer_id → get_public_question → optional Set-Cookie → response
```

`vote()` обслуживает `POST /questionnaire/{question_id}/votes`:

```text
cookie + VoteRequest → accept_vote → optional Set-Cookie → VoteResponse
```

`VoteRequest` принимает `option`, а `VoteResponse` возвращает `accepted`,
`question_id` и выбранный ключ.

### `backend/app/api/admin.py`

Handlers остаются тонкими и делегируют сервисам:

| Обработчик | Метод и путь | Сервис |
| --- | --- | --- |
| `create_question_route` | `POST /questions` | `create_question` |
| `list_questions_route` | `GET /questions` | `list_questions` |
| `get_question_route` | `GET /questions/{id}` | `get_question` |
| `update_question_route` | `PUT /questions/{id}` | `update_question` |
| `delete_question_route` | `DELETE /questions/{id}` | `delete_question` |
| `get_results_route` | `GET /questions/{id}/results` | `get_results` |
| `rebuild_results_route` | `POST /questions/{id}/results/rebuild` | `rebuild_results` |

`counter_shards` передаётся из настроек в операции, которым нужно проверить
или прочитать все Redis-счётчики.

## Backend: вопросы

### `backend/app/question/models.py`

`OptionInput` и `OptionOutput` описывают ключ и подпись; output дополнительно
содержит `position`.

`QuestionInput` валидирует:

- непустое имя;
- duration от 10 до 3600 секунд;
- от 2 до 10 вариантов;
- уникальные option keys;
- timezone-aware `show_time`;
- обязательный `show_time` для `published`.

`QuestionCreate` разрешает `draft` и `published`. Обновление также допускает
`cancelled`. `QuestionOutput` добавляет `id` и вычисленный
`effective_status`.

`effective_status()` реализует полуоткрытое окно:

```text
draft/cancelled → сохранённый статус
now < show_time → scheduled
show_time <= now < closes_at → live
now >= closes_at → closed
```

### `backend/app/question/cache.py`

Ключ карточки — `question:{id}`.

- `get_cached_question()` читает JSON и создаёт `QuestionOutput`;
- повреждённый JSON удаляется и считается cache miss;
- `cache_question()` сохраняет актуальную карточку;
- `evict_question()` удаляет карточку при физическом удалении вопроса.

TTL у карточки отсутствует: create/update всегда обновляют её, delete
инвалидирует.

### `backend/app/question/service.py`

`_load_one()` читает вопрос и его варианты, при необходимости с
`FOR UPDATE`.

`_to_output()` преобразует строку и варианты в `QuestionOutput`, вычисляя
эффективный статус на переданный момент времени.

`get_question()` открывает connection, вызывает `_load_one()` и возвращает
`404 not_found`, если записи нет.

`list_questions()` одним запросом читает вопросы, вторым — связанные
варианты, группирует их в памяти и создаёт outputs без N+1.

`_write_options()` вставляет варианты и присваивает `position` по порядку во
входном массиве.

`create_question()`:

1. начинает транзакцию;
2. вставляет `question`;
3. записывает варианты;
4. повторно загружает созданную модель;
5. после commit обновляет Redis-кэш.

`_same_options()` сравнивает текущие и новые пары `(key, label)`.

`_has_votes()` проверяет два источника:

1. наличие строки в PostgreSQL `vote`;
2. положительное значение в `HVALS` каждого Redis shard.

Нулевой hash не считается наличием голосов.

`update_question()` блокирует строку вопроса. Если набор вариантов изменён,
он вызывает `_has_votes()` и возвращает `409 options_locked` при первом
голосе. Допустимое обновление меняет вопрос, а изменённые варианты
перезаписывает целиком. После commit кэш обновляется.

`delete_question()` разрешает физическое удаление только `draft` без голосов.
Остальные случаи дают `409 delete_forbidden`. После commit карточка удаляется
из Redis.

## Backend: публичная форма и голос

### `backend/app/vote/service.py`

`dedup_hash(question_id, viewer_id)` вычисляет SHA-256 строки
`question_id|viewer_id`.

`client_ip_hash(client_ip, salt)` создаёт отдельный SHA-256 для журнала. Этот
хеш не участвует в дедупликации.

`_load_question()` сначала читает Redis-кэш, при промахе вызывает
`question.service.get_question()` и прогревает кэш. Ошибка Redis
преобразуется в `503 unavailable`.

`_check_window()` проверяет:

1. `status == published` и наличие `show_time`;
2. `now >= show_time`;
3. `now < show_time + duration`.

Она возвращает `closes_at` либо выбрасывает `not_published`,
`window_not_started` или `window_closed`.

`get_public_question()` загружает вопрос, проверяет окно и существование
dedup key. Уже проголосовавший браузер получает `409 already_voted`.
Публичная модель содержит только имя, варианты и `closes_at`.

### Lua hot path

`ACCEPT_VOTE_SCRIPT` принимает:

- `KEYS[1]` — `vote:{question_id}:{dedup_hash}`;
- `KEYS[2]` — `results:{question_id}:{shard}`;
- `ARGV[1]` — TTL;
- `ARGV[2]` — option key.

Скрипт атомарно:

1. возвращает `0`, если dedup уже существует;
2. проверяет, что counter key отсутствует или является hash;
3. ставит dedup с TTL;
4. выполняет `HINCRBY`;
5. возвращает `1`.

`_reserve_and_increment()` вызывает `redis.eval()` и переводит ответ в bool.
При ошибочном типе counter Lua завершается до установки dedup.

`accept_vote()`:

1. загружает вопрос;
2. проверяет окно;
3. проверяет option до изменения Redis;
4. вычисляет dedup;
5. выбирает shard через `crc32(dedup_key) % counter_shards`;
6. задаёт TTL как время до закрытия плюс сутки;
7. вызывает Lua;
8. при `0` возвращает `409 already_voted`;
9. создаёт `VoteEvent`;
10. записывает его синхронно либо ставит в очередь.

Redis-счётчик не откатывается, если последующая запись журнала не удалась.
Это текущее ограничение, зафиксированное в production-roadmap.

### `backend/app/vote/models.py`

`VoteEvent` — immutable dataclass с `question_id`, `option_key`,
`dedup_key`, `ip_hash`, `voted_at`. `as_row()` готовит mapping для SQLAlchemy.

`PublicQuestion` описывает безопасный публичный ответ без внутренних статусов
и идентификаторов.

## Backend: журнал голосов

### `backend/app/vote/journal.py`

`VoteJournal` содержит bounded `asyncio.Queue`.

- `start()` создаёт worker task;
- `enqueue()` делает `put_nowait`; полная очередь логирует потерю события;
- `write()` синхронно передаёт одно событие в `_write_batch()`;
- `_write_batch()` выполняет PostgreSQL `INSERT ... ON CONFLICT DO NOTHING`;
- `_next_batch()` собирает до 1000 событий или ждёт не более 50 мс;
- `_run()` бесконечно записывает batches и вызывает `task_done`;
- `close()` дожидается очереди и отменяет worker.

`init_journal()`, `get_journal()` и `close_journal()` управляют singleton.
Worker запускается только в асинхронном режиме.

Ограничение очереди — 10 000 элементов. Уникальность
`(question_id, dedup_key)` делает повторную запись идемпотентной.

## Backend: результаты

### `backend/app/result/models.py`

`OptionCount` содержит key, label и count. `QuestionResult` содержит вопрос,
effective status, total и полный массив вариантов.

### `backend/app/result/service.py`

`_read_counters()` через pipeline читает `HGETALL` каждого shard, суммирует
одноимённые поля и сообщает, существовал ли хотя бы один Redis-ключ.

`_response()` соединяет counts с вариантами вопроса. Отсутствующий вариант
получает ноль; `total` вычисляется как сумма.

`rebuild_results()`:

1. загружает вопрос;
2. выполняет `GROUP BY option_key` по журналу;
3. заменяет строки `question_result`;
4. удаляет все текущие counter shards;
5. записывает восстановленный mapping в shard `0`;
6. возвращает нормализованный `QuestionResult`.

`get_results()` загружает вопрос и Redis counters. Если ни одного counter key
нет и вопрос не `live`, запускается rebuild. Для live-вопроса автоматический
`GROUP BY` запрещён: при потере Redis админ увидит нули, пока не будет
выполнено явное восстановление.

## Backend: хранилища

### `backend/app/store/db.py`

- `init_engine()` создаёт async SQLAlchemy engine;
- `get_engine()` возвращает singleton;
- `ping()` выполняет `SELECT 1`;
- `close_engine()` вызывает `dispose()`.

### `backend/app/store/redis.py`

- `init_redis()` создаёт client с `decode_responses=True`;
- `get_redis()` возвращает singleton;
- `ping()` проверяет соединение;
- `close_redis()` закрывает client.

### `backend/app/store/keys.py`

Функции централизованно формируют:

- `question:{id}`;
- `vote:{question_id}:{dedup_hash}`;
- `results:{question_id}:{shard}`;
- список result keys для всех shards.

### `backend/app/store/schema.py`

SQLAlchemy Core `Table` повторяют физическую схему `question`,
`question_option`, `vote` и `question_result`.

## Миграции

`001_init.py` создаёт четыре таблицы, ограничения и индексы.

`002_partition_vote.py` заменяет исходный `vote` на HASH-partitioned таблицу:

- ключ партиционирования — `question_id`;
- 16 партиций `vote_p00`–`vote_p15`;
- primary key `(question_id, id)`;
- unique `(question_id, dedup_key)`;
- индекс `(question_id, option_key)`;
- существующие данные переносятся автоматически.

`migrations/env.py` запускает Alembic через async engine. Revision scripts
описывают DDL вручную.

## Backend-скрипты

### `backend/scripts/seed_demo.py`

`ApiClient` оборачивает stdlib HTTP-запросы. `demo_polls()` строит набор
автомобильных опросов разных статусов. `seed()`:

1. получает текущий список;
2. пропускает совпадающие имена;
3. создаёт отсутствующие вопросы;
4. отправляет демонстрационные голоса в live-вопросы с разными cookie.

Повторный запуск идемпотентен по имени вопроса.

### `backend/scripts/load_test.py`

Создаёт конкурентные POST votes с уникальным `vid` на запрос и печатает
локальные latency/RPS. Это smoke-нагрузка, не production capacity test.

## Backend-тесты

| Файл | Что проверяется |
| --- | --- |
| `test_admin_auth.py` | Bearer auth |
| `test_config.py` | URL и defaults |
| `test_health.py` | health response |
| `test_question_cache.py` | round-trip и повреждённый JSON |
| `test_question_service.py` | статусы, validation и наличие голосов |
| `test_vote_service.py` | dedup, конкурентность, Lua, IP и journal batch |
| `test_result_service.py` | сумма shards и нулевые варианты |
| `test_acceptance_http.py` | полный сценарий через Docker API |

Интеграционный тест активируется `RUN_INTEGRATION=1`.

## Frontend: маршрутизация и API

### `frontend/src/App.tsx`

| Маршрут | Компонент |
| --- | --- |
| `/q/:id` | `ViewerPage` |
| `/admin/login` | `LoginPage` |
| `/admin` | `RequireAuth → AdminPage` |
| `/admin/questions/:id` | `RequireAuth → ResultsPage` |
| `*` | redirect `/admin` |

`App.tsx` содержит только router и imports тематических CSS.

### `frontend/src/api.ts`

`request()` вызывает `fetch`, разбирает единое тело ошибок в `ApiError` и
возвращает `undefined` для `204`.

`adminRequest()` читает `adminToken` из `sessionStorage` и добавляет Bearer
header.

Объект `api` предоставляет типизированные методы:

- `getPublicQuestion`;
- `vote`;
- `listQuestions`;
- `getQuestion`;
- `createQuestion`;
- `updateQuestion`;
- `deleteQuestion`;
- `getResults`.

Cookies не настраиваются вручную: production и dev proxy сохраняют
same-origin.

### `frontend/src/types.ts`

Содержит TypeScript-зеркало request/response моделей и union стабильных кодов
ошибок.

## Frontend: страницы

### `pages/LoginPage.tsx`

`login()` сохраняет непустой токен в `sessionStorage` и перенаправляет на
`/admin`. Проверка токена происходит первым API-запросом.

### `pages/ViewerPage.tsx`

Состояния: `loading`, `ready`, `submitting`, `success`, `message`, `network`.

При mount выполняется `getPublicQuestion`. `submit(option)` блокирует
повторный клик, отправляет голос и показывает успех либо локализованное
сообщение. Сервер остаётся источником дедупликации.

### `pages/AdminPage.tsx`

`loadQuestions()` получает список и при `401` очищает token и возвращает на
login.

Страница хранит фильтры, сортировку и редактируемый вопрос. Она:

- показывает сводные карточки статусов;
- фильтрует таблицу;
- открывает `QuestionEditor`;
- показывает живой таймер scheduled/live вопросов;
- открывает QR/share-диалог для эфира;
- удаляет допустимый черновик после подтверждения;
- ведёт на страницу результатов.

Показанный номер строится отдельно от database id и начинается с единицы.
Ссылка результатов всегда использует настоящий id.

### `pages/ResultsPage.tsx`

`loadResults()` загружает агрегат и обрабатывает `401`. Пока статус `live`,
`useEffect` запускает polling раз в две секунды. Полосы вычисляют процент как
`count / total`; для пустого результата используется ноль.

## Frontend: компоненты и утилиты

### `components/RequireAuth.tsx`

Проверяет наличие токена в `sessionStorage`. Это навигационный guard, а не
security boundary: backend всё равно проверяет Bearer token.

### `components/AdminLayout.tsx`

Рисует общий header. `logout()` удаляет token и переводит на login.

### `components/QuestionEditor.tsx`

Локальное состояние формы и вариантов. `save()`:

1. блокирует публикацию без времени;
2. переводит `datetime-local` в UTC ISO;
3. вызывает create или update;
4. сообщает родителю об успешном сохранении;
5. отображает `options_locked` и общие ошибки.

Варианты можно добавлять до 10 и удалять до минимальных двух.

### `components/QuestionTiming.tsx`

Раз в секунду обновляет локальное `Date.now()` только для `scheduled` и
`live`. Показывает обратный отсчёт до старта либо завершения, не создавая
дополнительных API-запросов.

### `components/QuestionShareDialog.tsx`

Строит зрительскую ссылку `/q/{id}` и QR через `qrcode.react`. Диалог
показывает статус и время эфира, копирует ссылку, открывает форму в новой
вкладке и выгружает QR как SVG.

### `components/Icons.tsx`

Содержит доступные через подписанные кнопки SVG-иконки поиска, QR,
редактирования, удаления и выхода.

### `frontend/src/adminQuestions.ts`

`buildQuestionNumbers()` сортирует настоящие id и строит отображаемые номера
`1..N`.

`filterQuestions()` применяет:

- фильтр показанного номера;
- поиск по имени и вариантам;
- effective status;
- время показа;
- длительность;
- направление сортировки id.

### `frontend/src/ui.ts`

- `viewerMessages` локализует публичные коды ошибок;
- `statusLabels` подписывает effective statuses;
- `errorMessage()` безопасно извлекает сообщение;
- `toLocalInput()` переводит ISO datetime в значение `datetime-local`.

### Стили

- `index.css` — reset и общие tokens;
- `styles/public.css` — login и зритель;
- `styles/admin.css` — таблица, формы и modal;
- `styles/results.css` — полосы результатов;
- `styles/responsive.css` — адаптивные правила.

## Browser E2E

`frontend/e2e/voting-flow.spec.ts` выполняет:

1. вход администратора;
2. создание draft и published вопросов;
3. голос «Да» первого browser context;
4. проверку `already_voted` после reload;
5. голос «Нет» второго browser context;
6. проверку total `2` на странице результатов.

`playwright.config.ts` задаёт Chromium, base URL `http://localhost:3000`,
trace и screenshot при ошибке.

## Docker и Nginx

### `docker/compose.yml`

- `postgres` и `redis` имеют persistent volumes и healthchecks;
- `api` ждёт оба хранилища, публикует `8080` и проверяет `/healthz`;
- `frontend` ждёт API, публикует `3000` и проверяет `/health`.

Имена контейнеров заданы явно: `tv-poll-postgres`, `tv-poll-redis`,
`tv-poll-api`, `tv-poll-frontend`.

`docker/compose.verify.yml` переопределяет имена и порты для отдельного
проекта `tv-poll-verify`. Его временные тома удаляются после `make verify`,
поэтому тестовые вопросы не смешиваются с автомобильным seed.

### `docker/backend.Dockerfile`

Собирает Python-образ, устанавливает приложение, создаёт non-root user.
Команда контейнера сначала выполняет `alembic upgrade head`, затем запускает
Uvicorn.

### `docker/frontend.Dockerfile`

Первый stage выполняет `npm ci` и production build. Второй stage копирует
`dist` в Nginx.

### `docker/nginx.conf`

- `/health` возвращает локальный health response;
- `/questionnaire`, `/questions`, `/healthz`, `/docs`, `/openapi.json`
  проксируются в API;
- frontend routes получают `index.html`;
- статические assets кэшируются на год как immutable.

## CI и локальная проверка

`.github/workflows/ci.yml` содержит три jobs:

1. backend — pytest и Ruff;
2. frontend — build, oxlint и production dependency audit;
3. integration — чистый Compose, HTTP acceptance и Playwright.

`scripts/verify.sh` повторяет полный сценарий локально на портах `13000` и
`18080`, а `trap` всегда выполняет `down -v`. `make verify` является короткой
точкой входа.

## Главные инварианты кода

1. Временное окно всегда считается сервером как `[show_time, closes_at)`.
2. Невалидный вариант проверяется до резервирования dedup.
3. Dedup и Redis counter изменяются одним Lua-скриптом.
4. IP не определяет уникальность зрителя.
5. Варианты нельзя менять после положительного Redis counter или строки
   журнала.
6. Удаляется только draft без голосов.
7. Live results читаются из Redis shards без `GROUP BY`.
8. Автоматический rebuild разрешён только не-live вопросу без counter keys.
9. В публичных моделях нет cookie, IP, хешей и сохранённого статуса.
10. Route guard frontend не заменяет backend-аутентификацию.

## Известные ограничения

- асинхронная очередь журнала не переживает аварийный restart;
- переполненная очередь теряет событие журнала, сохраняя Redis counter;
- frontend не предоставляет кнопку принудительного rebuild;
- question cache не имеет TTL;
- список вопросов пока загружается без серверной пагинации;
- production IAM, observability и capacity validation ещё не реализованы.

Порядок устранения ограничений описан в
[05-production-roadmap.md](05-production-roadmap.md).
