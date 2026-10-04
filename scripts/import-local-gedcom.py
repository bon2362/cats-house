#!/usr/bin/env python3
"""Локальный предпросмотр и разовое применение GEDCOM без публикации файла."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from alembic import command
from alembic.config import Config
from app.core.config import Settings
from app.db.session import create_session_factory
from app.imports.service import apply_preview, create_preview


def main() -> int:
    parser = argparse.ArgumentParser(description="Локальный импорт GEDCOM Cat's House")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--at5", type=Path, help="Абсолютный путь к локальному файлу Древо Жизни AT5")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.file.is_absolute():
        parser.error("Укажите абсолютный путь к GEDCOM-файлу.")
    if not args.file.is_file():
        parser.error("GEDCOM-файл не найден.")
    if args.at5 is not None:
        if not args.at5.is_absolute():
            parser.error("Укажите абсолютный путь к файлу AT5.")
        if not args.at5.is_file():
            parser.error("Файл AT5 не найден.")

    settings = Settings()
    config = Config(str(ROOT / "apps" / "api" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    config.set_main_option("script_location", str(ROOT / "apps" / "api" / "alembic"))
    command.upgrade(config, "head")

    with create_session_factory(settings.database_url)() as session:
        run = create_preview(session, args.file.name, args.file.read_bytes(), at5_path=args.at5)
        if args.apply:
            run = apply_preview(session, run.id)
        print(f"Состояние: {run.state}")
        for label, key in (("Люди", "people"), ("Союзы", "unions"), ("Родительские связи", "parent_links"), ("События", "events")):
            print(f"{label}: {run.counts.get(key, 0)}")
        print(f"Предупреждения: {sum(issue.severity == 'warning' for issue in run.issues)}")
        print(f"Ошибки: {sum(issue.severity == 'error' for issue in run.issues)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
