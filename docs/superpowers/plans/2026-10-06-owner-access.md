# Owner Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The owner can sign in on `/login`, sees the owner state in the header, and can sign out; failed sign-ins are throttled and the owner password can be reset from the command line.

**Architecture:** The API gains a public status endpoint, a logout endpoint and an in-memory login throttle stored on `app.state`. The web shell owns the owner status, routes `/login` to a new login page and switches the header between guest and owner. A small `owner-session.ts` module is the only place that talks to the auth endpoints.

**Tech Stack:** FastAPI, Starlette `SessionMiddleware`, argon2-cffi, pytest + testcontainers; Lit, TypeScript, Vitest (jsdom), Playwright with installed Google Chrome.

**Spec:** `docs/superpowers/specs/2026-10-06-owner-access-design.md`

## Global Constraints

- All user-visible text is Russian.
- Status endpoint returns exactly `{"authenticated": bool, "totp_required": bool}` and no personal data.
- Throttle: 5 failed sign-ins within 15 minutes per client address → `429`, header `Retry-After` in seconds, detail «Слишком много попыток входа.»; a successful sign-in resets the address.
- Logout: `POST /api/v1/auth/logout` → `204`, also without a session.
- `next` is accepted only as an internal path starting with a single `/`, never `/login…`; otherwise `/`.
- Owner password: minimum 12 characters; written to `.env` as an Argon2 hash with every `$` escaped as `$$`; neither password nor hash is printed.
- The e2e owner test runs only when `CATS_HOUSE_E2E_OWNER_PASSWORD` is set; no password in the repository.
- Follow existing patterns: Lit components with `static styles = css\`…\``, no new frontend dependencies.
- Do not commit unless the owner asks (project rule).

## Review Focus

1. A `next` value such as `//evil.example`, `https://evil.example` or `/\evil.example` must never become the redirect target — covered in Task 4.
2. The throttle must still block a correct password once the limit is reached (otherwise it is no protection) — covered in Task 2.
3. A status request that fails (API down, HTML error page) must leave the header in guest mode, not crash the shell — covered in Task 5.
4. An empty password must not be sent (the API would answer 422 with an English validation body) — covered in Task 4.
5. Rewriting `.env` must keep every other line, including other `$$`-escaped secrets, byte-for-byte — covered in Task 3.

---

### Task 1: Login throttle

**Files:**
- Create: `apps/api/app/auth/throttle.py`
- Test: `apps/api/tests/test_login_throttle.py`

**Interfaces:**
- Produces: `class LoginThrottle(limit: int = 5, window_seconds: int = 900, clock: Callable[[], float] = time.monotonic)` with `retry_after(key: str) -> int | None`, `record_failure(key: str) -> None`, `reset(key: str) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
from app.auth.throttle import LoginThrottle


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_blocks_after_limit_and_reports_seconds_until_the_oldest_failure_expires():
    clock = Clock()
    throttle = LoginThrottle(limit=5, window_seconds=900, clock=clock)
    for _ in range(4):
        throttle.record_failure("1.1.1.1")
        clock.now += 10
    assert throttle.retry_after("1.1.1.1") is None

    throttle.record_failure("1.1.1.1")

    assert throttle.retry_after("1.1.1.1") == 860


def test_failures_older_than_the_window_are_forgotten():
    clock = Clock()
    throttle = LoginThrottle(limit=5, window_seconds=900, clock=clock)
    for _ in range(5):
        throttle.record_failure("1.1.1.1")

    clock.now += 900

    assert throttle.retry_after("1.1.1.1") is None


def test_addresses_are_counted_separately_and_reset_clears_one_address():
    throttle = LoginThrottle(limit=2, window_seconds=900, clock=Clock())
    throttle.record_failure("1.1.1.1")
    throttle.record_failure("1.1.1.1")

    assert throttle.retry_after("2.2.2.2") is None
    assert throttle.retry_after("1.1.1.1") is not None

    throttle.reset("1.1.1.1")

    assert throttle.retry_after("1.1.1.1") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/api && .venv/bin/pytest tests/test_login_throttle.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'app.auth.throttle'`.

- [ ] **Step 3: Implement**

