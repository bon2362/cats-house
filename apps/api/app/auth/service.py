import base64
import hashlib
import hmac
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from pydantic import SecretStr

password_hasher = PasswordHasher()


def verify_owner_password(password: str, password_hash: SecretStr) -> bool:
    try:
        return password_hasher.verify(password_hash.get_secret_value(), password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def totp_code(secret: str, timestamp: int | None = None) -> str:
    counter = int((timestamp if timestamp is not None else time.time()) // 30)
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def verify_totp(code: str | None, secret: str, timestamp: int | None = None) -> bool:
    if not code or not code.isdigit() or len(code) != 6:
        return False
    moment = timestamp if timestamp is not None else int(time.time())
    return any(hmac.compare_digest(code, totp_code(secret, moment + offset * 30)) for offset in (-1, 0, 1))
