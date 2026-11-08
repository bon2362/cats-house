import importlib.util
import io
from pathlib import Path

from drive_backup.endpoint import handle

from .test_settings import full_env

AUTH = "Bearer cron-secret-value-0123456789"


class Pings:
    def __init__(self):
        self.ok, self.failed = [], []

    def success(self, url):
        self.ok.append(url)
        return True

    def failure(self, url, message):
        self.failed.append((url, message))
        return True


def call(authorization, env, runner):
    pings = Pings()
    status, body = handle(authorization, env, runner=runner, success=pings.success, failure=pings.failure)
    return status, body, pings


def never(settings):
    raise AssertionError("должно было не дойти до копии")


def test_missing_or_wrong_secret_is_401_without_running():
    for header in (None, "", "Bearer wrong", "cron-secret-value-0123456789"):
        status, body, pings = call(header, full_env(), never)
        assert status == 401
        assert pings.ok == pings.failed == []


def test_success_returns_result_and_pings():
    status, body, pings = call(AUTH, full_env(), lambda s: {"file": "f.dump", "size": 1, "kept": 1, "trashed": []})
    assert status == 200 and body["file"] == "f.dump"
    assert pings.ok == ["https://hc-ping.com/abc-uuid"] and pings.failed == []


def test_failure_is_500_redacted_and_reported():
    def boom(settings):
        raise RuntimeError("pg_dump: error: postgresql://u:p%40ss-word@h/db failed, token refresh-token-value")

    status, body, pings = call(AUTH, full_env(), boom)
    assert status == 500
    for secret in ("p%40ss-word", "refresh-token-value", "postgresql://"):
        assert secret not in body["error"]
        assert secret not in pings.failed[0][1]
    assert pings.ok == []


def test_missing_settings_report_names_only():
    env = full_env(GOOGLE_REFRESH_TOKEN="")
    status, body, pings = call(AUTH, env, never)
    assert status == 500
    assert "GOOGLE_REFRESH_TOKEN" in body["error"]
    assert pings.failed and pings.failed[0][0] == "https://hc-ping.com/abc-uuid"


def test_missing_cron_secret_fails_closed():
    status, body, pings = call("Bearer ", full_env(CRON_SECRET=""), never)
    assert status == 500
    assert "CRON_SECRET" in body["error"]


def test_vercel_entry_answers_401_without_secret(monkeypatch):
    path = Path(__file__).parents[1] / "api" / "index.py"
    spec = importlib.util.spec_from_file_location("vercel_entry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("CRON_SECRET", "x" * 32)

    request = io.BytesIO(b"GET /api/backup HTTP/1.1\r\nHost: test\r\n\r\n")
    response = io.BytesIO()

    class Socket:
        def makefile(self, mode, *args, **kwargs):
            return request if "r" in mode else response

        def sendall(self, data):
            response.write(data)

    module.handler(Socket(), ("127.0.0.1", 1), None)
    assert response.getvalue().startswith(b"HTTP/1.0 401")


def test_large_copy_is_saved_but_owner_is_warned():
    result = {"file": "f.dump", "size": 310 * 1024 * 1024, "kept": 5, "trashed": []}
    status, body, pings = call(AUTH, full_env(), lambda s: result)
    assert status == 200 and body == result
    assert pings.ok == []
    assert len(pings.failed) == 1
    assert "сохранена" in pings.failed[0][1] and "310 МБ" in pings.failed[0][1]


def test_normal_copy_is_not_a_warning():
    status, body, pings = call(AUTH, full_env(), lambda s: {"file": "f", "size": 299 * 1024 * 1024, "kept": 1, "trashed": []})
    assert pings.ok and not pings.failed
