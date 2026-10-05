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
from rasterio.warp import transform, transform_bounds
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
    # Band name in the catalog (red, green, nir, swir22, scl...) to its Cloud-Optimized GeoTIFF.
    assets: dict[str, str]


@dataclass
class Window:
    red: np.ndarray
    nir: np.ndarray
    scl: np.ndarray
    transform: Affine
    crs: CRS


def search(
    client: httpx.Client, geometry: dict, start: date, end: date, max_cloud_percent: float
) -> list[Scene]:
    """Scenes over `geometry` (GeoJSON, EPSG:4326) between two dates, oldest first."""
    response = client.post(
        SEARCH_URL,
        json={
            "collections": [COLLECTION],
            "intersects": geometry,
            "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
            "query": {"eo:cloud_cover": {"lt": max_cloud_percent}},
            "limit": 200,
        },
        timeout=60,
    )
    response.raise_for_status()
    scenes = [
        Scene(
            acquired=date.fromisoformat(item["properties"]["datetime"][:10]),
            cloud_percent=item["properties"]["eo:cloud_cover"],
            assets={name: asset["href"] for name, asset in item["assets"].items()},
        )
        for item in response.json()["features"]
    ]
    return sorted(scenes, key=lambda s: s.acquired)


def clearest_per_day(scenes: list[Scene]) -> list[Scene]:
    """A field near a tile edge is in two scenes of the same pass: one per day, the clearest."""
    best: dict[date, Scene] = {}
    for scene in scenes:
        if scene.acquired not in best or scene.cloud_percent < best[scene.acquired].cloud_percent:
            best[scene.acquired] = scene
    return [best[d] for d in sorted(best)]


def monthly_scenes(
    client: httpx.Client, lat: float, lon: float, config: dict, today: date
) -> list[Scene]:
    """The clearest scene of each month over the point, for the last `months` months."""
    start = today - timedelta(days=30 * config["months"])
    point = {"type": "Point", "coordinates": [lon, lat]}
    best: dict[str, Scene] = {}
    for scene in search(client, point, start, today, config["max_scene_cloud_percent"]):
        month = scene.acquired.isoformat()[:7]
        if month not in best or scene.cloud_percent < best[month].cloud_percent:
            best[month] = scene
    return [best[m] for m in sorted(best)]


def read_window(scene: Scene, lat: float, lon: float, size_m: float, pixels: int) -> Window:
    """A `size_m` square centred on the point, resampled to `pixels` x `pixels` (10 m at 4 km)."""
    bands: dict[str, np.ndarray] = {}
    with rasterio.Env(**GDAL_OPTIONS):
        for name in ("red", "nir", "scl"):
            url = scene.assets[name]
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


@dataclass
class Box:
    """Bands read over a lon/lat box, on a regular grid in the scene's projection."""

    bands: dict[str, np.ndarray]
    transform: Affine
    crs: CRS


def read_box(
    scene: Scene, bounds: tuple[float, float, float, float], resolution_m: float, bands: list[str]
) -> Box:
    """`bands` over `bounds` (west, south, east, north in degrees) at `resolution_m`; 20 m bands
    are resampled onto the same 10 m grid."""
    out: dict[str, np.ndarray] = {}
    grid = crs = None
    with rasterio.Env(**GDAL_OPTIONS):
        for name in bands:
            with rasterio.open(scene.assets[name]) as src:
                west, south, east, north = transform_bounds("EPSG:4326", src.crs, *bounds)
                window = from_bounds(west, south, east, north, src.transform)
                if grid is None:
                    width = max(1, round((east - west) / resolution_m))
                    height = max(1, round((north - south) / resolution_m))
                    grid = src.window_transform(window) * Affine.scale(
                        window.width / width, window.height / height
                    )
                    crs = src.crs
                    shape = (height, width)
                out[name] = src.read(
                    1, window=window, out_shape=shape, resampling=Resampling.nearest
                ).astype("float32")
    return Box(out, grid, crs)
