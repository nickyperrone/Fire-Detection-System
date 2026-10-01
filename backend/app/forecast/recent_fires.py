"""Top up the fire history after the yearly archive with the FIRMS area API (S-NPP only)."""

from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import HistoricalDetection, IngestionRun, RunStatus
from app.providers import firms
from app.providers.firms_archive import ArchiveDetection
from app.services.fire_history import store_detections
from app.services.static_sources import drop_static_history

PROVIDER = "firms_recent"
# Standard processing appears a few months after the pass; before that only near real time exists.
STANDARD_AFTER = timedelta(days=120)


def windows(start: date, end: date, size: int) -> list[tuple[date, int]]:
    """(first day, number of days) chunks covering start..end, as the area API takes them."""
    out = []
    day = start
    while day <= end:
        days = min(size, (end - day).days + 1)
        out.append((day, days))
        day += timedelta(days=days)
    return out


def fetch_window(
    client: httpx.Client,
    config: dict,
    map_key: str,
    product: str,
    bbox: list[float],
    start: date,
    days: int,
    keep_types: list[int],
) -> list[ArchiveDetection]:
    url = config["api_url"].format(
        key=map_key,
        product=product,
        bbox=",".join(str(v) for v in bbox),
        days=days,
        date=f"{start:%Y-%m-%d}",
    )
    response = client.get(url, timeout=120)
    response.raise_for_status()
    observations = firms.parse_csv(response.text, product, {"nominal_from": 30, "high_from": 80})
    return [
        ArchiveDetection(
            product, o.acquired_at, o.latitude, o.longitude, o.confidence, o.frp_mw, o.day_night
        )
        for o in observations
        # Standard processing says what each detection is; near real time does not.
        if int(o.raw_payload.get("type") or 0) in keep_types
    ]


def top_up(
    session: Session,
    client: httpx.Client,
    map_key: str,
    forecast: dict,
    bbox: list[float],
    decimals: int,
    today: date,
    keep_types: list[int],
    static_radius_m: float,
) -> IngestionRun:
    """From the day after the newest stored detection (at least the day after the archive) to
    today. The last five days are always asked again: near real time keeps filling them in."""
    config = forecast["recent_fires"]
    newest = session.scalar(select(func.max(HistoricalDetection.acquired_at)))
    archive_end = date(forecast["last_year"], 12, 31)
    start = max(
        archive_end + timedelta(days=1),
        (newest.date() if newest else archive_end) - timedelta(days=4),
    )
    run = IngestionRun(
        provider=PROVIDER, product="VIIRS_SNPP", started_at=datetime.now(UTC), fetched=0, inserted=0
    )
    try:
        for first, days in windows(start, today, config["days_per_request"]):
            old = today - (first + timedelta(days=days)) > STANDARD_AFTER
            products = [config["standard_product"]] if old else []
            products.append(config["near_real_time_product"])
            for product in products:
                detections = fetch_window(
                    client, config, map_key, product, bbox, first, days, keep_types
                )
                if detections or product == products[-1]:
                    run.fetched += len(detections)
                    if detections:
                        run.inserted += store_detections(session, detections, decimals)
                    break
            session.commit()
        drop_static_history(session, config["near_real_time_product"], static_radius_m)
        run.status = RunStatus.SUCCESS
    except (httpx.HTTPError, firms.FirmsError, KeyError, ValueError) as exc:
        session.rollback()
        run.status = RunStatus.FAILED
        message = f"{type(exc).__name__}: {exc}"
        run.error = (message.replace(map_key, "<FIRMS_MAP_KEY>") if map_key else message)[:2000]
    run.finished_at = datetime.now(UTC)
    session.add(run)
    session.commit()
    return run
