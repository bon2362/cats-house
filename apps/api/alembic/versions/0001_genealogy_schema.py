"""Create the initial Cat's House genealogy schema."""

from alembic import op

from app.models import Base
import app.models.genealogy  # noqa: F401

revision = "0001_genealogy_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
