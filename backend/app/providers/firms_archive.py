"""FIRMS yearly country archive (standard processing), for fire history."""

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

from app.models import Confidence
from app.providers.firms import VIIRS_CONFIDENCE, parse_acquired_at


@dataclass(frozen=True)
class ArchiveDetection:
    product: str
    acquired_at: datetime
    latitude: float
    longitude: float
    confidence: Confidence
    frp_mw: float | None
    day_night: str | None


def archive_url(template: str, product: str, year: int, country: str) -> str:
    return template.format(product=product, year=year, country=country)


def download_year(client: httpx.Client, url: str, cache_dir: Path) -> Path:
    """The year's CSV, downloaded once. A partial download never replaces a complete file."""
    target = cache_dir / url.rsplit("/", 1)[-1]
    if target.exists():
        return target
    cache_dir.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    with client.stream("GET", url, timeout=300, follow_redirects=True) as response:
        response.raise_for_status()
        with partial.open("wb") as file:
            for chunk in response.iter_bytes():
                file.write(chunk)
    partial.rename(target)
    return target


def read_detections(
    path: Path, product: str, bbox: list[float], keep_types: list[int]
) -> Iterator[ArchiveDetection]:
    """Rows of the kept types inside the bounding box, streamed: a year is ~170,000 rows."""
    west, south, east, north = bbox
    with path.open(newline="") as file:
        for row in csv.DictReader(file):
            if int(row["type"]) not in keep_types:
                continue
            lat, lon = float(row["latitude"]), float(row["longitude"])
            if not (west <= lon <= east and south <= lat <= north):
                continue
            yield ArchiveDetection(
                product=product,
                acquired_at=parse_acquired_at(row["acq_date"], row["acq_time"]),
                latitude=lat,
                longitude=lon,
                confidence=VIIRS_CONFIDENCE[row["confidence"].strip().lower()],
                frp_mw=float(row["frp"]) if row["frp"] else None,
                day_night=row.get("daynight") or None,
            )
