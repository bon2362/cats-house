"""Fit all three maximum-length name parts in the composed display name."""

import sqlalchemy as sa
from alembic import op


revision = "0007_person_display_name_length"
down_revision = "0006_person_name_parts"
branch_labels = None
depends_on = None


def _resize(existing_length: int, length: int) -> None:
    column = next(
        column for column in sa.inspect(op.get_bind()).get_columns("people")
        if column["name"] == "display_name"
    )
    if getattr(column["type"], "length", None) != existing_length:
        return
    with op.batch_alter_table("people") as table:
        table.alter_column(
            "display_name", existing_type=column["type"], type_=sa.String(length),
            existing_nullable=column["nullable"],
        )


def upgrade() -> None:
    _resize(512, 767)


def downgrade() -> None:
    _resize(767, 512)
