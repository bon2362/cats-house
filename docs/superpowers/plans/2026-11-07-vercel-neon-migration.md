# Vercel and Neon Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish Cat’s House permanently on the owner’s Namecheap domain using Vercel and Neon without changing its visible behavior or losing family data.

**Architecture:** Deploy `apps/web` and `apps/api` as separate Vercel projects. The web project owns the visitor-facing domain and proxies its existing `/api/v1/*` paths to the API project, preserving the browser’s same-origin session. Neon becomes the PostgreSQL database; the current local database remains intact until a verified cutover and restore test have completed.

**Tech Stack:** Vite/Lit, FastAPI, SQLAlchemy/psycopg, PostgreSQL 16, Alembic, Vercel Functions, Neon, Cloudflare DNS, Namecheap.

**Spec:** `docs/superpowers/specs/2026-11-07-vercel-neon-migration-design.md`

## Global Constraints

- Domain registration stays in Namecheap; move only authoritative DNS to Cloudflare after the domain is purchased.
- Keep public URLs, relative `/api/v1/*` calls, owner password, TOTP, access rules and `noindex` behavior unchanged.
- Media remains in PostgreSQL for this release; do not add R2 or change the existing media API.
- Store production secrets only in Neon/Vercel configuration, never in Git, command-line arguments, logs, or the checked-in `.env.example`.
- Do not delete the local PostgreSQL volume, the local data, or existing backups.
- The actual data import and DNS cutover require the owner to schedule a short maintenance window and explicitly authorize the write operation.

## Review Focus

1. Production deployment must not start against an absent, non-TLS or non-pooled Neon URL; configuration must fail before serving traffic.
2. A request forged with `CF-Connecting-IP` or another client-controlled header must not change the rate-limit key on Vercel.
3. The web proxy must preserve `Set-Cookie` and the browser must retain the owner session after a refresh.
4. Hidden people and hidden/deleted media must remain unavailable through both the proxied main domain and the API subdomain.
5. A photo/PDF BLOB and its preview must survive `pg_dump` → `pg_restore`; counts alone are insufficient.

## File Structure

- Modify `apps/api/app/core/config.py` — add explicit deployment/runtime settings and validate production database requirements.
- Modify `apps/api/app/db/session.py` — use a serverless-safe SQLAlchemy engine policy.
- Modify `apps/api/app/web/limits.py` — select a trustworthy Vercel client address without weakening local tunnel behavior.
- Modify `apps/api/tests/test_config.py`, `apps/api/tests/test_public_site.py`, `apps/api/tests/test_media_api.py` — cover deployment configuration, rate-limit trust boundary and BLOB behavior.
- Create `apps/api/vercel.json` — Vercel API-project function configuration.
- Create `apps/web/vercel.json` — static-site build, security headers, SPA fallback and API rewrite.
- Create `scripts/neon-migrate.py` — guarded, non-destructive preflight/import verifier; it never accepts secrets as command arguments.
- Create `scripts/backup-neon.sh` and `scripts/com.cats-house.neon-backup.plist` — daily local portable backup and macOS launchd schedule.
- Modify `scripts/create-local-backup.py`, `scripts/restore-local-backup.py`, their tests and `README.md` — support a remote PostgreSQL URL safely and document operation and recovery.

### Task 1: Make the API safe for Neon and Vercel

**Files:**
- Modify: `apps/api/app/core/config.py`, `apps/api/app/db/session.py`, `apps/api/app/web/limits.py`
- Test: `apps/api/tests/test_config.py`, `apps/api/tests/test_public_site.py`

**Interfaces:**
- Consumes: `CATS_HOUSE_DATABASE_URL`, `CATS_HOUSE_ENVIRONMENT`, and a new explicit runtime selector `CATS_HOUSE_DEPLOYMENT` with values `local`, `tunnel`, or `vercel`.
- Produces: `create_session_factory(database_url, deployment)` that uses a non-persistent SQLAlchemy pool for Vercel; `client_address(request)` that reads Vercel’s provider-supplied `x-vercel-forwarded-for` only in `vercel` mode.

