"""land cover outlines

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-16

The outlines of trees, buildings and water inside each field, to draw on the map
(docs/15-land-cover.md). Nullable: fields read before this get theirs on the worker's next run.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "land_cover", sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("land_cover", "features")
