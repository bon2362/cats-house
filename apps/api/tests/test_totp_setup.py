import base64
from urllib.parse import parse_qs, urlparse

from app.auth.service import totp_code
from app.auth.totp_setup import TOTP_KEY, confirm_and_save, new_secret, otpauth_uri, remove_secret


def test_secret_is_160_bit_base32():
    secret = new_secret()
    assert len(base64.b32decode(secret)) == 20 and secret != new_secret()


def test_otpauth_uri_names_the_site_and_owner():
    uri = urlparse(otpauth_uri("JBSWY3DPEHPK3PXP", "owner@example.test"))
    assert (uri.scheme, uri.netloc) == ("otpauth", "totp")
    assert uri.path == "/Cat%27s%20House:owner%40example.test"
    assert parse_qs(uri.query) == {"secret": ["JBSWY3DPEHPK3PXP"], "issuer": ["Cat's House"]}


def test_secret_is_saved_only_after_a_correct_code(tmp_path):
    env = tmp_path / ".env"
    env.write_text("CATS_HOUSE_OWNER_EMAIL=owner@example.test\n")
    secret = new_secret()
    wrong = "000000" if totp_code(secret) != "000000" else "111111"

    assert confirm_and_save(env, secret, wrong) is False
    assert TOTP_KEY not in env.read_text()
    assert confirm_and_save(env, secret, totp_code(secret)) is True
    assert f"{TOTP_KEY}={secret}\n" in env.read_text()

    remove_secret(env)
    assert env.read_text() == "CATS_HOUSE_OWNER_EMAIL=owner@example.test\n"