- [ ] **Step 1: Write failing tests for production configuration and address selection**

Add cases that reject a production Vercel configuration without a TLS Neon connection string, confirm local/tunnel configuration remains valid, and verify that only Vercel mode uses `x-vercel-forwarded-for`; forged Cloudflare headers must remain ignored outside the existing local-tunnel condition.

- [ ] **Step 2: Run the focused API tests to verify they fail**

Run: `cd apps/api && .venv/bin/pytest -q tests/test_config.py tests/test_public_site.py`

Expected: FAIL because the deployment setting, validation and Vercel address behavior do not exist.

- [ ] **Step 3: Implement serverless settings and connection behavior**

Add a validated deployment selector. In Vercel mode, create engines with `sqlalchemy.pool.NullPool` and `pool_pre_ping=True`; require `sslmode=require` in the production URL. Preserve the current local/tunnel session behavior. In Vercel mode use the platform-overwritten `x-vercel-forwarded-for`; retain the current localhost-only `CF-Connecting-IP` rule for tunnel mode.

- [ ] **Step 4: Run the focused API tests to verify they pass**

Run: `cd apps/api && .venv/bin/pytest -q tests/test_config.py tests/test_public_site.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/core/config.py apps/api/app/db/session.py apps/api/app/web/limits.py apps/api/tests/test_config.py apps/api/tests/test_public_site.py
git commit -m "feat: prepare API for Neon and Vercel"
```

### Task 2: Add reproducible Vercel project definitions

**Files:**
- Create: `apps/api/vercel.json`
- Create: `apps/web/vercel.json`
- Test: `apps/api/tests/test_vercel_config.py`, `apps/web/test/vercel-config.test.ts`

**Interfaces:**
- Consumes: an API origin supplied during Vercel project setup as `https://api.<domain>`.
- Produces: two projects with `apps/api` and `apps/web` as their Vercel Root Directories; web visitor requests to `/api/:path*` are externally rewritten to the API origin while retaining `/api/:path*` in the destination.

- [ ] **Step 1: Write configuration-contract tests**

