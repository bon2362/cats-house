"""Preserve the source family on parent-child links."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0005_parent_child_unions"
down_revision = "0004_media_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    column_names = {column["name"] for column in inspector.get_columns("parent_children")}
    if "union_id" not in column_names:
        op.add_column(
            "parent_children",
            sa.Column("union_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("unions.id"), nullable=True),
        )

    # Existing imports predate this field. Restore only links with one exact
    # two-parent union; links with incomplete or ambiguous source stay null.
    op.execute(
        """
        WITH candidates AS (
            SELECT link.id AS link_id, family.id AS union_id
            FROM parent_children AS link
            JOIN unions AS family
              ON link.parent_id IN (family.partner_one_id, family.partner_two_id)
            JOIN parent_children AS other_parent
              ON other_parent.child_id = link.child_id
             AND other_parent.parent_id = CASE
                 WHEN link.parent_id = family.partner_one_id THEN family.partner_two_id
                 ELSE family.partner_one_id
             END
        ), unique_candidates AS (
            SELECT link_id, min(union_id::text)::uuid AS union_id
            FROM candidates
            GROUP BY link_id
            HAVING count(DISTINCT union_id) = 1
        )
        UPDATE parent_children AS link
        SET union_id = unique_candidates.union_id
        FROM unique_candidates
        WHERE link.id = unique_candidates.link_id
          AND link.union_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("parent_children", "union_id")
