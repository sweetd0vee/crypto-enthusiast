# Карта кода

Указатель по файлам и трём цепочкам. Сценарии по шагам —
в [разборе](07-walkthrough.md), контракт — в [API](03-api.md).

## Backend

```text
backend/app/
  main.py                 lifespan, /healthz, сборка FastAPI
  config.py               Settings из окружения, lru_cache
  errors.py               AppError и перевод RedisError в 503
  api/public.py           cookie vid, GET формы, POST голоса
  api/admin.py            CRUD, результаты, rebuild
  api/deps.py             singletons и require_admin
  api/errors.py           JSON для AppError и invalid_body
  question/models.py      схемы и effective_status
  question/voting_window.py  граница окна
  question/service.py     CRUD и запрет менять варианты
  question/cache.py       question:{id}
  vote/service.py         публичная форма и accept_vote
  vote/atomic_counter.py  Lua: дедуп и HINCRBY
  vote/journal.py         синхронная запись или очередь процесса
  vote/models.py          VoteEvent и PublicQuestion
  result/service.py       сумма шардов и rebuild
  store/keys.py           имена ключей Redis
  store/counter_shards.py чтение и сумма шардов
  store/schema.py         таблицы SQLAlchemy Core
  store/db.py             engine
  store/redis.py          клиент Redis
```

`lifespan()` открывает PostgreSQL, Redis и журнал. При `VOTE_ASYNC=true`
запускает worker. При остановке дожидается очереди и закрывает клиенты.
`GET /healthz` пингует оба хранилища.

`require_admin()` сравнивает Bearer с `ADMIN_TOKEN` через
`hmac.compare_digest`. Зависимость висит на всём admin-роутере.

Миграция `001_init` создаёт таблицы. `002_partition_vote` заменяет `vote`
на 16 hash-партиций `vote_p00`–`vote_p15` с уникальностью
`(question_id, dedup_key)`.

## Цепочка голоса

`POST /questionnaire/{id}/votes` → `accept_vote()`:

1. `_load_question()` — Redis, при промахе PostgreSQL и прогрев кэша.
2. `require_open_voting_window()` — публикация и полуинтервал.
3. ключ варианта есть среди `options`, иначе `422` до записи Redis.
4. `dedup_hash()` и шард `crc32(dedup_key) % COUNTER_SHARDS`.
5. `reserve_viewer_and_increment_counter()` выполняет Lua.
6. `0` от скрипта — `409`. `1` — `VoteEvent` в `journal.write()` или
   `journal.enqueue()`.

`GET /questionnaire/{id}` идёт тем же `_vote_context()`, затем `EXISTS`
дедуп-ключа. Уже голосовавший браузер получает `409` и форму не видит.
Новый `vid` ставится в cookie только если обработчик дошёл до ответа.

## Цепочка результата

`get_results()` читает вопрос из PostgreSQL и шарды через
`read_counter_shards()`. Пустые hash считаются отсутствием ключей. Если
полей нет и статус не `live`, вызывается `rebuild_results()`: `GROUP BY` по
журналу, замена `question_result`, удаление шардов, запись снимка в шард `0`.

`_has_votes()` для правки и удаления смотрит строку в `vote`, затем
`counter_shards_have_votes()`. Нулевой hash голосами не считается.

## Цепочка вопроса

`create_question()` в одной транзакции пишет `question` и `question_option`,
после commit кладёт карточку в Redis. `update_question()` блокирует строку
`FOR UPDATE`. Смена пар `(key, label)` при уже существующих голосах —
`409 options_locked`. `delete_question()` удаляет только `draft` без голосов
и затем вызывает `evict_question()`.

## Frontend

```text
frontend/src/
  App.tsx                  маршруты
  api.ts                   fetch и ApiError
  adminAuth.ts             токен в sessionStorage
  types.ts                 зеркало контракта
  errorMessages.ts         фразы зрителя и админки
  useAdminGuard.ts         401 → очистка токена и /admin/login
  questionListFilters.ts   фильтры, сортировка, номера строк
  displayFormatting.ts     статусы, длительность, datetime-local
  pages/ViewerPage.tsx     форма
  pages/LoginPage.tsx
  pages/AdminPage.tsx      список
  pages/ResultsPage.tsx    суммы, опрос каждые 2 с пока live
  components/              таблица, редактор, QR, модалки, бейджи
```

`api.ts` не вызывает `GET /questions/{id}` и rebuild. Токен читает
`getAdminToken()`. `RequireAuth` проверяет только наличие токена в браузере;
границу доступа держит backend.

QR строится в `QuestionShareDialog` через `qrcode.react` для `scheduled` и
`live`. Ссылка — `/q/{id}`, скачивание — SVG. У черновика в таблице нет
ссылки на результаты. Кнопка удаления выключена, если сохранённый статус не
`draft`.

`frontend/e2e/voting-flow.spec.ts` входит в админку, создаёт черновик и
опубликованный вопрос, голосует из двух browser context и проверяет
`total = 2`.

## Инварианты

1. Окно — `[show_time, closes_at)`, время сервера.
2. Чужой вариант не резервирует дедуп.
3. Дедуп и счётчик меняет один Lua.
4. IP не определяет уникальность.
5. Варианты нельзя сменить после строки журнала или положительного счётчика.
6. Удаляется только черновик без голосов.
7. Live-итог читается из шардов, без `GROUP BY`.
8. Автоматический rebuild — только не-live вопрос без полей в шардах.
9. Публичная модель не содержит cookie, IP, хешей и сохранённого статуса.
10. Guard во frontend не заменяет проверку Bearer.

## Тесты

| Файл | Что проверяет |
| --- | --- |
| `test_admin_auth.py` | Bearer |
| `test_config.py` | URL и значения по умолчанию |
| `test_health.py` | `/healthz` |
| `test_question_cache.py` | кэш и битый JSON |
| `test_question_service.py` | статусы, валидация, наличие голосов |
| `test_vote_service.py` | дедуп, гонка, Lua, IP, пачка журнала |
| `test_result_service.py` | сумма шардов и нулевые варианты |
| `test_acceptance_http.py` | HTTP-сценарий, включается `RUN_INTEGRATION=1` |

`backend/scripts/load_test.py` шлёт конкурентные POST с новым `vid` на запрос.
Это дым одного процесса, не отчёт о ёмкости.
