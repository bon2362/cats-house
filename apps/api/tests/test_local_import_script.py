from pathlib import Path
from subprocess import run
import sys


def test_local_import_script_is_present():
    assert (Path(__file__).parents[3] / "scripts" / "import-local-gedcom.py").is_file()


def test_local_import_script_accepts_at5_option_before_database_access():
    script = Path(__file__).parents[3] / "scripts" / "import-local-gedcom.py"

    result = run(
        [sys.executable, str(script), "--file", "relative.ged", "--at5", "/tmp/tree.at5"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "абсолютный путь к GEDCOM" in result.stderr
