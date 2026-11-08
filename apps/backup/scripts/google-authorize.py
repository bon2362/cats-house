#!/usr/bin/env python3
"""Разово выдать сервису копий доступ к своим файлам в Google Drive.

python3 apps/backup/scripts/google-authorize.py <client_secret.json> [--out <файл>]

Открывает страницу согласия Google, принимает ответ на 127.0.0.1 и записывает
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET и GOOGLE_REFRESH_TOKEN в файл (права 600).
Ключи на экран не выводятся.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCOPE = "https://www.googleapis.com/auth/drive.file"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_OUT = Path("~/.config/cats-house/backup-google.env").expanduser()


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def build_auth_url(client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })


def parse_callback(path: str, expected_state: str) -> str:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
    if query.get("state") != [expected_state]:
        raise ValueError("ответ Google не прошёл проверку state")
    if "error" in query:
        raise ValueError("Google отказал: " + query["error"][0])
    if "code" not in query:
        raise ValueError("в ответе Google нет кода")
    return query["code"][0]


def exchange_code(code: str, client_id: str, client_secret: str, redirect_uri: str, verifier: str, *,
                  token_url: str = TOKEN_URL, opener=urllib.request.urlopen) -> str:
    form = urllib.parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri,
        "grant_type": "authorization_code", "code_verifier": verifier,
    }).encode()
    request = urllib.request.Request(token_url, data=form, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    result = json.loads(opener(request, timeout=30).read())
    token = result.get("refresh_token")
    if not token:
        raise RuntimeError("Google не выдал refresh token — отзовите доступ приложения в аккаунте Google и повторите")
    return token


def save_env(path: Path, client_id: str, client_secret: str, refresh_token: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"GOOGLE_CLIENT_ID={client_id}\nGOOGLE_CLIENT_SECRET={client_secret}\n"
                     f"GOOGLE_REFRESH_TOKEN={refresh_token}\n")
    os.chmod(path, 0o600)


def wait_for_code(server: HTTPServer, state: str) -> str:
    holder: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if urllib.parse.urlparse(self.path).path != "/":
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            try:
                holder["code"] = parse_callback(self.path, state)
                text = "Готово. Окно можно закрыть."
            except ValueError as error:
                holder["error"] = error
                text = f"Не получилось: {error}"
            data = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server.RequestHandlerClass = Handler
    while "code" not in holder and "error" not in holder:
        server.handle_request()
    if "error" in holder:
        raise holder["error"]  # type: ignore[misc]
    return holder["code"]  # type: ignore[return-value]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Выдать сервису копий доступ к Google Drive")
    parser.add_argument("client_secret", type=Path, help="JSON OAuth-клиента (Desktop app) из Google Cloud")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    installed = json.loads(args.client_secret.read_text(encoding="utf-8"))["installed"]
    client_id, client_secret = installed["client_id"], installed["client_secret"]
    server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}/"
    state = secrets.token_urlsafe(24)
    verifier, challenge = pkce_pair()
    url = build_auth_url(client_id, redirect_uri, state, challenge)
    print("Открываю страницу Google. Если браузер не открылся, откройте адрес вручную:\n" + url)
    webbrowser.open(url)
    try:
        code = wait_for_code(server, state)
        token = exchange_code(code, client_id, client_secret, redirect_uri, verifier)
    except (ValueError, RuntimeError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    finally:
        server.server_close()
    save_env(args.out, client_id, client_secret, token)
    print(f"Ключи сохранены в {args.out} (права 600). На экран они не выводились.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
