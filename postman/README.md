# Postman

Коллекция для локальной проверки API. Запросы повторяют контракт из [`docs/03-api.md`](../docs/03-api.md): зритель, админка, коды ошибок.

Импортируйте в Postman оба файла:

- `tv-poll.postman_collection.json`
- `local.postman_environment.json`

Выберите окружение **TV poll local**. По умолчанию `baseUrl` — `http://localhost:8080`, токен — `dev-admin-token`. Через Nginx те же маршруты доступны на `http://localhost:3000`: поменяйте только `baseUrl`.

Запускайте коллекцию целиком, сверху вниз. Папка 04 создаёт живой вопрос и два голоса, папка 06 читает эти суммы. Папка 05 открывает отменённый вопрос из папки 03. id вопросов и cookie `vid` коллекция записывает сама и не берёт их из cookie jar.

В окружение не добавляйте `liveQuestionId`, `viewerA` и остальные id: переменная окружения перекрывает значение, которое коллекция сохраняет во время прогона.

Пересчёт в папке 06 сравнивает журнал с Redis и рассчитан на `VOTE_ASYNC=false` — так сервис запускается по умолчанию.

Из терминала, если установлен Newman:

```bash
newman run postman/tv-poll.postman_collection.json \
  -e postman/local.postman_environment.json
```
