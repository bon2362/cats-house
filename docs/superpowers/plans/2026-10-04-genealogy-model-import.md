# Genealogy Model and GEDCOM Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Создать собственную модель генеалогических данных Cat's House и безопасно импортировать реальный GEDCOM в непубличную локальную базу.

**Architecture:** PostgreSQL остаётся единственным рабочим хранилищем. SQLAlchemy и Alembic описывают и создают схему, ограниченный собственный GEDCOM-парсер превращает файл в нормализованный предпросмотр, а сервис импорта сохраняет предпросмотр и применяет его одной транзакцией. API доступен только владельцу; отдельный локальный сценарий использует тот же сервис для проверки реального файла, не добавляя его в репозиторий.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, psycopg 3, PostgreSQL 16, pytest, HTTPX.

**Spec:** `docs/superpowers/specs/2026-10-04-genealogy-model-import-design.md`

## Global Constraints

- Интерфейс API, ошибки и документация — на русском; технические имена Python, SQL и HTTP могут быть английскими.
- Cat's House не запускает Gramps и не использует его формат или API как рабочее хранилище.
- Реальные `Древо 2.at5`, `1.ged` и `1.xml` не копируются в Git, Docker-образы, тестовые фикстуры или облачные сервисы.
- Импорт выполняется только авторизованным владельцем и не создаёт частичных генеалогических записей при ошибке.
- Первый принятый импорт создаёт начальный набор; повторная миграция не перезаписывает данные автоматически.
- `source_uid` сохраняется у человека; GEDCOM-идентификаторы не становятся публичными идентификаторами API.

## Review Focus

- UTF-8 с BOM и кириллические имена должны импортироваться без потери символов — тест в Task 2.
- Запись, ссылающаяся на отсутствующего человека или семью, должна остановить применение без частичных строк — тесты в Task 4.
- `ABT`, `BEF`, `AFT`, `BET … AND …` и обычная дата должны оставаться проверяемыми, а не превращаться в вымышленную точную дату — тест в Task 2.
- Несколько союзов и дети из разных союзов должны создавать отдельные связи без дубликатов — тест в Task 4.
- Второй запрос применения одного предпросмотра или импорт при уже существующем наборе должен возвращать понятный конфликт — тест в Task 5.

---

## File Structure

| Путь | Ответственность |
| --- | --- |
| `apps/api/app/db/base.py` | Общая декларативная база SQLAlchemy и UUID-поля. |
| `apps/api/app/db/session.py` | Фабрика сессий PostgreSQL и FastAPI-зависимость сессии. |
| `apps/api/app/models/genealogy.py` | ORM-модели генеалогических сущностей и попытки импорта. |
| `apps/api/alembic/` | Конфигурация и ревизия схемы PostgreSQL. |
| `apps/api/app/gedcom/types.py` | Независимые структуры разобранного GEDCOM и отчёта. |
| `apps/api/app/gedcom/parser.py` | Разбор строк GEDCOM 5.5.1 в структуры `types.py`. |
| `apps/api/app/imports/service.py` | Предпросмотр, валидация, сохранение и атомарное применение. |
| `apps/api/app/api/routes/imports.py` | Закрытые HTTP-маршруты предпросмотра, отчёта и применения. |
| `apps/api/tests/fixtures/*.ged` | Минимальные синтетические GEDCOM-файлы без семейных данных. |
| `apps/api/tests/test_*.py` | Изолированные проверки схемы, парсера, сервиса и API. |
| `scripts/import-local-gedcom.py` | Локальный явный сценарий проверки/импорта файла по переданному пути. |

### Task 1: PostgreSQL schema and migration

**Files:**
- Create: `apps/api/app/db/base.py`, `apps/api/app/db/session.py`, `apps/api/app/models/__init__.py`, `apps/api/app/models/genealogy.py`
- Create: `apps/api/alembic.ini`, `apps/api/alembic/env.py`, `apps/api/alembic/versions/0001_genealogy_schema.py`
- Modify: `apps/api/pyproject.toml`, `apps/api/app/main.py`, `apps/api/tests/conftest.py`
- Test: `apps/api/tests/test_models.py`, `apps/api/tests/test_migrations.py`

**Interfaces:**
- Produces ORM models `Person`, `Union`, `ParentChild`, `Event`, `Note`, `Source`, `Media`, `ImportRun`, `ImportIssue` and `get_session() -> Iterator[Session]`.
- Produces Alembic revision `0001_genealogy_schema`, consumed by every database-backed import task.

