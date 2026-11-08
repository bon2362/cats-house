# Daily Neon Backup to Google Drive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A separate Vercel project takes a standard `pg_dump` of the Neon database every night, verifies it, uploads it to the owner's Google Drive, prunes old copies and reports to healthchecks.io.

**Architecture:** `apps/backup` is its own Vercel project with one Python function `api/backup.py` triggered by Vercel Cron. Logic lives in the package `drive_backup` (settings, retention, redaction, PostgreSQL tools, Drive client, health pings, job, HTTP endpoint), each a small module tested on its own. `pg_dump`/`pg_restore` 17.11 come from the PyPI package `postgresql-binaries`; Google and healthchecks.io are called with the standard library only.

**Tech Stack:** Python 3.12, `postgresql-binaries==17.11.0`, `urllib`, pytest, testcontainers (PostgreSQL 17), Vercel Functions + Cron, Google Drive API v3 (`drive.file`), healthchecks.io.

**Spec:** `docs/superpowers/specs/2026-11-08-daily-backup-to-drive-design.md`

## Global Constraints

- Only standard format: `pg_dump --format=custom --no-owner --no-privileges`; restorable with plain `pg_restore`.
- PostgreSQL tools pinned: `postgresql-binaries==17.11.0` (Neon is PostgreSQL 17).
- The only runtime dependency is `postgresql-binaries`; HTTP via `urllib`.
- Secrets (`BACKUP_DATABASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `HEALTHCHECK_URL`, `CRON_SECRET`) only in the `cats-house-backup` Vercel project; never in git, command arguments, logs or error text.
- `BACKUP_DATABASE_URL` must carry `sslmode=require`, `verify-ca` or `verify-full`.
- Drive scope only `https://www.googleapis.com/auth/drive.file`; old copies go to the trash (`trashed=true`), never permanently deleted; pruning only after a verified upload.
- Retention: newest copy always; latest copy of each of the last 30 days; latest copy of each of the last 12 months.
- File name `cats-house-YYYY-MM-DDTHHMMZ.dump` (UTC). Folder name `Cat's House — копии базы`, marked with `appProperties` `cats_house_backups=1`.
- Cron `0 2 * * *` (UTC), region `fra1`, `maxDuration` 300.
- Required dump tables: `people`, `unions`, `parent_children`, `events`, `media`.
- Error text sent anywhere: at most 500 characters, database URLs and secret values removed.
- User-facing messages in Russian. Tests never use real people's data.
- Do not commit without the owner's explicit request (owner rule); commit steps below run only once the owner has asked for commits for this plan.

## Review Focus

1. Neon compute asleep: the first connection fails, a second attempt 10 s later must succeed without a false alarm.
2. Google refresh token revoked or expired (consent screen left in Testing): the run must fail with a clear Russian message and a `/fail` ping, not a stack trace or a silent 200.
3. A partially written or altered upload: `md5Checksum` mismatch must trash the uploaded file, keep all old copies and report failure.
4. Error text from `pg_dump` or Google must not carry the database URL, its password, the refresh token, the client secret or the cron secret.
5. Pruning must never touch files with other names in the folder, never trash the newest copy, and never run after a failed upload.

## File Structure

- Create `apps/backup/requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `vercel.json`, `.vercelignore` — project definition.
- Create `apps/backup/drive_backup/__init__.py` — package marker.
- Create `apps/backup/drive_backup/settings.py` — read and validate the six settings.
- Create `apps/backup/drive_backup/retention.py` — file naming and which copies to trash.
- Create `apps/backup/drive_backup/redact.py` — strip secrets from text.
- Create `apps/backup/drive_backup/pgtools.py` — unpack binaries, libpq environment, dump with retry, verify dump.
- Create `apps/backup/drive_backup/drive.py` — Google Drive client.
- Create `apps/backup/drive_backup/health.py` — healthchecks.io pings.
- Create `apps/backup/drive_backup/job.py` — one backup run.
- Create `apps/backup/drive_backup/endpoint.py` — auth, error handling, pings.
- Create `apps/backup/api/backup.py` — Vercel function entry.
- Create `apps/backup/scripts/google-authorize.py` — one-time Google consent, writes env file.
- Create `apps/backup/scripts/verify-backup-file.py` — restore a downloaded dump and compare with Neon.
- Create `apps/backup/tests/…` — tests per module, `fake_drive.py`, `conftest.py`.
- Create `apps/backup/README.md`; modify `README.md`, `docs/superpowers/plans/2026-11-07-vercel-neon-migration.md`, the spec (script path).
- Outside the repo (Task 10): `~/archiving/cats-house/README.md`, `dashboard.py`, the launchd job.

Test command for every task: `cd apps/backup && .venv/bin/pytest -q` (the venv is created in Task 1).

---

### Task 1: Project skeleton and settings

**Files:**
- Create: `apps/backup/requirements.txt`, `apps/backup/requirements-dev.txt`, `apps/backup/pytest.ini`, `apps/backup/vercel.json`, `apps/backup/.vercelignore`, `apps/backup/drive_backup/__init__.py`, `apps/backup/drive_backup/settings.py`
- Test: `apps/backup/tests/test_settings.py`, `apps/backup/tests/test_vercel_config.py`

**Interfaces:**
- Produces: `Settings` (frozen dataclass: `database_url`, `google_client_id`, `google_client_secret`, `google_refresh_token`, `healthcheck_url`, `cron_secret`; method `secret_values() -> list[str]` including the URL password), `load_settings(env: Mapping[str, str]) -> Settings`, `SettingsError(Exception)`, `REQUIRED: tuple[str, ...]`.

- [ ] **Step 1: Create project files and the virtual environment**

`apps/backup/requirements.txt`:
```
postgresql-binaries==17.11.0
```

`apps/backup/requirements-dev.txt`:
```
-r requirements.txt
pytest>=8.3,<9
psycopg[binary]>=3.2,<4
testcontainers[community]>=4.15,<5
```

`apps/backup/pytest.ini`:
```
[pytest]
testpaths = tests
pythonpath = .
```

`apps/backup/vercel.json`:
```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "regions": ["fra1"],
  "functions": {
    "api/backup.py": {
      "maxDuration": 300
    }
  },
  "crons": [
    {
      "path": "/api/backup",
      "schedule": "0 2 * * *"
    }
  ]
}
```

`apps/backup/.vercelignore`:
```
.venv
tests
scripts
requirements-dev.txt
pytest.ini
```

`apps/backup/drive_backup/__init__.py`:
```python
"""Ежедневная копия базы Cat's House из Neon в Google Drive."""
```

Run: `cd apps/backup && /opt/homebrew/bin/python3.12 -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt`
Expected: exit 0.

- [ ] **Step 2: Write failing tests**

`apps/backup/tests/test_vercel_config.py`:
```python
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_vercel_config_runs_one_function_nightly_without_secrets():
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert config["regions"] == ["fra1"]
    assert config["functions"] == {"api/backup.py": {"maxDuration": 300}}
    assert config["crons"] == [{"path": "/api/backup", "schedule": "0 2 * * *"}]
    assert "env" not in config


def test_runtime_dependencies_are_only_pinned_postgres_binaries():
    lines = [l.strip() for l in (ROOT / "requirements.txt").read_text().splitlines() if l.strip()]
    assert lines == ["postgresql-binaries==17.11.0"]


def test_tests_and_scripts_are_not_deployed():
    ignored = (ROOT / ".vercelignore").read_text().split()
    assert {"tests", "scripts", ".venv"} <= set(ignored)
```

`apps/backup/tests/test_settings.py`:
```python
import pytest

from drive_backup.settings import REQUIRED, SettingsError, load_settings

URL = "postgresql://cats_house_backup:p%40ss-word@ep-test.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"


def full_env(**overrides):
    env = {
        "BACKUP_DATABASE_URL": URL,
        "GOOGLE_CLIENT_ID": "client-id.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "client-secret-value",
        "GOOGLE_REFRESH_TOKEN": "refresh-token-value",
        "HEALTHCHECK_URL": "https://hc-ping.com/abc-uuid",
        "CRON_SECRET": "cron-secret-value-0123456789",
    }
    env.update(overrides)
    return env


def test_loads_all_settings():
    settings = load_settings(full_env())
    assert settings.database_url == URL
    assert settings.cron_secret == "cron-secret-value-0123456789"


def test_names_every_missing_setting_without_values():
    with pytest.raises(SettingsError) as error:
        load_settings({"GOOGLE_CLIENT_ID": "x", "CRON_SECRET": "  "})
    message = str(error.value)
    for name in REQUIRED:
        if name != "GOOGLE_CLIENT_ID":
            assert name in message
    assert "GOOGLE_CLIENT_ID" not in message


@pytest.mark.parametrize("query", ["", "?sslmode=prefer", "?sslmode=disable"])
def test_rejects_database_url_without_tls(query):
    url = "postgresql://u:p@ep-test.neon.tech/neondb" + query
    with pytest.raises(SettingsError, match="sslmode=require"):
        load_settings(full_env(BACKUP_DATABASE_URL=url))


def test_rejects_non_postgres_url():
    with pytest.raises(SettingsError, match="PostgreSQL"):
        load_settings(full_env(BACKUP_DATABASE_URL="https://example.test/?sslmode=require"))


def test_secret_values_include_decoded_password():
    values = load_settings(full_env()).secret_values()
    assert "p@ss-word" in values
    assert URL in values
    assert "refresh-token-value" in values
    assert "client-secret-value" in values
    assert "cron-secret-value-0123456789" in values
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd apps/backup && .venv/bin/pytest -q tests/test_settings.py tests/test_vercel_config.py`
Expected: `test_settings.py` FAIL with `ModuleNotFoundError: No module named 'drive_backup.settings'`; `test_vercel_config.py` passes (the files exist from Step 1).

- [ ] **Step 4: Implement settings**

`apps/backup/drive_backup/settings.py`:
```python
"""Настройки сервиса копий: только из переменных окружения."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import parse_qs, unquote, urlparse

REQUIRED = (
    "BACKUP_DATABASE_URL",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    "HEALTHCHECK_URL",
    "CRON_SECRET",
)
STRICT_SSL = {"require", "verify-ca", "verify-full"}


class SettingsError(Exception):
    """Настройка отсутствует или неверна; текст без значений."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    google_client_id: str
    google_client_secret: str
    google_refresh_token: str
    healthcheck_url: str
    cron_secret: str

    def secret_values(self) -> list[str]:
        password = unquote(urlparse(self.database_url).password or "")
        values = [self.database_url, password, self.google_client_secret,
                  self.google_refresh_token, self.healthcheck_url, self.cron_secret]
        return [v for v in values if v]


