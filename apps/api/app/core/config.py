from pydantic import AnyHttpUrl
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