- [ ] **Step 1: Write failing migration and model tests**

```python
def test_initial_migration_creates_genealogy_and_import_tables(postgres_url):
    upgrade_database(postgres_url, "head")
    assert table_names(postgres_url) >= {"people", "unions", "parent_children", "events", "import_runs", "import_issues"}

def test_person_source_uid_is_unique_within_an_import(session):
    ...
    with pytest.raises(IntegrityError):
        session.flush()
```

- [ ] **Step 2: Run model and migration tests to verify they fail**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_models.py tests/test_migrations.py -q`  
Expected: FAIL because database models and Alembic revision do not exist.

- [ ] **Step 3: Add SQLAlchemy, Alembic and psycopg dependencies and implement the schema**

Use UUID primary keys. `ImportRun` stores state (`previewed`, `applied`, `failed`), SHA-256, original filename, JSONB normalized payload, JSONB counts and creation time. `ImportIssue` stores its import ID, severity (`warning` or `error`), Russian message, GEDCOM line and optional tag. `Event` stores raw date text plus nullable normalized lower/upper ISO dates and qualifier. Add foreign keys and uniqueness constraints needed to prevent duplicate parent-child links and duplicate `source_uid` within a run.

- [ ] **Step 4: Add Alembic startup configuration without automatic schema creation in the API**

`create_app()` must only configure the session factory; schema changes run explicitly through Alembic. Docker Compose will run `alembic upgrade head` before Uvicorn in a later task.

- [ ] **Step 5: Run Task 1 tests**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_models.py tests/test_migrations.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add apps/api
git commit -m "feat: add genealogy database schema"
```

### Task 2: GEDCOM parser and report model

**Files:**
- Create: `apps/api/app/gedcom/__init__.py`, `apps/api/app/gedcom/types.py`, `apps/api/app/gedcom/parser.py`
- Create: `apps/api/tests/fixtures/cyrillic-family.ged`, `apps/api/tests/fixtures/invalid-reference.ged`, `apps/api/tests/fixtures/complex-family.ged`
- Test: `apps/api/tests/test_gedcom_parser.py`

**Interfaces:**
- Produces `parse_gedcom(content: bytes) -> ParsedGedcom` and `build_preview(parsed: ParsedGedcom) -> ImportPreview`.
- `ImportPreview` provides `people`, `unions`, `parent_links`, `events`, `issues`, `counts`, and `has_errors: bool`; Task 3 persists it unchanged.

- [ ] **Step 1: Write failing parser tests for Cyrillic, `_UID`, links and dates**

```python
def test_parser_keeps_utf8_bom_cyrillic_and_source_uid():
    preview = build_preview(parse_gedcom(fixture_bytes("cyrillic-family.ged")))
    assert preview.people[0].name == "Анна Иванова"
    assert preview.people[0].source_uid == "E403332A_50"

@pytest.mark.parametrize("value, qualifier", [("ABT 1900", "about"), ("BEF 1900", "before"), ("BET 1900 AND 1910", "between")])
def test_parser_preserves_uncertain_dates(value, qualifier):
    assert parse_date(value).qualifier == qualifier
```

- [ ] **Step 2: Run parser tests to verify they fail**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_gedcom_parser.py -q`  
Expected: FAIL because the GEDCOM module does not exist.

- [ ] **Step 3: Implement the restricted GEDCOM 5.5.1 reader**

Decode UTF-8 with optional BOM, retain line numbers, parse level/tag/pointer lines, and support the tags named in the design spec. Map unknown optional tags to `warning` issues and malformed nesting, invalid encoding or required unresolved references to `error` issues. Do not silently drop an unknown tag.

- [ ] **Step 4: Add complex-family and invalid-reference tests**

Assert that two `FAMS` records create two unions, children remain attached to their correct union, and an absent `@I…@` produces an error with a GEDCOM line number.

- [ ] **Step 5: Run Task 2 tests**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_gedcom_parser.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```bash
git add apps/api/app/gedcom apps/api/tests
git commit -m "feat: parse GEDCOM import previews"
```

### Task 3: Persisted preview service

**Files:**
- Create: `apps/api/app/imports/__init__.py`, `apps/api/app/imports/service.py`
- Test: `apps/api/tests/test_import_preview.py`

**Interfaces:**
- Consumes `Session`, `parse_gedcom(content: bytes) -> ParsedGedcom`, `build_preview(...) -> ImportPreview`.
- Produces `create_preview(session: Session, filename: str, content: bytes) -> ImportRun` and `get_import_run(session: Session, import_id: UUID) -> ImportRun`.
- Task 4 consumes the normalized payload and issues stored by `create_preview`.

- [ ] **Step 1: Write failing preview-service tests**

```python
def test_create_preview_persists_counts_sha256_and_issues(session):
    run = create_preview(session, "family.ged", fixture_bytes("cyrillic-family.ged"))
    assert run.state == "previewed"
    assert run.counts["people"] == 2
    assert run.sha256 == hashlib.sha256(fixture_bytes("cyrillic-family.ged")).hexdigest()

