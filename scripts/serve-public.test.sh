#!/usr/bin/env bash
# Checks serve-public.sh refusals without network: external programs are stubs, dry run stops after the checks.
set -uo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/with" "$work/without"
for tool in cloudflared npm caffeinate; do printf '#!/bin/sh\nexit 0\n' > "$work/with/$tool"; done
for tool in npm caffeinate; do printf '#!/bin/sh\nexit 0\n' > "$work/without/$tool"; done
chmod +x "$work"/with/* "$work"/without/*
printf 'CATS_HOUSE_OWNER_EMAIL=owner@example.test\n' > "$work/no-2fa.env"
printf 'CATS_HOUSE_OWNER_EMAIL=owner@example.test\nCATS_HOUSE_OWNER_TOTP_SECRET=JBSWY3DPEHPK3PXP\n' > "$work/2fa.env"

failures=0
check() {  # name, expected exit, expected text, env file, PATH dir, args...
  local name="$1" expected="$2" text="$3" env_file="$4" bin="$5"; shift 5
  local output status
  output="$(CATS_HOUSE_DRY_RUN=1 CATS_HOUSE_ENV_FILE="$env_file" PATH="$bin:/usr/bin:/bin" bash "$root/scripts/serve-public.sh" "$@" 2>&1)"
  status=$?
  if [[ "$status" != "$expected" || "$output" != *"$text"* ]]; then
    echo "FAIL $name: exit $status, output: $output"
    failures=$((failures + 1))
  else
    echo "ok   $name"
  fi
}

check "refuses without two-factor sign-in" 1 "двухфакторный вход" "$work/no-2fa.env" "$work/with"
check "--without-2fa skips that check" 0 "Проверки пройдены" "$work/no-2fa.env" "$work/with" --without-2fa
check "asks to install the tunnel" 1 "brew install cloudflared" "$work/2fa.env" "$work/without"
check "passes with two-factor sign-in" 0 "Проверки пройдены" "$work/2fa.env" "$work/with"
# uvicorn must not rewrite the visitor address itself: the app's client_address() is the single trust point.
if grep -q "proxy_headers=False" "$root/scripts/serve-public.sh"; then
  echo "ok   uvicorn proxy header rewriting is off"
else
  echo "FAIL uvicorn proxy header rewriting is on"
  failures=$((failures + 1))
fi
exit "$failures"
