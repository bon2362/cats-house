import datetime as dt

import pytest

from drive_backup.drive import DriveError
from drive_backup.job import BackupError, run_backup
from drive_backup.pgtools import DumpError
from drive_backup.settings import Settings

from .fake_drive import FakeDrive

NOW = dt.datetime(2026, 11, 9, 2, 5, tzinfo=dt.timezone.utc)


def settings_for(url):
    return Settings(url, "id", "secret", "good-refresh", "https://hc-ping.com/uuid", "cron")


@pytest.fixture
def drive():
    with FakeDrive() as fake:
        yield fake


def seed(drive, client, names):
    folder = client.find_or_create_folder()
    for name in names:
        drive.files[name] = {"id": name, "name": name, "parents": [folder], "trashed": False, "content": b"old"}
    return folder


def test_real_dump_lands_in_drive_and_old_copies_are_trashed(drive, source_db, bin_dir, tmp_path):
    client = drive.client()
    folder = seed(drive, client, ["cats-house-2026-11-08T0200Z.dump", "cats-house-2026-10-01T0200Z.dump",
                                  "cats-house-2026-10-31T0200Z.dump", "notes.txt"])
    result = run_backup(settings_for(source_db["url"]), drive=client, now=NOW, bin_dir=bin_dir, workdir=tmp_path)
    assert result["file"] == "cats-house-2026-11-09T0205Z.dump"
    assert result["size"] > 0
    assert result["trashed"] == ["cats-house-2026-10-01T0200Z.dump"]
    assert drive.live_names(folder) == ["cats-house-2026-10-31T0200Z.dump", "cats-house-2026-11-08T0200Z.dump",
                                        "cats-house-2026-11-09T0205Z.dump", "notes.txt"]
    assert result["kept"] == 3
    assert list(tmp_path.iterdir()) == []


def fake_dumper(url, target, bin_dir):
    target.write_bytes(b"fake dump")


def test_checksum_mismatch_trashes_upload_and_keeps_old_copies(drive, tmp_path):
    client = drive.client()
    old = ["cats-house-2026-01-01T0200Z.dump"]
    folder = seed(drive, client, old)
    drive.corrupt_md5 = True
    with pytest.raises(BackupError, match="не совпал"):
        run_backup(settings_for("postgresql://x"), drive=client, now=NOW, bin_dir=tmp_path, workdir=tmp_path,
                   dumper=fake_dumper, verifier=lambda path, bin_dir: None)
    assert drive.live_names(folder) == old


def test_failed_upload_prunes_nothing(drive, tmp_path):
    client = drive.client()
    old = ["cats-house-2025-01-01T0200Z.dump", "cats-house-2025-02-01T0200Z.dump"]
    folder = seed(drive, client, old)
    drive.fail_upload = True
    with pytest.raises(DriveError):
        run_backup(settings_for("postgresql://x"), drive=client, now=NOW, bin_dir=tmp_path, workdir=tmp_path,
                   dumper=fake_dumper, verifier=lambda path, bin_dir: None)
    assert drive.live_names(folder) == old


def test_failed_verification_uploads_nothing(drive, tmp_path):
    client = drive.client()
    folder = seed(drive, client, [])

    def bad_verifier(path, bin_dir):
        raise DumpError("копия неполная: нет данных таблиц media")

    with pytest.raises(DumpError):
        run_backup(settings_for("postgresql://x"), drive=client, now=NOW, bin_dir=tmp_path, workdir=tmp_path,
                   dumper=fake_dumper, verifier=bad_verifier)
    assert drive.live_names(folder) == []
    assert list(tmp_path.iterdir()) == []


def test_unverifiable_upload_is_trashed(drive, tmp_path):
    client = drive.client()
    old = ["cats-house-2026-01-01T0200Z.dump"]
    folder = seed(drive, client, old)
    drive.fail_info = True
    with pytest.raises(DriveError):
        run_backup(settings_for("postgresql://x"), drive=client, now=NOW, bin_dir=tmp_path, workdir=tmp_path,
                   dumper=fake_dumper, verifier=lambda path, bin_dir: None)
    assert drive.live_names(folder) == old
