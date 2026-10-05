"""Ten years of fire near each field (docs/07-fire-history.md)."""

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from itertools import batched
from pathlib import Path

import httpx
from geoalchemy2 import WKTElement
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import HistoricalDetection, IngestionRun, RunStatus
from app.providers import firms_archive
from app.providers.firms_archive import ArchiveDetection
from app.services.static_sources import rebuild_static

PROVIDER = "firms_archive"
BATCH_ROWS = 5_000

# Days in Argentina time: a fire at 01:00 UTC belongs to the evening before for the user.
# A degree of longitude in metres at Argentina's southern tip (55° S), the shortest it gets in the
# country: a box this many degrees wide always holds the whole radius.
METERS_PER_DEGREE_SOUTHERNMOST = 63_800

FIRE_DAYS_SQL = text("""
    WITH t AS (SELECT geom FROM territory WHERE id = :territory_id)
    SELECT (h.acquired_at AT TIME ZONE 'America/Argentina/Buenos_Aires')::date AS day,
           min(ST_Distance(t.geom::geography, h.geom::geography)) AS nearest_m,
           bool_or(ST_Intersects(t.geom, h.geom)) AS inside
    FROM historical_detection h, t
    -- The box first, so the spatial index answers; then the exact distance.
    WHERE h.geom && ST_Expand(t.geom, :radius_deg)
      AND ST_DWithin(t.geom::geography, h.geom::geography, :radius_m)
      AND h.acquired_at >= :since AND h.acquired_at < :until
    GROUP BY day
    ORDER BY day
""")


def dedup_key(d: ArchiveDetection, decimals: int) -> str:
    parts = [
        d.product,
        d.acquired_at.isoformat(),
        f"{d.latitude:.{decimals}f}",
        f"{d.longitude:.{decimals}f}",
    ]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def store_detections(session: Session, detections: list[ArchiveDetection], decimals: int) -> int:
    rows = [
        {
            "product": d.product,
            "dedup_key": dedup_key(d, decimals),
            "acquired_at": d.acquired_at,
            "geom": WKTElement(f"POINT({d.longitude} {d.latitude})", srid=4326),
            "confidence": d.confidence,
            "frp_mw": d.frp_mw,
            "day_night": d.day_night,
        }
        for d in detections
    ]
    statement = (
        insert(HistoricalDetection)
        .values(rows)
        .on_conflict_do_nothing()
        .returning(HistoricalDetection.id)
    )
    return len(session.execute(statement).all())


def load_history(
    session: Session,
    client: httpx.Client,
    config: dict,
    bbox: list[float],
    decimals: int,
    root: Path,
    static: dict | None = None,
) -> list[IngestionRun]:
    """Downloads (once) and loads every configured year. A failed year does not stop the rest."""
    runs, paths = [], []
    for year in range(config["first_year"], config["last_year"] + 1):
        now = datetime.now(UTC)
        run = IngestionRun(
            provider=PROVIDER,
            product=f"{config['product']}_{year}",
            started_at=now,
            fetched=0,
            inserted=0,
        )
        url = firms_archive.archive_url(config["url"], config["product"], year, config["country"])
        try:
            path = firms_archive.download_year(client, url, root / config["cache_dir"])
            detections = firms_archive.read_detections(
                path, config["product"], bbox, config["keep_types"]
            )
            for batch in batched(detections, BATCH_ROWS):
                run.fetched += len(batch)
                run.inserted += store_detections(session, list(batch), decimals)
            paths.append(path)
            run.status = RunStatus.SUCCESS
        except (httpx.HTTPError, OSError, KeyError, ValueError) as exc:
            session.rollback()
            run.status = RunStatus.FAILED
            run.error = f"{type(exc).__name__}: {exc}"[:2000]
        run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        runs.append(run)
    if static is not None:
        rebuild_static(session, paths, bbox, static)
        session.commit()
    return runs


def loaded_years(session: Session, product: str) -> list[int]:
    products = session.scalars(
        select(IngestionRun.product)
        .where(IngestionRun.provider == PROVIDER, IngestionRun.status == RunStatus.SUCCESS)
        .distinct()
    ).all()
    prefix = f"{product}_"
    return sorted(int(p.removeprefix(prefix)) for p in products if p.startswith(prefix))


@dataclass(frozen=True)
class FireDay:
    day: date
    distance_m: float


@dataclass
class FireHistory:
    first_year: int
    last_year: int
    radius_m: int
    years_loaded: list[int]
    fire_days: int = 0
    inside_days: int = 0
    days_per_year: dict[int, int] = field(default_factory=dict)
    days_per_month: list[int] = field(default_factory=lambda: [0] * 12)
    nearest: FireDay | None = None
    latest: FireDay | None = None


def field_history(session: Session, territory_id: int, config: dict) -> FireHistory:
    first, last = config["first_year"], config["last_year"]
    history = FireHistory(
        first_year=first,
        last_year=last,
        radius_m=config["radius_m"],
        years_loaded=[y for y in loaded_years(session, config["product"]) if first <= y <= last],
    )
    rows = session.execute(
        FIRE_DAYS_SQL,
        {
            "territory_id": territory_id,
            "radius_m": config["radius_m"],
            "radius_deg": config["radius_m"] / METERS_PER_DEGREE_SOUTHERNMOST,
            "since": datetime(first, 1, 1, tzinfo=UTC),
            "until": datetime(last + 1, 1, 1, tzinfo=UTC),
        },
    ).all()
    per_year = Counter(r.day.year for r in rows)
    history.days_per_year = {y: per_year.get(y, 0) for y in history.years_loaded}
    for r in rows:
        history.days_per_month[r.day.month - 1] += 1
    history.fire_days = len(rows)
    history.inside_days = sum(1 for r in rows if r.inside)
    if rows:
        closest = min(rows, key=lambda r: (r.nearest_m, r.day))
        history.nearest = FireDay(closest.day, closest.nearest_m)
        history.latest = FireDay(rows[-1].day, rows[-1].nearest_m)
    return history
