from datetime import datetime

from pydantic import BaseModel, Field

from app.models import (
    DataQuality,
    FireEventStatus,
    RiskStatus,
    Severity,
    SprayStatus,
    TerritoryKind,
)
from app.services.spray_rules import RuleStatus


class TerritoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    geometry: dict = Field(description="GeoJSON Polygon or MultiPolygon, EPSG:4326")
    parent_id: int | None = Field(None, description="Field id, to create a section")
    tags: list[str] = Field(default_factory=list, description="key:value or plain labels")


class TagsIn(BaseModel):
    tags: list[str]


class TerritoryOut(BaseModel):
    id: int
    name: str
    kind: TerritoryKind
    parent_id: int | None
    hectares: float
    tags: list[str]
    geometry: dict


class FireEventOut(BaseModel):
    id: int
    status: FireEventStatus
    first_detected_at: datetime
    last_detected_at: datetime
    observation_count: int
    confidence: str
    max_frp_mw: float | None
    sensors: list[str]
    processing_version: str
    geometry: dict


class RiskEventOut(BaseModel):
    id: int
    territory_id: int
    fire_event_id: int
    severity: Severity
    distance_m: float
    direction: str | None
    status: RiskStatus
    factors: dict
    processing_version: str
    updated_at: datetime


class RiskStatusIn(BaseModel):
    status: RiskStatus


class FireAnswerOut(BaseModel):
    data_quality: DataQuality
    last_read_at: datetime | None
    severity: Severity | None
    distance_m: float | None
    direction: str | None
    sensors: list[str]
    confidence: str | None
    acquired_at: datetime | None
    received_at: datetime | None
    fire_event_id: int | None
    other_fires: int


class SprayAnswerOut(BaseModel):
    data_quality: DataQuality
    profile: str
    status: SprayStatus | None
    valid_at: datetime | None
    problems: list["SprayRuleOut"]
    drift_toward: str | None
    next_favorable: tuple[datetime, datetime] | None


class AnomalyAnswerOut(BaseModel):
    data_quality: DataQuality


class PortfolioEntryOut(BaseModel):
    territory_id: int
    name: str
    kind: TerritoryKind
    parent_id: int | None
    hectares: float
    tags: list[str]
    fire: FireAnswerOut
    spray: SprayAnswerOut
    anomaly: AnomalyAnswerOut


class SprayRuleOut(BaseModel):
    """Codes and numbers only; the frontend writes the sentence in the user's language."""

    rule: str
    status: RuleStatus
    value: float | None
    unit: str
    # Defaults: assessments stored before these fields existed do not have them.
    limit: float | None = None
    estimated: bool = False
    window_h: int | None = None


class SprayHourOut(BaseModel):
    valid_at: datetime
    status: SprayStatus
    data_quality: DataQuality
    rules: list[SprayRuleOut]
    weather: dict
    forecast_fetched_at: datetime
    processing_version: str


class SourceStatusOut(BaseModel):
    provider: str
    product: str
    last_run_at: datetime | None
    last_run_status: str | None
    last_success_at: datetime | None
    last_error: str | None


class LatestPassOut(BaseModel):
    sensor: str
    satellite: str
    acquired_at: datetime
    ingested_at: datetime


class HealthOut(BaseModel):
    database: bool
    processing_version: str
    fire_data_quality: DataQuality
    latest_pass: LatestPassOut | None
    sources: list[SourceStatusOut]
