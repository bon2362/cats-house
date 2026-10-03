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
    s3_endpoint: AnyHttpUrl
    s3_bucket: str
    owner_email: str
    owner_password_hash: SecretStr
    session_secret: SecretStr

    @field_validator("owner_password_hash")
    @classmethod
    def password_hash_must_use_argon2(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("$argon2"):
            raise ValueError("Хеш пароля владельца должен быть в формате Argon2.")
        return value

    @field_validator("session_secret")
    @classmethod
    def session_secret_must_be_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("Секрет сессии должен содержать не менее 32 символов.")
        return value
