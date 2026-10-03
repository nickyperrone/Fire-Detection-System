"""accounts and email alerts

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-03 18:07:37.371385

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "app_user",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("locale", sa.String(length=5), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
        sa.UniqueConstraint("email", name=op.f("uq_app_user_email")),
    )
    op.create_table(
        "login_link",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("locale", sa.String(length=5), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_link")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_login_link_token_hash")),
    )
    op.create_index(op.f("ix_login_link_email"), "login_link", ["email"], unique=False)
    op.create_table(
        "alert_email",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dangers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processing_version", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_alert_email_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_email")),
    )
    op.create_index(op.f("ix_alert_email_user_id"), "alert_email", ["user_id"], unique=False)
    op.create_table(
        "user_session",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_user_session_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_session")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_session_token_hash")),
    )
    op.create_index(op.f("ix_user_session_user_id"), "user_session", ["user_id"], unique=False)
    op.add_column(
        "field_risk_event",
        sa.Column(
            "notified_severity",
            sa.Enum(
                "CRITICAL",
                "VERY_HIGH",
                "HIGH",
                "WATCH",
                name="notified_severity",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "territory", sa.Column("lightning_notified_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("territory", "lightning_notified_at")
    op.drop_column("field_risk_event", "notified_severity")
    op.drop_index(op.f("ix_user_session_user_id"), table_name="user_session")
    op.drop_table("user_session")
    op.drop_index(op.f("ix_alert_email_user_id"), table_name="alert_email")
    op.drop_table("alert_email")
    op.drop_index(op.f("ix_login_link_email"), table_name="login_link")
    op.drop_table("login_link")
    op.drop_table("app_user")
