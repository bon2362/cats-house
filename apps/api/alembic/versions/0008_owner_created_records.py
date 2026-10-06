"""People and unions created on the site have no import run."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0008_owner_created_records"
down_revision = "0007_person_display_name_length"
branch_labels = None
depends_on = None


def _make_nullable(table: str) -> None:
    columns = {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns(table)}
    if not columns["import_run_id"]["nullable"]:
        op.alter_column(table, "import_run_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)


def upgrade() -> None:
    _make_nullable("people")
    _make_nullable("unions")


def downgrade() -> None:
    op.alter_column("unions", "import_run_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.alter_column("people", "import_run_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
