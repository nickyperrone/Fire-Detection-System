"""valid parcel outlines

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-15

Some provincial parcels cross themselves, and PostGIS fails on every intersection with them
(docs/08-cadastre.md). New ones are stored made valid; this fixes the ones already stored.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE cadastral_parcel
        SET geom = ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3))
        WHERE NOT ST_IsValid(geom)
        """
    )


def downgrade() -> None:
    # The invalid outlines are not kept: there is nothing to go back to.
    pass