def test_preview_with_parse_errors_is_recorded_but_not_applyable(session):
    assert create_preview(session, "broken.ged", fixture_bytes("invalid-reference.ged")).has_errors
```

- [ ] **Step 2: Run preview tests to verify they fail**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_import_preview.py -q`  
Expected: FAIL because the import service does not exist.

- [ ] **Step 3: Implement preview persistence**

Hash the original bytes with SHA-256. Serialize normalized parsed data, counts and every issue to the import tables. A syntax or reference error may be reported in a preview but never triggers a mutation of genealogy tables.

- [ ] **Step 4: Run Task 3 tests**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_import_preview.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```bash
git add apps/api/app/imports apps/api/tests/test_import_preview.py
git commit -m "feat: persist GEDCOM import previews"
```

### Task 4: Atomic import application

**Files:**
- Modify: `apps/api/app/imports/service.py`, `apps/api/app/models/genealogy.py`
- Test: `apps/api/tests/test_import_apply.py`

**Interfaces:**
- Consumes `apply_preview(session: Session, import_id: UUID) -> ImportRun`.
- Produces initial `Person`, `Union`, `ParentChild` and `Event` rows from one error-free `ImportRun`; Task 5 exposes it over HTTP.

- [ ] **Step 1: Write failing atomic-application tests**

```python
def test_apply_preview_creates_expected_people_unions_links_and_events(session):
    run = create_preview(session, "complex.ged", fixture_bytes("complex-family.ged"))
    applied = apply_preview(session, run.id)
    assert applied.state == "applied"
    assert count_rows(session, Person) == 4

def test_apply_rolls_back_all_genealogy_rows_when_payload_reference_is_invalid(session):
    ...
    assert count_rows(session, Person) == 0
    assert get_import_run(session, run.id).state == "failed"
```

- [ ] **Step 2: Run application tests to verify they fail**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_import_apply.py -q`  
Expected: FAIL because `apply_preview` does not exist.

- [ ] **Step 3: Implement `apply_preview` as one database transaction**

Reject previews containing `error` issues. Create people first, resolve GEDCOM pointers from the payload to newly created UUIDs, then create unions, parent-child links and events. On a database or reference failure, roll back genealogy rows, store the run as `failed` with a Russian issue, and re-raise a domain error.

- [ ] **Step 4: Add conflict tests**

Assert that an already applied run and any apply attempt after a successful initial import return a domain conflict and leave stored rows unchanged.

- [ ] **Step 5: Run Task 4 tests**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_import_apply.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add apps/api/app/imports apps/api/app/models apps/api/tests/test_import_apply.py
git commit -m "feat: apply GEDCOM imports atomically"
```

### Task 5: Owner-only import API and Docker migration

**Files:**
- Create: `apps/api/app/api/routes/imports.py`
- Modify: `apps/api/app/api/router.py`, `apps/api/app/api/dependencies.py`, `apps/api/app/main.py`, `docker-compose.yml`, `README.md`
- Test: `apps/api/tests/test_import_api.py`

**Interfaces:**
- Consumes `require_owner`, `get_session`, `create_preview`, `get_import_run`, `apply_preview`.
- Produces `POST /api/v1/admin/imports/preview`, `GET /api/v1/admin/imports/{id}`, and `POST /api/v1/admin/imports/{id}/apply`.

- [ ] **Step 1: Write failing API tests for access and lifecycle**

