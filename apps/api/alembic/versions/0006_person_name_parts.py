"""Store name parts separately from the composed display name."""

import sqlalchemy as sa
from alembic import op


revision = "0006_person_name_parts"
down_revision = "0005_parent_child_unions"
branch_labels = None
depends_on = None

NAME_COLUMNS = ("surname", "given_name", "patronymic", "birth_surname")


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("people")}
    for name in NAME_COLUMNS:
        if name not in existing:
            op.add_column("people", sa.Column(name, sa.String(255), nullable=True))


def downgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("people")}
    for name in reversed(NAME_COLUMNS):
        if name in existing:
            op.drop_column("people", name)
