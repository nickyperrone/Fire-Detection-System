"""GOES-19 fire and lightning ingestion from S3 files, continuing from the last processed key."""

from collections.abc import Callable
from datetime import datetime, timedelta

import httpx
from geoalchemy2 import WKTElement
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import IngestionRun, LightningFlash, RunStatus
from app.providers import goes_s3
from app.providers.goes_fire import parse_fire_file
from app.providers.goes_lightning import parse_lightning_file
from app.providers.records import LightningFlash as FlashRecord
from app.services.fire_ingestion import store_observations

# With no cursor yet, start from the newest files instead of two hours of backlog:
# 3 fire scans (30 min) and 9 lightning files (3 min).
FIRST_RUN_FILES = {"fire": 3, "lightning": 9}


def last_cursor(session: Session, provider: str, product: str) -> str | None:
    return session.scalar(
        select(IngestionRun.cursor)
        .where(
            IngestionRun.provider == provider,
            IngestionRun.product == product,
            IngestionRun.cursor.is_not(None),
        )
        .order_by(IngestionRun.finished_at.desc())
        .limit(1)
    )


def _ingest_files(
    session: Session,
    client: httpx.Client,
    product: str,
    first_run: int,
    store: Callable[[bytes], tuple[int, int]],
    bucket: str,
    now: datetime,
) -> IngestionRun:
    """Downloads every new file and hands it to `store`, which returns (fetched, inserted).

    The cursor advances file by file, so a failure halfway keeps the progress made.
    """
    run = IngestionRun(provider="goes", product=product, started_at=now, fetched=0, inserted=0)
    run.cursor = last_cursor(session, "goes", product)
    try:
        keys = goes_s3.new_keys(client, bucket, product, now, run.cursor, first_run)
        for key in keys:
            fetched, inserted = store(goes_s3.download(client, bucket, key))
            run.fetched += fetched
            run.inserted += inserted
            run.cursor = key
        run.status = RunStatus.SUCCESS
    except (httpx.HTTPError, OSError, KeyError, ValueError) as exc:
        # netCDF4 raises OSError for a truncated or corrupt file.
        run.status = RunStatus.FAILED
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
    run.finished_at = datetime.now(now.tzinfo)
    session.add(run)
    session.commit()
    return run


def ingest_goes_fire(
    session: Session, client: httpx.Client, thresholds: dict, now: datetime
) -> IngestionRun:
    goes, bbox = thresholds["goes"], thresholds["region"]["bbox"]
    decimals = thresholds["firms"]["dedup_coordinate_decimals"]

    def store(content: bytes) -> tuple[int, int]:
        observations = parse_fire_file(
            content, bbox, goes["fire_mask_confidence"], goes["min_confidence"]
        )
        return len(observations), store_observations(session, observations, now, decimals)

    return _ingest_files(
        session, client, goes["fire_product"], FIRST_RUN_FILES["fire"], store, goes["bucket"], now
    )


def store_flashes(session: Session, flashes: list[FlashRecord], ingested_at: datetime) -> int:
    if not flashes:
        return 0
    rows = [
        {
            "native_id": f.native_id,
            "observed_at": f.observed_at,
            "ingested_at": ingested_at,
            "geom": WKTElement(f"POINT({f.longitude} {f.latitude})", srid=4326),
            "energy_j": f.energy_j,
            "area_m2": f.area_m2,
        }
        for f in flashes
    ]
    statement = (
        insert(LightningFlash).values(rows).on_conflict_do_nothing().returning(LightningFlash.id)
    )
    return len(session.execute(statement).all())


def ingest_lightning(
    session: Session, client: httpx.Client, thresholds: dict, now: datetime
) -> IngestionRun:
    goes, bbox = thresholds["goes"], thresholds["region"]["bbox"]

    def store(content: bytes) -> tuple[int, int]:
        flashes = parse_lightning_file(content, bbox)
        return len(flashes), store_flashes(session, flashes, now)

    run = _ingest_files(
        session,
        client,
        goes["lightning_product"],
        FIRST_RUN_FILES["lightning"],
        store,
        goes["bucket"],
        now,
    )
    keep_since = now - timedelta(days=thresholds["lightning"]["keep_days"])
    session.execute(delete(LightningFlash).where(LightningFlash.observed_at < keep_since))
    session.commit()
    return run
