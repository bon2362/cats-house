#!/usr/bin/env bash

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

compose=(docker compose --env-file .env.example)
started_services=()

service_is_running() {
  "${compose[@]}" ps --status running -q "$1" | grep -q .
}

cleanup() {
  local exit_code=$?

  for ((index=${#started_services[@]} - 1; index >= 0; index--)); do
    "${compose[@]}" stop "${started_services[index]}" >/dev/null || true
  done

  exit "$exit_code"
}

trap cleanup EXIT

assert_contains() {
  local actual="$1"
  local expected="$2"

  if [[ "$actual" != *"$expected"* ]]; then
    echo "Ожидалась строка $expected, получено: $actual" >&2
    return 1
  fi
}

node --test scripts/check-notices.test.mjs
(
  cd apps/api
  .venv/bin/python -m pytest -q
)
(
  cd apps/web
  npm test
  npm run typecheck
  npm run build
)

"${compose[@]}" config >/dev/null

for service in postgres minio api; do
  if ! service_is_running "$service"; then
    started_services+=("$service")
  fi
done

"${compose[@]}" up -d api

for _ in {1..30}; do
  if health_response="$(curl --fail --silent --show-error http://localhost:8000/api/v1/health)"; then
    assert_contains "$health_response" "\"service\":\"Cat's House\""
    echo "Проверка фундамента завершена: $health_response"
    exit 0
  fi
  sleep 2
done

echo "API не ответил на проверку состояния за 60 секунд." >&2
exit 1
