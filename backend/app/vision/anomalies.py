"""Unusual patches in a field from Sentinel-2 (docs/11-field-anomalies.md).

Each pixel is compared with the rest of its field on the same date, and that difference with the
pixel's usual difference: a harvest moves the whole field and is not unusual; a patch that dries
out while the rest stays green is.
"""

import warnings
from dataclasses import dataclass
from datetime import date

import numpy as np
from affine import Affine
from rasterio.crs import CRS
from rasterio.features import shapes
from rasterio.warp import transform_geom
from scipy import ndimage
from shapely import set_precision
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from app.models import DataQuality
from app.providers.sentinel2 import CLOUDY_CLASSES
from app.services.field_risk import compass

# Bands read for each date: NDVI (red, nir), NDWI (green, nir), NBR (nir, swir22), clouds (scl).
BANDS = ["red", "green", "nir", "swir22", "scl"]
PIXEL_HA = 0.01  # 10 m pixels
COORDINATE_PRECISION = 1e-7


@dataclass
class FieldDate:
    """Indices of one clear date over the field's box; NaN outside the field or under cloud."""

    day: date
    ndvi: np.ndarray
    ndwi: np.ndarray
    nbr: np.ndarray


@dataclass
class Patch:
    kind: str  # "less_green", "water" or "burnt"
    area_ha: float
    score: float
    where: str  # compass point from the field's center, or "center"
    geometry: dict  # GeoJSON Polygon or MultiPolygon, EPSG:4326


@dataclass
class Finding:
    data_quality: DataQuality
    last_clear: date | None
    patches: list[Patch]


def _ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a - b) / np.maximum(a + b, 1)


def field_date(
    day: date, bands: dict[str, np.ndarray], field: np.ndarray, config: dict
) -> FieldDate | None:
    """The date's indices, or None when clouds hide too much of the field."""
    cloudy = np.isin(bands["scl"], CLOUDY_CLASSES)
    if cloudy[field].mean() > config["max_field_cloud_share"]:
        return None
    hidden = ~field | cloudy

    def masked(values: np.ndarray) -> np.ndarray:
        out = values.astype("float32")
        out[hidden] = np.nan
        return out

    return FieldDate(
        day=day,
        ndvi=masked(_ratio(bands["nir"], bands["red"])),
        ndwi=masked(_ratio(bands["green"], bands["nir"])),
        nbr=masked(_ratio(bands["nir"], bands["swir22"])),
    )


def _relative(index: np.ndarray) -> np.ndarray:
    """Each pixel minus the field's median that day."""
    return index - np.nanmedian(index)


def _baseline(stack: np.ndarray, min_dates: int) -> tuple[np.ndarray, np.ndarray]:
    """Mean and spread of each pixel over earlier dates; NaN where it has too few."""
    counts = np.sum(~np.isnan(stack), axis=0)
    # Pixels outside the field are NaN on every date; their empty mean is expected.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = np.nanmean(stack, axis=0)
        spread = np.nanstd(stack, axis=0)
    mean[counts < min_dates] = np.nan
    return mean, spread


def _where(region: np.ndarray, field: np.ndarray) -> str:
    rows, cols = np.nonzero(field)
    patch_rows, patch_cols = np.nonzero(region)
    dy = rows.mean() - patch_rows.mean()  # rows grow southwards
    dx = patch_cols.mean() - cols.mean()
    reach = max(np.ptp(rows), np.ptp(cols), 1)
    if np.hypot(dx, dy) < 0.2 * reach:
        return "center"
    return compass(float(np.degrees(np.arctan2(dx, dy)) % 360))


def _patches(
    flags: np.ndarray,
    scores: np.ndarray,
    kind: str,
    field: np.ndarray,
    transform: Affine,
    crs: CRS,
    config: dict,
) -> list[Patch]:
    labels, count = ndimage.label(flags)
    found = []
    for label in range(1, count + 1):
        region = labels == label
        pixels = int(region.sum())
        if pixels < config["min_patch_pixels"]:
            continue
        pieces = [
            shape(g)
            for g, v in shapes(region.astype("uint8"), mask=region, transform=transform)
            if v == 1
        ]
        outline = unary_union(pieces).simplify(config["simplify_m"])
        degrees = shape(transform_geom(crs, "EPSG:4326", mapping(outline)))
        found.append(
            Patch(
                kind=kind,
                area_ha=round(pixels * PIXEL_HA, 1),
                score=round(float(np.nanmedian(scores[region])), 2),
                where=_where(region, field),
                geometry=mapping(set_precision(degrees, COORDINATE_PRECISION)),
            )
        )
    return sorted(found, key=lambda p: p.area_ha, reverse=True)


def find_patches(
    dates: list[FieldDate],
    field: np.ndarray,
    transform: Affine,
    crs: CRS,
    today: date,
    config: dict,
) -> Finding:
    """Patches of the latest clear date against the earlier ones (`dates` oldest first)."""
    if not dates:
        return Finding(DataQuality.NO_DATA, None, [])
    latest, earlier = dates[-1], dates[:-1]
    if (today - latest.day).days > config["clear_within_days"]:
        return Finding(DataQuality.CLOUD_OBSCURED, latest.day, [])
    if len(earlier) < config["min_baseline_dates"]:
        return Finding(DataQuality.PARTIAL, latest.day, [])

    min_dates = config["min_baseline_dates"]
    patches: list[Patch] = []

    usual, spread = _baseline(np.stack([_relative(d.ndvi) for d in earlier]), min_dates)
    drop = usual - _relative(latest.ndvi)
    spread = np.maximum(spread, config["min_spread"])
    with np.errstate(invalid="ignore"):
        less_green = (drop >= config["less_green_sigmas"] * spread) & (
            drop >= config["less_green_min_drop"]
        )
    patches += _patches(less_green, drop / spread, "less_green", field, transform, crs, config)

    usual_water, _ = _baseline(np.stack([d.ndwi for d in earlier]), min_dates)
    with np.errstate(invalid="ignore"):
        water = (latest.ndwi > config["water_ndwi"]) & (usual_water < config["dry_ndwi"])
    patches += _patches(water, latest.ndwi, "water", field, transform, crs, config)

    usual_nbr, _ = _baseline(np.stack([_relative(d.nbr) for d in earlier]), min_dates)
    burn = usual_nbr - _relative(latest.nbr)
    with np.errstate(invalid="ignore"):
        burnt = burn >= config["burnt_min_drop"]
    patches += _patches(burnt, burn, "burnt", field, transform, crs, config)

    return Finding(DataQuality.GOOD, latest.day, patches)
