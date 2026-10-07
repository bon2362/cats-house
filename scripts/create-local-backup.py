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
from app.exports.service import build_archive, export_gedcom, media_contents


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
        # Files live in the database; each one is written next to the JSON and referenced from the manifest.
        media_dir = args.output / f"cats-house-{stamp}-media"
        manifest = {item["archive_id"]: item for item in archive["media_manifest"]}
        for archive_id, content in media_contents(session):
            media_dir.mkdir(exist_ok=True)
            filename = f"{archive_id}.bin"
            (media_dir / filename).write_bytes(content)
            manifest[archive_id]["backup_file"] = f"{media_dir.name}/{filename}"
        (args.output / f"cats-house-{stamp}.json").write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output / f"cats-house-{stamp}.ged").write_bytes(export_gedcom(session))
    print(f"Создана копия: {stamp}; люди: {archive['counts']['people']}; события: {archive['counts']['events']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
