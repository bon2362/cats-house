# Public Launch from the Mac Implementation Plan (stage 5.1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command publishes the site from the owner's Mac through a temporary Cloudflare tunnel: built pages served by the API, no indexing, a per-address request limit, the visitor's real address behind the tunnel, and owner two-factor sign-in enabled first.

**Architecture:** The API gains three optional settings-driven pieces in `app/web/` (security headers + robots, static site serving, public-mode client address + rate limit) wired in `create_app`. A helper module `app/auth/totp_setup.py` backs `scripts/enable-owner-totp.py`. `scripts/serve-public.sh` orchestrates build → backup+migrate (via `scripts/prepare-public.py`) → API on 8100 → `cloudflared` → `caffeinate`.

**Tech Stack:** FastAPI/Starlette middleware, pytest; Bash; `qrcode` (dev tool only); Vite.

**Spec:** `docs/superpowers/specs/2026-10-08-public-launch-from-mac-design.md` (authority).

## Global Constraints

- Texts: 429 «Слишком много запросов. Подождите минуту.»; TOTP script «Код не подошёл, секрет не сохранён.»; missing tunnel hint `brew install cloudflared`.
- Headers on every response: `X-Robots-Tag: noindex, nofollow, noarchive`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `X-Content-Type-Options: nosniff`.
- Rate limit only when `public_mode`: 120 `/api/` requests per 60 s per address, owner exempt, `Retry-After` header.
- `CF-Connecting-IP` is trusted only when `public_mode` and the connection comes from `127.0.0.1`/`::1`.
- Secrets never printed into logs or passed as command arguments; `.env` written with `write_env_value`.
- Public API port 8100; dev ports unchanged. No commits unless the owner asks.

## Review Focus

1. A forged `CF-Connecting-IP` from a non-local connection, or with public mode off, must be ignored — Task 2.
2. The SPA fallback must never swallow `/api/...` (a missing API route stays a JSON 404) and must not serve files outside the dist folder (`/../.env`) — Task 3.
3. One visitor's flood must not block another address or the signed-in owner — Task 2.
4. The TOTP secret is written only after a correct code; a typo leaves `.env` untouched — Task 4.
5. `serve-public.sh` stops both API and tunnel on Ctrl-C and refuses to start without 2FA unless `--without-2fa` — Task 5.

---

### Task 1: Settings, security headers, robots.txt

**Files:** Modify `apps/api/app/core/config.py`, `apps/api/app/main.py`; Create `apps/api/app/web/__init__.py`, `apps/api/app/web/protection.py`, `apps/web/public/robots.txt`; Modify `apps/web/index.html`. Test: `apps/api/tests/test_public_site.py`, `apps/web/test/index-html.test.ts`.

**Interfaces (produces):** `Settings.web_dist: Path | None = None`, `Settings.public_mode: bool = False`; `protection.ROBOTS_TXT`; `protection.add_security_headers(app)`.

- [ ] **Step 1: Failing tests** — `tests/test_public_site.py`:

```python
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app

HEADERS = {"x-robots-tag": "noindex, nofollow, noarchive", "x-frame-options": "DENY", "referrer-policy": "same-origin", "x-content-type-options": "nosniff"}


def call(app, method, path, headers=None, client=("127.0.0.1", 5000)):
    async def run():
        transport = ASGITransport(app=app, client=client)
        async with AsyncClient(transport=transport, base_url="https://testserver") as http:
            return await http.request(method, path, headers=headers)
    return asyncio.run(run())


def test_every_response_forbids_indexing_and_framing(settings):
    app = create_app(settings)
    for path in ("/api/v1/health", "/robots.txt"):
        response = call(app, "GET", path)
        assert {key: response.headers[key] for key in HEADERS} == HEADERS


def test_robots_txt_disallows_everything(settings):
    response = call(create_app(settings), "GET", "/robots.txt")
    assert response.status_code == 200 and response.text == "User-agent: *\nDisallow: /\n"
```

`apps/web/test/index-html.test.ts`:

```ts
import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'

it('asks search engines not to index the site', () => {
  expect(readFileSync('index.html', 'utf8')).toContain('<meta name="robots" content="noindex, nofollow" />')
})
```

- [ ] **Step 2:** run both → FAIL.
- [ ] **Step 3: Implement**
  - config: `web_dist: Path | None = None`, `public_mode: bool = False` (import `Path`).
  - `app/web/protection.py`:

```python
"""Headers that keep the site out of search engines and other sites' frames, plus robots.txt."""

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

ROBOTS_TXT = "User-agent: *\nDisallow: /\n"
SECURITY_HEADERS = {
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "X-Content-Type-Options": "nosniff",
}


def add_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response

    @app.get("/robots.txt", include_in_schema=False)
    def robots() -> PlainTextResponse:
        return PlainTextResponse(ROBOTS_TXT)
```

  - `main.py`: call `add_security_headers(app)` after creating the app.
  - `apps/web/public/robots.txt` with the same two lines; `index.html` head gains `<meta name="robots" content="noindex, nofollow" />`.
