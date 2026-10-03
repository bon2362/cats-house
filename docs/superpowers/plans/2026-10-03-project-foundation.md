# Cat's House: Project Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a reproducible AGPL-licensed monorepo for Cat's House with a Russian web shell, an independent API, PostgreSQL, and S3-compatible media storage.

**Architecture:** The project is a Docker Compose monorepo with `apps/web` for the Lit public and owner interface, `apps/api` for the FastAPI service, PostgreSQL for application records, and MinIO for development media storage. The web application accesses only the Cat's House API; no Gramps process or database is part of the runtime.

**Tech Stack:** TypeScript, Lit, Vite, Python, FastAPI, SQLAlchemy, Alembic, PostgreSQL 16, MinIO, Docker Compose, Vitest, pytest.

**Spec:** `docs/specs/family-tree-open-source-product-design.md`

## Global Constraints

- The repository is AGPL-3.0 and retains attribution for every copied or adapted Gramps file.
- User-facing interface text, validation messages, error messages, email templates, and documentation are Russian.
- PostgreSQL and the Cat's House API are the only runtime source of genealogy data; Gramps is not a runtime dependency.
- The public application must not expose owner credentials, database access, storage credentials, or internal administrative routes.
- Product data remains local to the controlled development environment until the owner explicitly approves a production migration.
- Run targeted tests during each task; run the complete test suites once after the final foundation change.

## Review Focus

- A browser started without an owner session must never receive an administrative route, cookie, token, or storage credential; Task 4 adds an API authorization test.
- Cyrillic names, labels, and error messages must remain UTF-8 through the API and browser; Task 3 adds a Russian API response test and Task 5 adds a rendered Russian UI test.
- A missing or malformed required environment variable must stop the API rather than silently use an unsafe default; Task 2 adds configuration validation tests.
- Starting the full development stack twice must not destroy PostgreSQL or MinIO volumes; Task 2 verifies named persistent volumes.
- A copied Gramps file without a corresponding `NOTICE` entry must fail the repository compliance check; Task 1 adds the check before any copied component is accepted.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `LICENSE` | Complete AGPL-3.0 license text. |
| `NOTICE` | Attribution and license mapping for Gramps-derived code. |
| `README.md` | Russian project overview and local startup instructions. |
| `docker-compose.yml` | Development services: web, API, PostgreSQL, MinIO. |
| `.env.example` | Safe, documented local configuration names without real secrets. |
| `apps/api/pyproject.toml` | Python dependencies and test configuration. |
| `apps/api/app/main.py` | FastAPI application factory and route registration. |
| `apps/api/app/core/config.py` | Validated configuration model. |
| `apps/api/app/api/routes/health.py` | Non-sensitive readiness endpoint. |
| `apps/api/tests/` | API and configuration tests. |
| `apps/web/package.json` | Frontend dependencies and commands. |
| `apps/web/src/main.ts` | Lit application bootstrap. |
| `apps/web/src/app-shell.ts` | Russian application shell and route outlet. |
| `apps/web/src/pages/home-page.ts` | Temporary Russian landing page for the product. |
| `apps/web/src/styles/tokens.css` | Project design tokens; no copied Gramps styles yet. |
| `apps/web/src/locales/ru.ts` | Central Russian interface strings. |
| `apps/web/test/` | Frontend unit tests. |
| `scripts/check-notices.mjs` | Fails when Gramps-derived source lacks a `NOTICE` record. |

### Task 1: Repository identity and AGPL compliance foundation

**Files:**
- Create: `LICENSE`
- Create: `NOTICE`
- Create: `README.md`
- Create: `.gitignore`
- Create: `scripts/check-notices.mjs`
- Test: `scripts/check-notices.test.mjs`

**Interfaces:**
- Consumes: approved project name `Cat's House` and AGPL-3.0 requirement.
- Produces: `node scripts/check-notices.mjs <path>` exits 0 for original project code and exits 1 for a file marked `Gramps-derived` without a matching `NOTICE` row.

- [ ] **Step 1: Write the failing compliance test**

```js
it('rejects a Gramps-derived file missing from NOTICE', async () => {
  await expect(runNoticeCheck('test/fixtures/missing-notice.js')).rejects.toMatch(
    /NOTICE/
  )
})
```

- [ ] **Step 2: Run the compliance test to verify it fails**

