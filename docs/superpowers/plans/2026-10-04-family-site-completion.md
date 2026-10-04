# Family Site Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Выпустить самостоятельный публичный семейный сайт с просмотром,
редактированием владельцем, материалами и переносимым архивом.

**Architecture:** FastAPI остаётся единственным API к PostgreSQL и объектному
хранилищу. Lit-клиент получает ограниченные публичные представления дерева и
карточек, а изменения принимает только закрытый API владельца. Экспорт и
резервное восстановление используют те же собственные модели, а не AT5.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Lit,
TypeScript, Vite, S3-compatible storage, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-04-family-site-completion-design.md`

## Global Constraints

- Публичны все люди и события; секреты, сессии, журналы, бэкапы и исходные
  GEDCOM/AT5 всегда закрыты.
- Интерфейс, ошибки и документация — на русском.
- Каждый запрос дерева ограничивает глубину и не отдаёт всю базу.
- Изменения доступны только владельцу, удаление заменяется архивированием.
- Gramps не является сервисом или хранилищем; заимствования фиксируются в
  `NOTICE`.

## Review Focus

- Глубокая или циклическая ветвь не должна перегружать API — Task 2.
- Анонимный запрос не должен изменять данные или получать журнал — Task 3.
- Архивированный человек не должен пропасть из уже существующих связей — Task 3.
- Недопустимый файл не должен попасть в S3 — Task 4.
- Восстановление архива должно вернуть те же контрольные количества — Task 5.

## File Structure

| Путь | Ответственность |
| --- | --- |
| `apps/api/app/api/routes/people.py` | Публичный поиск и карточки людей. |
| `apps/api/app/api/routes/tree.py` | Ограниченная выдача ветви дерева. |
| `apps/api/app/genealogy/read_service.py` | Построение публичных представлений. |
| `apps/web/src/pages/*.ts` | Поиск, карточка и дерево в браузере. |
| `apps/api/app/api/routes/admin_genealogy.py` | Изменение данных владельцем. |
| `apps/api/app/genealogy/write_service.py` | Валидация изменений, архивирование, журнал. |
| `apps/api/app/media/service.py` | Приём и выдача материалов через S3. |
| `apps/api/app/exports/service.py` | GEDCOM, архив и восстановление. |

### Task 1: Public read model and migration

**Files:** Modify `apps/api/app/models/genealogy.py`; create Alembic revision,
`apps/api/tests/test_public_models.py`.

**Interfaces:** Produces `Person.is_archived`, `Media` publication metadata and
`ChangeLog`; all following tasks use these fields.

- [ ] Write failing migration tests for archival state and an immutable change-log row.
- [ ] Run `cd apps/api && .venv/bin/python -m pytest tests/test_public_models.py -q`; expect failure.
- [ ] Add fields, constraints and Alembic revision; no automatic schema creation.
- [ ] Re-run the target tests; expect pass.
- [ ] Commit `feat: add public genealogy state`.

### Task 2: Public API and tree interface

**Files:** Create `read_service.py`, `routes/people.py`, `routes/tree.py`, API
tests and Lit pages/components for search, card and tree; modify API router and
web shell.

**Interfaces:** Produces `GET /api/v1/people`, `GET /api/v1/people/{id}` and
`GET /api/v1/tree/{id}` with `mode` and bounded `depth`.

- [ ] Write failing API tests for Cyrillic search, a public card and depth-limited ancestors, descendants and mixed tree.
- [ ] Run the API test file; expect missing routes.
- [ ] Implement response DTOs and traversal service with an explicit maximum depth.
- [ ] Write failing Lit tests for query results, person card navigation and mobile tree expansion.
- [ ] Implement responsive Russian UI without loading the complete database.
- [ ] Run API and web target tests; expect pass.
- [ ] Commit `feat: add public family tree`.

### Task 3: Owner editor, archive and audit log

**Files:** Create `write_service.py`, `routes/admin_genealogy.py`, editor pages
and tests; modify models and router.

**Interfaces:** Produces owner-only CRUD for people, unions, parent links and
events, and `archive_person(session, person_id, owner_email)`.

- [ ] Write failing tests for anonymous rejection, valid owner edits, archived records and before/after log values.
- [ ] Run target API tests; expect failure.
- [ ] Implement validation, owner routes and one transaction per edit.
- [ ] Implement Russian editor forms and their browser tests.
- [ ] Run target suites; expect pass.
- [ ] Commit `feat: add owner genealogy editor`.

### Task 4: Media storage and publication

**Files:** Create `media/service.py`, `routes/media.py`, tests and owner media UI;
modify models, dependencies and Compose settings.

**Interfaces:** Produces owner-only upload and metadata routes plus public
read-only material links for explicitly published media.

- [ ] Write failing tests for MIME type/size validation, private upload rejection and public-link visibility.
- [ ] Run target tests; expect failure.
- [ ] Implement object key generation, S3 upload, metadata persistence and signed/read-only links.
- [ ] Implement the owner upload and public gallery components.
- [ ] Run target tests; expect pass.
- [ ] Commit `feat: add genealogy media`.

### Task 5: Export, backup and recovery

**Files:** Create `exports/service.py`, owner routes, backup script, tests and
README recovery instructions.

**Interfaces:** Produces owner-only GEDCOM export and a technical archive with
database data, media manifest and restore command.

- [ ] Write failing tests for export structure, archive exclusion of secrets and restore into an empty database.
- [ ] Run target tests; expect failure.
- [ ] Implement deterministic export, archive manifest and isolated restore verification.
- [ ] Add scheduled backup configuration and Russian operations documentation.
- [ ] Run recovery test and complete project verification.
- [ ] Commit `feat: add archive and recovery workflow`.

## Plan self-review

All sections of the design map to Tasks 1–5. Public queries, edits, media and
archives have independent boundaries and explicit permission tests. The plan
does not add unsupported collaboration, external-tree synchronization, DNA
tools or research reports.
