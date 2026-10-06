#!/usr/bin/env python3
"""Заполнить фамилию, имя и отчество из файла Древо Жизни AT5 у людей, где они ещё пусты.

Без --apply — пробный прогон: печатается отчёт из чисел, база не меняется.
Отображаемое имя людей не меняется.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Части имени из AT5")
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
    from app.imports.name_backfill import backfill_name_parts

    with create_session_factory(Settings().database_url)() as session:
        try:
            report = backfill_name_parts(session, args.at5, apply=args.apply)
        except At5ImportError as error:
            print(f"Остановлено: {error}", file=sys.stderr)
            return 1
    print("Применено" if report.applied else "Пробный прогон: база не изменена")
    print(f"Заполнено людей: {report.filled}")
    print(f"Уже были заполнены: {report.already_filled}")
    print(f"Нет имени в AT5: {report.without_at5_names}")
    print(f"Без ссылки на AT5: {report.without_source}")
    print(f"Собранное имя отличается от отображаемого: {report.display_name_differs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
