"""greenness per lot

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-05 12:45:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("field_snapshot", sa.Column("ndvi_means", postgresql.JSONB(), nullable=True))
    # The field's own mean carries over; its lots are read again by the next run.
    op.execute(
        "UPDATE field_snapshot SET ndvi_means = jsonb_build_object(territory_id::text, ndvi_mean)"
    )
    op.alter_column("field_snapshot", "ndvi_means", nullable=False)
    op.drop_column("field_snapshot", "ndvi_mean")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("field_snapshot", sa.Column("ndvi_mean", sa.Float(), nullable=True))
    op.execute("UPDATE field_snapshot SET ndvi_mean = (ndvi_means ->> territory_id::text)::float")
    op.drop_column("field_snapshot", "ndvi_means")
