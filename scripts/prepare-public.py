#!/usr/bin/env python3
"""Перед публикацией: если в базе есть неприменённые миграции — снять копию базы и применить их."""

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "apps" / "api"
BACKUPS = Path.home() / "cats-house-backups"


def load_env(env_file: Path) -> None:
    """The same way dev-native.sh does: $$ is a literal $, the database is reached on localhost."""
    from dotenv import dotenv_values

    values = {key: value.replace("$$", "$") for key, value in dotenv_values(env_file).items() if value is not None}
    os.environ.update(values)
    os.environ["CATS_HOUSE_DATABASE_URL"] = os.environ["CATS_HOUSE_DATABASE_URL"].replace("@postgres:", "@127.0.0.1:")


def main() -> int:
    env_file = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / ".env"
    load_env(env_file)
    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine

    config = Config(str(API / "alembic.ini"))
    config.set_main_option("script_location", str(API / "alembic"))
    config.set_main_option("sqlalchemy.url", os.environ["CATS_HOUSE_DATABASE_URL"])
    head = ScriptDirectory.from_config(config).get_current_head()
    engine = create_engine(os.environ["CATS_HOUSE_DATABASE_URL"])
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    engine.dispose()
    if current == head:
        print(f"База в актуальном состоянии ({current}).")
        return 0

    BACKUPS.mkdir(exist_ok=True)
    backup = BACKUPS / f"before-migrate-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.sql"
    dump = subprocess.run(
        ["docker", "exec", "catshouse-postgres-1", "sh", "-c", 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],
        capture_output=True,
    )
    if dump.returncode != 0 or not dump.stdout:
        print("Не удалось снять копию базы — миграции не применены.", file=sys.stderr)
        return 1
    backup.write_bytes(dump.stdout)
    print(f"Копия базы: {backup}")
    command.upgrade(config, "head")
    print(f"Миграции применены: {current} → {head}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
