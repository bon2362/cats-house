import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_vercel_config_runs_one_function_nightly_without_secrets():
    config = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert config["regions"] == ["fra1"]
    assert config["functions"] == {"api/backup.py": {"maxDuration": 300}}
    assert config["crons"] == [{"path": "/api/backup", "schedule": "0 2 * * *"}]
    assert "env" not in config


def test_runtime_dependencies_are_only_pinned_postgres_binaries():
    lines = [l.strip() for l in (ROOT / "requirements.txt").read_text().splitlines() if l.strip()]
    assert lines == ["postgresql-binaries==18.6.0"]


def test_tests_and_scripts_are_not_deployed():
    ignored = (ROOT / ".vercelignore").read_text().split()
    assert {"tests", "scripts", ".venv"} <= set(ignored)