- [ ] **Step 4:** API suite + `npx vitest run test/index-html.test.ts` → PASS.

---

### Task 2: Visitor address and rate limit in public mode

**Files:** Create `apps/api/app/web/limits.py`; Modify `apps/api/app/main.py`, `apps/api/app/api/routes/auth.py`. Test: `apps/api/tests/test_public_site.py`.

**Interfaces (produces):** `limits.client_address(request) -> str`; `limits.RequestLimiter(limit=120, window_seconds=60, clock=time.monotonic)` with `hit(key) -> int | None` (seconds to wait or None); `limits.add_rate_limit(app)`.

- [ ] **Step 1: Failing tests** (append):

```python
def public(settings, **changes):
    return create_app(settings.model_copy(update={"public_mode": True, **changes}))


def test_public_mode_limits_each_address_separately(settings):
    app = public(settings)
    first = {"CF-Connecting-IP": "203.0.113.1"}
    statuses = [call(app, "GET", "/api/v1/health", first).status_code for _ in range(121)]
    other = call(app, "GET", "/api/v1/health", {"CF-Connecting-IP": "203.0.113.2"})

    assert statuses[:120] == [200] * 120 and statuses[120] == 429
    blocked = call(app, "GET", "/api/v1/health", first)
    assert blocked.json() == {"detail": "Слишком много запросов. Подождите минуту."} and int(blocked.headers["retry-after"]) >= 1
    assert other.status_code == 200
    assert call(app, "GET", "/robots.txt", first).status_code == 200  # not an /api/ request


def test_no_limit_outside_public_mode(settings):
    app = create_app(settings)
    assert {call(app, "GET", "/api/v1/health").status_code for _ in range(130)} == {200}


def test_forged_tunnel_header_is_ignored_from_a_remote_connection(settings):
    app = public(settings)
    for index in range(120):
        call(app, "GET", "/api/v1/health", {"CF-Connecting-IP": f"198.51.100.{index}"}, client=("192.0.2.9", 5000))
    assert call(app, "GET", "/api/v1/health", {"CF-Connecting-IP": "198.51.100.200"}, client=("192.0.2.9", 5000)).status_code == 429


def test_the_signed_in_owner_is_not_limited(settings):
    app = public(settings)
    async def run():
        transport = ASGITransport(app=app, client=("127.0.0.1", 5000))
        async with AsyncClient(transport=transport, base_url="https://testserver") as http:
            await http.post("/api/v1/auth/login", json={"password": "test-owner-password"}, headers={"CF-Connecting-IP": "203.0.113.5"})
            return [(await http.get("/api/v1/auth/status", headers={"CF-Connecting-IP": "203.0.113.5"})).status_code for _ in range(130)]
    assert set(asyncio.run(run())) == {200}


def test_login_throttle_counts_the_tunnel_visitor_address(settings):
    app = public(settings)
    async def run():
        transport = ASGITransport(app=app, client=("127.0.0.1", 5000))
        async with AsyncClient(transport=transport, base_url="https://testserver") as http:
            async def attempt(address):
                response = await http.post("/api/v1/auth/login", json={"password": "wrong"}, headers={"CF-Connecting-IP": address})
                return response.status_code
            first = [await attempt("203.0.113.7") for _ in range(6)]
            return first, await attempt("203.0.113.8")
    first, other = asyncio.run(run())
    assert first == [401] * 5 + [429] and other == 401
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Implement** `app/web/limits.py`:

```python
"""Public mode: the visitor's address behind the tunnel and a per-address request limit."""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import is_owner

LOCAL = {"127.0.0.1", "::1"}


def client_address(request: Request) -> str:
    """The tunnel's CF-Connecting-IP is trusted only in public mode and only from a local connection."""
    host = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("cf-connecting-ip", "").strip()
    if request.app.state.settings.public_mode and host in LOCAL and forwarded:
        return forwarded
    return host


class RequestLimiter:
    def __init__(self, limit: int = 120, window_seconds: int = 60, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window_seconds, self.clock = limit, window_seconds, clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """Record a request; seconds to wait when the address is over the limit (the request is not recorded then)."""
        with self._lock:
            now = self.clock()
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= self.window_seconds:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1, math.ceil(hits[0] + self.window_seconds - now))
            hits.append(now)
            if len(self._hits) > 10_000:  # forget idle addresses so memory stays bounded
                for stale in [key for key, value in self._hits.items() if not value or now - value[-1] >= self.window_seconds]:
                    self._hits.pop(stale, None)
            return None


