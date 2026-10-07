#!/usr/bin/env python3
"""Включить (или отключить) двухфакторный вход владельца: секрет пишется в .env, в журналы не попадает."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Двухфакторный вход владельца Cat's House")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env", help="Файл .env (по умолчанию в корне проекта)")
    parser.add_argument("--disable", action="store_true", help="Отключить двухфакторный вход")
    args = parser.parse_args()

    try:
        from dotenv import dotenv_values

        from app.auth.totp_setup import confirm_and_save, new_secret, otpauth_uri, remove_secret
    except ModuleNotFoundError:
        print("Запустите через Python проекта: apps/api/.venv/bin/python scripts/enable-owner-totp.py", file=sys.stderr)
        return 1
    if not args.env_file.exists():
        print(f"Нет файла {args.env_file}.", file=sys.stderr)
        return 1

    if args.disable:
        if input("Отключить двухфакторный вход? (да/нет): ").strip().lower() != "да":
            print("Ничего не изменено.")
            return 0
        remove_secret(args.env_file)
        print("Двухфакторный вход отключён. Перезапустите сайт.")
        return 0

    email = dotenv_values(args.env_file).get("CATS_HOUSE_OWNER_EMAIL") or "owner"
    secret = new_secret()
    uri = otpauth_uri(secret, email)
    print("Отсканируйте QR-код приложением-аутентификатором (1Password, Google Authenticator и др.):\n")
    try:
        import qrcode

        code = qrcode.QRCode(border=1)
        code.add_data(uri)
        code.print_ascii(invert=True)
    except ModuleNotFoundError:
        print("(Для QR-кода установите: apps/api/.venv/bin/pip install qrcode)")
    print(f"\nИли добавьте вручную по ссылке:\n{uri}\n")
    entered = input("Код из приложения (6 цифр): ")
    if not confirm_and_save(args.env_file, secret, entered):
        print("Код не подошёл, секрет не сохранён.", file=sys.stderr)
        return 1
    print("Двухфакторный вход включён. Перезапустите сайт.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
