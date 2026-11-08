#!/usr/bin/env python3
"""Восстановить копию из Google Drive в пустую базу.

CATS_HOUSE_RESTORE_DATABASE_URL="$(cat <файл с адресом базы>)" \\
  apps/backup/.venv/bin/python apps/backup/scripts/restore-backup.py <файл.dump>

Адрес базы берётся только из переменной окружения и передаётся pg_restore через
переменные PG*, а не в аргументах команды. В базу, где уже есть таблицы, скрипт
не восстанавливает — так рабочий сайт нельзя затереть по ошибке.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drive_backup.pgtools import ensure_binaries, pg_environment  # noqa: E402

TABLES_SQL = "select count(*) from pg_tables where schemaname not in ('pg_catalog', 'information_schema')"


def main(argv: list[str], env: Mapping[str, str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    url = (env.get("CATS_HOUSE_RESTORE_DATABASE_URL") or "").strip()
    if not url:
        print("Не задана переменная CATS_HOUSE_RESTORE_DATABASE_URL (адрес пустой базы для восстановления).",
              file=sys.stderr)
        return 2
    dump = Path(argv[0])
    bin_dir = ensure_binaries(Path("/tmp/cats-house-pg"))
    connection = pg_environment(url)
    count = subprocess.run([str(bin_dir / "psql"), "-At", "-v", "ON_ERROR_STOP=1", "-c", TABLES_SQL],
                           env=connection, capture_output=True, text=True, timeout=120)
    if count.returncode != 0:
        print("Не удалось подключиться к базе: " + (count.stderr.strip().splitlines() or ["без описания"])[-1],
              file=sys.stderr)
        return 1
    if count.stdout.strip() != "0":
        print(f"База «{connection['PGDATABASE']}» не пустая — восстанавливать в неё нельзя. "
              "Создайте новую пустую базу.", file=sys.stderr)
        return 1
    restore = subprocess.run([str(bin_dir / "pg_restore"), "--no-owner", "--no-privileges", "--exit-on-error",
                              "--dbname", connection["PGDATABASE"], str(dump)],
                             env=connection, capture_output=True, text=True, timeout=1800)
    if restore.returncode != 0:
        print("ОШИБКА восстановления:\n" + restore.stderr.strip(), file=sys.stderr)
        return 1
    print(f"Копия {dump.name} восстановлена в базу «{connection['PGDATABASE']}».")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], os.environ))
