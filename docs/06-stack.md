# Текущий стек и эксплуатация

Этот документ описывает фактически работающий контур. Семантика системы
находится в [архитектуре](02-architecture.md), HTTP-схемы — в
[контракте API](05-api.md).

## Компоненты

| Слой | Технологии | Назначение |
| --- | --- | --- |
| API | Python 3.12, FastAPI, Uvicorn, Pydantic v2 | публичные и административные маршруты |
| Данные | PostgreSQL 16, SQLAlchemy 2 Core, asyncpg, Alembic | вопросы, варианты, журнал и снимки |
| Hot path | Redis 7, redis-py asyncio, Lua | кэш карточки, дедуп и счётчики |
| Frontend | React 18, TypeScript, Vite, React Router | форма зрителя и админка |
| Web | Nginx | production SPA и same-origin proxy API |
| Проверки | pytest, fakeredis Lua, Ruff, oxlint, Playwright | unit, HTTP и browser acceptance |
| Локальный запуск | Docker Compose | полный воспроизводимый контур |

Elasticsearch не используется: результат — несколько числовых агрегатов, а
не полнотекстовый поиск. Redux и отдельный HTTP-клиент не нужны при текущем
объёме frontend-состояния. WebSocket не нужен: live-результат опрашивается раз
в две секунды.

## Структура приложения

```text
backend/
  app/
    api/                 # public/admin routes, auth, errors
    question/            # CRUD, статусы и Redis-кэш
    vote/                # окно, Lua hot path и журнал
    result/              # чтение шардов и rebuild
    store/               # PostgreSQL, Redis, keys, schema
  migrations/            # Alembic
  tests/
  scripts/               # seed и локальная нагрузка
frontend/
  src/
    pages/
    components/
    styles/
  e2e/                   # Playwright acceptance
docker/
  compose.yml
  backend.Dockerfile
  frontend.Dockerfile
  nginx.conf
scripts/verify.sh
```

## Конфигурация

| Переменная | Назначение | Локально |
| --- | --- | --- |
| `DATABASE_URL` | подключение PostgreSQL | задаёт Compose |
| `REDIS_URL` | подключение Redis | задаёт Compose |
| `ADMIN_TOKEN` | Bearer-токен админского API | `dev-admin-token` |
| `IP_HASH_SALT` | соль необратимого хеша IP | `dev-salt` |
| `COUNTER_SHARDS` | число Redis-шардов результата | `1` |
| `VOTE_ASYNC` | пакетная запись журнала | `false` |

Примеры находятся в `backend/.env.example` и `docker/.env.example`. Реальные
секреты в репозиторий не добавляются.

## Маршруты frontend

- `/q/:id` — мобильная форма зрителя;
- `/admin/login` — ввод локального токена;
- `/admin` — таблица, фильтры и редактор вопросов;
- `/admin/questions/:id` — обезличенные результаты.

Токен хранится в `sessionStorage` и добавляется в `Authorization`. Cookie
`vid` создаёт backend; frontend её не читает.

Vite используется для HMR на порту `5173`. Production-сборку Nginx отдаёт на
порту `3000` и проксирует `/questionnaire`, `/questions`, `/healthz`,
`/docs` и `/openapi.json` в API.

## Локальный запуск

```bash
docker compose -f docker/compose.yml up --build
python3 backend/scripts/seed_demo.py
```

Адреса:

- интерфейс — `http://localhost:3000`;
- API — `http://localhost:8080`;
- OpenAPI — `http://localhost:8080/docs`.

Контейнеры имеют healthcheck. Alembic применяется до запуска Uvicorn.

## Проверка

Единая команда:

```bash
make verify
```

Она выполняет:

1. pytest и Ruff;
2. TypeScript build и oxlint;
3. проверку и пересборку Compose;
4. полный HTTP-сценарий;
5. Playwright-сценарий входа, создания вопросов, двух зрителей и результата.

GitHub Actions повторяет эти проверки на push и pull request. Интеграционный
job поднимает чистые Docker-тома и всегда удаляет их после выполнения.

## Текущие эксплуатационные ограничения

- production-аутентификация администратора ещё не реализована;
- `VOTE_ASYNC=true` использует недолговечную очередь процесса;
- нет production metrics, SLO, alerts и distributed tracing;
- Docker Compose не является production orchestration;
- реальный предел нагрузки не подтверждён capacity-тестом.

Эти ограничения перечислены без повторения завершённых задач в
[production-roadmap](08-production-roadmap.md).
