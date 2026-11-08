#!/usr/bin/env python3
"""Проверить скачанную копию: восстановить во временную базу и сравнить с Neon.

apps/backup/.venv/bin/python apps/backup/scripts/verify-backup-file.py <файл.dump>

Восстанавливает копию во временный контейнер postgres:17-alpine (нужен Docker),
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
                          text=True).stdout.strip().splitlines()[0].rsplit(":", 1)[1]
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
                                  "--dbname", "postgres", str(dump)],
                                 env=pg_environment(url), capture_output=True, text=True, timeout=600)
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
