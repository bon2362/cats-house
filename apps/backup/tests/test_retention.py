import datetime as dt

from drive_backup.retention import backup_name, names_to_trash


def name(day: str, hhmm: str = "0200") -> str:
    return f"cats-house-{day}T{hhmm}Z.dump"


def test_backup_name_uses_utc():
    moment = dt.datetime(2026, 11, 9, 3, 7, tzinfo=dt.timezone(dt.timedelta(hours=1)))
    assert backup_name(moment) == "cats-house-2026-11-09T0207Z.dump"


def test_empty_folder_trashes_nothing():
    assert names_to_trash([], dt.date(2026, 11, 9)) == []


def test_keeps_latest_copy_per_day_for_30_days():
    names = [name("2026-11-09", "0200"), name("2026-11-09", "0900"), name("2026-10-11"), name("2026-10-10")]
    # monthly rule off (0): 2026-10-11 is 29 days old and kept, 2026-10-10 is 30 days old and trashed
    trash = names_to_trash(names, dt.date(2026, 11, 9), 30, 0)
    assert trash == [name("2026-10-10"), name("2026-11-09", "0200")]


def test_keeps_latest_copy_per_month_for_12_months():
    names = [name("2025-10-31"), name("2025-11-30"), name("2025-12-01"), name("2025-12-31"), name("2026-11-09")]
    # 2025-12 is 11 months back (kept: its latest copy), 2025-11 is 12 months back and 2025-10 is 13 (trashed)
    trash = names_to_trash(names, dt.date(2026, 11, 9), 30, 12)
    assert trash == [name("2025-10-31"), name("2025-11-30"), name("2025-12-01")]


def test_newest_copy_is_always_kept():
    names = [name("2020-01-01")]
    assert names_to_trash(names, dt.date(2026, 11, 9), 30, 12) == []


def test_other_names_are_never_trashed():
    names = ["notes.txt", "cats-house-2020-01-01.sql.gz", name("2026-11-09")]
    assert names_to_trash(names, dt.date(2026, 11, 9)) == []