```python
"""In-memory limit on failed owner sign-ins, per client address.

One owner and one API process: memory is enough. Behind a reverse proxy the
client address must come from a trusted header; that is outside this stage.
"""

import math
import time
from collections import deque
from collections.abc import Callable


class LoginThrottle:
    def __init__(self, limit: int = 5, window_seconds: int = 900, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self._failures: dict[str, deque[float]] = {}

    def _recent(self, key: str) -> tuple[float, deque[float]]:
        now = self.clock()
        failures = self._failures.get(key, deque())
        while failures and now - failures[0] >= self.window_seconds:
            failures.popleft()
        if failures:
            self._failures[key] = failures
        else:
            self._failures.pop(key, None)
        return now, failures

    def retry_after(self, key: str) -> int | None:
        """Seconds until a new attempt is allowed, or None when it is allowed now."""
        now, failures = self._recent(key)
        if len(failures) < self.limit:
            return None
        return max(1, math.ceil(failures[0] + self.window_seconds - now))

    def record_failure(self, key: str) -> None:
        now, failures = self._recent(key)
        failures.append(now)
        self._failures[key] = failures

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/api && .venv/bin/pytest tests/test_login_throttle.py -q`
Expected: `3 passed`.

---

### Task 2: Status, logout and throttled login endpoints

**Files:**
- Modify: `apps/api/app/api/dependencies.py`
- Modify: `apps/api/app/api/routes/auth.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_auth.py`

**Interfaces:**
- Consumes: `LoginThrottle` from Task 1.
- Produces: `GET /api/v1/auth/status` → `{"authenticated": bool, "totp_required": bool}`; `POST /api/v1/auth/logout` → `204`; `POST /api/v1/auth/login` → `204` / `401` / `429` + `Retry-After`. Helper `is_owner(request: Request) -> bool` in `app.api.dependencies`.

- [ ] **Step 1: Write the failing tests** (append to `apps/api/tests/test_auth.py`; the `client` fixture keeps cookies between calls and uses client address `127.0.0.1`)

```python
def test_status_reports_guest_then_owner_without_personal_data(client):
    assert client.get("/api/v1/auth/status").json() == {"authenticated": False, "totp_required": False}

    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})

    assert client.get("/api/v1/auth/status").json() == {"authenticated": True, "totp_required": False}


def test_status_reports_that_a_one_time_code_is_required(monkeypatch, settings):
    from httpx import ASGITransport, AsyncClient
    import asyncio
    from app.main import create_app

    configured = settings.model_copy(update={"owner_totp_secret": SecretStr("JBSWY3DPEHPK3PXP")})

    async def status():
        async with AsyncClient(transport=ASGITransport(app=create_app(configured)), base_url="https://testserver") as http_client:
            return (await http_client.get("/api/v1/auth/status")).json()

    assert asyncio.run(status()) == {"authenticated": False, "totp_required": True}


def test_logout_ends_the_owner_session_and_works_without_one(client):
    assert client.post("/api/v1/auth/logout").status_code == 204
    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})

    assert client.post("/api/v1/auth/logout").status_code == 204

    assert client.get("/api/v1/admin/session").status_code == 401
    assert client.get("/api/v1/auth/status").json()["authenticated"] is False


def test_fifth_failed_sign_in_blocks_even_the_correct_password(client):
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"password": "wrong-password"}).status_code == 401

    blocked = client.post("/api/v1/auth/login", json={"password": "test-owner-password"})

    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Слишком много попыток входа."}
    assert 1 <= int(blocked.headers["retry-after"]) <= 900


def test_successful_sign_in_resets_the_failure_count(client):
    for _ in range(4):
        client.post("/api/v1/auth/login", json={"password": "wrong-password"})
    assert client.post("/api/v1/auth/login", json={"password": "test-owner-password"}).status_code == 204

    for _ in range(4):
        assert client.post("/api/v1/auth/login", json={"password": "wrong-password"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"password": "test-owner-password"}).status_code == 204
```

Add `from pydantic import SecretStr` to the imports at the top of the file.

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && .venv/bin/pytest tests/test_auth.py -q`
Expected: the five new tests fail (`404` for status/logout, `401` instead of `429`).

- [ ] **Step 3: Implement**

`apps/api/app/api/dependencies.py` — extract the check so status and `require_owner` share it:

```python
def is_owner(request: Request) -> bool:
    session_email = request.session.get("owner_email")
    return isinstance(session_email, str) and compare_digest(session_email, request.app.state.settings.owner_email)


def require_owner(request: Request) -> OwnerSession:
    if not is_owner(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход владельца.",
        )
    return OwnerSession(email=request.app.state.settings.owner_email)
```

`apps/api/app/main.py` — one throttle per app, next to the other `app.state` values:

```python
from app.auth.throttle import LoginThrottle
...
    app.state.media_storage = S3MediaStorage(settings)
    app.state.login_throttle = LoginThrottle()