Assert that API configuration sets a supported Python runtime/function duration without embedding secrets, and web configuration has: Vite build output `dist`, a first `/api/:path*` rewrite to the API origin, then SPA fallback to `/index.html`; static responses contain `X-Robots-Tag: noindex, nofollow, noarchive`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin` and `X-Content-Type-Options: nosniff`.

- [ ] **Step 2: Run configuration tests to verify they fail**

Run: `cd apps/api && .venv/bin/pytest -q tests/test_vercel_config.py && cd ../web && npm test -- vercel-config.test.ts`

Expected: FAIL because neither Vercel configuration exists.

- [ ] **Step 3: Implement the two project configurations**

Use Vercel’s supported static `headers` and `rewrites` rules. Keep the API’s `CATS_HOUSE_WEB_DIST` unset on Vercel: its job is API only. Put the API host in a deliberately marked deployment placeholder, then set the real value in the Vercel dashboard only after the API project has a stable `vercel.app` address; do not put the purchased domain into Git before it exists.

- [ ] **Step 4: Validate deploy artifacts locally**

Run: `cd apps/web && npm ci && npm run build && npm test -- vercel-config.test.ts && npm run typecheck`; then `cd ../api && .venv/bin/pytest -q tests/test_vercel_config.py`

Expected: PASS; `apps/web/dist/index.html` exists.

- [ ] **Step 5: Commit**

```bash
git add apps/api/vercel.json apps/web/vercel.json apps/api/tests/test_vercel_config.py apps/web/test/vercel-config.test.ts
git commit -m "feat: add Vercel deployment configuration"
```

### Task 3: Make database migration and rollback evidence-based

**Files:**
- Create: `scripts/neon-migrate.py`
- Modify: `scripts/create-local-backup.py`, `scripts/restore-local-backup.py`
- Test: `apps/api/tests/test_neon_migrate.py`, `apps/api/tests/test_backup_scripts.py`

**Interfaces:**
- Consumes: `CATS_HOUSE_SOURCE_DATABASE_URL` and `CATS_HOUSE_TARGET_DATABASE_URL` only from the process environment; `--check` is read-only and `--apply` requires an exact interactive confirmation.
- Produces: a timestamped PostgreSQL custom-format dump outside the repository, a restore report with table counts plus chosen media IDs/content hashes, and non-zero exit on a mismatch.

- [ ] **Step 1: Write failing migration-script tests**

Cover: missing URLs; `--check` performs no dump/restore; `--apply` refuses without typed confirmation; command arguments and output redact credentials; a mismatched count or media digest prevents success.

- [ ] **Step 2: Run the migration-script tests to verify they fail**

Run: `cd apps/api && .venv/bin/pytest -q tests/test_neon_migrate.py tests/test_backup_scripts.py`

Expected: FAIL because the Neon migration helper and remote-backup support do not exist.

- [ ] **Step 3: Implement a one-way, recoverable migration helper**

Use `pg_dump --format=custom` and `pg_restore --clean --if-exists` only against a newly created empty Neon database after confirmation. First invoke the existing full local backup. Run Alembic `upgrade head` against Neon after restore, then compare all application-table counts and SHA-256 digests of a deterministic sample that includes JPEG/PNG/PDF content and image previews. Retain both the source database and dump; never call a delete command on either.

- [ ] **Step 4: Run focused tests and a disposable real-database rehearsal**

Run: `cd apps/api && .venv/bin/pytest -q tests/test_neon_migrate.py tests/test_backup_scripts.py`

Expected: PASS.

Then, with a disposable Neon branch and non-production local database selected by the owner, run: `CATS_HOUSE_SOURCE_DATABASE_URL='…' CATS_HOUSE_TARGET_DATABASE_URL='…' apps/api/.venv/bin/python scripts/neon-migrate.py --check`

Expected: preflight reports compatible schema and no data is written. Do not run `--apply` against real family data without the owner’s explicit go-ahead.

- [ ] **Step 5: Commit**

```bash
git add scripts/neon-migrate.py scripts/create-local-backup.py scripts/restore-local-backup.py apps/api/tests/test_neon_migrate.py apps/api/tests/test_backup_scripts.py
git commit -m "feat: add verified Neon migration workflow"
```

### Task 4: Preserve independent daily backups after cutover

> Заменено планом `docs/superpowers/plans/2026-11-08-daily-backup-to-drive.md` (копии делает сервис на Vercel, не Mac).

**Files:**
- Create: `scripts/backup-neon.sh`, `scripts/com.cats-house.neon-backup.plist`
- Modify: `README.md`
- Test: `scripts/backup-neon.test.sh`

**Interfaces:**
- Consumes: `CATS_HOUSE_DATABASE_URL` from a user-only environment file outside the repository.
- Produces: one access-restricted timestamped PostgreSQL dump in `~/Cat's House backups/Neon`, retention of the newest 14 successful dumps, and a non-zero exit without deleting a prior good backup on failure.

- [ ] **Step 1: Write the shell-level safety test**

Use a fake `pg_dump` and temporary directories to assert: the script rejects a missing environment file, writes a dated output atomically, retains 14 newest files only after a successful dump, and never echoes the URL.

- [ ] **Step 2: Run the backup test to verify it fails**

Run: `bash scripts/backup-neon.test.sh`

Expected: FAIL because the schedule and helper do not exist.

- [ ] **Step 3: Implement local backup and launchd installation documentation**

Implement the script with `set -euo pipefail`, `umask 077`, a temporary output followed by atomic rename, and explicit `pg_dump` failure checks. Supply a plist template scheduled daily at 03:15 Europe/Belgrade local time; document copying it to `~/Library/LaunchAgents/`, loading it, locating logs, and a quarterly restore drill into an empty local PostgreSQL database.

- [ ] **Step 4: Verify backup behavior**

