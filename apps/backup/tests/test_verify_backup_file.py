import importlib.util
from pathlib import Path

PATH = Path(__file__).parents[1] / "scripts" / "verify-backup-file.py"
spec = importlib.util.spec_from_file_location("verify_backup_file", PATH)
vbf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vbf)


def test_compare_lists_differences():
    assert vbf.compare({"public.people": "2", "media:sha256": "a"}, {"public.people": "3", "media:sha256": "a"}) == ["public.people"]
    assert vbf.compare({"x": "1"}, {"x": "1", "y": "0"}) == ["y"]


def test_collect_counts_rows_and_hashes_media(source_db, bin_dir):
    stats = vbf.collect(bin_dir, source_db["url"])
    assert stats["public.people"] == "2"
    assert stats["public.media"] == "5"
    assert len(stats["media:sha256"]) == 64


def test_restores_dump_and_matches_source(dump_file, source_db, capsys):
    code = vbf.main([str(dump_file)], {"CATS_HOUSE_SOURCE_DATABASE_URL": source_db["url"]})
    out = capsys.readouterr().out
    assert code == 0, out
    assert "совпадает" in out


def test_mismatch_is_reported(dump_file, source_db, capsys):
    import psycopg
    with psycopg.connect(source_db["url"].split("?")[0], autocommit=True) as conn:
        conn.execute("insert into events values (999, 'Добавлено после копии')")
    try:
        code = vbf.main([str(dump_file)], {"CATS_HOUSE_SOURCE_DATABASE_URL": source_db["url"]})
        assert code == 1
        assert "public.events" in capsys.readouterr().out
    finally:
        with psycopg.connect(source_db["url"].split("?")[0], autocommit=True) as conn:
            conn.execute("delete from events where id = 999")
