"""Field outlines from a year of Sentinel-2 images (docs/10-field-detection.md).

Region growing on a multi-temporal NDVI stack: a field is the connected land around the tap whose
crop history over the year matches the history at the tap.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx
import numpy as np
from affine import Affine
from rasterio.crs import CRS
from rasterio.features import shapes
from rasterio.transform import rowcol
from rasterio.warp import transform, transform_geom
from scipy import ndimage
from shapely import set_precision
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import unary_union
from skimage.filters import gaussian
from skimage.morphology import disk

from app.providers.sentinel2 import CLOUDY_CLASSES, Window, monthly_scenes, read_window

COORDINATE_PRECISION = 1e-7
# Side of the square around the tap whose median history is the field's reference, in pixels.
SEED_SIZE = 5


class DetectionError(Exception):
    """`code` is stable and translated by the frontend."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class CropHistory:
    """NDVI per clear date over a window: (dates, rows, columns)."""

    ndvi: np.ndarray
    dates: list[date]
    transform: Affine
    crs: CRS

    def pixel(self, lat: float, lon: float) -> tuple[int, int]:
        (x,), (y,) = transform("EPSG:4326", self.crs, [lon], [lat])
        return rowcol(self.transform, x, y)


@dataclass
class Detection:
    geometry: dict  # GeoJSON Polygon, EPSG:4326
    dates: list[date]


def crop_history(windows: list[tuple[date, Window]], config: dict) -> CropHistory:
    """NDVI of the dates whose window is clear, smoothed so single noisy pixels do not count."""
    clear = [
        (day, w)
        for day, w in windows
        if np.isin(w.scl, CLOUDY_CLASSES).mean() <= config["max_window_cloud_share"]
    ]
    if not clear:
        raise DetectionError("no_images")
    ndvi = np.stack(
        [
            gaussian(
                (w.nir - w.red) / np.maximum(w.nir + w.red, 1), sigma=config["smoothing_sigma"]
            )
            for _, w in clear
        ]
    ).astype("float32")
    first = clear[0][1]
    return CropHistory(ndvi, [day for day, _ in clear], first.transform, first.crs)


def grow_field(ndvi: np.ndarray, seed: tuple[int, int], config: dict) -> np.ndarray:
    """The connected pixels around `seed` whose history is within `similarity` of the seed's."""
    rows, cols = ndvi.shape[1:]
    r, c = seed
    half = SEED_SIZE // 2
    if not (half <= r < rows - half and half <= c < cols - half):
        raise DetectionError("no_field_found")
    patch = ndvi[:, r - half : r + half + 1, c - half : c + half + 1]
    reference = np.median(patch.reshape(len(ndvi), -1), axis=1)
    distance = np.sqrt(((ndvi - reference[:, None, None]) ** 2).mean(axis=0))
    similar = ndimage.binary_opening(
        distance < config["similarity"], structure=disk(config["opening_px"])
    )
    labels, _ = ndimage.label(similar)
    if labels[r, c] == 0:
        raise DetectionError("no_field_found")
    field = ndimage.binary_fill_holes(labels == labels[r, c])
    # Reaching the window's edge means no boundary was found around the tap.
    if field[0].any() or field[-1].any() or field[:, 0].any() or field[:, -1].any():
        raise DetectionError("no_field_found")
    return field


def outline(field: np.ndarray, history: CropHistory, config: dict) -> dict:
    """The region as a polygon in degrees: smoothed, simplified, and squared when it is a
    rectangle, as most fields here are."""
    # Closing fills the notches that weedy patches and single pixels leave in the edge; it can
    # also close a gap into a hole, so holes are filled after it.
    field = ndimage.binary_fill_holes(
        ndimage.binary_closing(field, structure=disk(config["closing_px"]))
    )
    pieces = [
        shape(geometry)
        for geometry, value in shapes(
            field.astype("uint8"), mask=field, transform=history.transform
        )
        if value == 1
    ]
    merged = unary_union(pieces)
    # A field is one piece without holes: the largest piece's outer ring.
    largest = max(getattr(merged, "geoms", [merged]), key=lambda piece: piece.area)
    polygon = Polygon(largest.exterior).simplify(config["simplify_m"])
    # GEOS warns on collinear edges while searching orientations; the rectangle is still valid
    # (checked on every benchmark outline).
    with np.errstate(invalid="ignore", divide="ignore"):
        rectangle = polygon.minimum_rotated_rectangle
    if polygon.area >= config["rectangle_fill"] * rectangle.area:
        polygon = rectangle
    degrees = shape(transform_geom(history.crs, "EPSG:4326", mapping(polygon)))
    # About 1 cm: the reprojection leaves 15 decimals, which map drawing tools reject.
    return mapping(set_precision(degrees, COORDINATE_PRECISION))


def load_history(
    client: httpx.Client, lat: float, lon: float, config: dict, today: date
) -> CropHistory:
    scenes = monthly_scenes(client, lat, lon, config, today)
    if not scenes:
        raise DetectionError("no_images")

    def read(scene):
        return scene.acquired, read_window(scene, lat, lon, config["window_m"], config["pixels"])

    # More parallel reads than this stall on the bucket instead of finishing sooner.
    with ThreadPoolExecutor(config["read_threads"]) as pool:
        windows = list(pool.map(read, scenes))
    return crop_history(windows, config)


def cache_path(lat: float, lon: float, cache_dir: Path) -> Path:
    """Where the window around the tap's 100 m cell is kept."""
    return cache_dir / f"{round(lat, 3):.3f}_{round(lon, 3):.3f}.npz"


def cached_history(
    client: httpx.Client, lat: float, lon: float, config: dict, today: date, cache_dir: Path
) -> CropHistory:
    """The history of the window around the tap's 100 m cell, read again after `cache_days`.

    Taps in the same cell share a window, so tapping a field again does not read the images again.
    """
    cell_lat, cell_lon = round(lat, 3), round(lon, 3)
    path = cache_path(lat, lon, cache_dir)
    if path.exists() and time.time() - path.stat().st_mtime < config["cache_days"] * 86400:
        saved = np.load(path)
        return CropHistory(
            saved["ndvi"],
            [date.fromisoformat(d) for d in saved["dates"]],
            Affine(*saved["transform"]),
            CRS.from_wkt(str(saved["crs"])),
        )
    history = load_history(client, cell_lat, cell_lon, config, today)
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        ndvi=history.ndvi,
        dates=np.array([d.isoformat() for d in history.dates]),
        transform=np.array(history.transform[:6]),
        crs=history.crs.to_wkt(),
    )
    return history


def detect_field(
    client: httpx.Client, lat: float, lon: float, config: dict, today: date, cache_dir: Path
) -> Detection:
    history = cached_history(client, lat, lon, config, today, cache_dir)
    field = grow_field(history.ndvi, history.pixel(lat, lon), config)
    return Detection(outline(field, history, config), history.dates)