```

`apps/api/app/api/routes/auth.py` — replace the login handler and add two routes:

```python
from app.api.dependencies import OwnerSession, is_owner, require_owner


@router.get("/auth/status")
def owner_status(request: Request) -> dict[str, bool]:
    return {
        "authenticated": is_owner(request),
        "totp_required": request.app.state.settings.owner_totp_secret is not None,
    }


@router.post("/auth/login", status_code=status.HTTP_204_NO_CONTENT)
def login_owner(payload: LoginRequest, request: Request) -> Response:
    settings = request.app.state.settings
    throttle = request.app.state.login_throttle
    address = request.client.host if request.client else "unknown"

    wait = throttle.retry_after(address)
    if wait is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа.",
            headers={"Retry-After": str(wait)},
        )
    if not verify_owner_password(payload.password, settings.owner_password_hash):
        throttle.record_failure(address)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный пароль.")
    if settings.owner_totp_secret and not verify_totp(payload.totp_code, settings.owner_totp_secret.get_secret_value()):
        throttle.record_failure(address)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный одноразовый код.")

    throttle.reset(address)
    request.session["owner_email"] = settings.owner_email
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_owner(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Run to verify they pass, then the whole API suite**

Run: `cd apps/api && .venv/bin/pytest tests/test_auth.py -q && .venv/bin/pytest -q`
Expected: all pass.

---

### Task 3: Owner password command

**Files:**
- Create: `apps/api/app/auth/password_file.py`
- Create: `scripts/set-owner-password.py`
- Test: `apps/api/tests/test_owner_password_file.py`

**Interfaces:**
- Produces: `OWNER_PASSWORD_KEY = "CATS_HOUSE_OWNER_PASSWORD_HASH"`, `MIN_PASSWORD_LENGTH = 12`, `validate_new_password(first: str, second: str) -> None` (raises `ValueError` with Russian text), `write_env_value(path: Path, key: str, value: str) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from argon2 import PasswordHasher

from app.auth.password_file import OWNER_PASSWORD_KEY, validate_new_password, write_env_value


def test_replaces_only_the_password_line_and_escapes_dollars(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nCATS_HOUSE_OWNER_PASSWORD_HASH=$$argon2id$$old\nB=x$$y\n", encoding="utf-8")
    new_hash = PasswordHasher().hash("correct horse battery")

    write_env_value(env, OWNER_PASSWORD_KEY, new_hash)

    lines = env.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "A=1"
    assert lines[2] == "B=x$$y"
    stored = lines[1].removeprefix(f"{OWNER_PASSWORD_KEY}=")
    assert "$" not in stored.replace("$$", "")
    assert PasswordHasher().verify(stored.replace("$$", "$"), "correct horse battery")


def test_adds_the_line_to_a_missing_or_new_file(tmp_path):
    env = tmp_path / ".env"

    write_env_value(env, OWNER_PASSWORD_KEY, "$argon2id$x")

    assert env.read_text(encoding="utf-8") == "CATS_HOUSE_OWNER_PASSWORD_HASH=$$argon2id$$x\n"


@pytest.mark.parametrize(
    ("first", "second", "message"),
    [("long enough pass", "long enough pasS", "не совпадают"), ("short", "short", "не менее 12")],
)
def test_rejects_mismatched_or_short_passwords(first, second, message):
    with pytest.raises(ValueError, match=message):
        validate_new_password(first, second)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/api && .venv/bin/pytest tests/test_owner_password_file.py -q`
Expected: `ModuleNotFoundError: No module named 'app.auth.password_file'`.

- [ ] **Step 3: Implement the module**

```python
"""Write the owner password hash into a .env file used by docker compose and dev-native.sh."""

from pathlib import Path

OWNER_PASSWORD_KEY = "CATS_HOUSE_OWNER_PASSWORD_HASH"
MIN_PASSWORD_LENGTH = 12


def validate_new_password(first: str, second: str) -> None:
    if first != second:
        raise ValueError("Пароли не совпадают.")
    if len(first) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Пароль должен содержать не менее {MIN_PASSWORD_LENGTH} символов.")


def write_env_value(path: Path, key: str, value: str) -> None:
    """Replace (or append) `key=value`; `$` is doubled as docker compose expects."""
    line = f"{key}={value.replace('$', '$$')}"
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    output, replaced = [], False
    for current in existing:
        if current.startswith(f"{key}="):
            if not replaced:
                output.append(line)
                replaced = True
            continue
        output.append(current)
    if not replaced:
        output.append(line)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Implement the command** `scripts/set-owner-password.py` (make it executable: `chmod +x scripts/set-owner-password.py`)

```python
#!/usr/bin/env python3
"""Задать новый пароль владельца: хеш Argon2 записывается в .env, пароль и хеш не печатаются."""

import argparse
import sys
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Смена пароля владельца Cat's House")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env", help="Файл .env (по умолчанию в корне проекта)")
    args = parser.parse_args()

    from argon2 import PasswordHasher
    from app.auth.password_file import OWNER_PASSWORD_KEY, validate_new_password, write_env_value

    first = getpass("Новый пароль владельца: ")
    second = getpass("Повторите пароль: ")
    try:
        validate_new_password(first, second)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    write_env_value(args.env_file, OWNER_PASSWORD_KEY, PasswordHasher().hash(first))
    print("Пароль владельца обновлён. Перезапустите API, чтобы он вступил в силу.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the tests and a smoke check**

Run: `cd apps/api && .venv/bin/pytest tests/test_owner_password_file.py -q && .venv/bin/python ../../scripts/set-owner-password.py --help`
Expected: `4 passed`; help text printed with exit code 0.

---

### Task 4: Owner session client and login page

**Files:**
- Create: `apps/web/src/owner-session.ts`
- Create: `apps/web/src/pages/login-page.ts`
- Test: `apps/web/test/login-page.test.ts`

**Interfaces:**
- Produces from `owner-session.ts`:
  - `type OwnerStatus = { authenticated: boolean; totp_required: boolean }`
  - `type LoginResult = { ok: true } | { ok: false; message: string }`
  - `fetchOwnerStatus(): Promise<OwnerStatus>` — never throws; failure → guest.
  - `loginOwner(password: string, totpCode?: string): Promise<LoginResult>`
  - `logoutOwner(): Promise<void>` — never throws.
  - `safeNext(raw: string | null | undefined): string`
- Produces `<cats-login-page>` with properties `status: OwnerStatus`, `next: string | null`, `navigate: (url: string) => void` (default `window.location.assign`), and event `owner-logout-request` (bubbles, composed) from its «Выйти» button.

- [ ] **Step 1: Write the failing tests** `apps/web/test/login-page.test.ts`

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'

import '../src/pages/login-page'
import { safeNext } from '../src/owner-session'

type LoginPage = HTMLElement & { status: { authenticated: boolean; totp_required: boolean }; next: string | null; navigate: (url: string) => void; updateComplete: Promise<boolean> }

const settle = () => new Promise((resolve) => setTimeout(resolve, 0))
async function renderPage(status = { authenticated: false, totp_required: false }, next: string | null = null) {
  const page = document.createElement('cats-login-page') as LoginPage
  page.status = status
  page.next = next
  page.navigate = vi.fn()
  document.body.append(page)
  await page.updateComplete
  return page
}
async function submit(page: LoginPage, password: string, code?: string) {
  const root = page.shadowRoot!
  const passwordInput = root.querySelector('input[name="password"]') as HTMLInputElement
  passwordInput.value = password
  passwordInput.dispatchEvent(new Event('input'))
  if (code !== undefined) {
    const codeInput = root.querySelector('input[name="totp"]') as HTMLInputElement
    codeInput.value = code
    codeInput.dispatchEvent(new Event('input'))
  }
  // Let Lit commit the typed values first, so clearing them later is a real change.
  await page.updateComplete
  root.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }))
  await settle()
  await page.updateComplete
}

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

