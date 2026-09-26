# Фронтенд TV Poll

React-интерфейс формы голосования и админки.

Production-сборка входит в общий Docker-контур:

```bash
docker compose -f ../docker/compose.yml up --build
```

Интерфейс будет доступен на `http://localhost:3000`.

Код разделён на `pages/`, переиспользуемые `components/`, чистые функции
фильтрации и отдельные файлы стилей в `styles/`. `App.tsx` содержит только
таблицу маршрутов.

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
npm run test:e2e
```

Browser-тест ожидает запущенный production-контур на
`http://localhost:3000`. Chromium устанавливается командой
`npx playwright install chromium`; полный сценарий подготовки и проверки
доступен из корня репозитория через `make verify`.
