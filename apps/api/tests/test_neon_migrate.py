from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "neon-migrate.py"


def load_script():
    spec = importlib.util.spec_from_file_location("neon_migrate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_validates_configuration_without_running_commands(monkeypatch, capsys):
    module = load_script()
    monkeypatch.setenv("CATS_HOUSE_SOURCE_DATABASE_URL", "postgresql://local/cats")
    monkeypatch.setenv("CATS_HOUSE_TARGET_DATABASE_URL", "postgresql://neon/cats?sslmode=require")
    monkeypatch.setattr(module, "run", lambda *_args, **_kwargs: pytest.fail("commands must not run in --check"))
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--check"])

    assert module.main() == 0
    assert "Проверка готовности завершена" in capsys.readouterr().out


def test_apply_requires_exact_confirmation(monkeypatch, capsys, tmp_path):
    module = load_script()
    monkeypatch.setenv("CATS_HOUSE_SOURCE_DATABASE_URL", "postgresql://local/cats")
    monkeypatch.setenv("CATS_HOUSE_TARGET_DATABASE_URL", "postgresql://neon/cats?sslmode=require")
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
    monkeypatch.setattr(module, "run", lambda *_args, **_kwargs: pytest.fail("commands must not run"))
    output = tmp_path.parent / "neon-dumps"
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--apply", "--output", str(output)])

    assert module.main() == 2
    assert "MIGRATE" in capsys.readouterr().out


def test_rejects_target_without_sslmode_require(monkeypatch):
    module = load_script()
    monkeypatch.setenv("CATS_HOUSE_SOURCE_DATABASE_URL", "postgresql://local/cats")
    monkeypatch.setenv("CATS_HOUSE_TARGET_DATABASE_URL", "postgresql://neon/cats")
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--check"])

    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2


def test_check_accepts_sqlalchemy_postgresql_driver_url(monkeypatch):
    module = load_script()
    monkeypatch.setenv("CATS_HOUSE_SOURCE_DATABASE_URL", "postgresql+psycopg://local/cats")
    monkeypatch.setenv("CATS_HOUSE_TARGET_DATABASE_URL", "postgresql://neon/cats?sslmode=require")
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--check"])

    assert module.main() == 0


def test_verification_rejects_different_table_counts(monkeypatch):
    module = load_script()
    monkeypatch.setattr(module, "table_counts", lambda url: {"people": "2"} if url == "source" else {"people": "1"})

    with pytest.raises(RuntimeError, match="Количество строк не совпадает"):
        module.verify_migration("source", "target")


def test_migrate_passes_target_database_name_to_pg_restore(monkeypatch, tmp_path):
    module = load_script()
    commands: list[list[str]] = []

    def fake_run(command, environment):
        commands.append(command)
        if command[0] == "psql":
            return subprocess.CompletedProcess(command, 0, stdout="0\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module, "verify_migration", lambda *_args: None)

    module.migrate(
        "postgresql://source/source_db",
        "postgresql://target/target_db?sslmode=require",
        tmp_path,
    )

    restore = next(command for command in commands if command[0] == "pg_restore")
    assert restore[restore.index("--dbname") + 1] == "target_db"
    assert all(command[1:3] != ["-m", "alembic"] for command in commands)