describe('safeNext', () => {
  it('keeps internal paths and rejects everything that could leave the site', () => {
    expect(safeNext('/tree?person=1&mode=mixed')).toBe('/tree?person=1&mode=mixed')
    for (const value of [null, '', 'tree', '//evil.example', '/\\evil.example', 'https://evil.example', '/login?next=/x']) expect(safeNext(value)).toBe('/')
  })
})

describe('cats-login-page', () => {
  it('signs in with the password and returns to the requested page', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const page = await renderPage(undefined, '/people/42')

    await submit(page, 'correct horse battery')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({ method: 'POST', body: JSON.stringify({ password: 'correct horse battery', totp_code: null }) }))
    expect(page.navigate).toHaveBeenCalledWith('/people/42')
  })

  it('does not send an empty password', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const page = await renderPage()

    await submit(page, '   ')

    expect(fetchMock).not.toHaveBeenCalled()
    expect(page.shadowRoot!.textContent).toContain('Введите пароль.')
  })

  it.each([
    [new Response(JSON.stringify({ detail: 'Неверный пароль.' }), { status: 401 }), 'Неверный пароль.'],
    [new Response(JSON.stringify({ detail: 'Слишком много попыток входа.' }), { status: 429, headers: { 'Retry-After': '61' } }), 'Слишком много попыток. Попробуйте через 2 мин.'],
    [new Response('<html>', { status: 502 }), 'Сервер недоступен. Попробуйте позже.'],
  ])('shows a Russian error for a failed sign-in', async (response, message) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    const page = await renderPage()

    await submit(page, 'some password here')

    expect(page.shadowRoot!.querySelector('[role="alert"]')?.textContent?.trim()).toBe(message)
    expect(page.navigate).not.toHaveBeenCalled()
    expect((page.shadowRoot!.querySelector('input[name="password"]') as HTMLInputElement).value).toBe('')
  })

  it('reports an unreachable server', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const page = await renderPage()

    await submit(page, 'some password here')

    expect(page.shadowRoot!.querySelector('[role="alert"]')?.textContent?.trim()).toBe('Сервер недоступен. Попробуйте позже.')
  })

  it('asks for the one-time code only when the server requires it', async () => {
    expect((await renderPage()).shadowRoot!.querySelector('input[name="totp"]')).toBeNull()
    document.body.replaceChildren()
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)
    const page = await renderPage({ authenticated: false, totp_required: true })

    await submit(page, 'some password here', '123456')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({ body: JSON.stringify({ password: 'some password here', totp_code: '123456' }) }))
  })

  it('shows the signed-in state with a sign-out request instead of the form', async () => {
    const page = await renderPage({ authenticated: true, totp_required: false })
    const requested = vi.fn()
    page.addEventListener('owner-logout-request', requested)

    expect(page.shadowRoot!.querySelector('form')).toBeNull()
    expect(page.shadowRoot!.textContent).toContain('Вы вошли как владелец')
    ;[...page.shadowRoot!.querySelectorAll('button')].find((button) => button.textContent?.includes('Выйти'))!.click()

    expect(requested).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/web && npx vitest run test/login-page.test.ts`
Expected: fails to import `../src/pages/login-page` / `../src/owner-session`.

- [ ] **Step 3: Implement `apps/web/src/owner-session.ts`**

```ts
export type OwnerStatus = { authenticated: boolean; totp_required: boolean }
export type LoginResult = { ok: true } | { ok: false; message: string }

const UNAVAILABLE = 'Сервер недоступен. Попробуйте позже.'
export const GUEST: OwnerStatus = { authenticated: false, totp_required: false }

/** The owner state as the API sees it; any failure means a guest. */
export async function fetchOwnerStatus(): Promise<OwnerStatus> {
  try {
    const response = await fetch('/api/v1/auth/status')
    if (!response.ok) return GUEST
    const data = await response.json()
    return { authenticated: data?.authenticated === true, totp_required: data?.totp_required === true }
  } catch {
    return GUEST
  }
}

export async function loginOwner(password: string, totpCode?: string): Promise<LoginResult> {
  let response: Response
  try {
    response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password, totp_code: totpCode?.trim() || null }),
    })
  } catch {
    return { ok: false, message: UNAVAILABLE }
  }
  if (response.status === 204) return { ok: true }
  if (response.status === 429) {
    const seconds = Number(response.headers.get('Retry-After')) || 900
    return { ok: false, message: `Слишком много попыток. Попробуйте через ${Math.ceil(seconds / 60)} мин.` }
  }
  if (response.status === 401) {
    const detail = await response.json().then((data) => data?.detail, () => null)
    return { ok: false, message: typeof detail === 'string' ? detail : 'Неверный пароль.' }
  }
  return { ok: false, message: UNAVAILABLE }
}

