import subprocess

import psycopg
import pytest

from drive_backup.pgtools import DumpError, dump, pg_environment, verify_dump

from .conftest import create_schema, media_digests


def test_unpacked_tools_are_postgres_17(bin_dir):
    for name in ("pg_dump", "pg_restore"):
        out = subprocess.run([str(bin_dir / name), "--version"], capture_output=True, text=True, check=True).stdout
        assert "17.11" in out


def test_environment_carries_connection_without_url():
    env = pg_environment(
        "postgresql://reader:p%40ss@ep-x.neon.tech:5433/neondb?sslmode=require&channel_binding=require", base={}
    )
    assert env == {
        "PGHOST": "ep-x.neon.tech", "PGPORT": "5433", "PGUSER": "reader", "PGPASSWORD": "p@ss",
        "PGDATABASE": "neondb", "PGSSLMODE": "require", "PGCHANNELBINDING": "require", "PGCONNECT_TIMEOUT": "15",
    }


def test_dump_restores_files_byte_for_byte(source_db, dump_file, bin_dir):
    verify_dump(dump_file, bin_dir)
    restored_url = source_db["url"].replace("/test?", "/restored?")
    subprocess.run(
        [str(bin_dir / "pg_restore"), "--no-owner", "--no-privileges", "--exit-on-error", "--dbname", "restored",
         str(dump_file)],
        env=pg_environment(restored_url), check=True, capture_output=True,
    )
    assert media_digests(restored_url.split("?")[0]) == media_digests(source_db["url"].split("?")[0])
    with psycopg.connect(restored_url.split("?")[0]) as conn:
        assert conn.execute("select full_name from people order by id").fetchall() == [("Тестова Анна",), ("Тестов Пётр",)]


def test_dump_without_media_table_is_rejected(source_db, bin_dir, tmp_path):
    url = source_db["url"].replace("/test?", "/no_media?")
    with psycopg.connect(url.split("?")[0], autocommit=True) as conn:
        create_schema(conn, with_media=False)
    target = tmp_path / "partial.dump"
    dump(url, target, bin_dir)
    with pytest.raises(DumpError, match="media"):
        verify_dump(target, bin_dir)


def test_garbage_file_is_rejected(bin_dir, tmp_path):
    bad = tmp_path / "bad.dump"
    bad.write_bytes(b"not a dump")
    with pytest.raises(DumpError, match="не читается"):
        verify_dump(bad, bin_dir)


class FakeRun:
    def __init__(self, codes):
        self.codes = list(codes)
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, self.codes.pop(0), "", "pg_dump: error: connection to server failed\n")


URL = "postgresql://reader:very-secret@ep-x.neon.tech/neondb?sslmode=require"


def test_dump_retries_once_and_keeps_url_out_of_arguments(tmp_path):
    run, waits = FakeRun([1, 0]), []
    dump(URL, tmp_path / "x.dump", tmp_path, run=run, sleep=waits.append)
    assert waits == [10]
    assert len(run.calls) == 2
    for cmd, kwargs in run.calls:
        assert not any("very-secret" in part or "neon.tech" in part for part in cmd)
        assert kwargs["env"]["PGPASSWORD"] == "very-secret"


def test_dump_fails_after_second_attempt_with_last_error_line(tmp_path):
    with pytest.raises(DumpError, match="connection to server failed"):
        dump(URL, tmp_path / "x.dump", tmp_path, run=FakeRun([1, 1]), sleep=lambda _: None)
