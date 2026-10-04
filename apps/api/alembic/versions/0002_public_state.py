"""Add archival state and the audit log."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0002_public_state"
down_revision = "0001_genealogy_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "is_archived" not in {column["name"] for column in inspector.get_columns("people")}:
        op.add_column("people", sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    if "change_logs" not in inspector.get_table_names():
        op.create_table(
            "change_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("owner_email", sa.String(length=255), nullable=False),
            sa.Column("before", postgresql.JSONB(), nullable=False),
            sa.Column("after", postgresql.JSONB(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("change_logs")
    op.drop_column("people", "is_archived")
