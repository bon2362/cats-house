#!/usr/bin/env bash
# Публикация сайта с этого Mac через временный туннель Cloudflare. Ctrl-C — остановить.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
env_file="${CATS_HOUSE_ENV_FILE:-$root/.env}"
api_python="${CATS_HOUSE_API_PYTHON:-$root/apps/api/.venv/bin/python}"
port=8100
without_2fa=0

for arg in "$@"; do
  case "$arg" in
    --without-2fa) without_2fa=1 ;;
    *) echo "Неизвестный параметр: $arg" >&2; exit 2 ;;
  esac
done

if [[ ! -f "$env_file" ]]; then
  echo "Нет $env_file. Скопируйте .env.example в .env и заполните секреты." >&2
  exit 1
fi
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Не найдена программа туннеля cloudflared. Установите её: brew install cloudflared" >&2
  exit 1
fi
if ! grep -Eq '^CATS_HOUSE_OWNER_TOTP_SECRET=.+' "$env_file" && [[ "$without_2fa" != 1 ]]; then
  echo "Сначала включите двухфакторный вход владельца: apps/api/.venv/bin/python scripts/enable-owner-totp.py" >&2
  echo "(или запустите с --without-2fa, если понимаете риск)" >&2
  exit 1
fi
if [[ "${CATS_HOUSE_DRY_RUN:-}" == 1 ]]; then
  echo "Проверки пройдены"
  exit 0
fi
if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Порт $port уже занят — возможно, публикация уже запущена." >&2
  exit 1
fi

echo "Собираю сайт…"
(cd "$root/apps/web" && npm run build >/dev/null)
"$api_python" "$root/scripts/prepare-public.py" "$env_file"

log="$(mktemp -t cats-house-tunnel)"
cleanup() {
  kill "${tunnel_pid:-}" "${api_pid:-}" "${awake_pid:-}" 2>/dev/null || true
  rm -f "$log"
}
trap cleanup EXIT INT TERM

"$api_python" - "$env_file" "$root/apps/api" "$root/apps/web/dist" "$port" <<'PY' &
import os, sys, uvicorn
from dotenv import dotenv_values
env_file, source, dist, port = sys.argv[1:]
values = {key: value.replace('$$', '$') for key, value in dotenv_values(env_file).items() if value is not None}
os.environ.update(values)
os.environ['CATS_HOUSE_DATABASE_URL'] = os.environ['CATS_HOUSE_DATABASE_URL'].replace('@postgres:', '@127.0.0.1:')
os.environ.update({'CATS_HOUSE_ENVIRONMENT': 'production', 'CATS_HOUSE_PUBLIC_MODE': 'true', 'CATS_HOUSE_WEB_DIST': dist})
sys.path.insert(0, source)
# proxy_headers=False: the app alone decides the visitor address (app.web.limits.client_address).
uvicorn.run('app.main:app', host='127.0.0.1', port=int(port), log_level='warning', proxy_headers=False)
PY
api_pid=$!

for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:$port/api/v1/health" >/dev/null 2>&1 && break
  sleep 1
done
if ! curl -sf "http://127.0.0.1:$port/api/v1/health" >/dev/null 2>&1; then
  echo "Сервер сайта не запустился." >&2
  exit 1
fi

cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$port" >"$log" 2>&1 &
tunnel_pid=$!
address=""
for _ in $(seq 1 60); do
  address="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$log" | head -n 1 || true)"
  [[ -n "$address" ]] && break
  sleep 1
done
if [[ -z "$address" ]]; then
  echo "Туннель не поднялся. Последние строки журнала туннеля:" >&2
  tail -n 5 "$log" >&2
  exit 1
fi

caffeinate -i -w "$api_pid" &
awake_pid=$!
echo
echo "Сайт доступен по адресу: $address"
echo "Mac не уснёт, пока работает публикация. Остановить — Ctrl-C."

while kill -0 "$api_pid" 2>/dev/null && kill -0 "$tunnel_pid" 2>/dev/null; do
  sleep 2
done
echo "Сервер или туннель остановился — публикация завершена." >&2