export async function logoutOwner(): Promise<void> {
  try {
    await fetch('/api/v1/auth/logout', { method: 'POST' })
  } catch {
    // The header switches to guest anyway; the next status request tells the truth.
  }
}

/** Only an internal path may be a redirect target after sign-in. */
export function safeNext(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\') || raw.startsWith('/login')) return '/'
  return raw
}
```

- [ ] **Step 4: Implement `apps/web/src/pages/login-page.ts`**

```ts
import { LitElement, css, html } from 'lit'

import { GUEST, loginOwner, safeNext, type OwnerStatus } from '../owner-session'

export class CatsLoginPage extends LitElement {
  static properties = { status: { attribute: false }, next: { attribute: false }, password: { state: true }, code: { state: true }, error: { state: true }, busy: { state: true } }
  declare status: OwnerStatus
  declare next: string | null
  private declare password: string
  private declare code: string
  private declare error: string
  private declare busy: boolean
  navigate: (url: string) => void = (url) => window.location.assign(url)

  constructor() {
    super()
    this.status = GUEST; this.next = null; this.password = ''; this.code = ''; this.error = ''; this.busy = false
  }

  static styles = css`
    :host { display:block; padding:4rem 1rem; }
    .panel { box-sizing:border-box; width:min(24rem,100%); margin:0 auto; padding:2rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; background:var(--sheet,#fff); }
    h1 { margin:0 0 1.5rem; font:400 2rem var(--font-serif,Georgia,serif); }
    label { display:block; margin-bottom:1rem; color:var(--text-2,#4a4c49); font-size:.875rem; font-weight:600; }
    input { box-sizing:border-box; display:block; width:100%; height:2.5rem; margin-top:.375rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; padding:0 .75rem; font:inherit; }
    input:focus { border-color:var(--green,#24513f); box-shadow:0 0 0 3px var(--green-light,#e4ece7); outline:0; }
    .actions { display:flex; gap:.5rem; flex-wrap:wrap; }
    button,.link { min-height:2.5rem; border:0; border-radius:3px; padding:0 1rem; background:var(--green,#24513f); color:#fff; font:600 .875rem Inter,system-ui,sans-serif; cursor:pointer; text-decoration:none; display:inline-flex; align-items:center; }
    .secondary { background:transparent; color:var(--ink,#171817); border:1px solid var(--border,#dcdcd8); }
    button:disabled { opacity:.6; cursor:default; }
    [role="alert"] { margin:0 0 1rem; color:#7d2b20; font-size:.875rem; }
  `

