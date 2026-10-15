"""The clouds and rain loop: one frame per GOES-19 scan over the box for the last two hours
(docs/06-goes.md#clouds-and-rain-on-the-map)."""

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import httpx
import numpy as np
import shapely
from scipy import ndimage
from shapely.geometry import box, shape

from app.config import REPO_ROOT
from app.providers.goes_s3 import download, hour_prefixes, list_keys, scan_of_key
from app.providers.goes_weather import grid_latitudes, read_grid
from app.vision.snapshots import png
from app.vision.weather_layer import paint

WEATHER_ROOT = REPO_ROOT / "data" / "weather"
META = "frames.json"
STAMP = "%Y%m%dT%H%M%S"
# Two hours of scans need the current hour and the two before it.
HOURS_BACK = 2


# Natural Earth draws Islas Malvinas apart from Argentina; the layer covers them too.
MALVINAS = box(-61.6, -52.5, -57.6, -50.9)


@lru_cache
def coverage(boundary: str, bbox: tuple, cell: float, buffer: float, feather: float) -> np.ndarray:
    """0 to 1 per grid cell: 1 over Argentina, Islas Malvinas and the sea around them, fading to
    0 outside, so the layer has no box edge and leaves neighboring countries clear."""
    collection = json.loads((REPO_ROOT / boundary).read_text())
    (feature,) = collection["features"]
    country = shape(feature["geometry"]).simplify(0.05).union(MALVINAS)
    area = country.buffer(buffer)
    west, _, east, _ = bbox
    lats = grid_latitudes(list(bbox), cell)
    lons = west + (np.arange(round((east - west) / cell)) + 0.5) * cell
    lat, lon = np.meshgrid(lats, lons, indexing="ij")
    inside = shapely.contains_xy(area, lon, lat).astype("float32")
    return np.clip(ndimage.gaussian_filter(inside, feather), 0, 1)


def frame_path(root: Path, scanned_at: datetime) -> Path:
    return root / "frames" / f"{scanned_at:{STAMP}}.png"


def scans(client: httpx.Client, bucket: str, product: str, now: datetime) -> dict[datetime, str]:
    """The product's files of the last hours by scan start."""
    keys = [
        key
        for prefix in hour_prefixes(product, now, HOURS_BACK)
        for key in list_keys(client, bucket, prefix)
    ]
    return {scan_of_key(key)[1]: key for key in sorted(keys)}


def layer_meta(root: Path) -> dict | None:
    path = root / META
    return json.loads(path.read_text()) if path.exists() else None


def _write(path: Path, content: bytes) -> None:
    # Written beside and renamed, so the API never serves half a file.
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_bytes(content)
    partial.replace(path)


def refresh_weather_layer(
    client: httpx.Client, thresholds: dict, root: Path, now: datetime
) -> dict:
    goes = thresholds["goes"]
    config = goes["weather_layer"]
    bucket, bbox, cell = goes["bucket"], config["bbox"], config["cell_degrees"]
    clouds = scans(client, bucket, config["cloud_product"], now)
    rain = scans(client, bucket, config["rain_product"], now)
    # Scans with both products, the newest few.
    wanted = sorted(set(clouds) & set(rain))[-config["frames_kept"] :]
    (root / "frames").mkdir(parents=True, exist_ok=True)
    # Frames drawn for another box or cell size would be stretched wrong: drawn again.
    previous = layer_meta(root)
    if previous and (previous.get("bbox") != bbox or previous.get("cell") != cell):
        for old in (root / "frames").glob("*.png"):
            old.unlink()

    mask = coverage(
        thresholds["territories"]["allowed_area"],
        tuple(bbox),
        cell,
        config["coverage_buffer_degrees"],
        config["coverage_feather_cells"],
    )
    added = 0
    for scanned_at in wanted:
        path = frame_path(root, scanned_at)
        if path.exists():
            continue
        # Clear sky counts as height 0, so cloud edges are interpolated instead of square.
        heights = read_grid(
            download(client, bucket, clouds[scanned_at]),
            config["cloud_product"],
            bbox,
            cell,
            clear=0,
        )
        rates = read_grid(
            download(client, bucket, rain[scanned_at]), config["rain_product"], bbox, cell
        )
        rgba = paint(heights.values, rates.values, config)
        rgba[..., 3] = (rgba[..., 3] * mask).round().astype("uint8")
        _write(path, png(rgba))
        added += 1

    kept = {frame_path(root, s).name for s in wanted}
    for old in (root / "frames").glob("*.png"):
        if old.name not in kept:
            old.unlink()
    frames = [s for s in wanted if frame_path(root, s).exists()]
    meta = {"bbox": bbox, "cell": cell, "frames": [s.isoformat() for s in frames]}
    _write(root / META, json.dumps(meta).encode())
    return {"frames": len(frames), "added": added}
