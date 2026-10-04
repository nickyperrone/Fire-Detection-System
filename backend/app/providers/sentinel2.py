"""Sentinel-2 L2A windows from the Earth Search STAC catalog (free Copernicus data on AWS).

Only the window around a point is read from each image: the files are Cloud-Optimized GeoTIFFs,
so a 4 x 4 km window is a few range requests, not a 1 GB download.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import httpx
import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.warp import transform
from rasterio.windows import from_bounds

SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
# Scene classification values for cloud shadow, cloud (medium, high) and thin cirrus.
CLOUDY_CLASSES = (3, 8, 9, 10)
# Public bucket: no credentials, and no directory listing on open (it would be one more request).
GDAL_OPTIONS = {
    "AWS_NO_SIGN_REQUEST": "YES",
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_TIMEOUT": "30",
    "GDAL_HTTP_MAX_RETRY": "2",
}


@dataclass(frozen=True)
class Scene:
    acquired: date
    cloud_percent: float
    red_url: str
    nir_url: str
    scl_url: str


@dataclass
class Window:
    red: np.ndarray
    nir: np.ndarray
    scl: np.ndarray
    transform: Affine
    crs: CRS


def monthly_scenes(
    client: httpx.Client, lat: float, lon: float, config: dict, today: date
) -> list[Scene]:
    """The clearest scene of each month over the point, for the last `months` months."""
    start = today - timedelta(days=30 * config["months"])
    response = client.post(
        SEARCH_URL,
        json={
            "collections": [COLLECTION],
            "intersects": {"type": "Point", "coordinates": [lon, lat]},
            "datetime": f"{start.isoformat()}T00:00:00Z/{today.isoformat()}T23:59:59Z",
            "query": {"eo:cloud_cover": {"lt": config["max_scene_cloud_percent"]}},
            "limit": 200,
        },
        timeout=60,
    )
    response.raise_for_status()
    best: dict[str, Scene] = {}
    for item in response.json()["features"]:
        props, assets = item["properties"], item["assets"]
        scene = Scene(
            acquired=date.fromisoformat(props["datetime"][:10]),
            cloud_percent=props["eo:cloud_cover"],
            red_url=assets["red"]["href"],
            nir_url=assets["nir"]["href"],
            scl_url=assets["scl"]["href"],
        )
        month = scene.acquired.isoformat()[:7]
        if month not in best or scene.cloud_percent < best[month].cloud_percent:
            best[month] = scene
    return [best[m] for m in sorted(best)]


def read_window(scene: Scene, lat: float, lon: float, size_m: float, pixels: int) -> Window:
    """A `size_m` square centred on the point, resampled to `pixels` x `pixels` (10 m at 4 km)."""
    bands: dict[str, np.ndarray] = {}
    with rasterio.Env(**GDAL_OPTIONS):
        for name, url in (("red", scene.red_url), ("nir", scene.nir_url), ("scl", scene.scl_url)):
            with rasterio.open(url) as src:
                (x,), (y,) = transform("EPSG:4326", src.crs, [lon], [lat])
                half = size_m / 2
                window = from_bounds(x - half, y - half, x + half, y + half, src.transform)
                bands[name] = src.read(
                    1, window=window, out_shape=(pixels, pixels), resampling=Resampling.nearest
                ).astype("float32")
                if name == "red":
                    # The window's own transform, scaled to the resampled grid.
                    grid = src.window_transform(window) * Affine.scale(
                        window.width / pixels, window.height / pixels
                    )
                    crs = src.crs
    return Window(bands["red"], bands["nir"], bands["scl"], grid, crs)
