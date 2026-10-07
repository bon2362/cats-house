"""Files, previews, captions and portraits are stored in the database."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0009_media_in_database"
down_revision = "0008_owner_created_records"
branch_labels = None
depends_on = None

MEDIA_COLUMNS = (
    sa.Column("content", sa.LargeBinary(), nullable=True),
    sa.Column("preview", sa.LargeBinary(), nullable=True),
    sa.Column("caption", sa.Text(), nullable=True),
    sa.Column("date_label", sa.String(64), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column("is_deleted", sa.Boolean(), server_default="false", nullable=False),
)


def _columns(table: str) -> dict:
    return {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    media = _columns("media")
    for column in MEDIA_COLUMNS:
        if column.name not in media:
            op.add_column("media", column)
    if not media["storage_key"]["nullable"]:
        op.alter_column("media", "storage_key", existing_type=sa.String(1024), nullable=True)
    if "portrait_media_id" not in _columns("people"):
        op.add_column("people", sa.Column("portrait_media_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key("fk_people_portrait_media", "people", "media", ["portrait_media_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_people_portrait_media", "people", type_="foreignkey")
    op.drop_column("people", "portrait_media_id")
    for column in reversed(MEDIA_COLUMNS):
        op.drop_column("media", column.name)
