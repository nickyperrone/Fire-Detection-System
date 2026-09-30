"""Normalized records returned by providers. Services only depend on these."""

from dataclasses import dataclass
from datetime import datetime

from app.models import Confidence


@dataclass(frozen=True)
class FireObservation:
    source: str
    product: str
    satellite: str
    sensor: str
    native_id: str | None
    acquired_at: datetime
    latitude: float
    longitude: float
    confidence_raw: str
    confidence: Confidence
    frp_mw: float | None
    brightness_k: float | None
    day_night: str | None
    raw_payload: dict


@dataclass(frozen=True)
class HourlyWeather:
    time: datetime
    temperature_c: float | None
    relative_humidity_pct: float | None
    precipitation_mm: float | None
    precipitation_probability_pct: float | None
    wind_speed_kmh: float | None
    wind_direction_deg: float | None
    wind_gusts_kmh: float | None
    cloud_cover_pct: float | None
    is_day: bool | None


@dataclass(frozen=True)
class PointForecast:
    latitude: float
    longitude: float
    hours: list[HourlyWeather]
    sunrises: list[datetime]


@dataclass(frozen=True)
class LightningFlash:
    native_id: str
    observed_at: datetime
    latitude: float
    longitude: float
    energy_j: float
    area_m2: float
