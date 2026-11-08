import os

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.models import Base
import app.models.genealogy  # noqa: F401

config = context.config
if database_url := os.getenv("CATS_HOUSE_DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", database_url)
target_metadata = Base.metadata


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        connection.execute(text("SET search_path TO public"))
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema="public",
        )
        with context.begin_transaction():
            context.run_migrations()
        # SET search_path above opened the transaction, so Alembic leaves committing to us.
        connection.commit()


run_migrations_online()