Run: `node --test scripts/check-notices.test.mjs`
Expected: FAIL because the checker does not exist.

- [ ] **Step 3: Add AGPL files and implement the notice checker**

`NOTICE` must contain columns for local path, upstream repository path, upstream copyright notice, and license. `check-notices.mjs` scans only files explicitly marked `Gramps-derived` and verifies that each has a local-path entry.

- [ ] **Step 4: Run the compliance test to verify it passes**

Run: `node --test scripts/check-notices.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit the repository identity**

```bash
git add LICENSE NOTICE README.md .gitignore scripts
git commit -m "chore: initialize Cat's House repository"
```

### Task 2: Reproducible local services and validated API configuration

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/app/core/config.py`
- Create: `apps/api/tests/test_config.py`

**Interfaces:**
- Consumes: environment variables `CATS_HOUSE_DATABASE_URL`, `CATS_HOUSE_S3_ENDPOINT`, `CATS_HOUSE_S3_BUCKET`, `CATS_HOUSE_OWNER_EMAIL`.
- Produces: `Settings()` either returns validated values or raises a clear configuration error; Compose defines persistent `postgres_data` and `minio_data` volumes.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_settings_reject_missing_database_url(monkeypatch):
    monkeypatch.delenv("CATS_HOUSE_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings()

def test_settings_preserves_utf8_owner_email(monkeypatch):
    monkeypatch.setenv("CATS_HOUSE_OWNER_EMAIL", "владелец@example.test")
    assert Settings().owner_email == "владелец@example.test"
```

- [ ] **Step 2: Run the configuration tests to verify they fail**

Run: `cd apps/api && pytest tests/test_config.py -q`
Expected: FAIL because the API package and `Settings` do not exist.

- [ ] **Step 3: Implement `Settings` and the Compose services**

Use a strict Pydantic settings model. Compose must start PostgreSQL 16 and MinIO with named volumes, and pass only variables declared in `.env.example` to the API.

- [ ] **Step 4: Run configuration and Compose validation**

Run: `cd apps/api && pytest tests/test_config.py -q && docker compose config`
Expected: all tests pass; Compose prints valid resolved configuration without secrets.

- [ ] **Step 5: Commit local service foundation**

```bash
git add docker-compose.yml .env.example apps/api
git commit -m "chore: add local service foundation"
```

### Task 3: Independent API application and health contract

**Files:**
- Create: `apps/api/app/main.py`
- Create: `apps/api/app/api/routes/health.py`
- Create: `apps/api/app/api/router.py`
- Create: `apps/api/tests/test_health.py`

**Interfaces:**
- Consumes: `Settings` from `app.core.config`.
- Produces: `create_app(settings: Settings) -> FastAPI`; `GET /api/v1/health` returns `{"status":"ok","service":"Cat's House"}` and never returns configuration values.

- [ ] **Step 1: Write the failing health tests**

```python
def test_health_returns_russian_product_identity(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Cat's House"}

def test_health_never_returns_database_url(client):
    assert "database" not in client.get("/api/v1/health").text.lower()
```

- [ ] **Step 2: Run the health tests to verify they fail**

Run: `cd apps/api && pytest tests/test_health.py -q`
Expected: FAIL because the application factory and route do not exist.

- [ ] **Step 3: Implement the API factory and health route**

Mount the public versioned router at `/api/v1`. Keep route registration independent from database setup so later domain tests can use a transaction-scoped test database.

- [ ] **Step 4: Run the health tests to verify they pass**

Run: `cd apps/api && pytest tests/test_health.py -q`
Expected: PASS.

- [ ] **Step 5: Commit the API contract**

```bash
git add apps/api
git commit -m "feat: add Cat's House API health contract"
```

### Task 4: Owner authentication boundary

**Files:**
- Create: `apps/api/app/auth/service.py`
- Create: `apps/api/app/api/routes/auth.py`
- Create: `apps/api/app/api/dependencies.py`
- Create: `apps/api/tests/test_auth.py`

**Interfaces:**
- Consumes: `POST /api/v1/auth/login` with an owner credential in the request body.
- Produces: `require_owner(request) -> OwnerSession`; unauthenticated access to `/api/v1/admin/*` returns HTTP 401; public routes never set an owner session.

- [ ] **Step 1: Write failing owner-boundary tests**

```python
def test_admin_route_rejects_anonymous_client(client):
    assert client.get("/api/v1/admin/session").status_code == 401

def test_public_health_does_not_set_owner_cookie(client):
    response = client.get("/api/v1/health")
    assert "set-cookie" not in response.headers
```

- [ ] **Step 2: Run the authorization tests to verify they fail**

Run: `cd apps/api && pytest tests/test_auth.py -q`
Expected: FAIL because authentication routes and dependencies do not exist.

- [ ] **Step 3: Implement the minimal owner-session boundary**

Use a password hash and an HTTP-only secure session cookie. This task establishes the boundary only; two-factor authentication is added in the safety phase before production migration.

- [ ] **Step 4: Run the authorization tests to verify they pass**

Run: `cd apps/api && pytest tests/test_auth.py -q`
Expected: PASS.

- [ ] **Step 5: Commit the owner boundary**

```bash
git add apps/api
git commit -m "feat: add owner authentication boundary"
```

### Task 5: Russian Lit web shell

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/vite.config.ts`
- Create: `apps/web/src/main.ts`
- Create: `apps/web/src/app-shell.ts`
- Create: `apps/web/src/pages/home-page.ts`
- Create: `apps/web/src/locales/ru.ts`
- Create: `apps/web/src/styles/tokens.css`
- Create: `apps/web/test/app-shell.test.ts`

**Interfaces:**
- Consumes: `GET /api/v1/health` without owner credentials.
- Produces: custom element `<cats-house-app>`; it renders Russian project navigation and a Russian loading/error state if health cannot be reached.

- [ ] **Step 1: Write the failing Russian shell test**

```ts
it('renders the Russian public navigation', async () => {
  const element = await fixture<CatsHouseApp>(html`<cats-house-app></cats-house-app>`)
  expect(element.shadowRoot?.textContent).toContain('Дерево')
  expect(element.shadowRoot?.textContent).toContain('Поиск')
})
```

- [ ] **Step 2: Run the shell test to verify it fails**

Run: `cd apps/web && npm test -- app-shell.test.ts`
Expected: FAIL because the web project and custom element do not exist.

- [ ] **Step 3: Implement `<cats-house-app>` and Russian string module**

Do not copy Gramps styles in this phase. Create project tokens and a minimal Russian shell with placeholders for `Дерево`, `Поиск`, and `Войти`.

- [ ] **Step 4: Run the shell test to verify it passes**

Run: `cd apps/web && npm test -- app-shell.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit the web foundation**

```bash
git add apps/web
git commit -m "feat: add Russian web shell"
```

### Task 6: Foundation integration verification

**Files:**
- Modify: `README.md`
- Create: `scripts/verify-foundation.sh`

**Interfaces:**
- Consumes: local Compose stack and the commands established in Tasks 1–5.
- Produces: `scripts/verify-foundation.sh` exits 0 only when API tests, web tests, notice check, Compose configuration, and a live `GET /api/v1/health` succeed.

- [ ] **Step 1: Write the failing integration verification script assertion**

```bash
assert_contains "$(curl -fsS http://localhost:8000/api/v1/health)" '"service":"Cat'\''s House"'
```

- [ ] **Step 2: Run verification before adding the stack startup steps**

Run: `scripts/verify-foundation.sh`
Expected: FAIL because services are not started or the script does not exist.

- [ ] **Step 3: Implement the verification script and document startup**

The script must run targeted test commands, validate Compose, start required local services without deleting volumes, wait for health, then stop only the application containers it started.

- [ ] **Step 4: Run the full foundation verification**

Run: `scripts/verify-foundation.sh`
Expected: PASS; API health responds with `{"status":"ok","service":"Cat's House"}`.

- [ ] **Step 5: Commit the verified foundation**

```bash
git add README.md scripts docker-compose.yml apps
git commit -m "test: verify project foundation"
```

## Self-Review

- Spec coverage: this plan intentionally covers only the project foundation. Genealogical data, migration, public tree, editor, export, and backups are scoped to later roadmap phases.
- Type consistency: all API routes in this plan use the `/api/v1` prefix; the application factory is `create_app`; the web root is `<cats-house-app>`.
- Review focus coverage: Tasks 1–5 each include the matching targeted test described in Review Focus.
- Proportion: the plan specifies one independently testable foundation milestone and does not duplicate later implementation plans.
