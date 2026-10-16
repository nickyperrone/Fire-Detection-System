import json
import unicodedata
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints, field_validator

from app.models import (
    DataQuality,
    FireEventStatus,
    Priority,
    RiskStatus,
    Severity,
    SprayStatus,
    SummaryFrequency,
    TerritoryKind,
)
from app.services.spray_rules import RuleStatus

# Limits on what an account sends (docs/01-product.md#fields-sections-and-tags): names and tags
# end up in emails and Telegram messages, and shapes in geometry operations.
MAX_VERTICES = 10_000


def _plain_text(value: str) -> str:
    """One line of visible text: no line breaks or other control characters."""
    if any(unicodedata.category(c) == "Cc" for c in value):
        raise ValueError("control characters are not allowed")
    return value


def _small_geometry(value: dict) -> dict:
    count = 0

    def walk(node) -> None:
        nonlocal count
        if isinstance(node, list):
            if node and isinstance(node[0], int | float):
                count += 1
                return
            for child in node:
                walk(child)

    walk(value.get("coordinates"))
    if count > MAX_VERTICES:
        raise ValueError(f"at most {MAX_VERTICES} vertices")
    return value


def _small_object(value: dict | None) -> dict | None:
    if value is not None and len(json.dumps(value)) > 2000:
        raise ValueError("too large")
    return value


Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(_plain_text),
]
TagLabel = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(_plain_text),
]
Tags = Annotated[list[TagLabel], Field(max_length=30)]
Geometry = Annotated[dict, AfterValidator(_small_geometry)]


class TerritoryIn(BaseModel):
    name: Name
    geometry: Geometry = Field(description="GeoJSON Polygon or MultiPolygon, EPSG:4326")
    parent_id: int | None = Field(None, description="Field id, to create a section")
    tags: Tags = Field(default_factory=list, description="key:value or plain labels")
    cadastre: Annotated[dict | None, AfterValidator(_small_object)] = Field(
        None, description="The parcel the outline came from (province, department, partida, plano)"
    )


class OutlineIn(BaseModel):
    operation: Literal["add", "remove"]
    geometry: Geometry = Field(description="GeoJSON Polygon of the piece, EPSG:4326")
    preview: bool = Field(False, description="Answer with the result without saving it")


class TagsIn(BaseModel):
    tags: Tags


class TagOut(BaseModel):
    id: int
    label: str
    color: str


class TagsOut(BaseModel):
    palette: list[str] = Field(description="The colors a tag can take, in order")
    tags: list[TagOut]


class TagColorIn(BaseModel):
    color: str = Field(description="One of the palette colors, #rrggbb")


class DetectIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class DetectOut(BaseModel):
    geometry: dict = Field(description="GeoJSON Polygon, EPSG:4326")
    dates: int = Field(description="Clear Sentinel-2 dates the outline was found in")
    first: date
    last: date


class LoginIn(BaseModel):
    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    locale: Literal["es", "en"] = "es"
    # Cloudflare Turnstile's token (docs/09-accounts-and-alerts.md#bots).
    captcha: str | None = Field(default=None, max_length=2048)

    @field_validator("email", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        # Phone keyboards add a space after an autocompleted address.
        return value.strip() if isinstance(value, str) else value


class Channels(BaseModel):
    """Where one kind of alert goes (docs/13-notifications.md#channels)."""

    email: bool
    telegram: bool


class Notifications(BaseModel):
    fire_high: Channels
    fire_medium: Channels
    fire_far: Channels
    lightning: Channels
    weather: Channels
    summary: Channels


class TelegramOut(BaseModel):
    # False when the server has no bot set up: the page says Telegram is not available.
    available: bool
    connected: bool


class MeOut(BaseModel):
    email: str
    locale: str
    summary: SummaryFrequency
    notifications: Notifications
    telegram: TelegramOut


class MeIn(BaseModel):
    """Only what is given changes."""

    summary: SummaryFrequency | None = None
    notifications: Notifications | None = None


class AuthConfigOut(BaseModel):
    # Public: the page needs it to show Cloudflare's check. None when there is no check.
    captcha_site_key: str | None


class TelegramLinkOut(BaseModel):
    # Opens the bot in Telegram with the one-time code.
    url: str


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


class LandCoverOut(BaseModel):
    shares: dict[str, float] = Field(description="Share of the field per class, adding up to 1")
    trees_share: float
    built_m2: float
    built_nearby_m2: float
    wooded: bool = Field(description="Enough trees to make a fire there one band worse")
    has_buildings: bool = Field(description="Buildings in or near the field")
    source: str
    computed_at: datetime


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


class WeatherAnswerOut(BaseModel):
    data_quality: DataQuality
    valid_at: datetime | None
    temperature_c: float | None
    relative_humidity_pct: float | None
    wind_speed_kmh: float | None
    wind_from: str | None = Field(description="Compass point the wind comes from")
    wind_gusts_kmh: float | None
    cloud_cover_pct: float | None
    rain_24h_mm: float | None
    rain_probability_pct: float | None = Field(description="Highest in the next 24 hours")


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


class AnomalyPatchOut(BaseModel):
    kind: str = Field(description="less_green, water or burnt")
    area_ha: float
    where: str = Field(description="Compass point from the field's center, or center")
    lot: str | None = Field(None, description="The lot it is in, for a field split into lots")


class AnomalyAnswerOut(BaseModel):
    data_quality: DataQuality
    observed_on: date | None
    patches: list[AnomalyPatchOut]
    checked_at: datetime | None = Field(description="None until the field is first looked at")


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
    weather: WeatherAnswerOut
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


class PlaceOut(BaseModel):
    name: str
    context: str
    kind: str
    longitude: float
    latitude: float
    bbox: tuple[float, float, float, float] | None


class WeatherFrameOut(BaseModel):
    scanned_at: datetime
    # Names the frame's image: /weather-layer/{id}.png.
    id: str


class WeatherLayerOut(BaseModel):
    """The clouds and rain loop: the box it covers (west, south, east, north) and its frames,
    oldest first."""

    bbox: list[float]
    frames: list[WeatherFrameOut]


class SnapshotOutlineOut(BaseModel):
    territory_id: int
    name: str
    kind: TerritoryKind
    # SVG path in the image's pixels.
    path: str


class SnapshotOut(BaseModel):
    date: date
    cloud_share: float
    ndvi_mean: float | None


class SnapshotsOut(BaseModel):
    """A field's satellite photos, oldest first (docs/12-field-page.md). A lot answers with its
    field's photos; `field_id` is the field whose images to load."""

    field_id: int
    width: int
    height: int
    outlines: list[SnapshotOutlineOut]
    snapshots: list[SnapshotOut]


class SourceStatusOut(BaseModel):
    provider: str
    product: str
    last_run_at: datetime | None
    last_run_status: str | None
    last_success_at: datetime | None
    # The error text stays in the server's log: it can name internal addresses.


class LatestPassOut(BaseModel):
    sensor: str
    satellite: str
    acquired_at: datetime
    ingested_at: datetime


class HealthOut(BaseModel):
    database: bool
    processing_version: str
    fire_data_quality: DataQuality
    # The newest polar pass with a detection, and GOES's newest scan, detection or not.
    latest_pass: LatestPassOut | None
    latest_scan: LatestPassOut | None
    sources: list[SourceStatusOut]


class SnapIn(BaseModel):
    geometry: Geometry = Field(description="GeoJSON Polygon drawn by hand, EPSG:4326")


class SnapOut(BaseModel):
    method: str = Field(description="parcels, edges or none")
    geometry: dict
    parcels: list[dict]