  private async submit(event: Event) {
    event.preventDefault()
    if (this.busy) return
    if (!this.password.trim()) { this.error = 'Введите пароль.'; return }
    this.busy = true; this.error = ''
    const result = await loginOwner(this.password, this.status.totp_required ? this.code : undefined)
    this.password = ''; this.code = ''; this.busy = false
    if (result.ok) this.navigate(safeNext(this.next))
    else this.error = result.message
  }

  private requestLogout() {
    this.dispatchEvent(new CustomEvent('owner-logout-request', { bubbles: true, composed: true }))
  }

  render() {
    if (this.status.authenticated) {
      return html`<section class="panel"><h1>Вход для владельца</h1><p>Вы вошли как владелец.</p><div class="actions"><button @click=${this.requestLogout}>Выйти</button><a class="link secondary" href=${safeNext(this.next)}>На главную</a></div></section>`
    }
    return html`<section class="panel"><h1>Вход для владельца</h1>
      <form @submit=${this.submit} novalidate>
        ${this.error ? html`<p role="alert">${this.error}</p>` : ''}
        <label>Пароль<input name="password" type="password" autocomplete="current-password" .value=${this.password} @input=${(event: Event) => { this.password = (event.target as HTMLInputElement).value }} /></label>
        ${this.status.totp_required ? html`<label>Одноразовый код<input name="totp" inputmode="numeric" autocomplete="one-time-code" maxlength="6" .value=${this.code} @input=${(event: Event) => { this.code = (event.target as HTMLInputElement).value }} /></label>` : ''}
        <div class="actions"><button type="submit" ?disabled=${this.busy}>${this.busy ? 'Проверяем…' : 'Войти'}</button></div>
      </form></section>`
  }
}