```python
def test_anonymous_client_cannot_preview_or_apply_import(client):
    assert client.post("/api/v1/admin/imports/preview", files={"file": (...) }).status_code == 401

def test_owner_can_preview_read_report_and_apply_once(owner_client):
    preview = owner_client.post("/api/v1/admin/imports/preview", files={"file": gedcom_upload()})
    assert preview.status_code == 201
    assert owner_client.post(f"/api/v1/admin/imports/{preview.json()['id']}/apply").status_code == 200
    assert owner_client.post(f"/api/v1/admin/imports/{preview.json()['id']}/apply").status_code == 409
```

- [ ] **Step 2: Run API tests to verify they fail**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_import_api.py -q`  
Expected: FAIL because import routes are not registered.

- [ ] **Step 3: Implement the three Russian-response routes**

Use multipart upload only for `.ged` files, return a compact Pydantic response containing ID, state, counts and issues, and map domain validation/conflict errors to 422/409 without exposing tracebacks. Keep `GET` reports owner-only.

- [ ] **Step 4: Run Alembic during container startup and document local API use**

Change the API Compose command to run `alembic upgrade head` before Uvicorn. README documents copying `.env`, installing `.[dev]`, logging in at `/api/v1/auth/login`, and the preview/apply curl sequence without embedding a password or family file path.

- [ ] **Step 5: Run Task 5 tests**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_import_api.py tests/test_auth.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add apps/api docker-compose.yml README.md
git commit -m "feat: add owner GEDCOM import API"
```

### Task 6: Local real-file acceptance and complete verification

**Files:**
- Create: `scripts/import-local-gedcom.py`
- Modify: `scripts/verify-foundation.sh`, `README.md`
- Test: `apps/api/tests/test_local_import_script.py`

**Interfaces:**
- Consumes `create_preview(session, filename, content)` and `apply_preview(session, import_id)`.
- Produces `python scripts/import-local-gedcom.py --file /absolute/path/1.ged --apply`, which prints only aggregate counts and issues, never GEDCOM contents.

- [ ] **Step 1: Write a failing script test using a temporary synthetic GEDCOM**

```python
def test_local_script_requires_explicit_apply_and_prints_counts(tmp_path):
    result = run_import_script(tmp_path / "family.ged")
    assert result.returncode == 0
    assert "Люди" in result.stdout
    assert database_has_no_people()
```

- [ ] **Step 2: Run the script test to verify it fails**

Run: `cd apps/api && .venv/bin/python -m pytest tests/test_local_import_script.py -q`  
Expected: FAIL because the local import script does not exist.

- [ ] **Step 3: Implement the explicit local acceptance command**

Require an absolute `--file` path and `--apply` for mutation. Default mode creates only a preview and prints state, counts and issue totals. Refuse to print parsed names, biographies or GEDCOM source lines. Read the same database settings as the API and run Alembic upgrade before creating a session.

- [ ] **Step 4: Run the real local acceptance import once**

Run: `python scripts/import-local-gedcom.py --file "/Users/ekoshkin/Downloads/telegram/1.ged" --apply`  
Expected: a non-public local database contains the imported data; the command prints counts, including at least 285 people and 398 events, plus warnings/errors. Do not commit the file, output containing personal data, database volume or generated report.

- [ ] **Step 5: Run complete verification**

Run: `scripts/verify-foundation.sh && cd apps/web && npm audit --omit=dev --audit-level=moderate`  
Expected: all API, web, NOTICE, migration and import tests pass; direct and proxied health checks pass; audit reports `found 0 vulnerabilities`.

- [ ] **Step 6: Commit Task 6 without family data**

```bash
git add scripts/import-local-gedcom.py scripts/verify-foundation.sh README.md apps/api/tests/test_local_import_script.py
git commit -m "feat: add local GEDCOM acceptance workflow"
```

## Plan self-review

- Coverage: Tasks 1–4 implement every persisted entity needed for this import and the atomic workflow; Task 5 implements all three specified owner-only routes; Task 6 performs the agreed real local acceptance run without tracking data.
- Interfaces: `parse_gedcom`/`build_preview` feed `create_preview`; `ImportRun` feeds `apply_preview`; those services feed the API and local script with consistent UUID input.
- Failure coverage: the five Review Focus cases are assigned to Tasks 2, 4 and 5; encoding, pointers, date qualifiers, complex families and duplicate applies are each explicitly tested.
- Scope: public presentation, editing, exports, media upload and repeat migrations remain outside this plan.
