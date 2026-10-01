"""Industrial heat sources that satellites see every day (docs/03-rules.md#static-heat-sources)."""

import csv
from collections import Counter
from datetime import date
from pathlib import Path

from geoalchemy2 import WKTElement
from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import StaticSource

MARK_OBSERVATIONS_SQL = text("""
    UPDATE observation o SET static_source = true
    WHERE NOT o.static_source
      AND EXISTS (
          SELECT 1 FROM static_source s
          WHERE ST_DWithin(o.geom::geography, s.geom::geography, :radius_m)
      )
""")

DROP_HISTORY_SQL = text("""
    DELETE FROM historical_detection h
    WHERE h.product = :product
      AND EXISTS (
          SELECT 1 FROM static_source s
          WHERE ST_DWithin(h.geom::geography, s.geom::geography, :radius_m)
      )
""")


def read_static(
    path: Path, bbox: list[float], types: list[int], grid: float
) -> tuple[Counter, dict]:
    """Detections of the static types in an archive file, counted per rounded location."""
    west, south, east, north = bbox
    counts: Counter = Counter()
    last_seen: dict[tuple[float, float], date] = {}
    with path.open(newline="") as file:
        for row in csv.DictReader(file):
            if int(row["type"]) not in types:
                continue
            lat, lon = float(row["latitude"]), float(row["longitude"])
            if not (west <= lon <= east and south <= lat <= north):
                continue
            key = (round(round(lat / grid) * grid, 4), round(round(lon / grid) * grid, 4))
            counts[key] += 1
            day = date.fromisoformat(row["acq_date"])
            last_seen[key] = max(last_seen.get(key, day), day)
    return counts, last_seen


def store_static(session: Session, counts: Counter, last_seen: dict) -> int:
    if not counts:
        return 0
    rows = [
        {
            "latitude": lat,
            "longitude": lon,
            "geom": WKTElement(f"POINT({lon} {lat})", srid=4326),
            "detections": n,
            "last_seen": last_seen[(lat, lon)],
        }
        for (lat, lon), n in counts.items()
    ]
    session.execute(insert(StaticSource).values(rows))
    return len(rows)


# Events created before a source was known as static: if every detection in them is static,
# they were never fires.
CLOSE_EVENTS_SQL = text("""
    UPDATE fire_event fe SET status = 'CLOSED', updated_at = now()
    WHERE fe.status <> 'CLOSED'
      AND NOT EXISTS (
          SELECT 1 FROM observation_event_link l JOIN observation o ON o.id = l.observation_id
          WHERE l.fire_event_id = fe.id AND NOT o.static_source
      )
""")


def mark_observations(session: Session, radius_m: float) -> int:
    """Flags new detections near a static source and closes events made only of them."""
    marked = session.execute(MARK_OBSERVATIONS_SQL, {"radius_m": radius_m}).rowcount
    if marked:
        session.execute(CLOSE_EVENTS_SQL)
    return marked


def drop_static_history(session: Session, product: str, radius_m: float) -> int:
    """For products without a `type` column (near real time)."""
    return session.execute(DROP_HISTORY_SQL, {"product": product, "radius_m": radius_m}).rowcount


def rebuild_static(session: Session, paths: list[Path], bbox: list[float], config: dict) -> int:
    """Recomputes the table from every loaded archive file, so loading twice changes nothing."""
    counts: Counter = Counter()
    last_seen: dict = {}
    for path in paths:
        file_counts, file_last = read_static(path, bbox, config["types"], config["grid_degrees"])
        counts.update(file_counts)
        for key, day in file_last.items():
            last_seen[key] = max(last_seen.get(key, day), day)
    session.execute(delete(StaticSource))
    return store_static(session, counts, last_seen)
