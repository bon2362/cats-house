"""pg_dump и pg_restore из пакета postgresql-binaries."""

from __future__ import annotations

import os
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Mapping, Optional
from urllib.parse import parse_qs, unquote, urlparse

REQUIRED_TABLES = ("people", "unions", "parent_children", "events", "media")


class DumpError(Exception):
    """Копия не снялась или не прошла проверку."""


def ensure_binaries(target: Path = Path("/tmp/pg")) -> Path:
    """Unpack the PostgreSQL tools of the installed package (once) and return their bin directory.

    The directory is named after the package archive, so tools of another version unpacked into the
    same target are never picked up by mistake.
    """
    import postgresql_binaries

    archive = next(Path(postgresql_binaries.__file__).parent.glob("*.tar.gz"))
    bin_dir = Path(target) / archive.name.removesuffix(".tar.gz") / "bin"
    if not (bin_dir / "pg_dump").exists():
        Path(target).mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            tar.extractall(target, filter="data")
    if not (bin_dir / "pg_dump").exists():
        raise DumpError(f"в пакете postgresql-binaries нет {bin_dir.name}/pg_dump")
    for name in ("pg_dump", "pg_restore", "psql"):
        tool = bin_dir / name
        if tool.exists():
            tool.chmod(0o755)
    return bin_dir


def pg_environment(url: str, base: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    env = dict(os.environ if base is None else base)
    env.update({
        "PGHOST": parsed.hostname or "",
        "PGPORT": str(parsed.port or 5432),
        "PGUSER": unquote(parsed.username or ""),
        "PGPASSWORD": unquote(parsed.password or ""),
        "PGDATABASE": unquote(parsed.path.lstrip("/")),
        "PGSSLMODE": query.get("sslmode", ["prefer"])[0],
        "PGCONNECT_TIMEOUT": "15",
    })
    if "channel_binding" in query:
        env["PGCHANNELBINDING"] = query["channel_binding"][0]
    return env


def _last_line(text: str) -> str:
    lines = [line for line in (text or "").strip().splitlines() if line.strip()]
    return lines[-1] if lines else "без описания"


def dump(url: str, target: Path, bin_dir: Path, *, run=subprocess.run, sleep=time.sleep, retry_delay: float = 10) -> None:
    cmd = [str(Path(bin_dir) / "pg_dump"), "--format=custom", "--no-owner", "--no-privileges", "--file", str(target)]
    env = pg_environment(url)
    result = None
    for attempt in (1, 2):
        result = run(cmd, env=env, capture_output=True, text=True, timeout=240)
        if result.returncode == 0:
            return
        if attempt == 1:
            sleep(retry_delay)
    raise DumpError("pg_dump завершился с ошибкой: " + _last_line(result.stderr))


def verify_dump(path: Path, bin_dir: Path, *, run=subprocess.run) -> None:
    result = run([str(Path(bin_dir) / "pg_restore"), "--list", str(path)], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise DumpError("копия не читается: " + _last_line(result.stderr))
    present = set()
    for line in result.stdout.splitlines():
        if " TABLE DATA " in line:
            parts = line.split(" TABLE DATA ", 1)[1].split()
            if len(parts) >= 2:
                present.add(parts[1])
    missing = [table for table in REQUIRED_TABLES if table not in present]
    if missing:
        raise DumpError("копия неполная: нет данных таблиц " + ", ".join(missing))
