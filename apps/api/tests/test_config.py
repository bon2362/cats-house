import pytest
from pydantic import ValidationError

from app.core.config import Settings


def set_required_settings(monkeypatch):
    monkeypatch.setenv(
        "CATS_HOUSE_DATABASE_URL",
        "postgresql+psycopg://cats_house:password@localhost:5432/cats_house",
    )
    monkeypatch.setenv("CATS_HOUSE_S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("CATS_HOUSE_S3_BUCKET", "cats-house-media")
    monkeypatch.setenv("CATS_HOUSE_OWNER_EMAIL", "owner@example.test")


def test_settings_reject_missing_database_url(monkeypatch):
    set_required_settings(monkeypatch)
    monkeypatch.delenv("CATS_HOUSE_DATABASE_URL")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_preserves_utf8_owner_email(monkeypatch):
    set_required_settings(monkeypatch)
    monkeypatch.setenv("CATS_HOUSE_OWNER_EMAIL", "владелец@example.test")

    assert Settings().owner_email == "владелец@example.test"
