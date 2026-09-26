# Фронтенд TV Poll

React-интерфейс формы голосования и админки.

Production-сборка входит в общий Docker-контур:

```bash
docker compose -f ../docker/compose.yml up --build
```

Интерфейс будет доступен на `http://localhost:3000`.

```bash
npm install
npm run dev
```

- форма зрителя: `http://localhost:5173/q/<id>`;
- админка: `http://localhost:5173/admin`;
- локальный токен: `dev-admin-token`.

Проверки:

```bash
npm run build
npm run lint
```
