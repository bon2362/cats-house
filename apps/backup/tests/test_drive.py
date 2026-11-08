import hashlib

import pytest

from drive_backup.drive import FOLDER_NAME, DriveError

from .fake_drive import FakeDrive


@pytest.fixture
def drive():
    with FakeDrive() as fake:
        yield fake


def test_creates_marked_folder_once(drive):
    client = drive.client()
    first = client.find_or_create_folder()
    second = client.find_or_create_folder()
    assert first == second
    assert drive.files[first]["name"] == FOLDER_NAME
    assert drive.files[first]["appProperties"] == {"cats_house_backups": "1"}


def test_upload_reports_matching_checksum(drive, tmp_path):
    client = drive.client()
    folder = client.find_or_create_folder()
    path = tmp_path / "cats-house-2026-11-09T0200Z.dump"
    path.write_bytes(b"dump-bytes" * 1000)
    file_id = client.upload(folder, path, path.name)
    info = client.file_info(file_id)
    assert info["md5Checksum"] == hashlib.md5(path.read_bytes()).hexdigest()
    assert drive.live_names(folder) == [path.name]


def test_list_and_trash(drive, tmp_path):
    client = drive.client()
    folder = client.find_or_create_folder()
    path = tmp_path / "a.dump"
    path.write_bytes(b"a")
    file_id = client.upload(folder, path, "a.dump")
    assert [f["name"] for f in client.list_files(folder)] == ["a.dump"]
    client.trash(file_id)
    assert client.list_files(folder) == []
    assert drive.files[file_id]["trashed"] is True


def test_revoked_refresh_token_gives_clear_error(drive):
    with pytest.raises(DriveError, match="ключ доступа Google не действует"):
        drive.client(refresh_token="revoked").find_or_create_folder()


def test_failed_upload_raises(drive, tmp_path):
    client = drive.client()
    folder = client.find_or_create_folder()
    drive.fail_upload = True
    path = tmp_path / "a.dump"
    path.write_bytes(b"a")
    with pytest.raises(DriveError, match="503"):
        client.upload(folder, path, "a.dump")


def test_unreachable_google_raises_drive_error(tmp_path):
    from drive_backup.drive import DriveClient
    client = DriveClient("id", "secret", "token", token_url="http://127.0.0.1:9/token",
                         api_url="http://127.0.0.1:9/drive/v3", upload_url="http://127.0.0.1:9/upload/drive/v3", timeout=2)
    with pytest.raises(DriveError, match="недоступен"):
        client.find_or_create_folder()
