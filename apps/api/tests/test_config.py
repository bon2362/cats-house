import pytest
from argon2 import PasswordHasher
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
    monkeypatch.setenv(
        "CATS_HOUSE_OWNER_PASSWORD_HASH",
        PasswordHasher().hash("test-owner-password"),
    )
    monkeypatch.setenv(
        "CATS_HOUSE_SESSION_SECRET",
        "test-session-secret-with-at-least-thirty-two-characters",
    )


def test_settings_reject_missing_database_url(monkeypatch):
    set_required_settings(monkeypatch)
    monkeypatch.delenv("CATS_HOUSE_DATABASE_URL")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_preserves_utf8_owner_email(monkeypatch):
    set_required_settings(monkeypatch)
    monkeypatch.setenv("CATS_HOUSE_OWNER_EMAIL", "владелец@example.test")

    assert Settings().owner_email == "владелец@example.test"


def test_settings_rejects_short_session_secret(monkeypatch):
    set_required_settings(monkeypatch)
    monkeypatch.setenv("CATS_HOUSE_SESSION_SECRET", "too-short")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_rejects_non_argon2_password_hash(monkeypatch):
    set_required_settings(monkeypatch)
    monkeypatch.setenv("CATS_HOUSE_OWNER_PASSWORD_HASH", "plain-text-password")

    with pytest.raises(ValidationError):
        Settings()