customElements.define('cats-login-page', CatsLoginPage)
```

Note: «На главную» in the signed-in view uses `safeNext(this.next)`, which is `/` unless the owner arrived with a `next`; that is intended (it returns the owner where they came from).

- [ ] **Step 5: Run to verify it passes**

Run: `cd apps/web && npx vitest run test/login-page.test.ts`
Expected: all tests pass.

---

### Task 5: Shell routing and header owner state

**Files:**
- Modify: `apps/web/src/app-shell.ts`
- Test: `apps/web/test/app-shell.test.ts`

**Interfaces:**
- Consumes: `fetchOwnerStatus`, `logoutOwner`, `GUEST`, `OwnerStatus` from Task 4; `<cats-login-page>` with `.status`, `.next`, event `owner-logout-request`.
- Produces: `cats-house-app` renders `<cats-login-page>` on `/login`; header shows `.owner-link` (guest) or `.owner-state` + `button.owner-logout` (owner).

- [ ] **Step 1: Write the failing tests** (append inside the existing `describe('cats-house-app', …)` block)

```ts
  const statusFetch = (status: { authenticated: boolean; totp_required: boolean }) => vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/status')) return Promise.resolve(new Response(JSON.stringify(status)))
    if (url.endsWith('/api/v1/auth/logout') && init?.method === 'POST') return Promise.resolve(new Response(null, { status: 204 }))
    return Promise.resolve(new Response('[]'))
  })
  const settled = async (element: CatsHouseApp) => { await new Promise((resolve) => setTimeout(resolve, 0)); await element.updateComplete }

  it('links the guest to the login page with the current address as next', async () => {
    history.pushState({}, '', '/tree?person=42&mode=mixed')
    vi.stubGlobal('fetch', statusFetch({ authenticated: false, totp_required: false }))
    const element = await renderApp()
    await settled(element)

    const link = element.shadowRoot?.querySelector('a.owner-link') as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe(`/login?next=${encodeURIComponent('/tree?person=42&mode=mixed')}`)
    expect(link.querySelector('.short')?.textContent).toBe('Владелец')
  })

  it('shows the owner state and signs out from the header', async () => {
    const fetchMock = statusFetch({ authenticated: true, totp_required: false })
    vi.stubGlobal('fetch', fetchMock)
    const element = await renderApp()
    await settled(element)

    expect(element.shadowRoot?.querySelector('.owner-state')?.textContent).toContain('Владелец')
    ;(element.shadowRoot?.querySelector('button.owner-logout') as HTMLButtonElement).click()
    await settled(element)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/logout', { method: 'POST' })
    expect(element.shadowRoot?.querySelector('a.owner-link')).not.toBeNull()
  })

  it('treats a failing status request as a guest', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => String(input).endsWith('/auth/status') ? Promise.reject(new Error('down')) : Promise.resolve(new Response('[]'))))
    const element = await renderApp()
    await settled(element)

    expect(element.shadowRoot?.querySelector('a.owner-link')).not.toBeNull()
  })

  it('renders the login page on /login with status and next', async () => {
    history.pushState({}, '', '/login?next=%2Fpeople%2F7')
    vi.stubGlobal('fetch', statusFetch({ authenticated: false, totp_required: true }))
    const element = await renderApp()
    await settled(element)

    const page = element.shadowRoot?.querySelector('cats-login-page') as HTMLElement & { status: { totp_required: boolean }; next: string | null }
    expect(page).not.toBeNull()
    expect(page.next).toBe('/people/7')
    expect(page.status.totp_required).toBe(true)
    expect(element.shadowRoot?.querySelector('cats-house-home')).toBeNull()
  })

  it('signs out when the login page asks for it', async () => {
    history.pushState({}, '', '/login')
    const fetchMock = statusFetch({ authenticated: true, totp_required: false })
    vi.stubGlobal('fetch', fetchMock)
    const element = await renderApp()
    await settled(element)

    element.shadowRoot?.querySelector('cats-login-page')?.dispatchEvent(new CustomEvent('owner-logout-request', { bubbles: true, composed: true }))
    await settled(element)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/logout', { method: 'POST' })
    expect((element.shadowRoot?.querySelector('cats-login-page') as HTMLElement & { status: { authenticated: boolean } }).status.authenticated).toBe(false)
  })
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/web && npx vitest run test/app-shell.test.ts`
Expected: the five new tests fail; existing ones still pass.

- [ ] **Step 3: Implement in `apps/web/src/app-shell.ts`**

Imports:

```ts
import './pages/login-page'
import { GUEST, fetchOwnerStatus, logoutOwner, type OwnerStatus } from './owner-session'
```

Add `ownerStatus: { state: true }` to `static properties`, `private declare ownerStatus: OwnerStatus`, initialise `this.ownerStatus = GUEST` in the constructor, and load it with the other start-up requests in `connectedCallback` (next to `checkPublicApi()`):

```ts
void this.loadOwnerStatus()
```

Methods:

```ts
  private async loadOwnerStatus() { this.ownerStatus = await fetchOwnerStatus() }
  private async signOut() { await logoutOwner(); this.ownerStatus = { ...this.ownerStatus, authenticated: false } }
  private ownerControls() {
    if (this.ownerStatus.authenticated) return html`<span class="owner-state">Владелец · <button class="owner-logout" @click=${this.signOut}>Выйти</button></span>`
    const next = `${window.location.pathname}${window.location.search}`
    return html`<a class="owner-link" href="/login?next=${encodeURIComponent(next)}"><span class="full">Вход для владельца</span><span class="short">Владелец</span></a>`
  }