Run: `bash scripts/backup-neon.test.sh && bash -n scripts/backup-neon.sh`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/backup-neon.sh scripts/backup-neon.test.sh scripts/com.cats-house.neon-backup.plist README.md
git commit -m "feat: back up Neon database locally"
```

### Task 5: Create cloud resources, test preview deployments, and cut over the domain

**Files:**
- Modify: `README.md`, `.env.example`
- No automated test file; this is an owner-operated deployment checklist backed by Tasks 1–4.

**Interfaces:**
- Consumes: purchased Namecheap domain, Cloudflare zone, Neon production project/pooled URL, Vercel API and Web projects, and the secrets already present in the owner’s local `.env`.
- Produces: a live HTTPS website on the main domain; `api.<domain>` assigned to the API project; DNS managed by Cloudflare; production secrets scoped only to the API Vercel project.

- [ ] **Step 1: Create the accounts and projects without moving production traffic**

In Namecheap, keep the domain registered there. Add the domain as a Cloudflare zone and replace Namecheap nameservers with the two Cloudflare-assigned nameservers. Create an empty Neon project in the region closest to the selected Vercel function region. Import the GitHub repository twice into the existing Vercel account: Web root `apps/web`, API root `apps/api`.

- [ ] **Step 2: Configure production and preview secrets**

Add only these API environment variables in Vercel: `CATS_HOUSE_DATABASE_URL` (Neon pooled TLS URL), `CATS_HOUSE_OWNER_EMAIL`, `CATS_HOUSE_OWNER_PASSWORD_HASH`, `CATS_HOUSE_OWNER_TOTP_SECRET`, `CATS_HOUSE_SESSION_SECRET`, `CATS_HOUSE_ENVIRONMENT=production`, and `CATS_HOUSE_DEPLOYMENT=vercel`. Set distinct preview database/secrets or disable owner writes in preview before sharing any preview URL. Redeploy after saving variables.

- [ ] **Step 3: Prove the cloud deployment before data migration**

Deploy API and Web previews. On the Web preview, verify `GET /api/v1/health` crosses the rewrite, each security header is present, `robots.txt` disallows all crawlers, and the API’s docs endpoint is unavailable. Confirm invalid login attempts are throttled independently using Vercel’s real client-address header. Do not upload real family data yet.

- [ ] **Step 4: Perform the approved data migration and release**

Announce maintenance, stop writes on the temporary Mac publication, create a new local portable backup, then run the reviewed migration helper with `--apply`. Compare its report and manually open a sample person, hidden person, published photo, hidden photo and PDF from the Vercel preview. Assign `api.<domain>` to API Vercel, put that exact host in the Web rewrite, then assign the main domain and optional `www` redirect to Web Vercel. Wait for Cloudflare DNS and Vercel HTTPS to become active.

- [ ] **Step 5: Run final acceptance and retain rollback path**

Run: `cd apps/api && .venv/bin/pytest -q && cd ../web && npm test && npm run typecheck && npm run build && cd ../.. && bash scripts/backup-neon.test.sh`

Expected: PASS.

From a phone and a signed-out browser verify the live main domain, person URL, tree, search, `robots.txt`, headers, owner TOTP login, an edit, upload of a small test photo, refresh with the session preserved, and that a hidden record is not available. Keep the Cloudflare Tunnel/Mac data and the pre-cutover dump for at least 30 days. Rollback consists of removing the Vercel custom-domain binding and restarting `scripts/serve-public.sh`; do not attempt to reverse-copy edited production data automatically.

- [ ] **Step 6: Commit documentation only**

```bash
git add README.md .env.example
git commit -m "docs: document permanent Vercel and Neon deployment"
```

## Self-Review

- Spec coverage: Tasks 1–2 cover Vercel behavior and security; Task 3 preserves and verifies database/media data; Task 4 restores independent backups; Task 5 covers the Namecheap/Cloudflare DNS handoff, runtime secrets, validation and rollback.
- Type consistency: Task 1 defines the deployment selector and session factory consumed by Task 2 and Task 5; all database migration inputs are process environment variables, never command arguments.
- Review focus coverage: production URL/address headers are Task 1; session proxying and hidden-content access are Task 2/5; BLOB integrity is Task 3.
- Proportion: the plan leaves provider-console clicks and code internals to each task but fixes the deployment topology, safety gates, interfaces and tests needed for a safe move.

