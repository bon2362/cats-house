"""Add media publication metadata."""

import sqlalchemy as sa
from alembic import op


revision = "0003_media_publication"
down_revision = "0002_public_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("media")}
    if "original_filename" not in columns:
        op.add_column("media", sa.Column("original_filename", sa.String(length=255), nullable=False, server_default=""))
    if "is_published" not in columns:
        op.add_column("media", sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("media", "is_published")
    op.drop_column("media", "original_filename")
