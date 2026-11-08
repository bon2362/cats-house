import importlib.util
from pathlib import Path

import psycopg

from .conftest import media_digests

PATH = Path(__file__).parents[1] / "scripts" / "restore-backup.py"
spec = importlib.util.spec_from_file_location("restore_backup", PATH)
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)


def test_needs_target_url_from_environment(dump_file, capsys):
    assert rb.main([str(dump_file)], {}) == 2
    assert "CATS_HOUSE_RESTORE_DATABASE_URL" in capsys.readouterr().err


def test_restores_into_empty_database_and_refuses_a_second_time(dump_file, source_db, capsys):
    base = source_db["url"].split("?")[0]
    with psycopg.connect(base, autocommit=True) as conn:
        conn.execute("create database restore_target")
    target = source_db["url"].replace("/test?", "/restore_target?")
    assert rb.main([str(dump_file)], {"CATS_HOUSE_RESTORE_DATABASE_URL": target}) == 0
    assert media_digests(target.split("?")[0]) == media_digests(base)
    assert rb.main([str(dump_file)], {"CATS_HOUSE_RESTORE_DATABASE_URL": target}) == 1
    err = capsys.readouterr().err
    assert "не пустая" in err
    assert "test@" not in err and "postgresql://" not in err
