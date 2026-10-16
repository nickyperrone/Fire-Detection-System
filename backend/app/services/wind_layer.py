"""The wind over Argentina as a grid of vectors, for the animated map layer
(docs/06-goes.md#wind-on-the-map)."""

import json
import logging
from datetime import datetime
from pathlib import Path

import httpx

from app.providers.open_meteo_grid import fetch_wind

log = logging.getLogger(__name__)
FILE = "wind.json"


def grid_points(config: dict) -> tuple[list[float], list[float]]:
    """Longitudes west to east and latitudes north to south."""
    west, south, east, north = config["bbox"]
    step = config["step_degrees"]
    lons = [round(west + i * step, 4) for i in range(int((east - west) / step) + 1)]
    lats = [round(north - i * step, 4) for i in range(int((north - south) / step) + 1)]
    return lons, lats


def refresh_wind_layer(client: httpx.Client, config: dict, root: Path, now: datetime) -> dict:
    lons, lats = grid_points(config)
    points = [(lat, lon) for lat in lats for lon in lons]
    try:
        wind = fetch_wind(client, points)
    except httpx.HTTPError as exc:
        # The last grid stays on the map; it says how old it is.
        log.warning("wind grid not read: %s", exc)
        return {"wind_points": 0, "error": type(exc).__name__}
    missing = sum(v is None for v in wind)
    if missing > len(wind) // 4:
        return {"wind_points": 0, "error": "too many points missing"}
    # A missing point takes its neighbor's wind: the animation needs a full grid.
    last = (0.0, 0.0)
    filled = []
    for v in wind:
        last = v or last
        filled.append(last)
    root.mkdir(parents=True, exist_ok=True)
    body = {
        "bbox": [lons[0], lats[-1], lons[-1], lats[0]],
        "nx": len(lons),
        "ny": len(lats),
        "dx": config["step_degrees"],
        "fetched_at": now.isoformat(),
        "u": [round(v[0], 1) for v in filled],
        "v": [round(v[1], 1) for v in filled],
    }
    tmp = root / (FILE + ".tmp")
    tmp.write_text(json.dumps(body, separators=(",", ":")))
    tmp.replace(root / FILE)
    return {"wind_points": len(filled), "missing": missing}


def read_wind_layer(root: Path) -> dict | None:
    path = root / FILE
    return json.loads(path.read_text()) if path.exists() else None
