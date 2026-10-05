"""Looking at every field for unusual patches, once per new Sentinel-2 scene
(docs/11-field-anomalies.md)."""

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import httpx
import numpy as np
from affine import Affine
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from rasterio.crs import CRS
from rasterio.features import rasterize
from rasterio.warp import transform_geom
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.models import DataQuality, FieldAnomaly, FieldAnomalyCheck, Territory, TerritoryKind
from app.providers.sentinel2 import Box, Scene, clearest_per_day, read_box, search
from app.vision.anomalies import BANDS, Finding, Patch, field_date, find_patches

log = logging.getLogger(__name__)

# The box read around a field, in degrees, so its edge pixels are whole.
MARGIN_DEG = 0.002
RESOLUTION_M = 10


def _cache_dir(root: Path, territory: Territory, bounds: tuple[float, ...]) -> Path:
    """One folder per field and outline: an edited outline reads its box again."""
    outline = hashlib.sha1(repr(bounds).encode()).hexdigest()[:10]
    return root / f"{territory.id}-{outline}"


def _load(path: Path) -> Box:
    saved = np.load(path)
    return Box(
        {name: saved[name].astype("float32") for name in BANDS},
        Affine(*saved["transform"]),
        CRS.from_wkt(str(saved["crs"])),
    )


def _save(path: Path, box: Box) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reflectances are integers up to 10,000 and the classes are small: uint16 loses nothing.
    np.savez_compressed(
        path,
        **{name: box.bands[name].astype("uint16") for name in BANDS},
        transform=np.array(box.transform[:6]),
        crs=box.crs.to_wkt(),
    )


def field_boxes(
    client: httpx.Client, territory: Territory, config: dict, today: date, cache_root: Path
) -> list[tuple[date, Box]]:
    """Every scene of the lookback over the field's box, reading only dates not cached."""
    outline = to_shape(territory.geom)
    west, south, east, north = outline.bounds
    bounds = (west - MARGIN_DEG, south - MARGIN_DEG, east + MARGIN_DEG, north + MARGIN_DEG)
    folder = _cache_dir(cache_root, territory, bounds)
    scenes = clearest_per_day(
        search(
            client,
            mapping(outline.envelope),
            today - timedelta(days=config["lookback_days"]),
            today,
            config["max_scene_cloud_percent"],
        )
    )

    def box_for(scene: Scene) -> tuple[date, Box]:
        path = folder / f"{scene.acquired.isoformat()}.npz"
        if path.exists():
            return scene.acquired, _load(path)
        box = read_box(scene, bounds, RESOLUTION_M, BANDS)
        _save(path, box)
        return scene.acquired, box

    # More parallel reads than this stall on the bucket instead of finishing sooner.
    with ThreadPoolExecutor(config["read_threads"]) as pool:
        return list(pool.map(box_for, scenes))


def analyze_field(
    client: httpx.Client, territory: Territory, config: dict, today: date, cache_root: Path
) -> Finding:
    boxes = field_boxes(client, territory, config, today, cache_root)
    if not boxes:
        return Finding(DataQuality.NO_DATA, None, [])
    first = boxes[-1][1]
    shape_ = next(iter(first.bands.values())).shape
    outline = transform_geom("EPSG:4326", first.crs, mapping(to_shape(territory.geom)))
    field = rasterize([outline], out_shape=shape_, transform=first.transform).astype(bool)
    dates = [
        found
        for day, box in boxes
        # A scene from another tile can land on a slightly different grid; it is left out.
        if next(iter(box.bands.values())).shape == shape_
        and (found := field_date(day, box.bands, field, config)) is not None
    ]
    return find_patches(dates, field, first.transform, first.crs, today, config)


# A satellite fire detection near the patch, between the two clear dates.
FIRE_NEAR_PATCH_SQL = text("""
    SELECT EXISTS (
        SELECT 1 FROM observation o
        WHERE NOT o.static_source
          AND o.acquired_at >= :since AND o.acquired_at < :until
          AND ST_DWithin(o.geom::geography, ST_GeomFromGeoJSON(:patch)::geography, :radius_m)
    )
""")


def confirm_burns(session: Session, finding: Finding, radius_m: float) -> Finding:
    """A burnt-looking patch is called burnt only with a fire detection near it between the two
    clear dates: freshly tilled or sprayed-off ground darkens the same index. Otherwise it is a
    less-green change, reported once even when the less-green test flagged the same ground."""
    if finding.previous_clear is None:
        return finding
    since = datetime.combine(finding.previous_clear, time.min, UTC)
    until = datetime.combine(finding.last_clear + timedelta(days=1), time.min, UTC)

    def fire_near(patch: Patch) -> bool:
        params = {"since": since, "until": until, "radius_m": radius_m}
        return bool(
            session.scalar(FIRE_NEAR_PATCH_SQL, params | {"patch": json.dumps(patch.geometry)})
        )

    burnt = [p for p in finding.patches if p.kind == "burnt" and fire_near(p)]
    unconfirmed = [p for p in finding.patches if p.kind == "burnt" and p not in burnt]
    others = [p for p in finding.patches if p.kind != "burnt"]
    if burnt:
        # A confirmed burn is the whole story of that ground.
        area = unary_union([shape(p.geometry) for p in burnt])
        others = [p for p in others if not shape(p.geometry).intersects(area)]
    less_green = unary_union([shape(p.geometry) for p in others if p.kind == "less_green"])
    relabeled = [
        replace(p, kind="less_green")
        for p in unconfirmed
        if less_green.is_empty or not shape(p.geometry).intersects(less_green)
    ]
    return replace(finding, patches=burnt + others + relabeled)


def store_finding(
    session: Session, territory_id: int, finding: Finding, now: datetime, version: str
) -> None:
    session.execute(delete(FieldAnomaly).where(FieldAnomaly.territory_id == territory_id))
    for patch in finding.patches:
        session.add(
            FieldAnomaly(
                territory_id=territory_id,
                observed_on=finding.last_clear,
                kind=patch.kind,
                area_ha=patch.area_ha,
                score=patch.score,
                where=patch.where,
                geom=WKTElement(shape(patch.geometry).wkt, srid=4326),
                processing_version=version,
            )
        )
    session.merge(
        FieldAnomalyCheck(
            territory_id=territory_id,
            checked_at=now,
            last_clear=finding.last_clear,
            data_quality=finding.data_quality,
            processing_version=version,
        )
    )
    session.commit()


def check_fields(
    session: Session,
    client: httpx.Client,
    config: dict,
    version: str,
    now: datetime,
    cache_root: Path,
) -> dict:
    """Every field (lots take their field's patches), one at a time."""
    fields = session.scalars(select(Territory).where(Territory.kind == TerritoryKind.FIELD)).all()
    checked = failed = patches = 0
    for territory in fields:
        try:
            finding = confirm_burns(
                session,
                analyze_field(client, territory, config, now.date(), cache_root),
                config["burn_fire_radius_m"],
            )
        except (httpx.HTTPError, OSError, ValueError) as exc:
            # One field's unreadable scene must not stop the others.
            log.warning("anomaly check of territory %s failed: %s", territory.id, exc)
            failed += 1
            continue
        store_finding(session, territory.id, finding, now, version)
        checked += 1
        patches += len(finding.patches)
    return {"fields_checked": checked, "fields_failed": failed, "patches": patches}