def load_settings(env: Mapping[str, str]) -> Settings:
    values = {name: (env.get(name) or "").strip() for name in REQUIRED}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SettingsError("Не заданы настройки: " + ", ".join(missing) + ".")
    url = values["BACKUP_DATABASE_URL"]
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql") or not parsed.hostname:
        raise SettingsError("BACKUP_DATABASE_URL должен быть адресом PostgreSQL (postgresql://…).")
    if not set(parse_qs(parsed.query).get("sslmode", [])) & STRICT_SSL:
        raise SettingsError("BACKUP_DATABASE_URL должен содержать sslmode=require.")
    return Settings(
        database_url=url,
        google_client_id=values["GOOGLE_CLIENT_ID"],
        google_client_secret=values["GOOGLE_CLIENT_SECRET"],
        google_refresh_token=values["GOOGLE_REFRESH_TOKEN"],
        healthcheck_url=values["HEALTHCHECK_URL"],
        cron_secret=values["CRON_SECRET"],
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/backup && .venv/bin/pytest -q`
Expected: PASS (9 tests).

- [ ] **Step 6: Commit**

```bash
git add apps/backup
git commit -m "feat: scaffold the nightly backup service and its settings"
```

### Task 2: Retention and redaction

**Files:**
- Create: `apps/backup/drive_backup/retention.py`, `apps/backup/drive_backup/redact.py`
- Test: `apps/backup/tests/test_retention.py`, `apps/backup/tests/test_redact.py`

**Interfaces:**
- Produces: `backup_name(moment: datetime) -> str`; `names_to_trash(names: list[str], today: date, keep_days: int = 30, keep_months: int = 12) -> list[str]`; `redact(text: str, secrets: Iterable[str], limit: int = 500) -> str`.

- [ ] **Step 1: Write failing tests**

`apps/backup/tests/test_retention.py`:
```python
import datetime as dt

from drive_backup.retention import backup_name, names_to_trash


def name(day: str, hhmm: str = "0200") -> str:
    return f"cats-house-{day}T{hhmm}Z.dump"


def test_backup_name_uses_utc():
    moment = dt.datetime(2026, 11, 9, 3, 7, tzinfo=dt.timezone(dt.timedelta(hours=1)))
    assert backup_name(moment) == "cats-house-2026-11-09T0207Z.dump"


def test_empty_folder_trashes_nothing():
    assert names_to_trash([], dt.date(2026, 11, 9)) == []


def test_keeps_latest_copy_per_day_for_30_days():
    names = [name("2026-11-09", "0200"), name("2026-11-09", "0900"), name("2026-10-11"), name("2026-10-10")]
    # monthly rule off (0): 2026-10-11 is 29 days old and kept, 2026-10-10 is 30 days old and trashed
    trash = names_to_trash(names, dt.date(2026, 11, 9), 30, 0)
    assert trash == [name("2026-10-10"), name("2026-11-09", "0200")]


def test_keeps_latest_copy_per_month_for_12_months():
    names = [name("2025-10-31"), name("2025-11-30"), name("2025-12-01"), name("2025-12-31"), name("2026-11-09")]
    # 2025-12 is 11 months back (kept: its latest copy), 2025-11 is 12 months back and 2025-10 is 13 (trashed)
    trash = names_to_trash(names, dt.date(2026, 11, 9), 30, 12)
    assert trash == [name("2025-10-31"), name("2025-11-30"), name("2025-12-01")]


def test_newest_copy_is_always_kept():
    names = [name("2020-01-01")]
    assert names_to_trash(names, dt.date(2026, 11, 9), 30, 12) == []


def test_other_names_are_never_trashed():
    names = ["notes.txt", "cats-house-2020-01-01.sql.gz", name("2026-11-09")]
    assert names_to_trash(names, dt.date(2026, 11, 9)) == []
```

`apps/backup/tests/test_redact.py`:
```python
from drive_backup.redact import redact


def test_removes_database_urls_of_any_driver():
    text = 'pg_dump: error: connection to "postgresql://u:secret@host/db?sslmode=require" failed; also postgres+psycopg://a:b@c/d'
    out = redact(text, [])
    assert "secret" not in out and "a:b@c" not in out
    assert out.count("<адрес базы>") == 2


def test_removes_secret_values_longest_first():
    out = redact("token abc123 and abc", ["abc", "abc123"])
    assert out == "token *** and ***"


def test_ignores_empty_secrets_and_limits_length():
    out = redact("x" * 600, ["", None])
    assert len(out) == 500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/backup && .venv/bin/pytest -q tests/test_retention.py tests/test_redact.py`
Expected: FAIL with `ModuleNotFoundError` for `drive_backup.retention` and `drive_backup.redact`.

- [ ] **Step 3: Implement**

`apps/backup/drive_backup/retention.py`:
```python
"""Имена файлов копий и правило хранения."""

from __future__ import annotations

import datetime as dt
import re

FILE_RE = re.compile(r"^cats-house-(\d{4}-\d{2}-\d{2})T(\d{4})Z\.dump$")


def backup_name(moment: dt.datetime) -> str:
    utc = moment.astimezone(dt.timezone.utc)
    return f"cats-house-{utc:%Y-%m-%dT%H%M}Z.dump"


def names_to_trash(names: list[str], today: dt.date, keep_days: int = 30, keep_months: int = 12) -> list[str]:
    """Оставляем самую новую копию, последнюю за каждый из keep_days дней и за каждый из keep_months месяцев."""
    parsed = sorted((name, dt.date.fromisoformat(m.group(1))) for name in names if (m := FILE_RE.match(name)))
    if not parsed:
        return []
    keep = {parsed[-1][0]}
    latest_by_day: dict[dt.date, str] = {}
    latest_by_month: dict[tuple[int, int], str] = {}
    for name, day in parsed:
        latest_by_day[day] = name
        latest_by_month[(day.year, day.month)] = name
    for day, name in latest_by_day.items():
        if (today - day).days < keep_days:
            keep.add(name)
    this_month = today.year * 12 + today.month
    for (year, month), name in latest_by_month.items():
        if this_month - (year * 12 + month) < keep_months:
            keep.add(name)
    return [name for name, _ in parsed if name not in keep]
```

`apps/backup/drive_backup/redact.py`:
```python
"""Убрать из текста ошибок адреса баз и значения секретов."""

from __future__ import annotations

import re
from typing import Iterable, Optional

URL_RE = re.compile(r"postgres(?:ql)?(?:\+\w+)?://\S+")


def redact(text: str, secrets: Iterable[Optional[str]], limit: int = 500) -> str:
    out = URL_RE.sub("<адрес базы>", text)
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        out = out.replace(secret, "***")
    return out[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/backup && .venv/bin/pytest -q`
Expected: PASS (all tests from Tasks 1–2).

- [ ] **Step 5: Commit**

```bash
git add apps/backup/drive_backup/retention.py apps/backup/drive_backup/redact.py apps/backup/tests/test_retention.py apps/backup/tests/test_redact.py
git commit -m "feat: add backup retention rule and secret redaction"
```

### Task 3: PostgreSQL tools

**Files:**
- Create: `apps/backup/drive_backup/pgtools.py`, `apps/backup/tests/conftest.py`
- Test: `apps/backup/tests/test_pgtools.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `REQUIRED_TABLES: tuple[str, ...]`; `DumpError(Exception)`; `ensure_binaries(target: Path = Path("/tmp/pg")) -> Path` (returns the `bin` directory); `pg_environment(url: str, base: Mapping[str, str] | None = None) -> dict[str, str]`; `dump(url: str, target: Path, bin_dir: Path, *, run=subprocess.run, sleep=time.sleep, retry_delay: float = 10) -> None`; `verify_dump(path: Path, bin_dir: Path, *, run=subprocess.run) -> None`.
- Test fixtures produced in `conftest.py` (used by Tasks 5 and 8): `bin_dir` (session), `source_db` (session; dict with `url`, `container`), `dump_file` (session; a verified `.dump` of `source_db`).

- [ ] **Step 1: Write the fixtures and failing tests**

`apps/backup/tests/conftest.py`:
```python
"""Тестовая база PostgreSQL 17 с выдуманными данными и настоящие pg_dump/pg_restore."""

import hashlib

import psycopg
import pytest
from testcontainers.community.postgres import PostgresContainer

FAKE_FILES = [bytes([i]) * 50_000 + b"%PDF-fake" for i in range(5)]


@pytest.fixture(scope="session")
def bin_dir(tmp_path_factory):
    from drive_backup.pgtools import ensure_binaries
    return ensure_binaries(tmp_path_factory.mktemp("pg"))


def create_schema(conn, with_media=True):
    conn.execute("create table people (id int primary key, full_name text not null)")
    conn.execute("create table unions (id int primary key)")
    conn.execute("create table parent_children (id int primary key)")
    conn.execute("create table events (id int primary key, label text)")
    if with_media:
        conn.execute("create table media (id int primary key, content bytea, preview bytea)")


@pytest.fixture(scope="session")
def source_db():
    with PostgresContainer("postgres:17-alpine", driver=None) as container:
        url = container.get_connection_url()
        with psycopg.connect(url, autocommit=True) as conn:
            create_schema(conn)
            conn.execute("insert into people values (1, 'Тестова Анна'), (2, 'Тестов Пётр')")
            conn.execute("insert into unions values (1)")
            conn.execute("insert into parent_children values (1), (2)")
            conn.execute("insert into events values (1, 'Рождение')")
            for i, content in enumerate(FAKE_FILES):
                conn.execute("insert into media values (%s, %s, %s)", (i, content, content[:100] if i % 2 else None))
            conn.execute("create database restored")
            conn.execute("create database no_media")
        yield {"url": url + "?sslmode=disable", "container": container}


@pytest.fixture(scope="session")
def dump_file(tmp_path_factory, source_db, bin_dir):
    from drive_backup.pgtools import dump
    target = tmp_path_factory.mktemp("dump") / "cats-house-2026-11-09T0200Z.dump"
    dump(source_db["url"], target, bin_dir)
    return target


def media_digests(url):
    with psycopg.connect(url) as conn:
        rows = conn.execute("select id, content from media order by id").fetchall()
    return [(row[0], hashlib.sha256(row[1]).hexdigest()) for row in rows]
```

`apps/backup/tests/test_pgtools.py`:
```python
import subprocess

import psycopg
import pytest

from drive_backup import pgtools
from drive_backup.pgtools import DumpError, dump, pg_environment, verify_dump

from .conftest import create_schema, media_digests


def test_unpacked_tools_are_postgres_17(bin_dir):
    for name in ("pg_dump", "pg_restore"):
        out = subprocess.run([str(bin_dir / name), "--version"], capture_output=True, text=True, check=True).stdout
        assert "17.11" in out


def test_environment_carries_connection_without_url():
    env = pg_environment(
        "postgresql://reader:p%40ss@ep-x.neon.tech:5433/neondb?sslmode=require&channel_binding=require", base={}
    )
    assert env == {
        "PGHOST": "ep-x.neon.tech", "PGPORT": "5433", "PGUSER": "reader", "PGPASSWORD": "p@ss",
        "PGDATABASE": "neondb", "PGSSLMODE": "require", "PGCHANNELBINDING": "require", "PGCONNECT_TIMEOUT": "15",
    }


def test_dump_restores_files_byte_for_byte(source_db, dump_file, bin_dir):
    verify_dump(dump_file, bin_dir)
    restored_url = source_db["url"].replace("/test?", "/restored?")
    subprocess.run(
        [str(bin_dir / "pg_restore"), "--no-owner", "--no-privileges", "--exit-on-error", str(dump_file)],
        env=pg_environment(restored_url), check=True, capture_output=True,
    )
    assert media_digests(restored_url.split("?")[0]) == media_digests(source_db["url"].split("?")[0])
    with psycopg.connect(restored_url.split("?")[0]) as conn:
        assert conn.execute("select full_name from people order by id").fetchall() == [("Тестова Анна",), ("Тестов Пётр",)]


def test_dump_without_media_table_is_rejected(source_db, bin_dir, tmp_path):
    url = source_db["url"].replace("/test?", "/no_media?")
    with psycopg.connect(url.split("?")[0], autocommit=True) as conn:
        create_schema(conn, with_media=False)
    target = tmp_path / "partial.dump"
    dump(url, target, bin_dir)
    with pytest.raises(DumpError, match="media"):
        verify_dump(target, bin_dir)


def test_garbage_file_is_rejected(bin_dir, tmp_path):
    bad = tmp_path / "bad.dump"
    bad.write_bytes(b"not a dump")
    with pytest.raises(DumpError, match="не читается"):
        verify_dump(bad, bin_dir)


class FakeRun:
    def __init__(self, codes):
        self.codes = list(codes)
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, self.codes.pop(0), "", "pg_dump: error: connection to server failed\n")


URL = "postgresql://reader:very-secret@ep-x.neon.tech/neondb?sslmode=require"


def test_dump_retries_once_and_keeps_url_out_of_arguments(tmp_path):
    run, waits = FakeRun([1, 0]), []
    dump(URL, tmp_path / "x.dump", tmp_path, run=run, sleep=waits.append)
    assert waits == [10]
    assert len(run.calls) == 2
    for cmd, kwargs in run.calls:
        assert not any("very-secret" in part or "neon.tech" in part for part in cmd)
        assert kwargs["env"]["PGPASSWORD"] == "very-secret"


def test_dump_fails_after_second_attempt_with_last_error_line(tmp_path):
    with pytest.raises(DumpError, match="connection to server failed"):
        dump(URL, tmp_path / "x.dump", tmp_path, run=FakeRun([1, 1]), sleep=lambda _: None)
```

Create an empty `apps/backup/tests/__init__.py` so `from .conftest import …` works.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/backup && .venv/bin/pytest -q tests/test_pgtools.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'drive_backup.pgtools'`.

- [ ] **Step 3: Implement**

`apps/backup/drive_backup/pgtools.py`:
```python
"""pg_dump и pg_restore из пакета postgresql-binaries."""

from __future__ import annotations

import os
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import parse_qs, unquote, urlparse

REQUIRED_TABLES = ("people", "unions", "parent_children", "events", "media")


class DumpError(Exception):
    """Копия не снялась или не прошла проверку."""


def ensure_binaries(target: Path = Path("/tmp/pg")) -> Path:
    found = sorted(Path(target).glob("*/bin/pg_dump"))
    if not found:
        import postgresql_binaries

        archive = next(Path(postgresql_binaries.__file__).parent.glob("*.tar.gz"))
        Path(target).mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            tar.extractall(target, filter="data")
        found = sorted(Path(target).glob("*/bin/pg_dump"))
    bin_dir = found[0].parent
    for name in ("pg_dump", "pg_restore", "psql"):
        tool = bin_dir / name
        if tool.exists():
            tool.chmod(0o755)
    return bin_dir


def pg_environment(url: str, base: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    env = dict(os.environ if base is None else base)
    env.update({
        "PGHOST": parsed.hostname or "",
        "PGPORT": str(parsed.port or 5432),
        "PGUSER": unquote(parsed.username or ""),
        "PGPASSWORD": unquote(parsed.password or ""),
        "PGDATABASE": unquote(parsed.path.lstrip("/")),
        "PGSSLMODE": query.get("sslmode", ["prefer"])[0],
        "PGCONNECT_TIMEOUT": "15",
    })
    if "channel_binding" in query:
        env["PGCHANNELBINDING"] = query["channel_binding"][0]
    return env


def _last_line(text: str) -> str:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    return lines[-1] if lines else "без описания"


def dump(url: str, target: Path, bin_dir: Path, *, run=subprocess.run, sleep=time.sleep, retry_delay: float = 10) -> None:
    cmd = [str(Path(bin_dir) / "pg_dump"), "--format=custom", "--no-owner", "--no-privileges", "--file", str(target)]
    env = pg_environment(url)
    result = None
    for attempt in (1, 2):
        result = run(cmd, env=env, capture_output=True, text=True, timeout=240)
        if result.returncode == 0:
            return
        if attempt == 1:
            sleep(retry_delay)
    raise DumpError("pg_dump завершился с ошибкой: " + _last_line(result.stderr))


def verify_dump(path: Path, bin_dir: Path, *, run=subprocess.run) -> None:
    result = run([str(Path(bin_dir) / "pg_restore"), "--list", str(path)], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise DumpError("копия не читается: " + _last_line(result.stderr))
    present = set()
    for line in result.stdout.splitlines():
        if " TABLE DATA " in line:
            parts = line.split(" TABLE DATA ", 1)[1].split()
            if len(parts) >= 2:
                present.add(parts[1])
    missing = [table for table in REQUIRED_TABLES if table not in present]
    if missing:
        raise DumpError("копия неполная: нет данных таблиц " + ", ".join(missing))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/backup && .venv/bin/pytest -q`
Expected: PASS. (Needs Docker Desktop running; the first run pulls `postgres:17-alpine`.)

- [ ] **Step 5: Commit**

```bash
git add apps/backup/drive_backup/pgtools.py apps/backup/tests/__init__.py apps/backup/tests/conftest.py apps/backup/tests/test_pgtools.py
git commit -m "feat: dump and verify the database with bundled PostgreSQL 17 tools"
```

### Task 4: Google Drive client

**Files:**
- Create: `apps/backup/drive_backup/drive.py`, `apps/backup/tests/fake_drive.py`
- Test: `apps/backup/tests/test_drive.py`

**Interfaces:**
- Produces: `DriveError(Exception)`; `FOLDER_NAME`, `MARK_KEY`; `DriveClient(client_id, client_secret, refresh_token, *, token_url, api_url, upload_url, timeout=60)` with `find_or_create_folder() -> str`, `upload(folder_id: str, path: Path, name: str) -> str` (file id), `file_info(file_id: str) -> dict` (`id`, `name`, `size`, `md5Checksum`), `list_files(folder_id: str) -> list[dict]` (`id`, `name`), `trash(file_id: str) -> None`.
- Produces for tests (used by Task 5): `FakeDrive` context manager with `.client(refresh_token="good-refresh") -> DriveClient`, `.files: dict[str, dict]`, `.corrupt_md5: bool`, `.fail_upload: bool`.

- [ ] **Step 1: Write the fake server and failing tests**

`apps/backup/tests/fake_drive.py`:
```python
"""Поддельный Google OAuth + Drive v3 для тестов (только то, что использует клиент)."""

import hashlib
import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from drive_backup.drive import DriveClient

ACCESS = "fake-access"


class FakeDrive:
    def __init__(self):
        self.files = {}
        self.sessions = {}
        self.corrupt_md5 = False
        self.fail_upload = False
        drive = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, code, body=None, headers=None):
                data = json.dumps(body or {}).encode()
                self.send_response(code)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def body(self):
                return self.rfile.read(int(self.headers.get("Content-Length", 0)))

            def authorized(self):
                if self.headers.get("Authorization") != f"Bearer {ACCESS}":
                    self.reply(401, {"error": {"message": "Invalid Credentials"}})
                    return False
                return True

            def do_POST(self):
                url = urlparse(self.path)
                if url.path == "/token":
                    form = parse_qs(self.body().decode())
                    if form.get("grant_type") == ["refresh_token"] and form.get("refresh_token") == ["good-refresh"]:
                        return self.reply(200, {"access_token": ACCESS, "expires_in": 3599})
                    return self.reply(400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
                if not self.authorized():
                    return
                if url.path == "/drive/v3/files":
                    meta = json.loads(self.body())
                    file_id = uuid.uuid4().hex
                    drive.files[file_id] = {**meta, "id": file_id, "trashed": False, "parents": meta.get("parents", ["root"])}
                    return self.reply(200, {"id": file_id})
                if url.path == "/upload/drive/v3/files" and parse_qs(url.query).get("uploadType") == ["resumable"]:
                    session = uuid.uuid4().hex
                    drive.sessions[session] = json.loads(self.body())
                    host = f"http://127.0.0.1:{drive.port}"
                    return self.reply(200, {}, {"Location": f"{host}/upload-session?upload_id={session}"})
                self.reply(404)

            def do_PUT(self):
                url = urlparse(self.path)
                session = parse_qs(url.query).get("upload_id", [""])[0]
                content = self.body()
                if url.path != "/upload-session" or session not in drive.sessions:
                    return self.reply(404)
                if drive.fail_upload:
                    return self.reply(503, {"error": {"message": "Backend Error"}})
                meta = drive.sessions.pop(session)
                file_id = uuid.uuid4().hex
                drive.files[file_id] = {**meta, "id": file_id, "trashed": False, "content": content}
                self.reply(200, {"id": file_id, "name": meta["name"]})

            def do_GET(self):
                if not self.authorized():
                    return
                url = urlparse(self.path)
                match = re.fullmatch(r"/drive/v3/files/([^/]+)", url.path)
                if match:
                    item = drive.files.get(match.group(1))
                    if not item:
                        return self.reply(404)
                    md5 = hashlib.md5(item.get("content", b"")).hexdigest()
                    if drive.corrupt_md5:
                        md5 = "0" * 32
                    return self.reply(200, {"id": item["id"], "name": item["name"],
                                            "size": str(len(item.get("content", b""))), "md5Checksum": md5})
                if url.path == "/drive/v3/files":
                    q = parse_qs(url.query)["q"][0]
                    live = [f for f in drive.files.values() if not f["trashed"]]
                    if "appProperties has" in q:
                        found = [f for f in live if f.get("appProperties", {}).get("cats_house_backups") == "1"]
                    else:
                        parent = re.search(r"'(\w+)' in parents", q).group(1)
                        found = [f for f in live if parent in f.get("parents", [])]
                    return self.reply(200, {"files": [{"id": f["id"], "name": f["name"]} for f in found]})
                self.reply(404)

            def do_PATCH(self):
                if not self.authorized():
                    return
                match = re.fullmatch(r"/drive/v3/files/([^/]+)", urlparse(self.path).path)
                if not match or match.group(1) not in drive.files:
                    return self.reply(404)
                drive.files[match.group(1)].update(json.loads(self.body()))
                self.reply(200, {"id": match.group(1)})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()

    def client(self, refresh_token="good-refresh"):
        base = f"http://127.0.0.1:{self.port}"
        return DriveClient("client-id", "client-secret", refresh_token, token_url=f"{base}/token",
                           api_url=f"{base}/drive/v3", upload_url=f"{base}/upload/drive/v3")

    def live_names(self, folder_id):
        return sorted(f["name"] for f in self.files.values() if not f["trashed"] and folder_id in f.get("parents", []))
```

`apps/backup/tests/test_drive.py`:
```python
import hashlib

import pytest

from drive_backup.drive import FOLDER_NAME, DriveError

from .fake_drive import FakeDrive


@pytest.fixture
def drive():
    with FakeDrive() as fake:
        yield fake


def test_creates_marked_folder_once(drive):
    client = drive.client()
    first = client.find_or_create_folder()
    second = client.find_or_create_folder()
    assert first == second
    assert drive.files[first]["name"] == FOLDER_NAME
    assert drive.files[first]["appProperties"] == {"cats_house_backups": "1"}


def test_upload_reports_matching_checksum(drive, tmp_path):
    client = drive.client()
    folder = client.find_or_create_folder()
    path = tmp_path / "cats-house-2026-11-09T0200Z.dump"
    path.write_bytes(b"dump-bytes" * 1000)
    file_id = client.upload(folder, path, path.name)
    info = client.file_info(file_id)
    assert info["md5Checksum"] == hashlib.md5(path.read_bytes()).hexdigest()
    assert drive.live_names(folder) == [path.name]


def test_list_and_trash(drive, tmp_path):
    client = drive.client()
    folder = client.find_or_create_folder()
    path = tmp_path / "a.dump"
    path.write_bytes(b"a")
    file_id = client.upload(folder, path, "a.dump")
    assert [f["name"] for f in client.list_files(folder)] == ["a.dump"]
    client.trash(file_id)
    assert client.list_files(folder) == []
    assert drive.files[file_id]["trashed"] is True


def test_revoked_refresh_token_gives_clear_error(drive):
    with pytest.raises(DriveError, match="ключ доступа Google не действует"):
        drive.client(refresh_token="revoked").find_or_create_folder()


def test_failed_upload_raises(drive, tmp_path):
    client = drive.client()
    folder = client.find_or_create_folder()
    drive.fail_upload = True
    path = tmp_path / "a.dump"
    path.write_bytes(b"a")
    with pytest.raises(DriveError, match="503"):
        client.upload(folder, path, "a.dump")


def test_unreachable_google_raises_drive_error(tmp_path):
    from drive_backup.drive import DriveClient
    client = DriveClient("id", "secret", "token", token_url="http://127.0.0.1:9/token",
                         api_url="http://127.0.0.1:9/drive/v3", upload_url="http://127.0.0.1:9/upload/drive/v3", timeout=2)
    with pytest.raises(DriveError, match="недоступен"):
        client.find_or_create_folder()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/backup && .venv/bin/pytest -q tests/test_drive.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'drive_backup.drive'`.

- [ ] **Step 3: Implement**

`apps/backup/drive_backup/drive.py`:
```python
"""Google Drive v3 через urllib: своя папка, загрузка, список, корзина."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FOLDER_MIME = "application/vnd.google-apps.folder"
FOLDER_NAME = "Cat's House — копии базы"
MARK_KEY = "cats_house_backups"
JSON_TYPE = "application/json; charset=UTF-8"


class DriveError(Exception):
    """Google Drive не выполнил запрос."""


class DriveClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str, *,
                 token_url: str = "https://oauth2.googleapis.com/token",
                 api_url: str = "https://www.googleapis.com/drive/v3",
                 upload_url: str = "https://www.googleapis.com/upload/drive/v3",
                 timeout: float = 60) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.token_url = token_url
        self.api_url = api_url
        self.upload_url = upload_url
        self.timeout = timeout
        self._access_token: str | None = None

    def _send(self, method: str, url: str, *, data: bytes | None = None,
              headers: dict[str, str] | None = None, auth: bool = True):
        headers = dict(headers or {})
        if auth:
            headers["Authorization"] = f"Bearer {self._token()}"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                return response.headers, (json.loads(body) if body else {})
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            raise DriveError(f"Google Drive ответил {error.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise DriveError(f"Google Drive недоступен: {reason}") from None

    def _token(self) -> str:
        if self._access_token is None:
            form = urllib.parse.urlencode({
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            }).encode()
            try:
                _, result = self._send("POST", self.token_url, data=form, auth=False,
                                       headers={"Content-Type": "application/x-www-form-urlencoded"})
            except DriveError as error:
                if "invalid_grant" in str(error) or "invalid_client" in str(error):
                    raise DriveError("ключ доступа Google не действует — нужно заново выдать разрешение "
                                     "(apps/backup/scripts/google-authorize.py)") from None
                raise
            token = result.get("access_token")
            if not token:
                raise DriveError("Google не выдал ключ доступа.")
            self._access_token = token
        return self._access_token

    def _files_url(self, suffix: str = "", **params) -> str:
        query = ("?" + urllib.parse.urlencode(params)) if params else ""
        return f"{self.api_url}/files{suffix}{query}"

    def find_or_create_folder(self) -> str:
        q = (f"mimeType='{FOLDER_MIME}' and appProperties has {{ key='{MARK_KEY}' and value='1' }} "
             "and trashed=false")
        _, found = self._send("GET", self._files_url(q=q, orderBy="createdTime", fields="files(id,name)",
                                                     pageSize=10, spaces="drive"))
        if found.get("files"):
            return found["files"][0]["id"]
        meta = {"name": FOLDER_NAME, "mimeType": FOLDER_MIME, "appProperties": {MARK_KEY: "1"}}
        _, created = self._send("POST", self._files_url(fields="id"), data=json.dumps(meta).encode(),
                                headers={"Content-Type": JSON_TYPE})
        return created["id"]

    def upload(self, folder_id: str, path: Path, name: str) -> str:
        content = Path(path).read_bytes()
        meta = {"name": name, "parents": [folder_id], "mimeType": "application/octet-stream"}
        headers, _ = self._send(
            "POST", f"{self.upload_url}/files?uploadType=resumable", data=json.dumps(meta).encode(),
            headers={"Content-Type": JSON_TYPE, "X-Upload-Content-Type": "application/octet-stream",
                     "X-Upload-Content-Length": str(len(content))},
        )
        session = headers.get("Location")
        if not session:
            raise DriveError("Google Drive не начал загрузку.")
        _, uploaded = self._send("PUT", session, data=content,
                                 headers={"Content-Type": "application/octet-stream"})
        if "id" not in uploaded:
            raise DriveError("Google Drive не подтвердил загрузку.")
        return uploaded["id"]

    def file_info(self, file_id: str) -> dict:
        _, info = self._send("GET", self._files_url(f"/{file_id}", fields="id,name,size,md5Checksum"))
        return info

    def list_files(self, folder_id: str) -> list[dict]:
        files: list[dict] = []
        page_token = None
        while True:
            params = {"q": f"'{folder_id}' in parents and trashed=false",
                      "fields": "nextPageToken,files(id,name)", "pageSize": 1000}
            if page_token:
                params["pageToken"] = page_token
            _, page = self._send("GET", self._files_url(**params))
            files.extend(page.get("files", []))
            page_token = page.get("nextPageToken")
            if not page_token:
                return files

    def trash(self, file_id: str) -> None:
        self._send("PATCH", self._files_url(f"/{file_id}", fields="id"),
                   data=json.dumps({"trashed": True}).encode(), headers={"Content-Type": JSON_TYPE})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/backup && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backup/drive_backup/drive.py apps/backup/tests/fake_drive.py apps/backup/tests/test_drive.py
git commit -m "feat: add a minimal Google Drive client for backups"
```

### Task 5: Health pings and the backup job

**Files:**
- Create: `apps/backup/drive_backup/health.py`, `apps/backup/drive_backup/job.py`
- Test: `apps/backup/tests/test_health.py`, `apps/backup/tests/test_job.py`

**Interfaces:**
- Consumes: `Settings` (Task 1), `backup_name`, `names_to_trash` (Task 2), `pgtools.dump`, `pgtools.verify_dump` (Task 3), `DriveClient` (Task 4), fixtures `bin_dir`, `source_db` (Task 3), `FakeDrive` (Task 4).
- Produces: `ping_success(url: str, *, opener=urllib.request.urlopen) -> bool`; `ping_fail(url: str, message: str, *, opener=…) -> bool`; `BackupError(Exception)`; `run_backup(settings: Settings, *, drive, now: datetime, bin_dir: Path, workdir: Path, dumper=pgtools.dump, verifier=pgtools.verify_dump) -> dict` returning `{"file", "size", "kept", "trashed"}`.

- [ ] **Step 1: Write failing tests**

`apps/backup/tests/test_health.py`:
```python
import urllib.error

from drive_backup.health import ping_fail, ping_success


class Recorder:
    def __init__(self, fail=False):
        self.requests = []
        self.fail = fail

    def __call__(self, request, timeout):
        self.requests.append(request)
        if self.fail:
            raise urllib.error.URLError("down")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"OK"
        return Response()


def test_success_ping_is_get_to_check_url():
    rec = Recorder()
    assert ping_success("https://hc-ping.com/uuid", opener=rec) is True
    assert rec.requests[0].full_url == "https://hc-ping.com/uuid"
    assert rec.requests[0].get_method() == "GET"


def test_fail_ping_posts_message_to_fail_url():
    rec = Recorder()
    assert ping_fail("https://hc-ping.com/uuid/", "копия неполная", opener=rec) is True
    request = rec.requests[0]
    assert request.full_url == "https://hc-ping.com/uuid/fail"
    assert request.get_method() == "POST"
    assert request.data == "копия неполная".encode()


def test_ping_errors_are_swallowed():
    assert ping_success("https://hc-ping.com/uuid", opener=Recorder(fail=True)) is False
    assert ping_fail("https://hc-ping.com/uuid", "x", opener=Recorder(fail=True)) is False
```

`apps/backup/tests/test_job.py`:
```python
import datetime as dt

import pytest

from drive_backup.drive import DriveError
from drive_backup.job import BackupError, run_backup
from drive_backup.pgtools import DumpError
from drive_backup.settings import Settings

from .fake_drive import FakeDrive

NOW = dt.datetime(2026, 11, 9, 2, 5, tzinfo=dt.timezone.utc)


def settings_for(url):
    return Settings(url, "id", "secret", "good-refresh", "https://hc-ping.com/uuid", "cron")


@pytest.fixture
def drive():
    with FakeDrive() as fake:
        yield fake


def seed(drive, client, names):
    folder = client.find_or_create_folder()
    for name in names:
        drive.files[name] = {"id": name, "name": name, "parents": [folder], "trashed": False, "content": b"old"}
    return folder


def test_real_dump_lands_in_drive_and_old_copies_are_trashed(drive, source_db, bin_dir, tmp_path):
    client = drive.client()
    folder = seed(drive, client, ["cats-house-2026-11-08T0200Z.dump", "cats-house-2026-10-01T0200Z.dump",
                                  "cats-house-2026-10-31T0200Z.dump", "notes.txt"])
    result = run_backup(settings_for(source_db["url"]), drive=client, now=NOW, bin_dir=bin_dir, workdir=tmp_path)
    assert result["file"] == "cats-house-2026-11-09T0205Z.dump"
    assert result["size"] > 0
    assert result["trashed"] == ["cats-house-2026-10-01T0200Z.dump"]
    assert drive.live_names(folder) == ["cats-house-2026-10-31T0200Z.dump", "cats-house-2026-11-08T0200Z.dump",
                                        "cats-house-2026-11-09T0205Z.dump", "notes.txt"]
    assert result["kept"] == 3
    assert list(tmp_path.iterdir()) == []


def fake_dumper(url, target, bin_dir):
    target.write_bytes(b"fake dump")


def test_checksum_mismatch_trashes_upload_and_keeps_old_copies(drive, tmp_path):
    client = drive.client()
    old = ["cats-house-2026-01-01T0200Z.dump"]
    folder = seed(drive, client, old)
    drive.corrupt_md5 = True
    with pytest.raises(BackupError, match="не совпал"):
        run_backup(settings_for("postgresql://x"), drive=client, now=NOW, bin_dir=tmp_path, workdir=tmp_path,
                   dumper=fake_dumper, verifier=lambda path, bin_dir: None)
    assert drive.live_names(folder) == old


def test_failed_upload_prunes_nothing(drive, tmp_path):
    client = drive.client()
    old = ["cats-house-2025-01-01T0200Z.dump", "cats-house-2025-02-01T0200Z.dump"]
    folder = seed(drive, client, old)
    drive.fail_upload = True
    with pytest.raises(DriveError):
        run_backup(settings_for("postgresql://x"), drive=client, now=NOW, bin_dir=tmp_path, workdir=tmp_path,
                   dumper=fake_dumper, verifier=lambda path, bin_dir: None)
    assert drive.live_names(folder) == old


def test_failed_verification_uploads_nothing(drive, tmp_path):
    client = drive.client()
    folder = seed(drive, client, [])

    def bad_verifier(path, bin_dir):
        raise DumpError("копия неполная: нет данных таблиц media")

    with pytest.raises(DumpError):
        run_backup(settings_for("postgresql://x"), drive=client, now=NOW, bin_dir=tmp_path, workdir=tmp_path,
                   dumper=fake_dumper, verifier=bad_verifier)
    assert drive.live_names(folder) == []
    assert list(tmp_path.iterdir()) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/backup && .venv/bin/pytest -q tests/test_health.py tests/test_job.py`
Expected: FAIL with `ModuleNotFoundError` for `drive_backup.health` / `drive_backup.job`.

- [ ] **Step 3: Implement**

`apps/backup/drive_backup/health.py`:
```python
"""Сигналы сторожу healthchecks.io. Ошибки сигналов не ломают запуск."""

from __future__ import annotations

import urllib.request


def _send(request: urllib.request.Request, opener) -> bool:
    try:
        with opener(request, timeout=10) as response:
            response.read()
        return True
    except Exception:  # noqa: BLE001 — сторож недоступен: копия от этого не хуже
        return False


def ping_success(url: str, *, opener=urllib.request.urlopen) -> bool:
    return _send(urllib.request.Request(url, method="GET"), opener)


def ping_fail(url: str, message: str, *, opener=urllib.request.urlopen) -> bool:
    request = urllib.request.Request(url.rstrip("/") + "/fail", data=message.encode("utf-8"), method="POST",
                                     headers={"Content-Type": "text/plain; charset=utf-8"})
    return _send(request, opener)
```

`apps/backup/drive_backup/job.py`:
```python
"""Один запуск: копия → проверка → Drive → сверка → хранение."""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

from drive_backup import pgtools
from drive_backup.retention import backup_name, names_to_trash
from drive_backup.settings import Settings


class BackupError(Exception):
    """Запуск не удался по причине, найденной самим сервисом."""


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_backup(settings: Settings, *, drive, now: dt.datetime, bin_dir: Path, workdir: Path,
               dumper=pgtools.dump, verifier=pgtools.verify_dump) -> dict:
    name = backup_name(now)
    target = Path(workdir) / name
    try:
        dumper(settings.database_url, target, bin_dir)
        verifier(target, bin_dir)
        size = target.stat().st_size
        local_md5 = _md5(target)
        folder = drive.find_or_create_folder()
        file_id = drive.upload(folder, target, name)
        if drive.file_info(file_id).get("md5Checksum") != local_md5:
            drive.trash(file_id)
            raise BackupError("файл в Google Drive не совпал с копией — загрузка отменена")
        files = drive.list_files(folder)
        to_trash = set(names_to_trash([f["name"] for f in files], now.astimezone(dt.timezone.utc).date()))
        trashed = []
        for item in files:
            if item["name"] in to_trash:
                drive.trash(item["id"])
                trashed.append(item["name"])
        kept = sum(1 for f in files if f["name"].startswith("cats-house-") and f["name"] not in to_trash)
        return {"file": name, "size": size, "kept": kept, "trashed": sorted(trashed)}
    finally:
        target.unlink(missing_ok=True)
```

Note: `kept` counts files whose names start with `cats-house-` (backup copies), not `notes.txt`; the test expects 3.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/backup && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backup/drive_backup/health.py apps/backup/drive_backup/job.py apps/backup/tests/test_health.py apps/backup/tests/test_job.py
git commit -m "feat: run one verified backup into Drive with retention and health pings"
```

### Task 6: HTTP endpoint and Vercel entry

**Files:**
- Create: `apps/backup/drive_backup/endpoint.py`, `apps/backup/api/backup.py`
- Test: `apps/backup/tests/test_endpoint.py`

**Interfaces:**
- Consumes: `load_settings`, `REQUIRED`, `SettingsError` (Task 1), `redact` (Task 2), `ensure_binaries` (Task 3), `DriveClient` (Task 4), `ping_success`, `ping_fail`, `run_backup` (Task 5).
- Produces: `handle(authorization: str | None, env: Mapping[str, str], *, runner=None, success=ping_success, failure=ping_fail) -> tuple[int, dict]`; `default_runner(settings) -> dict`; Vercel `handler` class in `api/backup.py`.

- [ ] **Step 1: Write failing tests**

`apps/backup/tests/test_endpoint.py`:
```python
import importlib.util
import io
from pathlib import Path

from drive_backup.endpoint import handle

from .test_settings import full_env

AUTH = "Bearer cron-secret-value-0123456789"


class Pings:
    def __init__(self):
        self.ok, self.failed = [], []

    def success(self, url):
        self.ok.append(url)
        return True

    def failure(self, url, message):
        self.failed.append((url, message))
        return True


def call(authorization, env, runner):
    pings = Pings()
    status, body = handle(authorization, env, runner=runner, success=pings.success, failure=pings.failure)
    return status, body, pings


def never(settings):
    raise AssertionError("должно было не дойти до копии")


def test_missing_or_wrong_secret_is_401_without_running():
    for header in (None, "", "Bearer wrong", "cron-secret-value-0123456789"):
        status, body, pings = call(header, full_env(), never)
        assert status == 401
        assert pings.ok == pings.failed == []


def test_success_returns_result_and_pings():
    status, body, pings = call(AUTH, full_env(), lambda s: {"file": "f.dump", "size": 1, "kept": 1, "trashed": []})
    assert status == 200 and body["file"] == "f.dump"
    assert pings.ok == ["https://hc-ping.com/abc-uuid"] and pings.failed == []


def test_failure_is_500_redacted_and_reported():
    def boom(settings):
        raise RuntimeError("pg_dump: error: postgresql://u:p%40ss-word@h/db failed, token refresh-token-value")

    status, body, pings = call(AUTH, full_env(), boom)
    assert status == 500
    for secret in ("p%40ss-word", "refresh-token-value", "postgresql://"):
        assert secret not in body["error"]
        assert secret not in pings.failed[0][1]
    assert pings.ok == []


def test_missing_settings_report_names_only():
    env = full_env(GOOGLE_REFRESH_TOKEN="")
    status, body, pings = call(AUTH, env, never)
    assert status == 500
    assert "GOOGLE_REFRESH_TOKEN" in body["error"]
    assert pings.failed and pings.failed[0][0] == "https://hc-ping.com/abc-uuid"


def test_missing_cron_secret_fails_closed():
    status, body, pings = call("Bearer ", full_env(CRON_SECRET=""), never)
    assert status == 500
    assert "CRON_SECRET" in body["error"]


def test_vercel_entry_answers_401_without_secret(monkeypatch):
    path = Path(__file__).parents[1] / "api" / "backup.py"
    spec = importlib.util.spec_from_file_location("vercel_entry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("CRON_SECRET", "x" * 32)

    request = io.BytesIO(b"GET /api/backup HTTP/1.1\r\nHost: test\r\n\r\n")
    response = io.BytesIO()

    class Socket:
        def makefile(self, mode, *args, **kwargs):
            return request if "r" in mode else response

        def sendall(self, data):
            response.write(data)

    module.handler(Socket(), ("127.0.0.1", 1), None)
    assert response.getvalue().startswith(b"HTTP/1.0 401")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/backup && .venv/bin/pytest -q tests/test_endpoint.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'drive_backup.endpoint'`.

- [ ] **Step 3: Implement**

`apps/backup/drive_backup/endpoint.py`:
```python
"""Проверка секрета, запуск, ответ и сигналы сторожу."""

from __future__ import annotations

import datetime as dt
import hmac
import tempfile
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import unquote, urlparse

from drive_backup.drive import DriveClient
from drive_backup.health import ping_fail, ping_success
from drive_backup.job import run_backup
from drive_backup.pgtools import ensure_binaries
from drive_backup.redact import redact
from drive_backup.settings import REQUIRED, Settings, load_settings


def default_runner(settings: Settings) -> dict:
    bin_dir = ensure_binaries()
    drive = DriveClient(settings.google_client_id, settings.google_client_secret, settings.google_refresh_token)
    with tempfile.TemporaryDirectory() as workdir:
        return run_backup(settings, drive=drive, now=dt.datetime.now(dt.timezone.utc),
                          bin_dir=bin_dir, workdir=Path(workdir))


def _secrets(env: Mapping[str, str]) -> list[str]:
    values = [(env.get(name) or "").strip() for name in REQUIRED]
    password = unquote(urlparse((env.get("BACKUP_DATABASE_URL") or "").strip()).password or "")
    return [v for v in values + [password, password and password.replace("@", "%40")] if v]


def handle(authorization: Optional[str], env: Mapping[str, str], *, runner=None,
           success=ping_success, failure=ping_fail) -> tuple[int, dict]:
    healthcheck = (env.get("HEALTHCHECK_URL") or "").strip()
    expected = (env.get("CRON_SECRET") or "").strip()
    if not expected:
        message = "Не задана настройка CRON_SECRET."
        if healthcheck:
            failure(healthcheck, message)
        return 500, {"error": message}
    if not authorization or not hmac.compare_digest(authorization.encode(), f"Bearer {expected}".encode()):
        return 401, {"error": "Нет доступа."}
    try:
        settings = load_settings(env)
        result = (runner or default_runner)(settings)
    except Exception as error:  # noqa: BLE001 — любая ошибка должна дойти до сторожа
        message = redact(str(error) or error.__class__.__name__, _secrets(env))
        if healthcheck:
            failure(healthcheck, message)
        return 500, {"error": message}
    success(settings.healthcheck_url)
    return 200, result
```

Note: `_secrets` also redacts the URL-encoded form of the password (`%40` for `@`), because error text can quote the raw URL; the URL pattern in `redact` covers whole URLs.

`apps/backup/api/backup.py`:
```python
"""Вход функции Vercel: GET /api/backup, вызывается расписанием Vercel Cron."""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drive_backup.endpoint import handle  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, body = handle(self.headers.get("Authorization"), os.environ)
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/backup && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backup/drive_backup/endpoint.py apps/backup/api/backup.py apps/backup/tests/test_endpoint.py
git commit -m "feat: expose the nightly backup as a secret-protected Vercel function"
```

### Task 7: One-time Google authorization script

**Files:**
- Create: `apps/backup/scripts/google-authorize.py`
- Test: `apps/backup/tests/test_google_authorize.py`

**Interfaces:**
- Produces (module loaded by path): `SCOPE`, `build_auth_url(client_id, redirect_uri, state, challenge) -> str`, `pkce_pair() -> tuple[str, str]`, `parse_callback(path: str, expected_state: str) -> str` (raises `ValueError`), `exchange_code(code, client_id, client_secret, redirect_uri, verifier, *, token_url, opener) -> str` (refresh token; raises `RuntimeError`), `save_env(path: Path, client_id, client_secret, refresh_token) -> None`, `main(argv) -> int`.
- Usage: `python3 apps/backup/scripts/google-authorize.py <client_secret.json> [--out ~/.config/cats-house/backup-google.env]`. Writes `GOOGLE_CLIENT_ID=…`, `GOOGLE_CLIENT_SECRET=…`, `GOOGLE_REFRESH_TOKEN=…` (file mode `600`, directory `700`); prints only the file path.

- [ ] **Step 1: Write failing tests**

`apps/backup/tests/test_google_authorize.py`:
```python
import importlib.util
import io
import json
import stat
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

PATH = Path(__file__).parents[1] / "scripts" / "google-authorize.py"
spec = importlib.util.spec_from_file_location("google_authorize", PATH)
ga = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ga)


def test_consent_url_asks_only_for_own_files_offline():
    url = urlparse(ga.build_auth_url("cid", "http://127.0.0.1:5555/", "st", "ch"))
    q = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    assert q["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert q["code_challenge_method"] == ["S256"] and q["code_challenge"] == ["ch"]
    assert q["state"] == ["st"] and q["redirect_uri"] == ["http://127.0.0.1:5555/"]


def test_pkce_pair_is_s256():
    import base64, hashlib
    verifier, challenge = ga.pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected and len(verifier) >= 43


def test_callback_checks_state_and_errors():
    assert ga.parse_callback("/?state=st&code=abc", "st") == "abc"
    with pytest.raises(ValueError, match="state"):
        ga.parse_callback("/?state=other&code=abc", "st")
    with pytest.raises(ValueError, match="access_denied"):
        ga.parse_callback("/?state=st&error=access_denied", "st")


class Opener:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def __call__(self, request, timeout):
        self.request = request
        return io.BytesIO(json.dumps(self.payload).encode())


def test_exchange_returns_refresh_token_and_sends_verifier():
    opener = Opener({"access_token": "a", "refresh_token": "r-token"})
    token = ga.exchange_code("code", "cid", "csecret", "http://127.0.0.1:1/", "verifier",
                             token_url="https://oauth2.googleapis.com/token", opener=opener)
    assert token == "r-token"
    form = parse_qs(opener.request.data.decode())
    assert form["code_verifier"] == ["verifier"] and form["grant_type"] == ["authorization_code"]


def test_exchange_without_refresh_token_fails():
    with pytest.raises(RuntimeError, match="refresh"):
        ga.exchange_code("code", "cid", "cs", "http://127.0.0.1:1/", "v",
                         token_url="https://x/token", opener=Opener({"access_token": "a"}))


def test_env_file_is_private(tmp_path):
    out = tmp_path / "dir" / "backup-google.env"
    ga.save_env(out, "cid", "csecret", "r-token")
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert stat.S_IMODE(out.parent.stat().st_mode) == 0o700
    assert out.read_text().splitlines() == [
        "GOOGLE_CLIENT_ID=cid", "GOOGLE_CLIENT_SECRET=csecret", "GOOGLE_REFRESH_TOKEN=r-token"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/backup && .venv/bin/pytest -q tests/test_google_authorize.py`
Expected: FAIL with `FileNotFoundError` for `scripts/google-authorize.py`.

- [ ] **Step 3: Implement**

`apps/backup/scripts/google-authorize.py`:
```python
#!/usr/bin/env python3
"""Разово выдать сервису копий доступ к своим файлам в Google Drive.

python3 apps/backup/scripts/google-authorize.py <client_secret.json> [--out <файл>]

Открывает страницу согласия Google, принимает ответ на 127.0.0.1 и записывает
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET и GOOGLE_REFRESH_TOKEN в файл (права 600).
Ключи на экран не выводятся.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCOPE = "https://www.googleapis.com/auth/drive.file"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_OUT = Path("~/.config/cats-house/backup-google.env").expanduser()


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def build_auth_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })


def parse_callback(path: str, expected_state: str) -> str:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
    if query.get("state") != [expected_state]:
        raise ValueError("ответ Google не прошёл проверку state")
    if "error" in query:
        raise ValueError("Google отказал: " + query["error"][0])
    if "code" not in query:
        raise ValueError("в ответе Google нет кода")
    return query["code"][0]


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str, verifier: str, *,
                  token_url: str = TOKEN_URL, opener=urllib.request.urlopen) -> str:
    form = urllib.parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri,
        "grant_type": "authorization_code", "code_verifier": verifier,
    }).encode()
    request = urllib.request.Request(token_url, data=form, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    result = json.loads(opener(request, timeout=30).read())
    token = result.get("refresh_token")
    if not token:
        raise RuntimeError("Google не выдал refresh token — отзовите доступ приложения в аккаунте Google и повторите")
    return token


def save_env(path: Path, client_id: str, client_secret: str, refresh_token: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"GOOGLE_CLIENT_ID={client_id}\nGOOGLE_CLIENT_SECRET={client_secret}\n"
                     f"GOOGLE_REFRESH_TOKEN={refresh_token}\n")
    os.chmod(path, 0o600)


def wait_for_code(server: HTTPServer, state: str) -> str:
    holder: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                holder["code"] = parse_callback(self.path, state)
                text = "Готово. Окно можно закрыть."
            except ValueError as error:
                holder["error"] = error
                text = f"Не получилось: {error}"
            data = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server.RequestHandlerClass = Handler
    while "code" not in holder and "error" not in holder:
        server.handle_request()
    if "error" in holder:
        raise holder["error"]  # type: ignore[misc]
    return holder["code"]  # type: ignore[return-value]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Выдать сервису копий доступ к Google Drive")
    parser.add_argument("client_secret", type=Path, help="JSON OAuth-клиента (Desktop app) из Google Cloud")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    installed = json.loads(args.client_secret.read_text(encoding="utf-8"))["installed"]
    client_id, client_secret = installed["client_id"], installed["client_secret"]
    server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/"
    state = secrets.token_urlsafe(24)
    verifier, challenge = pkce_pair()
    url = build_auth_url(client_id, redirect_uri, state, challenge)
    print("Открываю страницу Google. Если браузер не открылся, откройте адрес вручную:\n" + url)
    webbrowser.open(url)
    try:
        code = wait_for_code(server, state)
        token = exchange_code(code, client_id, client_secret, redirect_uri, verifier)
    except (ValueError, RuntimeError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    finally:
        server.server_close()
    save_env(args.out, client_id, client_secret, token)
    print(f"Ключи сохранены в {args.out} (права 600). На экран они не выводились.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/backup && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backup/scripts/google-authorize.py apps/backup/tests/test_google_authorize.py
git commit -m "feat: add one-time Google Drive authorization for backups"
```

### Task 8: Restore-check script

**Files:**
- Create: `apps/backup/scripts/verify-backup-file.py`
- Modify: `docs/superpowers/specs/2026-11-08-daily-backup-to-drive-design.md` (script path `scripts/verify-backup-file.py` → `apps/backup/scripts/verify-backup-file.py`)
- Test: `apps/backup/tests/test_verify_backup_file.py`

**Interfaces:**
- Consumes: `ensure_binaries`, `pg_environment` (Task 3); fixtures `bin_dir`, `source_db`, `dump_file` (Task 3).
- Produces (module loaded by path): `STATS_SQL`, `MEDIA_SQL`, `collect(bin_dir, url) -> dict[str, str]` (table → row count as text, plus key `media:sha256`), `compare(restored, source) -> list[str]` (names that differ), `main(argv, env) -> int`.
- Usage: `apps/backup/.venv/bin/python apps/backup/scripts/verify-backup-file.py <файл.dump>`; optional `CATS_HOUSE_SOURCE_DATABASE_URL` from the environment. Needs Docker. Exit 0 = restored (and matches, if compared), 1 = restore failed or mismatch.

- [ ] **Step 1: Write failing tests**

`apps/backup/tests/test_verify_backup_file.py`:
```python
import importlib.util
from pathlib import Path

PATH = Path(__file__).parents[1] / "scripts" / "verify-backup-file.py"
spec = importlib.util.spec_from_file_location("verify_backup_file", PATH)
vbf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vbf)


def test_compare_lists_differences():
    assert vbf.compare({"public.people": "2", "media:sha256": "a"}, {"public.people": "3", "media:sha256": "a"}) == ["public.people"]
    assert vbf.compare({"x": "1"}, {"x": "1", "y": "0"}) == ["y"]


def test_collect_counts_rows_and_hashes_media(source_db, bin_dir):
    stats = vbf.collect(bin_dir, source_db["url"])
    assert stats["public.people"] == "2"
    assert stats["public.media"] == "5"
    assert len(stats["media:sha256"]) == 64


def test_restores_dump_and_matches_source(dump_file, source_db, capsys):
    code = vbf.main([str(dump_file)], {"CATS_HOUSE_SOURCE_DATABASE_URL": source_db["url"]})
    out = capsys.readouterr().out
    assert code == 0, out
    assert "совпадает" in out


def test_mismatch_is_reported(dump_file, source_db, capsys):
    import psycopg
    with psycopg.connect(source_db["url"].split("?")[0], autocommit=True) as conn:
        conn.execute("insert into events values (999, 'Добавлено после копии')")
    try:
        code = vbf.main([str(dump_file)], {"CATS_HOUSE_SOURCE_DATABASE_URL": source_db["url"]})
        assert code == 1
        assert "public.events" in capsys.readouterr().out
    finally:
        with psycopg.connect(source_db["url"].split("?")[0], autocommit=True) as conn:
            conn.execute("delete from events where id = 999")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/backup && .venv/bin/pytest -q tests/test_verify_backup_file.py`
Expected: FAIL with `FileNotFoundError` for `scripts/verify-backup-file.py`.

- [ ] **Step 3: Implement**

`apps/backup/scripts/verify-backup-file.py`:
```python
#!/usr/bin/env python3
"""Проверить скачанную копию: восстановить во временную базу и сравнить с Neon.

apps/backup/.venv/bin/python apps/backup/scripts/verify-backup-file.py <файл.dump>

Восстанавливает копию в временный контейнер postgres:17-alpine (нужен Docker),
считает строки во всех таблицах и SHA-256 содержимого всех файлов. Если задана
переменная CATS_HOUSE_SOURCE_DATABASE_URL — сравнивает с этой базой.
Контейнер удаляется. Ни Neon, ни Drive не изменяются.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drive_backup.pgtools import ensure_binaries, pg_environment  # noqa: E402

IMAGE = "postgres:17-alpine"
STATS_SQL = (
    "select table_schema || '.' || table_name, "
    "(xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', "
    "table_schema, table_name), false, true, '')))[1]::text "
    "from information_schema.tables "
    "where table_schema not in ('pg_catalog', 'information_schema') and table_type = 'BASE TABLE' order by 1"
)
MEDIA_SQL = (
    "select encode(sha256(convert_to(coalesce(string_agg(id::text || ':' || encode(sha256(content), 'hex') || ':' "
    "|| coalesce(encode(sha256(preview), 'hex'), '-'), ',' order by id::text), ''), 'UTF8')), 'hex') from media"
)


def psql(bin_dir: Path, url: str, sql: str) -> str:
    return subprocess.run([str(bin_dir / "psql"), "-AtF", "\t", "-v", "ON_ERROR_STOP=1", "-c", sql],
                          env=pg_environment(url), capture_output=True, text=True, check=True, timeout=300).stdout


def collect(bin_dir: Path, url: str) -> dict[str, str]:
    stats = dict(line.split("\t") for line in psql(bin_dir, url, STATS_SQL).splitlines() if line)
    stats["media:sha256"] = psql(bin_dir, url, MEDIA_SQL).strip()
    return stats


def compare(restored: dict[str, str], source: dict[str, str]) -> list[str]:
    return sorted(name for name in set(restored) | set(source) if restored.get(name) != source.get(name))


def start_container() -> tuple[str, str]:
    name = f"cats-house-verify-{os.getpid()}"
    subprocess.run(["docker", "run", "-d", "--rm", "--name", name, "-p", "127.0.0.1::5432",
                    "-e", "POSTGRES_PASSWORD=verify-only", IMAGE], check=True, capture_output=True, timeout=300)
    port = subprocess.run(["docker", "port", name, "5432/tcp"], check=True, capture_output=True,
                          text=True).stdout.strip().rsplit(":", 1)[1]
    return name, f"postgresql://postgres:verify-only@127.0.0.1:{port}/postgres?sslmode=disable"


def wait_ready(bin_dir: Path, url: str) -> None:
    ok = 0
    for _ in range(120):
        try:
            psql(bin_dir, url, "select 1")
            ok += 1
        except subprocess.CalledProcessError:
            ok = 0
        if ok >= 2:
            return
        time.sleep(1)
    raise RuntimeError("временная база не запустилась")


def main(argv: list[str], env: Mapping[str, str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    dump = Path(argv[0])
    bin_dir = ensure_binaries(Path("/tmp/cats-house-pg"))
    name, url = start_container()
    try:
        wait_ready(bin_dir, url)
        restore = subprocess.run([str(bin_dir / "pg_restore"), "--no-owner", "--no-privileges", "--exit-on-error",
                                  str(dump)], env=pg_environment(url), capture_output=True, text=True, timeout=600)
        if restore.returncode != 0:
            print("ОШИБКА восстановления:\n" + restore.stderr.strip())
            return 1
        restored = collect(bin_dir, url)
    finally:
        subprocess.run(["docker", "stop", name], capture_output=True, timeout=120)
    source_url = (env.get("CATS_HOUSE_SOURCE_DATABASE_URL") or "").strip()
    source = collect(bin_dir, source_url) if source_url else None
    print(f"Копия: {dump.name}")
    print(f"{'таблица':40} {'в копии':>12} {'в базе':>12}")
    for key in sorted(set(restored) | set(source or {})):
        there = source.get(key, "—") if source is not None else "—"
        mark = "  ≠" if source is not None and restored.get(key) != there else ""
        print(f"{key:40} {str(restored.get(key, '—'))[:12]:>12} {str(there)[:12]:>12}{mark}")
    if source is None:
        print("Копия восстанавливается. С базой не сравнивалось (нет CATS_HOUSE_SOURCE_DATABASE_URL).")
        return 0
    differences = compare(restored, source)
    if differences:
        print("Расхождения: " + ", ".join(differences) + ". Если базу правили после копии, это нормально.")
        return 1
    print("Копия восстанавливается и совпадает с базой.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
```

In the spec, replace `Скрипт \`scripts/verify-backup-file.py <файл.dump>\`` with `Скрипт \`apps/backup/scripts/verify-backup-file.py <файл.dump>\`` (it reuses the package's PostgreSQL tools).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/backup && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backup/scripts/verify-backup-file.py apps/backup/tests/test_verify_backup_file.py docs/superpowers/specs/2026-11-08-daily-backup-to-drive-design.md
git commit -m "feat: add a restore check for downloaded backups"
```

### Task 9: Documentation

**Files:**
- Create: `apps/backup/README.md`
- Modify: `README.md` (short section), `docs/superpowers/plans/2026-11-07-vercel-neon-migration.md` (Task 4 note)
- Test: `apps/backup/tests/test_docs.py`

**Interfaces:**
- Consumes: commands and names from Tasks 1–8.

- [ ] **Step 1: Write the failing doc test**

`apps/backup/tests/test_docs.py`:
```python
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_readme_covers_setup_and_restore():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for needle in ("pg_read_all_data", "google-authorize.py", "In production", "healthchecks.io",
                   "vercel env add", "pg_restore --no-owner --no-privileges --exit-on-error",
                   "verify-backup-file.py", "CATS_HOUSE_DATABASE_URL"):
        assert needle in text, needle
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/backup && .venv/bin/pytest -q tests/test_docs.py`
Expected: FAIL with `FileNotFoundError` for `README.md`.

- [ ] **Step 3: Write the documentation**

`apps/backup/README.md` — Russian, sections:
1. **Что это** — nightly copy (02:00 UTC), Drive folder «Cat's House — копии базы», retention, healthchecks.io, what the service never does (no permanent deletion, no writes to Neon).
2. **Разовая настройка** with exact commands:
   - Neon SQL Editor:
     ```sql
     CREATE ROLE cats_house_backup LOGIN PASSWORD '<сгенерированный пароль>';
     GRANT pg_read_all_data TO cats_house_backup;
     ```
     fallback block (`GRANT CONNECT ON DATABASE neondb …; GRANT USAGE ON SCHEMA public …; GRANT SELECT ON ALL TABLES IN SCHEMA public …; GRANT SELECT ON ALL SEQUENCES IN SCHEMA public …; ALTER DEFAULT PRIVILEGES … GRANT SELECT ON TABLES …`); take the direct (non-pooled) connection string with `sslmode=require`.
   - Google Cloud: create project, enable Drive API, OAuth consent screen External → add scope `drive.file` → **publish to «In production»**, create OAuth client «Desktop app», download JSON; run `python3 apps/backup/scripts/google-authorize.py ~/Downloads/client_secret_….json`.
   - healthchecks.io: check «Cat's House backup», period 1 day, grace 3 hours, email integration; copy the ping URL.
   - Vercel: `vercel project add cats-house-backup`, Root Directory `apps/backup`; secrets only through files/stdin, never typed in the command:
     ```bash
     grep '^GOOGLE_REFRESH_TOKEN=' ~/.config/cats-house/backup-google.env | cut -d= -f2- | vercel env add GOOGLE_REFRESH_TOKEN production
     ```
     (same for `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`; `BACKUP_DATABASE_URL`, `HEALTHCHECK_URL` from a private file the owner creates; `CRON_SECRET` from `openssl rand -hex 32 > file`), then `vercel deploy --prod`.
3. **Проверить вручную** — `vercel curl` with the cron secret header read from file; expected JSON.
4. **Восстановление** — download the file from Drive; create a Neon branch or empty database; `pg_restore --no-owner --no-privileges --exit-on-error -d "$URL" <файл>` with `URL` read from a file; switch the site: change `CATS_HOUSE_DATABASE_URL` of the API Vercel project and redeploy.
5. **Ежеквартальная проверка** — `CATS_HOUSE_SOURCE_DATABASE_URL="$(cat ~/…/neon-url)" apps/backup/.venv/bin/python apps/backup/scripts/verify-backup-file.py <файл>`.
6. **Если пришло письмо от сторожа** — table of messages → actions (Google key expired → rerun `google-authorize.py` and update the env var; `pg_dump` connection error → check Neon status and the role password; checksum mismatch → rerun manually).

`README.md` (root) — add a short «Резервные копии» section pointing to `apps/backup/README.md`.

`docs/superpowers/plans/2026-11-07-vercel-neon-migration.md` — under «Task 4» add: `> Заменено планом docs/superpowers/plans/2026-11-08-daily-backup-to-drive.md (копии делает сервис на Vercel, не Mac).`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/backup && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backup/README.md apps/backup/tests/test_docs.py README.md docs/superpowers/plans/2026-11-07-vercel-neon-migration.md
git commit -m "docs: document setup and restore of nightly backups"
```

### Task 10: Setup with the owner, first run, retire the Mac job

**Files:**
- Modify (outside the repo, separate git repo `~/archiving`): `~/archiving/cats-house/README.md`, `~/archiving/cats-house/dashboard.py`
- No new automated tests in this repo; this is an owner-assisted checklist backed by Tasks 1–9.

**Interfaces:**
- Consumes: everything above; the owner's Neon console, Google account, healthchecks.io account, Vercel account `bon2362-5067`.

- [ ] **Step 1: Owner creates the read-only Neon role** following `apps/backup/README.md`; owner saves the direct connection string into a private file (e.g. `~/.config/cats-house/backup-db.url`, mode 600). The agent never sees the password.

- [ ] **Step 2: Owner sets up Google Cloud** (consent screen published «In production», Desktop client) and runs `google-authorize.py`. Expected: `~/.config/cats-house/backup-google.env` with mode 600.

- [ ] **Step 3: Owner creates the healthchecks.io check** and saves its ping URL into `~/.config/cats-house/backup-healthcheck.url` (mode 600).

- [ ] **Step 4: Create the Vercel project and secrets** (agent, with the owner's go-ahead): create `cats-house-backup` with Root Directory `apps/backup`; generate `CRON_SECRET` into `~/.config/cats-house/backup-cron.secret` (`openssl rand -hex 32`, mode 600); add all six variables to Production by piping from the files. Run `vercel env ls production` in `apps/backup`. Expected: six names listed, no values printed.

- [ ] **Step 5: Deploy and trigger once**

Run: `cd apps/backup && vercel deploy --prod --yes`, then call `/api/backup` with `Authorization: Bearer $(cat ~/.config/cats-house/backup-cron.secret)` via `vercel curl` (header value read from file inside the command substitution, not typed).
Expected: `200` with `file`, `size > 0`, `kept: 1`; the file is visible in «Мой диск» → «Cat's House — копии базы»; healthchecks.io shows the check «up». A call without the header returns `401`.

- [ ] **Step 6: Verify restore against Neon**

Owner downloads the file from Drive. Run: `CATS_HOUSE_SOURCE_DATABASE_URL="$(cat ~/.config/cats-house/backup-db.url)" apps/backup/.venv/bin/python apps/backup/scripts/verify-backup-file.py ~/Downloads/cats-house-…Z.dump`
Expected: «Копия восстанавливается и совпадает с базой.»

- [ ] **Step 7: Confirm the schedule** — the next morning check that a second file appeared on its own around 02:00–02:59 UTC and healthchecks.io received the ping. If not: Vercel project → Cron Jobs / logs.

- [ ] **Step 8: Retire the Mac job** (only after Steps 5–7 succeeded):
```bash
launchctl bootout gui/$(id -u)/com.ekoshkin.cats-house-backup
```
```bash
rm ~/Library/LaunchAgents/com.ekoshkin.cats-house-backup.plist
```
Run: `launchctl list | grep cats-house-backup`
Expected: no output. Leave `~/archiving/cats-house`, `~/Cat's House backups` and the Docker database untouched.

Edit `~/archiving/cats-house/README.md`: a first paragraph «Выведено из работы 2026-11-… : копии делает сервис `apps/backup` на Vercel (см. `~/Cat's House/apps/backup/README.md`); старые копии оставлены как есть». Edit `~/archiving/cats-house/dashboard.py` `status()` to return `state: "ready"`, `contents: ["копии делает Vercel каждую ночь — статус на healthchecks.io", <старая последняя копия>]`, `inProgress: []`, without the Docker staleness warning. Run: `/usr/bin/python3 -c "import sys; sys.path.insert(0, '$HOME/archiving/cats-house'); import dashboard, json; print(json.dumps(dashboard.status(), ensure_ascii=False))"`
Expected: JSON with `"state": "ready"` and the new line. Commit in `~/archiving` only on the owner's request.

- [ ] **Step 9: Final suite**

Run: `cd apps/backup && .venv/bin/pytest -q`
Expected: PASS.

## Self-Review

- Spec coverage: schedule/region/duration — Task 1; auth `401` — Task 6; dump via `PG*` env + TLS + one retry — Tasks 1, 3; dump check incl. table list — Task 3; naming — Task 2; folder find/create by `appProperties` — Task 4; upload + MD5 check + trash on mismatch — Tasks 4, 5; retention after successful upload, trash not delete — Tasks 2, 5; health success/fail, ping errors swallowed — Task 5; redaction ≤500 chars — Tasks 2, 6; response shape and temp-file cleanup — Tasks 5, 6; Google OAuth client, Production consent, refresh-token script, `cat … |` into Vercel — Tasks 7, 9, 10; Neon read-only role — Tasks 9, 10; missing settings named — Tasks 1, 6; restore guide and check script — Tasks 8, 9; Mac retirement, README, dashboard, migration-plan note — Tasks 9, 10; all listed checks — Tasks 1–8, manual ones in Task 10.
- Ruling vs spec: `verify-backup-file.py` lives in `apps/backup/scripts` (reuses `drive_backup.pgtools` and the bundled `psql`); Task 8 updates the spec. Missing `CRON_SECRET` answers `500` (fails closed, reported to the watchdog) rather than `401`.
- Type consistency: `Settings`, `load_settings`, `REQUIRED` (Task 1) used in Tasks 5–6; `backup_name`/`names_to_trash` (Task 2) in Task 5; `dump`/`verify_dump`/`ensure_binaries`/`pg_environment` (Task 3) in Tasks 5, 6, 8; `DriveClient` methods (Task 4) match `run_backup` calls; `FakeDrive.client/live_names/corrupt_md5/fail_upload` used consistently.
- Review Focus coverage: retry — `test_dump_retries_once…`; revoked token — `test_revoked_refresh_token_gives_clear_error` + endpoint failure path; checksum mismatch — `test_checksum_mismatch_trashes_upload…`; redaction — `test_failure_is_500_redacted_and_reported`; pruning safety — `test_other_names_are_never_trashed`, `test_newest_copy_is_always_kept`, `test_failed_upload_prunes_nothing`.
