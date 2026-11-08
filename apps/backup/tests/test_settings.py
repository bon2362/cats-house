import pytest

from drive_backup.settings import REQUIRED, SettingsError, load_settings

URL = "postgresql://cats_house_backup:p%40ss-word@ep-test.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"


def full_env(**overrides):
    env = {
        "BACKUP_DATABASE_URL": URL,
        "GOOGLE_CLIENT_ID": "client-id.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "client-secret-value",
        "GOOGLE_REFRESH_TOKEN": "refresh-token-value",
        "HEALTHCHECK_URL": "https://hc-ping.com/abc-uuid",
        "CRON_SECRET": "cron-secret-value-0123456789",
    }
    env.update(overrides)
    return env


def test_loads_all_settings():
    settings = load_settings(full_env())
    assert settings.database_url == URL
    assert settings.cron_secret == "cron-secret-value-0123456789"


def test_names_every_missing_setting_without_values():
    with pytest.raises(SettingsError) as error:
        load_settings({"GOOGLE_CLIENT_ID": "x", "CRON_SECRET": "  "})
    message = str(error.value)
    for name in REQUIRED:
        if name != "GOOGLE_CLIENT_ID":
            assert name in message
    assert "GOOGLE_CLIENT_ID" not in message


@pytest.mark.parametrize("query", ["", "?sslmode=prefer", "?sslmode=disable"])
def test_rejects_database_url_without_tls(query):
    url = "postgresql://u:p@ep-test.neon.tech/neondb" + query
    with pytest.raises(SettingsError, match="sslmode=require"):
        load_settings(full_env(BACKUP_DATABASE_URL=url))


def test_rejects_non_postgres_url():
    with pytest.raises(SettingsError, match="PostgreSQL"):
        load_settings(full_env(BACKUP_DATABASE_URL="https://example.test/?sslmode=require"))


def test_secret_values_include_decoded_password():
    values = load_settings(full_env()).secret_values()
    assert "p@ss-word" in values
    assert URL in values
    assert "refresh-token-value" in values
    assert "client-secret-value" in values
    assert "cron-secret-value-0123456789" in values
