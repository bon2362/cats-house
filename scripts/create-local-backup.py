#!/usr/bin/env python3
"""Создать локальный GEDCOM и полный JSON-архив Cat's House."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.core.config import Settings
from app.db.session import create_session_factory
from app.exports.service import build_archive, export_gedcom
from app.media.service import S3MediaStorage


def main() -> int:
    parser = argparse.ArgumentParser(description="Локальная резервная копия Cat's House")
    parser.add_argument("--output", required=True, type=Path, help="Абсолютный каталог для копии")
    args = parser.parse_args()
    if not args.output.is_absolute():
        parser.error("Укажите абсолютный каталог для резервной копии.")
    args.output.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    settings = Settings()
    with create_session_factory(settings.database_url)() as session:
        archive = build_archive(session)
        storage = S3MediaStorage(settings)
        media_dir = args.output / f"cats-house-{stamp}-media"
        for item in archive["media_manifest"]:
            media_dir.mkdir(exist_ok=True)
            filename = f"{item['archive_id']}.bin"
            (media_dir / filename).write_bytes(storage.get(item["storage_key"]))
            item["backup_file"] = f"{media_dir.name}/{filename}"
        (args.output / f"cats-house-{stamp}.json").write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output / f"cats-house-{stamp}.ged").write_bytes(export_gedcom(session))
    print(f"Создана копия: {stamp}; люди: {archive['counts']['people']}; события: {archive['counts']['events']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
