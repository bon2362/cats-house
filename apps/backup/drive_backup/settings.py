"""Настройки сервиса копий: только из переменных окружения."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import parse_qs, unquote, urlparse

REQUIRED = (
    "BACKUP_DATABASE_URL",
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    "HEALTHCHECK_URL",
    "CRON_SECRET",
)
STRICT_SSL = {"require", "verify-ca", "verify-full"}


class SettingsError(Exception):
    """Настройка отсутствует или неверна; текст без значений."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    google_client_id: str
    google_client_secret: str
    google_refresh_token: str
    healthcheck_url: str
    cron_secret: str

    def secret_values(self) -> list[str]:
        password = unquote(urlparse(self.database_url).password or "")
        values = [self.database_url, password, self.google_client_secret,
                  self.google_refresh_token, self.healthcheck_url, self.cron_secret]
        return [v for v in values if v]


def load_settings(env: Mapping[str, str]) -> Settings:
    values = {name: (env.get(name) or "").strip() for name in REQUIRED}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SettingsError("Не заданы настройки: " + ", ".join(missing) + ".")
    url = values["BACKUP_DATABASE_URL"]
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql") or not parsed.hostname:
        raise SettingsError("BACKUP_DATABASE_URL должен быть адресом PostgreSQL (postgresql://…).")
    if not set(parse_qs(parsed.query).get("sslmode", [])) & STRICT_SSL:
        raise SettingsError("BACKUP_DATABASE_URL должен содержать sslmode=require.")
    return Settings(
        database_url=url,
        google_client_id=values["GOOGLE_CLIENT_ID"],
        google_client_secret=values["GOOGLE_CLIENT_SECRET"],
        google_refresh_token=values["GOOGLE_REFRESH_TOKEN"],
        healthcheck_url=values["HEALTHCHECK_URL"],
        cron_secret=values["CRON_SECRET"],
    )
