"""field anomalies

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-04 22:39:44.500740

"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "field_anomaly",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("territory_id", sa.BigInteger(), nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("area_ha", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("where", sa.String(length=10), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("processing_version", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["territory.id"],
            name=op.f("fk_field_anomaly_territory_id_territory"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_field_anomaly")),
    )
    op.create_index(
        "ix_field_anomaly_geom", "field_anomaly", ["geom"], unique=False, postgresql_using="gist"
    )
    op.create_index(
        op.f("ix_field_anomaly_territory_id"), "field_anomaly", ["territory_id"], unique=False
    )
    op.create_table(
        "field_anomaly_check",
        sa.Column("territory_id", sa.BigInteger(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_clear", sa.Date(), nullable=True),
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
            nullable=False,
        ),
        sa.Column("processing_version", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["territory_id"],
            ["territory.id"],
            name=op.f("fk_field_anomaly_check_territory_id_territory"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("territory_id", name=op.f("pk_field_anomaly_check")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("field_anomaly_check")
    op.drop_index(op.f("ix_field_anomaly_territory_id"), table_name="field_anomaly")
    op.drop_index("ix_field_anomaly_geom", table_name="field_anomaly", postgresql_using="gist")
    op.drop_table("field_anomaly")
