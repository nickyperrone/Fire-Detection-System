"""The clouds and rain loop: one frame per GOES-19 scan over the box for the last two hours
(docs/06-goes.md#clouds-and-rain-on-the-map)."""

import json
from datetime import datetime
from pathlib import Path

import httpx

from app.config import REPO_ROOT
from app.providers.goes_s3 import download, hour_prefixes, list_keys, scan_of_key
from app.providers.goes_weather import read_grid
from app.vision.snapshots import png
from app.vision.weather_layer import paint

WEATHER_ROOT = REPO_ROOT / "data" / "weather"
META = "frames.json"
STAMP = "%Y%m%dT%H%M%S"
# Two hours of scans need the current hour and the two before it.
HOURS_BACK = 2


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
        _write(path, png(paint(heights.values, rates.values, config)))
        added += 1

    kept = {frame_path(root, s).name for s in wanted}
    for old in (root / "frames").glob("*.png"):
        if old.name not in kept:
            old.unlink()
    frames = [s for s in wanted if frame_path(root, s).exists()]
    meta = {"bbox": bbox, "frames": [s.isoformat() for s in frames]}
    _write(root / META, json.dumps(meta).encode())
    return {"frames": len(frames), "added": added}
