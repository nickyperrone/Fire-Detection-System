from datetime import date, datetime
from enum import StrEnum

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def _enum(enum_cls: type[StrEnum]) -> Enum:
    # Stored as varchar + CHECK, so adding a value is a small migration, not an ALTER TYPE.
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda e: [m.value for m in e],
    )


class TerritoryKind(StrEnum):
    FIELD = "FIELD"
    SECTION = "SECTION"


class Confidence(StrEnum):
    LOW = "low"
    NOMINAL = "nominal"
    HIGH = "high"


class FireEventStatus(StrEnum):
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    CLOSED = "CLOSED"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    VERY_HIGH = "VERY_HIGH"
    HIGH = "HIGH"
    WATCH = "WATCH"


class RiskStatus(StrEnum):
    NEW = "NEW"
    SEEN = "SEEN"
    RESOLVED = "RESOLVED"


class SprayStatus(StrEnum):
    FAVORABLE = "FAVORABLE"
    CAUTION = "CAUTION"
    UNFAVORABLE = "UNFAVORABLE"


class DataQuality(StrEnum):
    GOOD = "GOOD"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    CLOUD_OBSCURED = "CLOUD_OBSCURED"
    NO_DATA = "NO_DATA"


class RunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Tag(Base):
    __tablename__ = "tag"
    __table_args__ = (
        UniqueConstraint("owner", "key", "value", postgresql_nulls_not_distinct=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner: Mapped[str] = mapped_column(String(100))
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[str | None] = mapped_column(String(200))
    color: Mapped[str | None] = mapped_column(String(7))

    @property
    def label(self) -> str:
        return self.key if self.value is None else f"{self.key}:{self.value}"


class TerritoryTag(Base):
    __tablename__ = "territory_tag"

    territory_id: Mapped[int] = mapped_column(
        ForeignKey("territory.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True)


class Territory(Base):
    __tablename__ = "territory"
    __table_args__ = (Index("ix_territory_geom", "geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[TerritoryKind] = mapped_column(_enum(TerritoryKind))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("territory.id", ondelete="CASCADE"), index=True
    )
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False)
    hectares: Mapped[float] = mapped_column(Float)
    attributes: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tags: Mapped[list[Tag]] = relationship(secondary="territory_tag", lazy="selectin")
    sections: Mapped[list["Territory"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan", passive_deletes=True
    )
    parent: Mapped["Territory | None"] = relationship(back_populates="sections", remote_side=[id])


class Observation(Base):
    __tablename__ = "observation"
    __table_args__ = (
        Index("ix_observation_geom", "geom", postgresql_using="gist"),
        Index(
            "uq_observation_native_id",
            "source",
            "native_id",
            unique=True,
            postgresql_where=text("native_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(30))
    product: Mapped[str] = mapped_column(String(40))
    satellite: Mapped[str] = mapped_column(String(30))
    sensor: Mapped[str] = mapped_column(String(20))
    native_id: Mapped[str | None] = mapped_column(String(100))
    dedup_key: Mapped[str] = mapped_column(String(40), unique=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    confidence_raw: Mapped[str] = mapped_column(String(10))
    confidence: Mapped[Confidence] = mapped_column(_enum(Confidence))
    frp_mw: Mapped[float | None] = mapped_column(Float)
    brightness_k: Mapped[float | None] = mapped_column(Float)
    day_night: Mapped[str | None] = mapped_column(String(1))
    raw_payload: Mapped[dict] = mapped_column(JSONB)
    # Within reach of a known industrial heat source: kept, but never part of a fire event.
    static_source: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class FireEvent(Base):
    __tablename__ = "fire_event"
    __table_args__ = (Index("ix_fire_event_geom", "geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Point for one observation, polygon hull for several.
    geom = mapped_column(Geometry("GEOMETRY", srid=4326, spatial_index=False), nullable=False)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    observation_count: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[Confidence] = mapped_column(_enum(Confidence))
    max_frp_mw: Mapped[float | None] = mapped_column(Float)
    sensors: Mapped[list[str]] = mapped_column(ARRAY(String(30)))
    status: Mapped[FireEventStatus] = mapped_column(_enum(FireEventStatus), index=True)
    processing_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ObservationEventLink(Base):
    __tablename__ = "observation_event_link"

    observation_id: Mapped[int] = mapped_column(
        ForeignKey("observation.id", ondelete="CASCADE"), primary_key=True
    )
    fire_event_id: Mapped[int] = mapped_column(
        ForeignKey("fire_event.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[dict] = mapped_column(JSONB)
    processing_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FieldRiskEvent(Base):
    __tablename__ = "field_risk_event"
    __table_args__ = (UniqueConstraint("territory_id", "fire_event_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    territory_id: Mapped[int] = mapped_column(
        ForeignKey("territory.id", ondelete="CASCADE"), index=True
    )
    fire_event_id: Mapped[int] = mapped_column(
        ForeignKey("fire_event.id", ondelete="CASCADE"), index=True
    )
    distance_m: Mapped[float] = mapped_column(Float)
    bearing_deg: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[Severity] = mapped_column(_enum(Severity))
    factors: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[RiskStatus] = mapped_column(_enum(RiskStatus))
    processing_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    fire_event: Mapped[FireEvent] = relationship(lazy="joined")


class SprayAssessment(Base):
    __tablename__ = "spray_assessment"
    __table_args__ = (UniqueConstraint("territory_id", "profile", "valid_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    territory_id: Mapped[int] = mapped_column(
        ForeignKey("territory.id", ondelete="CASCADE"), index=True
    )
    profile: Mapped[str] = mapped_column(String(50))
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[SprayStatus] = mapped_column(_enum(SprayStatus))
    rules: Mapped[list[dict]] = mapped_column(JSONB)
    weather: Mapped[dict] = mapped_column(JSONB)
    data_quality: Mapped[DataQuality] = mapped_column(_enum(DataQuality))
    forecast_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processing_version: Mapped[str] = mapped_column(String(40))


class IngestionRun(Base):
    __tablename__ = "ingestion_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), index=True)
    product: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus))
    fetched: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    inserted: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(String(2000))
    # File-based providers (GOES): the last object key processed, so the next run continues there.
    cursor: Mapped[str | None] = mapped_column(String(300))


class LightningFlash(Base):
    __tablename__ = "lightning_flash"
    __table_args__ = (Index("ix_lightning_flash_geom", "geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    native_id: Mapped[str] = mapped_column(String(60), unique=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    energy_j: Mapped[float] = mapped_column(Float)
    area_m2: Mapped[float] = mapped_column(Float)


class HistoricalDetection(Base):
    """Archive detections for fire history. Separate from `observation` on purpose: history
    must never create fire events or alerts (docs/07-fire-history.md)."""

    __tablename__ = "historical_detection"
    __table_args__ = (Index("ix_historical_detection_geom", "geom", postgresql_using="gist"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product: Mapped[str] = mapped_column(String(30))
    dedup_key: Mapped[str] = mapped_column(String(40), unique=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    confidence: Mapped[Confidence] = mapped_column(_enum(Confidence))
    frp_mw: Mapped[float | None] = mapped_column(Float)
    day_night: Mapped[str | None] = mapped_column(String(1))


class WeatherDay(Base):
    """One day of weather at a forecast weather point, with the FWI codes as of that day.

    POWER rows replace Open-Meteo rows when POWER publishes (docs/05-fire-forecast.md#live-data).
    """

    __tablename__ = "weather_day"

    latitude: Mapped[float] = mapped_column(Float, primary_key=True)
    longitude: Mapped[float] = mapped_column(Float, primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    source: Mapped[str] = mapped_column(String(20))
    tmax_c: Mapped[float] = mapped_column(Float)
    rh_pct: Mapped[float] = mapped_column(Float)
    wind_kmh: Mapped[float] = mapped_column(Float)
    rain_mm: Mapped[float] = mapped_column(Float)
    ffmc: Mapped[float | None] = mapped_column(Float)
    dmc: Mapped[float | None] = mapped_column(Float)
    dc: Mapped[float | None] = mapped_column(Float)
    isi: Mapped[float | None] = mapped_column(Float)
    bui: Mapped[float | None] = mapped_column(Float)
    fwi: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CellForecast(Base):
    """Latest fire probability per forecast cell and horizon; replaced on every run."""

    __tablename__ = "cell_forecast"

    row: Mapped[int] = mapped_column(Integer, primary_key=True)
    col: Mapped[int] = mapped_column(Integer, primary_key=True)
    horizon_days: Mapped[int] = mapped_column(Integer, primary_key=True)
    valid_from: Mapped[date] = mapped_column(Date)
    probability: Mapped[float] = mapped_column(Float)
    factors: Mapped[list[dict]] = mapped_column(JSONB)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str] = mapped_column(String(60))


class FireForecast(Base):
    """Latest fire probability per territory and horizon (cells within the radius combined)."""

    __tablename__ = "fire_forecast"

    territory_id: Mapped[int] = mapped_column(
        ForeignKey("territory.id", ondelete="CASCADE"), primary_key=True
    )
    horizon_days: Mapped[int] = mapped_column(Integer, primary_key=True)
    valid_from: Mapped[date] = mapped_column(Date)
    probability: Mapped[float] = mapped_column(Float)
    band: Mapped[str] = mapped_column(String(20))
    factors: Mapped[list[dict]] = mapped_column(JSONB)
    data_quality: Mapped[DataQuality] = mapped_column(_enum(DataQuality))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str] = mapped_column(String(60))
    processing_version: Mapped[str] = mapped_column(String(40))


class StaticSource(Base):
    """A place hot every day (industry, gas flares), from archive detections of type 2.

    Live detections near one never alert (docs/03-rules.md#static-heat-sources).
    """

    __tablename__ = "static_source"
    __table_args__ = (Index("ix_static_source_geom", "geom", postgresql_using="gist"),)

    # Rounded to the static_sources grid, so repeated detections of one plant are one row.
    latitude: Mapped[float] = mapped_column(Float, primary_key=True)
    longitude: Mapped[float] = mapped_column(Float, primary_key=True)
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=False), nullable=False)
    detections: Mapped[int] = mapped_column(Integer)
    last_seen: Mapped[date] = mapped_column(Date)
