"""Turn the owner's two-factor sign-in on or off by writing the secret into .env."""

import base64
import os
import secrets
import tempfile
from pathlib import Path
from urllib.parse import quote, urlencode

from app.auth.password_file import LINE, write_env_value
from app.auth.service import verify_totp

TOTP_KEY = "CATS_HOUSE_OWNER_TOTP_SECRET"
ISSUER = "Cat's House"


def new_secret() -> str:
    """160 random bits in base32, as authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def otpauth_uri(secret: str, email: str) -> str:
    label = quote(f"{ISSUER}:{email}", safe=":")
    return f"otpauth://totp/{label}?{urlencode({'secret': secret, 'issuer': ISSUER})}"


def confirm_and_save(env_file: Path, secret: str, code: str) -> bool:
    """Write the secret only when the code from the app is right, so a typo cannot lock the owner out."""
    if not verify_totp(code.strip(), secret):
        return False
    write_env_value(env_file, TOTP_KEY, secret)
    return True


def remove_secret(env_file: Path) -> None:
    content = env_file.read_bytes().decode("utf-8")
    kept = "".join(line for line in LINE.findall(content) if not line.startswith(f"{TOTP_KEY}="))
    mode = env_file.stat().st_mode & 0o777
    descriptor, temporary = tempfile.mkstemp(dir=env_file.parent, prefix=f".{env_file.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(kept.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, env_file)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
