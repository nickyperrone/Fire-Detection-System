"""field snapshots

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-05 12:15:18.215527

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "field_snapshot",
        sa.Column("territory_id", sa.BigInteger(), nullable=False),
        sa.Column("acquired_on", sa.Date(), nullable=False),
        sa.Column("box_key", sa.String(length=10), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("grid", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cloud_share", sa.Float(), nullable=False),
        sa.Column("ndvi_mean", sa.Float(), nullable=True),
        sa.Column("processing_version", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["territory.id"],
            name=op.f("fk_field_snapshot_territory_id_territory"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("territory_id", "acquired_on", name=op.f("pk_field_snapshot")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("field_snapshot")
