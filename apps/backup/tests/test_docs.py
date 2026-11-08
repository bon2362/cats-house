from pathlib import Path

ROOT = Path(__file__).parents[1]
REPO = ROOT.parents[1]


def test_readme_covers_setup_and_restore():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for needle in ("pg_read_all_data", "google-authorize.py", "In production", "healthchecks.io",
                   "vercel env add", "pg_restore --no-owner --no-privileges --exit-on-error",
                   "verify-backup-file.py", "CATS_HOUSE_DATABASE_URL"):
        assert needle in text, needle


def test_operations_guide_points_to_the_backup_service():
    text = (REPO / "docs" / "operations.md").read_text(encoding="utf-8")
    assert "cats-house-backup" in text
    assert "apps/backup/README.md" in text
    assert "пока **не настроена**" not in text
