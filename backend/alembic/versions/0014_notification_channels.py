"""notification channels

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-14 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Alerts now go by email or Telegram: the log of emails becomes the log of deliveries.
    op.rename_table("alert_email", "alert_delivery")
    op.execute("ALTER INDEX ix_alert_email_user_id RENAME TO ix_alert_delivery_user_id")
    op.execute("ALTER SEQUENCE alert_email_id_seq RENAME TO alert_delivery_id_seq")
    op.execute("ALTER TABLE alert_delivery RENAME CONSTRAINT pk_alert_email TO pk_alert_delivery")
    op.execute(
        "ALTER TABLE alert_delivery RENAME CONSTRAINT fk_alert_email_user_id_app_user "
        "TO fk_alert_delivery_user_id_app_user"
    )
    op.add_column(
        "alert_delivery",
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="email"),
    )
    op.alter_column("alert_delivery", "channel", server_default=None)
    op.add_column("app_user", sa.Column("notifications", postgresql.JSONB(astext_type=sa.Text())))
    op.add_column("app_user", sa.Column("telegram_chat_id", sa.BigInteger()))
    op.add_column("app_user", sa.Column("telegram_code_hash", sa.String(length=64)))
    op.add_column("app_user", sa.Column("telegram_code_expires_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint(
        op.f("uq_app_user_telegram_code_hash"), "app_user", ["telegram_code_hash"]
    )
    op.add_column("territory", sa.Column("weather_notified_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("territory", "weather_notified_at")
    op.drop_constraint(op.f("uq_app_user_telegram_code_hash"), "app_user", type_="unique")
    for column in (
        "telegram_code_expires_at",
        "telegram_code_hash",
        "telegram_chat_id",
        "notifications",
    ):
        op.drop_column("app_user", column)
    op.drop_column("alert_delivery", "channel")
    op.execute(
        "ALTER TABLE alert_delivery RENAME CONSTRAINT fk_alert_delivery_user_id_app_user "
        "TO fk_alert_email_user_id_app_user"
    )
    op.execute("ALTER TABLE alert_delivery RENAME CONSTRAINT pk_alert_delivery TO pk_alert_email")
    op.execute("ALTER INDEX ix_alert_delivery_user_id RENAME TO ix_alert_email_user_id")
    op.execute("ALTER SEQUENCE alert_delivery_id_seq RENAME TO alert_email_id_seq")
    op.rename_table("alert_delivery", "alert_email")
