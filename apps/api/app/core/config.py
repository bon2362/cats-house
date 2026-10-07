from typing import Literal

from pydantic import AnyHttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Обязательные настройки собственного API Cat's House."""

    model_config = SettingsConfigDict(
        env_prefix="CATS_HOUSE_",
        case_sensitive=False,
        extra="forbid",
    )

    database_url: str
    # Files are stored in the database since stage 4; kept optional so old .env files still load.
    s3_endpoint: AnyHttpUrl | None = None
    s3_bucket: str | None = None
    owner_email: str
    owner_password_hash: SecretStr
    owner_totp_secret: SecretStr | None = None
    session_secret: SecretStr
    environment: Literal["development", "production"]

    @field_validator("owner_password_hash")
    @classmethod
    def password_hash_must_use_argon2(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("$argon2"):
            raise ValueError("Хеш пароля владельца должен быть в формате Argon2.")
        return value

    @field_validator("session_secret")
    @classmethod
    def session_secret_must_be_long_enough(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32:
            raise ValueError("Секрет сессии должен содержать не менее 32 символов.")
        if secret.startswith("replace-this-"):
            raise ValueError("Замените пример секрета сессии уникальным значением.")
        return value

    @property
    def session_cookie_secure(self) -> bool:
        return self.environment == "production"
