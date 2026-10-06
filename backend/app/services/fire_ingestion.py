import hashlib
from datetime import datetime

import httpx
from geoalchemy2 import WKTElement
from shapely.prepared import PreparedGeometry
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.boundaries import country_area, inside
from app.models import IngestionRun, Observation, RunStatus
from app.providers import firms
from app.providers.records import FireObservation
from app.services.watched_areas import watched_areas


def dedup_key(observation: FireObservation, decimals: int) -> str:
    parts = [
        observation.product,
        observation.satellite,
        observation.acquired_at.isoformat(),
        f"{observation.latitude:.{decimals}f}",
        f"{observation.longitude:.{decimals}f}",
    ]
    return hashlib.sha1("|".join(parts).encode()).hexdigest()


def store_observations(
    session: Session,
    observations: list[FireObservation],
    ingested_at: datetime,
    decimals: int,
    area: PreparedGeometry,
) -> int:
    """Insert new observations inside `area` (Argentina) and return how many were new.
    Duplicates are ignored."""
    observations = [o for o in observations if inside(area, o.latitude, o.longitude)]
    if not observations:
        return 0
    rows = [
        {
            "source": o.source,
            "product": o.product,
            "satellite": o.satellite,
            "sensor": o.sensor,
            "native_id": o.native_id,
            "dedup_key": dedup_key(o, decimals),
            "acquired_at": o.acquired_at,
            "ingested_at": ingested_at,
            "geom": WKTElement(f"POINT({o.longitude} {o.latitude})", srid=4326),
            "confidence_raw": o.confidence_raw,
            "confidence": o.confidence,
            "frp_mw": o.frp_mw,
            "brightness_k": o.brightness_k,
            "day_night": o.day_night,
            "raw_payload": o.raw_payload,
        }
        for o in observations
    ]
    # No conflict target: skips rows that clash on dedup_key or on (source, native_id).
    statement = insert(Observation).values(rows).on_conflict_do_nothing().returning(Observation.id)
    return len(session.execute(statement).all())


def ingest_firms(
    session: Session, client: httpx.Client, map_key: str, thresholds: dict, now: datetime
) -> list[IngestionRun]:
    """Read every FIRMS product over every watched area. A failed product does not stop the
    rest."""
    config = thresholds["firms"]
    area = country_area(thresholds)
    boxes = watched_areas(session, thresholds)
    runs = []
    for product in config["products"]:
        run = IngestionRun(provider="firms", product=product, started_at=now)
        try:
            observations = [
                observation
                for box in boxes
                for observation in firms.fetch_observations(
                    client,
                    map_key,
                    product,
                    list(box),
                    config["day_range"],
                    config["modis_confidence"],
                )
            ]
        except (httpx.HTTPError, firms.FirmsError, KeyError, ValueError) as exc:
            run.status = RunStatus.FAILED
            # httpx errors include the request URL, and the FIRMS key is part of the path.
            message = f"{type(exc).__name__}: {exc}"
            run.error = (message.replace(map_key, "<FIRMS_MAP_KEY>") if map_key else message)[:2000]
        else:
            run.status = RunStatus.SUCCESS
            run.fetched = len(observations)
            run.inserted = store_observations(
                session, observations, now, config["dedup_coordinate_decimals"], area
            )
        run.finished_at = datetime.now(now.tzinfo)
        session.add(run)
        session.commit()
        runs.append(run)
    return runs
