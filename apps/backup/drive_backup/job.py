"""Один запуск: копия → проверка → Drive → сверка → хранение."""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path

from drive_backup import pgtools
from drive_backup.retention import backup_name, names_to_trash
from drive_backup.settings import Settings


class BackupError(Exception):
    """Запуск не удался по причине, найденной самим сервисом."""


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_backup(settings: Settings, *, drive, now: dt.datetime, bin_dir: Path, workdir: Path,
               dumper=pgtools.dump, verifier=pgtools.verify_dump) -> dict:
    name = backup_name(now)
    target = Path(workdir) / name
    try:
        dumper(settings.database_url, target, bin_dir)
        verifier(target, bin_dir)
        size = target.stat().st_size
        local_md5 = _md5(target)
        folder = drive.find_or_create_folder()
        file_id = drive.upload(folder, target, name)
        if drive.file_info(file_id).get("md5Checksum") != local_md5:
            drive.trash(file_id)
            raise BackupError("файл в Google Drive не совпал с копией — загрузка отменена")
        files = drive.list_files(folder)
        to_trash = set(names_to_trash([f["name"] for f in files], now.astimezone(dt.timezone.utc).date()))
        trashed = []
        for item in files:
            if item["name"] in to_trash:
                drive.trash(item["id"])
                trashed.append(item["name"])
        kept = sum(1 for f in files if f["name"].startswith("cats-house-") and f["name"] not in to_trash)
        return {"file": name, "size": size, "kept": kept, "trashed": sorted(trashed)}
    finally:
        target.unlink(missing_ok=True)