def add_rate_limit(app: FastAPI) -> None:
    app.state.request_limiter = RequestLimiter()

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.app.state.settings.public_mode and request.url.path.startswith("/api/") and not is_owner(request):
            wait = request.app.state.request_limiter.hit(client_address(request))
            if wait is not None:
                return JSONResponse({"detail": "Слишком много запросов. Подождите минуту."}, status_code=429, headers={"Retry-After": str(wait)})
        return await call_next(request)
```

Middleware order: `request.session` must exist inside `rate_limit`, so add this middleware **before** `SessionMiddleware` in `create_app` (Starlette runs the last-added middleware first; SessionMiddleware is added last so it wraps everything). `auth.py` login uses `client_address(request)` instead of `request.client.host`.

- [ ] **Step 4:** API suite → PASS (existing `test_auth.py` throttle tests keep passing: public mode off).

---

### Task 3: Serving the built site from the API

**Files:** Create `apps/api/app/web/site.py`; Modify `apps/api/app/main.py`. Test: `apps/api/tests/test_public_site.py`.

**Interfaces (produces):** `site.mount_site(app, dist: Path)` — called from `create_app` when `settings.web_dist` is set, **after** the API router.

- [ ] **Step 1: Failing tests:**

```python
def site(settings, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    return create_app(settings.model_copy(update={"web_dist": tmp_path}))


def test_built_pages_and_assets_are_served(settings, tmp_path):
    app = site(settings, tmp_path)
    page = call(app, "GET", "/people/123")
    asset = call(app, "GET", "/assets/app.js")
    assert page.status_code == 200 and page.text == "<html>app</html>" and page.headers["x-robots-tag"].startswith("noindex")
    assert asset.status_code == 200 and asset.text == "console.log(1)"


def test_api_routes_and_files_outside_dist_are_not_swallowed(settings, tmp_path):
    app = site(settings, tmp_path)
    missing_api = call(app, "GET", "/api/v1/no-such-route")
    escape = call(app, "GET", "/../secret.txt")
    encoded = call(app, "GET", "/%2e%2e/secret.txt")
    assert missing_api.status_code == 404 and missing_api.json() == {"detail": "Not Found"}
    assert "nope" not in escape.text and "nope" not in encoded.text
    assert call(app, "GET", "/robots.txt").text.startswith("User-agent")
```

- [ ] **Step 2:** FAIL. **Step 3: Implement** `site.py`:

```python
"""Serve the built web app: real files from dist, index.html for page addresses."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse


def mount_site(app: FastAPI, dist: Path) -> None:
    root = dist.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def page(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)
```

`create_app`: after `include_router` and `add_security_headers`, `if settings.web_dist: mount_site(app, settings.web_dist)`. The robots route is registered before the catch-all (Task 1 registers it in `add_security_headers`; keep that call before `mount_site`).

- [ ] **Step 4:** API suite → PASS.

---

### Task 4: Owner two-factor setup

**Files:** Create `apps/api/app/auth/totp_setup.py`, `scripts/enable-owner-totp.py`; Modify `apps/api/pyproject.toml` (`[project.optional-dependencies] dev` += `"qrcode>=8,<9"`). Test: `apps/api/tests/test_totp_setup.py`.

**Interfaces (produces):** `TOTP_KEY = "CATS_HOUSE_OWNER_TOTP_SECRET"`; `new_secret() -> str`; `otpauth_uri(secret, email) -> str`; `confirm_and_save(env_file: Path, secret: str, code: str) -> bool`; `remove_secret(env_file: Path) -> None`.

- [ ] **Step 1: Failing tests:**

```python
import base64
from urllib.parse import parse_qs, urlparse

from app.auth.service import totp_code
from app.auth.totp_setup import TOTP_KEY, confirm_and_save, new_secret, otpauth_uri, remove_secret


def test_secret_is_160_bit_base32():
    secret = new_secret()
    assert len(base64.b32decode(secret)) == 20 and secret != new_secret()


def test_otpauth_uri_names_the_site_and_owner():
    uri = urlparse(otpauth_uri("JBSWY3DPEHPK3PXP", "owner@example.test"))
    assert (uri.scheme, uri.netloc) == ("otpauth", "totp")
    assert uri.path == "/Cat's%20House:owner%40example.test"
    assert parse_qs(uri.query) == {"secret": ["JBSWY3DPEHPK3PXP"], "issuer": ["Cat's House"]}


def test_secret_is_saved_only_after_a_correct_code(tmp_path):
    env = tmp_path / ".env"
    env.write_text("CATS_HOUSE_OWNER_EMAIL=owner@example.test\n")
    secret = new_secret()

    assert confirm_and_save(env, secret, "000000" if totp_code(secret) != "000000" else "111111") is False
    assert TOTP_KEY not in env.read_text()
    assert confirm_and_save(env, secret, totp_code(secret)) is True
    assert f"{TOTP_KEY}={secret}\n" in env.read_text()

    remove_secret(env)
    assert env.read_text() == "CATS_HOUSE_OWNER_EMAIL=owner@example.test\n"
```

- [ ] **Step 2:** FAIL. **Step 3: Implement** `totp_setup.py` (uses `secrets.token_bytes(20)`, `base64.b32encode(...).decode().rstrip("=")`, `urllib.parse.quote`, `verify_totp`, `write_env_value`; `remove_secret` rewrites the file without lines starting with `TOTP_KEY=` atomically via a temp file + `os.replace`, keeping the mode). Script `enable-owner-totp.py`: reads `CATS_HOUSE_OWNER_EMAIL` from `.env` (`dotenv_values`), creates the secret, prints the QR (`qrcode.QRCode().add_data(uri); print_ascii(invert=True)`; if `qrcode` is missing prints the install hint and the URI), asks `input("Код из приложения: ")`, calls `confirm_and_save`, prints «Двухфакторный вход включён. Перезапустите сайт.» or «Код не подошёл, секрет не сохранён.»; `--disable` asks «Отключить двухфакторный вход? (да/нет)» and calls `remove_secret`. Install `qrcode` into the venv: `.venv/bin/pip install "qrcode>=8,<9"`.
- [ ] **Step 4:** API suite → PASS.

---

### Task 5: `serve-public.sh` and `prepare-public.py`

**Files:** Create `scripts/serve-public.sh`, `scripts/prepare-public.py`. Test: `scripts/serve-public.test.sh` (bash, no network).

- [ ] **Step 1: Failing test** `scripts/serve-public.test.sh` runs the script with a fake `PATH` (stub `cloudflared`, `npm`, `caffeinate`, python stub) and checks: without TOTP in a temp `.env` → exit 1 with «двухфакторный вход»; with `--without-2fa` passes that check; missing `cloudflared` → exit 1 with `brew install cloudflared`. Use env `CATS_HOUSE_ENV_FILE`, `CATS_HOUSE_DRY_RUN=1` (the script stops after the checks and prints «Проверки пройдены»).
- [ ] **Step 2:** `bash scripts/serve-public.test.sh` → FAIL.
- [ ] **Step 3: Implement**
  - `prepare-public.py`: loads `.env` like `dev-native.sh` (dotenv, `$$`→`$`, `@postgres:`→`@127.0.0.1:`); compares `alembic` current revision with head (`alembic.script.ScriptDirectory`, `alembic.runtime.migration.MigrationContext`); if behind: `docker exec catshouse-postgres-1 sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"'` into `~/cats-house-backups/before-migrate-<UTC stamp>.sql`, then `command.upgrade(config, "head")`; prints what it did; never prints the database URL.
  - `serve-public.sh` (`set -euo pipefail`): parse `--without-2fa`; checks (`command -v cloudflared`, TOTP key present and non-empty in the env file unless the flag); dry-run exit; `npm run build` in `apps/web`; `prepare-public.py`; start API with the env file values plus `CATS_HOUSE_ENVIRONMENT=production CATS_HOUSE_PUBLIC_MODE=true CATS_HOUSE_WEB_DIST=<abs dist>` on `127.0.0.1:8100` (same Python launcher style as `dev-native.sh`); wait for `/api/v1/health`; start `cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8100` with output to a log, wait for the `https://…trycloudflare.com` line and print «Сайт доступен по адресу: …»; `caffeinate -i -w <api pid> &`; `trap` stops API, tunnel and caffeinate on exit/INT/TERM.
- [ ] **Step 4:** `bash scripts/serve-public.test.sh` → PASS; `bash -n scripts/serve-public.sh`.

---

### Task 6: README, verification, manual launch check

- [ ] **Step 1: README** — section «Публикация с Mac (временный адрес)»: what the command does, `brew install cloudflared`, enabling 2FA first (`apps/api/.venv/bin/python scripts/enable-owner-totp.py`), the address changes every start, the site is visible only while the command runs, search engines are asked not to index, 120 requests/min limit.
- [ ] **Step 2: Final verification:** `cd apps/api && .venv/bin/pytest -q`; `cd apps/web && npm test && npm run typecheck && npm run build`; `bash scripts/serve-public.test.sh`; `CATS_HOUSE_E2E_URL=http://127.0.0.1:5176 npm run test:e2e`.
- [ ] **Step 3: Manual check with the owner** (needs their phone and `brew install cloudflared`, which the owner approves): run `enable-owner-totp.py`, then `serve-public.sh`, open the tunnel address on a phone, check a person page, the tree, `robots.txt`, owner sign-in with the code.
- [ ] **Step 4:** independent whole-branch review; RED→GREEN fixes; ask before commit/merge/push.
