#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
env_file="${CATS_HOUSE_ENV_FILE:-$root/.env}"
api_python="${CATS_HOUSE_API_PYTHON:-$root/apps/api/.venv/bin/python}"

if [[ ! -f "$env_file" ]]; then
  echo "Нет $env_file. Скопируйте .env.example в .env и заполните секреты." >&2
  exit 1
fi

docker compose --env-file "$env_file" up -d postgres minio

cleanup() { kill "${api_pid:-}" "${web_pid:-}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

"$api_python" - "$env_file" "$root/apps/api" <<'PY' &
import os, sys, uvicorn
from dotenv import dotenv_values
env_file, source = sys.argv[1:]
values = {key: value.replace('$$', '$') for key, value in dotenv_values(env_file).items() if value is not None}
os.environ.update(values)
os.environ['CATS_HOUSE_DATABASE_URL'] = os.environ['CATS_HOUSE_DATABASE_URL'].replace('@postgres:', '@127.0.0.1:')
sys.path.insert(0, source)
uvicorn.run('app.main:app', host='127.0.0.1', port=8000)
PY
api_pid=$!

(cd "$root/apps/web" && npm run dev -- --host 127.0.0.1 --port 5173) &
web_pid=$!
wait "$api_pid" "$web_pid"
