#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT_DIR/backend/.venv/bin/python"
COMPOSE=(
  docker compose
  -f "$ROOT_DIR/docker/compose.yml"
  -f "$ROOT_DIR/docker/compose.verify.yml"
)

cleanup() {
  "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
}

if [[ ! -x "$PYTHON" ]]; then
  python3 -m venv "$ROOT_DIR/backend/.venv"
fi

if ! "$PYTHON" -c "import fakeredis, lupa, pytest, ruff" 2>/dev/null; then
  "$ROOT_DIR/backend/.venv/bin/pip" install -e "$ROOT_DIR/backend[dev]"
fi

if [[ ! -x "$ROOT_DIR/frontend/node_modules/.bin/playwright" ]]; then
  npm --prefix "$ROOT_DIR/frontend" ci
fi

(
  cd "$ROOT_DIR/backend"
  "$PYTHON" -m pytest
  "$PYTHON" -m ruff check .
)

(
  cd "$ROOT_DIR/frontend"
  npm run build
  npm run lint
)

"${COMPOSE[@]}" config --quiet
cleanup
trap cleanup EXIT
"${COMPOSE[@]}" up --build -d

for _ in {1..30}; do
  if curl --fail --silent http://localhost:13000/health >/dev/null; then
    break
  fi
  sleep 2
done
curl --fail --silent http://localhost:13000/health >/dev/null

(
  cd "$ROOT_DIR/backend"
  API_URL=http://localhost:18080 \
    RUN_INTEGRATION=1 \
    "$PYTHON" -m pytest tests/test_acceptance_http.py
)

(
  cd "$ROOT_DIR/frontend"
  npx playwright install chromium
  E2E_BASE_URL=http://localhost:13000 npm run test:e2e
)
