#!/usr/bin/env python3
"""Восстановить JSON-архив и сохранённые медиа-файлы Cat's House."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from alembic import command
from alembic.config import Config
from app.core.config import Settings
from app.db.session import create_session_factory
from app.exports.service import restore_archive


def main() -> int:
    parser = argparse.ArgumentParser(description="Восстановление резервной копии Cat's House")
    parser.add_argument("--archive", required=True, type=Path, help="Абсолютный JSON-архив")
    args = parser.parse_args()
    if not args.archive.is_absolute() or not args.archive.is_file():
        parser.error("Укажите существующий абсолютный JSON-архив.")
    archive = json.loads(args.archive.read_text(encoding="utf-8"))
    settings = Settings()
    config = Config(str(ROOT / "apps" / "api" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    config.set_main_option("script_location", str(ROOT / "apps" / "api" / "alembic"))
    command.upgrade(config, "head")
    contents: dict[str, bytes] = {}
    for item in archive.get("media_manifest", []):
        backup_file = item.get("backup_file")
        if not backup_file:
            continue  # a manifest entry without stored bytes (e.g. an old S3 record) is restored without a file
        source = args.archive.parent / backup_file
        if not source.is_file():
            raise ValueError("Файл медиа из архива не найден.")
        contents[item["archive_id"]] = source.read_bytes()
    with create_session_factory(settings.database_url)() as session:
        restore_archive(session, archive, contents)
    print(f"Восстановлено: люди {archive['counts']['people']}; события {archive['counts']['events']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
