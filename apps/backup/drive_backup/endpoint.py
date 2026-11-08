"""Проверка секрета, запуск, ответ и сигналы сторожу."""

from __future__ import annotations

import datetime as dt
import hmac
import tempfile
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import unquote, urlparse

from drive_backup.drive import DriveClient
from drive_backup.health import ping_fail, ping_success
from drive_backup.job import run_backup
from drive_backup.pgtools import ensure_binaries
from drive_backup.redact import redact
from drive_backup.settings import REQUIRED, Settings, load_settings


def default_runner(settings: Settings) -> dict:
    bin_dir = ensure_binaries()
    drive = DriveClient(settings.google_client_id, settings.google_client_secret, settings.google_refresh_token)
    with tempfile.TemporaryDirectory() as workdir:
        return run_backup(settings, drive=drive, now=dt.datetime.now(dt.timezone.utc),
                          bin_dir=bin_dir, workdir=Path(workdir))


def _secrets(env: Mapping[str, str]) -> list[str]:
    values = [(env.get(name) or "").strip() for name in REQUIRED]
    password = unquote(urlparse((env.get("BACKUP_DATABASE_URL") or "").strip()).password or "")
    return [v for v in values + [password, password and password.replace("@", "%40")] if v]


def handle(authorization: Optional[str], env: Mapping[str, str], *, runner=None,
           success=ping_success, failure=ping_fail) -> tuple[int, dict]:
    healthcheck = (env.get("HEALTHCHECK_URL") or "").strip()
    expected = (env.get("CRON_SECRET") or "").strip()
    if not expected:
        message = "Не задана настройка CRON_SECRET."
        if healthcheck:
            failure(healthcheck, message)
        return 500, {"error": message}
    if not authorization or not hmac.compare_digest(authorization.encode(), f"Bearer {expected}".encode()):
        return 401, {"error": "Нет доступа."}
    try:
        settings = load_settings(env)
        result = (runner or default_runner)(settings)
    except Exception as error:  # noqa: BLE001 — любая ошибка должна дойти до сторожа
        message = redact(str(error) or error.__class__.__name__, _secrets(env))
        if healthcheck:
            failure(healthcheck, message)
        return 500, {"error": message}
    success(settings.healthcheck_url)
    return 200, result
