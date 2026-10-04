from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def upgrade_database(database_url: str) -> None:
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


def test_initial_migration_creates_genealogy_and_import_tables(postgres_url):
    upgrade_database(postgres_url)

    engine = create_engine(postgres_url)
    assert set(inspect(engine).get_table_names()) >= {
        "people",
        "unions",
        "parent_children",
        "events",
        "import_runs",
        "import_issues",
    }
