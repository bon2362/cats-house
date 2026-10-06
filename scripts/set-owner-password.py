#!/usr/bin/env python3
"""Задать новый пароль владельца: хеш Argon2 записывается в .env, пароль и хеш не печатаются."""

import argparse
import sys
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Смена пароля владельца Cat's House")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env", help="Файл .env (по умолчанию в корне проекта)")
    args = parser.parse_args()

    try:
        from argon2 import PasswordHasher
    except ModuleNotFoundError:
        print("Запустите команду через Python проекта: apps/api/.venv/bin/python scripts/set-owner-password.py", file=sys.stderr)
        return 1
    from app.auth.password_file import OWNER_PASSWORD_KEY, validate_new_password, write_env_value

    first = getpass("Новый пароль владельца: ")
    second = getpass("Повторите пароль: ")
    try:
        validate_new_password(first, second)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    write_env_value(args.env_file, OWNER_PASSWORD_KEY, PasswordHasher().hash(first))
    print("Пароль владельца обновлён. Перезапустите API, чтобы он вступил в силу.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
