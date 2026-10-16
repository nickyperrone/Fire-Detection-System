"""land cover per territory

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-16

Trees, crops and buildings in and around each field, from ESA WorldCover (docs/15-land-cover.md).
A new table only: existing fields get theirs on the worker's next run.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "land_cover",
        sa.Column("territory_id", sa.BigInteger(), nullable=False),
        sa.Column("shares", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("built_m2", sa.Float(), nullable=False),
        sa.Column("built_nearby_m2", sa.Float(), nullable=False),
        sa.Column("outline", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=60), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["territory.id"],
            name=op.f("fk_land_cover_territory_id_territory"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("territory_id", name=op.f("pk_land_cover")),
    )


def downgrade() -> None:
    op.drop_table("land_cover")
