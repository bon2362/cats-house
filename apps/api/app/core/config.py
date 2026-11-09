from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlparse

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Обязательные настройки собственного API Cat's House."""

    model_config = SettingsConfigDict(
        env_prefix="CATS_HOUSE_",
        case_sensitive=False,
        extra="forbid",
    )

    database_url: str
    owner_email: str
    owner_password_hash: SecretStr
    owner_totp_secret: SecretStr | None = None
    session_secret: SecretStr
    environment: Literal["development", "production"]
    # Folder of the built web app; when set the API also serves the pages (public launch).
    web_dist: Path | None = None
    # Public launch behind the tunnel: trust its visitor-address header and limit request rates.
    public_mode: bool = False
    # The trusted reverse-proxy environment, if any.
    deployment: Literal["local", "tunnel", "vercel"] = "local"

    @field_validator("database_url", mode="before")
    @classmethod
    def standard_postgres_url_uses_psycopg(cls, value: str) -> str:
        """Accept Neon URLs while using the project's installed PostgreSQL driver."""
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @field_validator("owner_password_hash")
    @classmethod
    def password_hash_must_use_argon2(cls, value: SecretStr) -> SecretStr:
        password_hash = value.get_secret_value()
        # Docker Compose escapes a literal dollar as `$$`; accept a hash copied from .env directly to hosting.
        if password_hash.startswith("$$argon2"):
            password_hash = password_hash[1:]
        if not password_hash.startswith("$argon2"):
            raise ValueError("Хеш пароля владельца должен быть в формате Argon2.")
        return SecretStr(password_hash)

    @field_validator("session_secret")
    @classmethod
    def session_secret_must_be_long_enough(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32:
            raise ValueError("Секрет сессии должен содержать не менее 32 символов.")
        if secret.startswith("replace-this-"):
            raise ValueError("Замените пример секрета сессии уникальным значением.")
        return value

    @model_validator(mode="after")
    def vercel_database_must_use_tls(self) -> "Settings":
        if self.deployment == "vercel":
            sslmode = parse_qs(urlparse(self.database_url).query).get("sslmode", [])
            if "require" not in sslmode:
                raise ValueError("Для Vercel укажите PostgreSQL URL Neon с sslmode=require.")
        return self

    @property
    def session_cookie_secure(self) -> bool:
        return self.environment == "production"
