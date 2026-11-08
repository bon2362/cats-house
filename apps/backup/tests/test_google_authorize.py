import importlib.util
import io
import json
import stat
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

PATH = Path(__file__).parents[1] / "scripts" / "google-authorize.py"
spec = importlib.util.spec_from_file_location("google_authorize", PATH)
ga = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ga)


def test_consent_url_asks_only_for_own_files_offline():
    url = urlparse(ga.build_auth_url("cid", "http://127.0.0.1:5555/", "st", "ch"))
    q = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    assert q["scope"] == ["https://www.googleapis.com/auth/drive.file"]
    assert q["access_type"] == ["offline"] and q["prompt"] == ["consent"]
    assert q["code_challenge_method"] == ["S256"] and q["code_challenge"] == ["ch"]
    assert q["state"] == ["st"] and q["redirect_uri"] == ["http://127.0.0.1:5555/"]


def test_pkce_pair_is_s256():
    import base64, hashlib
    verifier, challenge = ga.pkce_pair()
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected and len(verifier) >= 43


def test_callback_checks_state_and_errors():
    assert ga.parse_callback("/?state=st&code=abc", "st") == "abc"
    with pytest.raises(ValueError, match="state"):
        ga.parse_callback("/?state=other&code=abc", "st")
    with pytest.raises(ValueError, match="access_denied"):
        ga.parse_callback("/?state=st&error=access_denied", "st")


class Opener:
    def __init__(self, payload):
        self.payload = payload
        self.request = None

    def __call__(self, request, timeout):
        self.request = request
        return io.BytesIO(json.dumps(self.payload).encode())


def test_exchange_returns_refresh_token_and_sends_verifier():
    opener = Opener({"access_token": "a", "refresh_token": "r-token"})
    token = ga.exchange_code("code", "cid", "csecret", "http://127.0.0.1:1/", "verifier",
                             token_url="https://oauth2.googleapis.com/token", opener=opener)
    assert token == "r-token"
    form = parse_qs(opener.request.data.decode())
    assert form["code_verifier"] == ["verifier"] and form["grant_type"] == ["authorization_code"]


def test_exchange_without_refresh_token_fails():
    with pytest.raises(RuntimeError, match="refresh"):
        ga.exchange_code("code", "cid", "cs", "http://127.0.0.1:1/", "v",
                         token_url="https://x/token", opener=Opener({"access_token": "a"}))


def test_env_file_is_private(tmp_path):
    out = tmp_path / "dir" / "backup-google.env"
    ga.save_env(out, "cid", "csecret", "r-token")
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert stat.S_IMODE(out.parent.stat().st_mode) == 0o700
    assert out.read_text().splitlines() == [
        "GOOGLE_CLIENT_ID=cid", "GOOGLE_CLIENT_SECRET=csecret", "GOOGLE_REFRESH_TOKEN=r-token"]


def test_wait_for_code_ignores_other_browser_requests():
    import threading
    import urllib.request
    from http.server import BaseHTTPRequestHandler, HTTPServer

    server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def browser():
        for path in ("/favicon.ico", "/?state=st&code=the-code"):
            try:
                urllib.request.urlopen(base + path, timeout=5).read()
            except Exception:
                pass

    thread = threading.Thread(target=browser)
    thread.start()
    try:
        assert ga.wait_for_code(server, "st") == "the-code"
    finally:
        thread.join()
        server.server_close()
