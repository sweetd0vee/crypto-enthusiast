# Docker-контур

Все контейнеры проекта запускаются одной командой из корня репозитория:

```bash
docker compose -f docker/compose.yml up --build
```

Сервисы:

- `tv-poll-frontend` — Nginx и собранный React, `http://localhost:3000`;
- `tv-poll-api` — FastAPI, `http://localhost:8080`;
- `tv-poll-postgres` — PostgreSQL, порт `5432`;
- `tv-poll-redis` — Redis, порт `6379`.

Для своих значений скопируйте `docker/.env.example` в `docker/.env`. Compose
автоматически читает этот файл, потому что он расположен рядом с
`compose.yml`.

Остановка без удаления данных:

```bash
docker compose -f docker/compose.yml down
```

Полная очистка локальных томов:

```bash
docker compose -f docker/compose.yml down -v
```

`make verify` использует дополнительный `compose.verify.yml`, отдельные порты
и временные тома. После проверки этот контур удаляется автоматически и не
добавляет `E2E`/`Integration` записи в локальную админку.
