"""The clouds and rain layer: GOES-19's newest scan over the box, painted into one PNG every
10 minutes (docs/06-goes.md#clouds-and-rain-on-the-map)."""

import json
from datetime import datetime
from pathlib import Path

import httpx

from app.config import REPO_ROOT
from app.providers.goes_s3 import download, hour_prefixes, list_keys
from app.providers.goes_weather import read_grid
from app.vision.snapshots import png
from app.vision.weather_layer import paint

WEATHER_ROOT = REPO_ROOT / "data" / "weather"
IMAGE, META = "latest.png", "latest.json"


def newest_key(client: httpx.Client, bucket: str, product: str, now: datetime) -> str | None:
    keys = [k for prefix in hour_prefixes(product, now) for k in list_keys(client, bucket, prefix)]
    return max(keys, default=None)


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
    products = [config["cloud_product"], config["rain_product"]]
    keys = {p: newest_key(client, goes["bucket"], p, now) for p in products}
    if None in keys.values():
        return {"status": "no files yet", "keys": keys}
    previous = layer_meta(root)
    if previous and previous["keys"] == keys:
        return {"status": "unchanged"}
    cloud_product, rain_product = products
    bbox, cell = config["bbox"], config["cell_degrees"]
    # Clear sky counts as height 0, so cloud edges are interpolated instead of square.
    clouds = read_grid(
        download(client, goes["bucket"], keys[cloud_product]), cloud_product, bbox, cell, clear=0
    )
    rain = read_grid(download(client, goes["bucket"], keys[rain_product]), rain_product, bbox, cell)
    root.mkdir(parents=True, exist_ok=True)
    _write(root / IMAGE, png(paint(clouds.values, rain.values, config)))
    meta = {
        "keys": keys,
        "clouds_at": clouds.scanned_at.isoformat(),
        "rain_at": rain.scanned_at.isoformat(),
        "bbox": config["bbox"],
    }
    _write(root / META, json.dumps(meta).encode())
    return {"status": "updated", "clouds_at": meta["clouds_at"], "rain_at": meta["rain_at"]}
