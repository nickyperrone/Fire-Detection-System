"""summaries by email

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-04 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "app_user",
        sa.Column(
            "summary",
            sa.Enum(
                "WEEKLY",
                "DAILY",
                "OFF",
                name="summaryfrequency",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            server_default="WEEKLY",
            nullable=False,
        ),
    )
    op.add_column(
        "app_user", sa.Column("summary_sent_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("app_user", "summary_sent_at")
    op.drop_column("app_user", "summary")