```

In `render()`, replace `<a class="owner-link" href="/login">Вход для владельца</a>` with `${this.ownerControls()}`, and extend the page switch so `/login` comes first:

```ts
const isLoginPage = window.location.pathname === '/login'
...
${isLoginPage ? html`<cats-login-page .status=${this.ownerStatus} .next=${new URLSearchParams(window.location.search).get('next')} @owner-logout-request=${this.signOut}></cats-login-page>` : isTreePage ? … (unchanged chain)}
```

Styles — replace the `.owner-link` rule and the mobile media query line:

```css
    .owner-link,.owner-state { color:var(--text-2,var(--cats-muted)); font-size:.8125rem; text-decoration:none; white-space:nowrap; }
    .owner-link .short { display:none; }
    .owner-logout { border:0; background:transparent; color:var(--green,var(--cats-accent)); cursor:pointer; font:inherit; font-weight:600; padding:0; }
    @media (max-width:45rem) { header { gap:1rem; padding:0 1rem; } .header-right { gap:.75rem; } .search { width:11rem; } .owner-link .full { display:none; } .owner-link .short { display:inline; } }
```

Check whether an existing test asserts `textContent` contains «Вход для владельца» — it still does (the full label is in the DOM, only hidden by CSS on narrow screens).

- [ ] **Step 4: Run to verify they pass, then the whole web suite and typecheck**

Run: `cd apps/web && npx vitest run test/app-shell.test.ts && npm test && npm run typecheck`
Expected: all pass, typecheck exits 0.

---

### Task 6: End-to-end sign-in, docs and final verification

**Files:**
- Create: `apps/web/e2e/owner-login.spec.ts`
- Modify: `README.md` (section «Публичное семейное дерево» → add «Вход владельца» subsection after it)

**Interfaces:**
- Consumes: everything above, running stack (API `http://localhost:8000`, UI `CATS_HOUSE_E2E_URL`, default `http://localhost:5176`).

- [ ] **Step 1: Write the e2e test**

```ts
import { expect, test } from '@playwright/test'

const password = process.env.CATS_HOUSE_E2E_OWNER_PASSWORD

test('the owner signs in from the header, returns to the page and signs out', async ({ page }) => {
  test.skip(!password, 'Set CATS_HOUSE_E2E_OWNER_PASSWORD to run the owner sign-in check.')
  await page.goto('/')
  await page.getByRole('link', { name: 'Вход для владельца' }).click()
  await expect(page).toHaveURL(/\/login\?next=%2F$/)

  await page.getByLabel('Пароль').fill(password!)
  await page.getByRole('button', { name: 'Войти' }).click()

  await expect(page).toHaveURL(/\/$/)
  await expect(page.locator('cats-house-app .owner-state')).toContainText('Владелец')
  await page.getByRole('button', { name: 'Выйти' }).click()
  await expect(page.getByRole('link', { name: 'Вход для владельца' })).toBeVisible()
})
```

- [ ] **Step 2: Add the README subsection**

```markdown
### Вход владельца

Ссылка «Вход для владельца» в шапке ведёт на `/login`. После входа в шапке
видно «Владелец · Выйти». После пяти неверных паролей за 15 минут вход с
этого адреса временно блокируется.

Новый пароль задаётся командой; она дважды спросит пароль (не менее 12
символов) и запишет только его хеш в `.env`. После смены перезапустите API.

```sh
python scripts/set-owner-password.py
```

Сквозная проверка входа запускается, только если пароль передан через
переменную окружения `CATS_HOUSE_E2E_OWNER_PASSWORD`.
```

- [ ] **Step 3: Restart the running API so the new endpoints exist**

The dev stack started with `scripts/dev-native.sh` does not reload Python code. Stop it (Ctrl-C in its terminal tab) and start it again:

```bash
CATS_HOUSE_WEB_PORT=5176 bash scripts/dev-native.sh
```

- [ ] **Step 4: Final verification**

Run each and expect exit code 0:

```bash
cd apps/api && .venv/bin/pytest -q
cd apps/web && npm test && npm run typecheck && npm run build && npm run test:e2e
```

Without `CATS_HOUSE_E2E_OWNER_PASSWORD` the owner e2e test reports as skipped; the six existing e2e tests pass. Then open `http://localhost:5176/login` and check by hand: wrong password shows «Неверный пароль.», the header link on a narrow window reads «Владелец».

- [ ] **Step 5: Hand over** — do not commit; report to the owner and ask whether to commit.
