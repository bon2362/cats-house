"""Write the owner password hash into a .env file used by docker compose and dev-native.sh."""

import os
import re
import tempfile
from pathlib import Path

OWNER_PASSWORD_KEY = "CATS_HOUSE_OWNER_PASSWORD_HASH"
MIN_PASSWORD_LENGTH = 12


def validate_new_password(first: str, second: str) -> None:
    if first != second:
        raise ValueError("Пароли не совпадают.")
    if len(first) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Пароль должен содержать не менее {MIN_PASSWORD_LENGTH} символов.")


LINE = re.compile(r"[^\r\n]*(?:\r\n|\n|\r)|[^\r\n]+$")


def write_env_value(path: Path, key: str, value: str) -> None:
    """Replace (or append) `key=value`, `$` doubled as docker compose expects.

    Every other byte of the file is kept, including line endings. The new
    content is written to a temporary file and moved over the original in one
    step, so an interruption never leaves a truncated .env.
    """
    entry = f"{key}={value.replace('$', '$$')}"
    content = path.read_bytes().decode("utf-8") if path.exists() else ""
    lines, replaced = [], False
    for line in LINE.findall(content):
        body = line.rstrip("\r\n")
        if body.startswith(f"{key}="):
            if not replaced:
                lines.append(entry + line[len(body):])
                replaced = True
            continue
        lines.append(line)
    if not replaced:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += "\n"
        lines.append(entry + "\n")

    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write("".join(lines).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
