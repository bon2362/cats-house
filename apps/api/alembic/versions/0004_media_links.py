"""Add links from media to people or events."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0004_media_links"
down_revision = "0003_media_publication"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "media_links" not in inspector.get_table_names():
        op.create_table(
            "media_links",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("media_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media.id"), nullable=False),
            sa.Column("person_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("people.id"), nullable=True),
            sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=True),
            sa.CheckConstraint(
                "(person_id IS NOT NULL AND event_id IS NULL) OR (person_id IS NULL AND event_id IS NOT NULL)",
                name="ck_media_links_one_target",
            ),
        )


def downgrade() -> None:
    op.drop_table("media_links")
