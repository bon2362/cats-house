#!/usr/bin/env python3
"""Проверяемо перенести PostgreSQL Cat's House в Neon.

URLs передаются только через переменные окружения и не сохраняются в репозитории:
  CATS_HOUSE_SOURCE_DATABASE_URL
  CATS_HOUSE_TARGET_DATABASE_URL
"""

import argparse
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]


def parser_error(message: str) -> None:
    print(f"Ошибка: {message}", file=sys.stderr)
    raise SystemExit(2)


def database_url(name: str) -> str:
    value = os.getenv(name)
    if not value:
        parser_error(f"Не задана переменная {name}.")
    parsed = urlparse(value)
    if not parsed.scheme.startswith(("postgresql", "postgres")) or not parsed.hostname or not parsed.path:
        parser_error(f"{name} должен быть URL PostgreSQL.")
    return value


def target_is_tls(url: str) -> bool:
    return "require" in parse_qs(urlparse(url).query).get("sslmode", [])


def pg_environment(url: str) -> dict[str, str]:
    """Return libpq environment without exposing the URL in subprocess arguments."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    environment = os.environ.copy()
    environment.update(
        {
            "PGHOST": parsed.hostname or "",
            "PGPORT": str(parsed.port or 5432),
            "PGUSER": unquote(parsed.username or ""),
            "PGPASSWORD": unquote(parsed.password or ""),
            "PGDATABASE": parsed.path.lstrip("/"),
            "PGSSLMODE": query.get("sslmode", ["prefer"])[0],
        }
    )
    return environment


def run(command: list[str], environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, env=environment, text=True, check=True, capture_output=True)


def require_tools() -> None:
    missing = [name for name in ("pg_dump", "pg_restore", "psql") if shutil.which(name) is None]
    if missing:
        parser_error(f"Не найдены утилиты PostgreSQL: {', '.join(missing)}.")


def target_is_empty(target_url: str) -> bool:
    result = run(
        [
            "psql",
            "--no-align",
            "--tuples-only",
            "--command",
            "SELECT count(*) FROM pg_tables WHERE schemaname = 'public';",
        ],
        pg_environment(target_url),
    )
    return result.stdout.strip() == "0"


def scalar(url: str, query: str) -> str:
    return run(
        ["psql", "--no-align", "--tuples-only", "--command", query],
        pg_environment(url),
    ).stdout.strip()


def table_counts(url: str) -> dict[str, str]:
    tables = scalar(
        url,
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;",
    ).splitlines()
    return {table: scalar(url, f'SELECT count(*) FROM public."{table}";') for table in tables if table}


def media_fingerprint(url: str) -> str:
    """A stable checksum of stored originals and previews, without reading bytes locally."""
    return scalar(
        url,
        "SELECT coalesce(md5(string_agg(coalesce(md5(content), '') || coalesce(md5(preview), ''), '' ORDER BY id)), '') FROM media;",
    )


def verify_migration(source_url: str, target_url: str) -> None:
    source_counts = table_counts(source_url)
    target_counts = table_counts(target_url)
    if source_counts != target_counts:
        raise RuntimeError(f"Количество строк не совпадает: источник {source_counts}; Neon {target_counts}.")
    if "media" in source_counts and media_fingerprint(source_url) != media_fingerprint(target_url):
        raise RuntimeError("Контрольные суммы файлов media не совпадают.")
    print(f"Проверка данных пройдена: таблиц {len(source_counts)}, файлов media {source_counts.get('media', '0')}.")


def migrate(source_url: str, target_url: str, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    dump = output / f"cats-house-neon-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.dump"
    if not target_is_empty(target_url):
        parser_error("Целевая база Neon не пуста; перенос отменён.")
    run(["pg_dump", "--format=custom", "--file", str(dump)], pg_environment(source_url))
    target_environment = pg_environment(target_url)
    run(
        [
            "pg_restore",
            "--dbname",
            target_environment["PGDATABASE"],
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            str(dump),
        ],
        target_environment,
    )
    verify_migration(source_url, target_url)
    print(f"Перенос завершён. Файл выгрузки сохранён: {dump}")
    print("Далее выполните проверку приложения на Vercel до изменения DNS.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Перенос PostgreSQL Cat's House в Neon")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Проверить параметры без подключений и изменений")
    mode.add_argument("--apply", action="store_true", help="Создать dump и восстановить его в пустую базу Neon")
    parser.add_argument("--output", type=Path, help="Абсолютный каталог для файла dump (только с --apply)")
    args = parser.parse_args()

    source_url = database_url("CATS_HOUSE_SOURCE_DATABASE_URL")
    target_url = database_url("CATS_HOUSE_TARGET_DATABASE_URL")
    if source_url == target_url:
        parser_error("Исходная и целевая базы не должны совпадать.")
    if not target_is_tls(target_url):
        parser_error("Для Neon укажите sslmode=require в CATS_HOUSE_TARGET_DATABASE_URL.")

    if args.check:
        print("Проверка готовности завершена: URLs заданы, целевой URL использует TLS.")
        return 0

    if args.output is None or not args.output.is_absolute():
        parser_error("Для --apply укажите абсолютный каталог --output вне репозитория.")
    if ROOT in args.output.resolve().parents or args.output.resolve() == ROOT:
        parser_error("Каталог с dump должен находиться вне репозитория.")
    print("Будет создана выгрузка локальной базы и записана в пустую базу Neon.")
    if input("Для продолжения введите MIGRATE: ") != "MIGRATE":
        print("Перенос отменён. Для запуска нужно ввести ровно MIGRATE.")
        return 2
    require_tools()
    try:
        migrate(source_url, target_url, args.output)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(getattr(error, "stderr", None) or str(error) or "Команда PostgreSQL завершилась с ошибкой.", file=sys.stderr)
        return getattr(error, "returncode", 1) or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
