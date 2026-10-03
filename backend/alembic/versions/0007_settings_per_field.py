"""settings per field: alerts, visibility and priority

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-03 11:08:14.202467

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "territory",
        sa.Column("alerts", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "territory",
        sa.Column("visible", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "territory",
        sa.Column(
            "priority",
            sa.Enum(
                "HIGH",
                "NORMAL",
                "LOW",
                name="priority",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default="NORMAL",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("territory", "priority")
    op.drop_column("territory", "visible")
    op.drop_column("territory", "alerts")
