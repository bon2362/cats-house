from pathlib import Path
import runpy

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, select


def upgrade_database(database_url: str) -> None:
    api_root = Path(__file__).parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
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


def test_people_have_optional_name_parts_after_upgrade(postgres_url):
    upgrade_database(postgres_url)

    columns = {column["name"]: column for column in inspect(create_engine(postgres_url)).get_columns("people")}

    for name in ("surname", "given_name", "patronymic", "birth_surname"):
        assert columns[name]["nullable"] is True


def test_display_name_fits_three_maximum_length_name_parts_after_upgrade(postgres_url):
    upgrade_database(postgres_url)

    columns = {column["name"]: column for column in inspect(create_engine(postgres_url)).get_columns("people")}

    assert columns["display_name"]["type"].length == 767


def test_display_name_resize_preserves_rows_and_is_idempotent_on_sqlite():
    migration = runpy.run_path(
        str(Path(__file__).parents[1] / "alembic" / "versions" / "0007_person_display_name_length.py")
    )
    engine = create_engine("sqlite://")
    people = Table(
        "people", MetaData(),
        Column("id", Integer, primary_key=True),
        Column("display_name", String(512), nullable=False),
    )
    people.create(engine)

    with engine.begin() as connection:
        connection.execute(people.insert().values(id=1, display_name="Анна Иванова"))
        with Operations.context(MigrationContext.configure(connection)):
            migration["upgrade"]()
            migration["upgrade"]()
        columns = {column["name"]: column for column in inspect(connection).get_columns("people")}
        assert columns["display_name"]["type"].length == 767
        assert connection.scalar(select(people.c.display_name)) == "Анна Иванова"

        with Operations.context(MigrationContext.configure(connection)):
            migration["downgrade"]()
            migration["downgrade"]()
        columns = {column["name"]: column for column in inspect(connection).get_columns("people")}
        assert columns["display_name"]["type"].length == 512
        assert connection.scalar(select(people.c.display_name)) == "Анна Иванова"
