# Стек и запуск

Семантика — в [архитектуре](02-architecture.md), HTTP — в
[контракте](03-api.md), где какой файл — в [карте кода](06-code-reference.md).

## Компоненты

| Слой | Технологии | Назначение |
| --- | --- | --- |
| API | Python 3.12, FastAPI, Uvicorn, Pydantic v2 | публичные и административные маршруты |
| Данные | PostgreSQL 16, SQLAlchemy 2 Core, asyncpg, Alembic | вопросы, журнал, снимки |
| Hot path | Redis 7, redis-py, Lua | карточка, дедуп, счётчики |
| Frontend | React 18, TypeScript, Vite, React Router | форма зрителя и админка |
| Web | Nginx | production SPA и same-origin proxy |
| Проверки | pytest, fakeredis, lupa, Ruff, oxlint, Playwright | unit, HTTP и браузер |
| Локально | Docker Compose | полный контур |

Итог — суммы по 2–10 ключам, поэтому поиска нет. Live-результат
опрашивается раз в две секунды, WebSocket нет. Отдельного брокера нет:
пачка журнала живёт в `asyncio.Queue` процесса.

## Конфигурация

| Переменная | Назначение | Локально |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL, драйвер нормализуется к asyncpg | задаёт Compose |
| `REDIS_URL` | Redis | задаёт Compose |
| `ADMIN_TOKEN` | Bearer-токен админки | `dev-admin-token` |
| `IP_HASH_SALT` | соль хеша IP в журнале | `dev-salt` |
| `COUNTER_SHARDS` | число шардов счётчика | `1` |
| `VOTE_ASYNC` | пачечная запись журнала | `false` |

Примеры — `backend/.env.example` и `docker/.env.example`. Секреты в
репозиторий не кладутся.

## Интерфейс

- `/q/:id` — форма зрителя;
- `/admin/login` — ввод токена;
- `/admin` — список, фильтры, редактор;
- `/admin/questions/:id` — суммы.

Токен лежит в `sessionStorage` и уходит в `Authorization`. Cookie `vid`
ставит backend, JavaScript её не читает. QR и ссылка `/q/{id}` доступны для
вопросов `scheduled` и `live`, файл скачивается как SVG.

Vite для разработки слушает `5173` и проксирует API на `localhost:8080`.
Nginx на `3000` отдаёт сборку и проксирует `/questionnaire`, `/questions`,
`/healthz`, `/docs`, `/openapi.json`.

## Запуск

```bash
docker compose -f docker/compose.yml up --build
python3 backend/scripts/seed_demo.py
```

- интерфейс — `http://localhost:3000`;
- API — `http://localhost:8080`;
- OpenAPI — `http://localhost:8080/docs`.

Alembic выполняется до Uvicorn. Контейнеры имеют healthcheck.
`seed_demo.py` идемпотентен по имени вопроса: черновики, запланированные,
эфир, завершённые и отменённые опросы, голоса с разными cookie.

## Проверка

```bash
make verify
```

Скрипт `scripts/verify.sh` по порядку:

1. pytest и Ruff в `backend/.venv`;
2. сборка TypeScript и oxlint;
3. `docker compose` с `compose.yml` и `compose.verify.yml`;
4. HTTP-сценарий на `http://localhost:18080`;
5. Playwright на `http://localhost:13000`.

Проверочный контур — проект `tv-poll-verify` с другими портами и временными
томами. `trap` всегда делает `down -v`, тестовые вопросы не попадают в
локальные демо-данные.

GitHub Actions на push и pull request гоняет три job: backend, frontend
(`npm audit --omit=dev` включительно) и integration. Integration поднимает
обычный `docker/compose.yml` на портах `3000` и `8080`, затем тоже удаляет
тома. Это не тот же Compose-файл, что у `make verify`.

Отдельный backend:

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check .
```

HTTP-сценарий против уже запущенного API:

```bash
RUN_INTEGRATION=1 .venv/bin/pytest tests/test_acceptance_http.py -v
```

## Чего в этом контуре нет

Статический токен вместо IAM, журнал в памяти процесса при `VOTE_ASYNC=true`,
нет метрик и трейсов, Compose не является production-оркестрацией, предел
1,7 млн RPS не измерен. Список — в [roadmap](05-production-roadmap.md).
