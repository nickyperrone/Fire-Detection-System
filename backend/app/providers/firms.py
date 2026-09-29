"""NASA FIRMS active fire detections (area API, CSV)."""

import csv
import io
from datetime import UTC, datetime

import httpx

from app.models import Confidence
from app.providers.records import FireObservation

AREA_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{product}/{bbox}/{days}"

SATELLITES = {
    "N": "Suomi NPP",
    "N20": "NOAA-20",
    "N21": "NOAA-21",
    "T": "Terra",
    "A": "Aqua",
    "Terra": "Terra",
    "Aqua": "Aqua",
}
VIIRS_CONFIDENCE = {
    "l": Confidence.LOW,
    "n": Confidence.NOMINAL,
    "h": Confidence.HIGH,
    "low": Confidence.LOW,
    "nominal": Confidence.NOMINAL,
    "high": Confidence.HIGH,
}
REQUIRED_COLUMNS = {"latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence"}


class FirmsError(Exception):
    """FIRMS answered, but not with a detections CSV (bad key, quota, changed format)."""


def fetch_observations(
    client: httpx.Client,
    map_key: str,
    product: str,
    bbox: list[float],
    day_range: int,
    modis_confidence: dict,
) -> list[FireObservation]:
    if not map_key:
        raise FirmsError("FIRMS_MAP_KEY is not set")
    url = AREA_URL.format(
        key=map_key, product=product, bbox=",".join(str(v) for v in bbox), days=day_range
    )
    response = client.get(url, timeout=60)
    response.raise_for_status()
    return parse_csv(response.text, product, modis_confidence)


def parse_csv(text: str, product: str, modis_confidence: dict) -> list[FireObservation]:
    reader = csv.DictReader(io.StringIO(text))
    columns = set(reader.fieldnames or [])
    # FIRMS returns HTTP 200 with a plain text message for an invalid key or an exceeded quota.
    if not REQUIRED_COLUMNS <= columns:
        raise FirmsError(f"unexpected FIRMS response: {text[:200].strip()!r}")
    return [_to_observation(row, product, modis_confidence) for row in reader]


def _to_observation(row: dict, product: str, modis_confidence: dict) -> FireObservation:
    sensor = row.get("instrument") or product.split("_")[0]
    is_modis = sensor.upper() == "MODIS"
    brightness = row.get("brightness") if is_modis else row.get("bright_ti4")
    return FireObservation(
        source="firms",
        product=product,
        satellite=SATELLITES.get(row["satellite"], row["satellite"]),
        sensor=sensor.upper(),
        native_id=None,
        acquired_at=parse_acquired_at(row["acq_date"], row["acq_time"]),
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        confidence_raw=row["confidence"],
        confidence=(
            modis_confidence_level(int(row["confidence"]), modis_confidence)
            if is_modis
            else VIIRS_CONFIDENCE[row["confidence"].strip().lower()]
        ),
        frp_mw=_float_or_none(row.get("frp")),
        brightness_k=_float_or_none(brightness),
        day_night=row.get("daynight") or None,
        raw_payload=dict(row),
    )


def parse_acquired_at(acq_date: str, acq_time: str) -> datetime:
    # acq_time is HHMM in UTC, and FIRMS drops leading zeros: "512" is 05:12.
    hhmm = acq_time.strip().zfill(4)
    day = datetime.strptime(acq_date, "%Y-%m-%d")
    return day.replace(hour=int(hhmm[:2]), minute=int(hhmm[2:]), tzinfo=UTC)


def modis_confidence_level(value: int, thresholds: dict) -> Confidence:
    if value >= thresholds["high_from"]:
        return Confidence.HIGH
    if value >= thresholds["nominal_from"]:
        return Confidence.NOMINAL
    return Confidence.LOW


def _float_or_none(value: str | None) -> float | None:
    return float(value) if value not in (None, "") else None
