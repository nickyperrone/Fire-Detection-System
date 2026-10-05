"""A photo of every clear Sentinel-2 pass over each field (docs/12-field-page.md)."""

import logging
import shutil
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import httpx
from affine import Affine
from geoalchemy2.shape import to_shape
from rasterio.warp import transform_geom
from shapely.geometry import mapping, shape
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.models import FieldSnapshot, Territory
from app.services.anomalies import box_key, field_bounds, field_boxes, field_mask
from app.services.territories import natural_key
from app.vision.snapshots import greenness, pass_stats, png, true_color

log = logging.getLogger(__name__)

PHOTO_ROOT = REPO_ROOT / "data" / "snapshots"

View = Literal["true_color", "greenness"]
RENDER: dict[View, Callable] = {"true_color": true_color, "greenness": greenness}


def photo_path(root: Path, territory_id: int, day: date, view: View) -> Path:
    return root / str(territory_id) / f"{day.isoformat()}-{view}.png"


def snapshot_field(
    session: Session,
    client: httpx.Client,
    field: Territory,
    config: dict,
    version: str,
    today: date,
    cache_root: Path,
    photo_root: Path,
) -> int:
    """Keeps the passes of the lookback not kept yet; returns how many were added."""
    key = box_key(field_bounds(field))
    moved = select(FieldSnapshot).where(
        FieldSnapshot.territory_id == field.id, FieldSnapshot.box_key != key
    )
    if session.scalars(moved).first():
        # The outline was edited: the old photos show another box.
        session.execute(delete(FieldSnapshot).where(FieldSnapshot.territory_id == field.id))
        shutil.rmtree(photo_root / str(field.id), ignore_errors=True)
    kept = set(
        session.scalars(
            select(FieldSnapshot.acquired_on).where(FieldSnapshot.territory_id == field.id)
        )
    )
    added = 0
    for day, box in field_boxes(client, field, config, today, cache_root):
        if day in kept:
            continue
        stats = pass_stats(box.bands, field_mask(field, box))
        if stats.cloud_share > config["max_field_cloud_share"]:
            continue
        for view, render in RENDER.items():
            path = photo_path(photo_root, field.id, day, view)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(png(render(box.bands, config)))
        height, width = box.bands["scl"].shape
        session.add(
            FieldSnapshot(
                territory_id=field.id,
                acquired_on=day,
                box_key=key,
                width=width,
                height=height,
                grid={"crs": box.crs.to_wkt(), "transform": list(box.transform)[:6]},
                cloud_share=stats.cloud_share,
                ndvi_mean=stats.ndvi_mean,
                processing_version=version,
            )
        )
        added += 1
    session.commit()
    return added


def take_snapshots(
    session: Session,
    client: httpx.Client,
    config: dict,
    version: str,
    now: datetime,
    cache_root: Path,
    photo_root: Path,
) -> dict:
    """Every field (lots are shown on their field's photos), one at a time."""
    fields = session.scalars(select(Territory).where(Territory.parent_id.is_(None))).all()
    done = failed = added = 0
    for field in fields:
        try:
            added += snapshot_field(
                session, client, field, config, version, now.date(), cache_root, photo_root
            )
            done += 1
        except (httpx.HTTPError, OSError, ValueError) as exc:
            # One field's unreadable scene must not stop the others.
            session.rollback()
            log.warning("photos of territory %s failed: %s", field.id, exc)
            failed += 1
    # Photos of deleted fields: their rows went with the field.
    ids = {str(field.id) for field in fields}
    if photo_root.exists():
        for folder in photo_root.iterdir():
            if folder.is_dir() and folder.name not in ids:
                shutil.rmtree(folder)
    return {"fields": done, "fields_failed": failed, "photos_added": added}


def _svg_path(geometry: dict, to_pixels: Affine) -> str:
    """The outline in image pixels, as an SVG path."""
    rings = []
    polygons = shape(geometry)
    for polygon in getattr(polygons, "geoms", [polygons]):
        for ring in [polygon.exterior, *polygon.interiors]:
            points = [to_pixels @ xy for xy in ring.coords]
            rings.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in points) + "Z")
    return "".join(rings)


def field_snapshots(session: Session, territory: Territory) -> dict:
    """The photos of a field, or of a lot's field, with every outline in image pixels."""
    field = territory.parent or territory
    rows = session.scalars(
        select(FieldSnapshot)
        .where(FieldSnapshot.territory_id == field.id)
        .order_by(FieldSnapshot.acquired_on)
    ).all()
    answer = {"field_id": field.id, "width": 0, "height": 0, "outlines": [], "snapshots": []}
    if not rows:
        return answer
    latest = rows[-1]
    to_pixels = ~Affine(*latest.grid["transform"])
    outlines = [
        {
            "territory_id": t.id,
            "name": t.name,
            "kind": t.kind,
            "path": _svg_path(
                transform_geom("EPSG:4326", latest.grid["crs"], mapping(to_shape(t.geom))),
                to_pixels,
            ),
        }
        for t in [field, *sorted(field.sections, key=lambda lot: natural_key(lot.name))]
    ]
    return answer | {
        "width": latest.width,
        "height": latest.height,
        "outlines": outlines,
        "snapshots": [
            {"date": r.acquired_on, "cloud_share": r.cloud_share, "ndvi_mean": r.ndvi_mean}
            for r in rows
        ],
    }
