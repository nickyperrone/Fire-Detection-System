from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models import (
    DataQuality,
    FireEventStatus,
    Priority,
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
    cadastre: dict | None = Field(
        None, description="The parcel the outline came from (province, department, partida, plano)"
    )


class OutlineIn(BaseModel):
    operation: Literal["add", "remove"]
    geometry: dict = Field(description="GeoJSON Polygon of the piece, EPSG:4326")
    preview: bool = Field(False, description="Answer with the result without saving it")


class TagsIn(BaseModel):
    tags: list[str]


class TagOut(BaseModel):
    id: int
    label: str
    color: str


class TagsOut(BaseModel):
    palette: list[str] = Field(description="The colors a tag can take, in order")
    tags: list[TagOut]


class TagColorIn(BaseModel):
    color: str = Field(description="One of the palette colors, #rrggbb")


class SettingsIn(BaseModel):
    """Only the settings given are changed."""

    alerts: bool | None = None
    visible: bool | None = None
    priority: Priority | None = None


class TerritoryOut(BaseModel):
    id: int
    name: str
    kind: TerritoryKind
    parent_id: int | None
    hectares: float
    tags: list[str]
    alerts: bool
    visible: bool
    priority: Priority
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


class LightningAnswerOut(BaseModel):
    data_quality: DataQuality
    window_minutes: int
    flashes: int
    nearest_m: float | None
    last_at: datetime | None


class ForecastFactorOut(BaseModel):
    code: str
    value: float


class ForecastDayOut(BaseModel):
    horizon_days: int
    valid_from: date
    probability: float
    band: str
    factors: list[ForecastFactorOut]


class ForecastAnswerOut(BaseModel):
    data_quality: DataQuality
    issued_at: datetime | None
    days: list[ForecastDayOut]


class AnomalyAnswerOut(BaseModel):
    data_quality: DataQuality


class PortfolioEntryOut(BaseModel):
    territory_id: int
    name: str
    kind: TerritoryKind
    parent_id: int | None
    hectares: float
    tags: list[str]
    alerts: bool
    visible: bool
    priority: Priority
    fire: FireAnswerOut
    spray: SprayAnswerOut
    lightning: LightningAnswerOut
    forecast: ForecastAnswerOut
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


class FireDayOut(BaseModel):
    day: date
    distance_m: float


class FireHistoryOut(BaseModel):
    first_year: int
    last_year: int
    radius_m: int
    years_loaded: list[int]
    fire_days: int
    inside_days: int
    days_per_year: dict[int, int]
    days_per_month: list[int]
    nearest: FireDayOut | None
    latest: FireDayOut | None


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


class SnapIn(BaseModel):
    geometry: dict = Field(description="GeoJSON Polygon drawn by hand, EPSG:4326")


class SnapOut(BaseModel):
    method: str = Field(description="parcels, edges or none")
    geometry: dict
    parcels: list[dict]
