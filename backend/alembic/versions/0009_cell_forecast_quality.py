"""cell forecast data quality

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-04 16:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "cell_forecast",
        sa.Column(
            "data_quality",
            sa.Enum(
                "GOOD",
                "PARTIAL",
                "STALE",
                "CLOUD_OBSCURED",
                "NO_DATA",
                name="dataquality",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default="GOOD",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("cell_forecast", "data_quality")
