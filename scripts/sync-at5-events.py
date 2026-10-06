#!/usr/bin/env python3
"""Пересобрать события (рождения, смерти, браки) из файла Древо Жизни AT5.

Без --apply выполняется пробный прогон: печатается отчёт, база не меняется.
Люди, союзы и родственные связи не меняются. Отчёт содержит только числа.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Пересборка событий Cat's House из AT5")
    parser.add_argument("--at5", required=True, type=Path, help="Абсолютный путь к файлу Древо Жизни AT5")
    parser.add_argument("--apply", action="store_true", help="Записать изменения в базу")
    args = parser.parse_args()
    if not args.at5.is_absolute():
        parser.error("Укажите абсолютный путь к файлу AT5.")
    if not args.at5.is_file():
        parser.error("Файл AT5 не найден.")

    from app.core.config import Settings
    from app.db.session import create_session_factory
    from app.gedcom.at5 import At5ImportError
    from app.imports.at5_sync import sync_events_from_at5

    settings = Settings()
    with create_session_factory(settings.database_url)() as session:
        try:
            report = sync_events_from_at5(session, args.at5, apply=args.apply)
        except At5ImportError as error:
            print(f"Остановлено: {error}", file=sys.stderr)
            return 1
    print("Применено" if report.applied else "Пробный прогон: база не изменена")
    print(f"События до:    {report.before}; с датой: {report.dated_before}")
    print(f"События после: {report.after}; с датой: {report.dated_after}")
    print(f"Пропущено событий людей, которых нет на сайте: {report.skipped_absent_people}")
    print(f"Пропущено событий без главного участника: {report.skipped_without_owner}")
    print(f"Браков без союза на сайте (записаны на людей): {report.marriages_without_union}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
