"""ESA WorldCover 10 m land cover, read from its public cloud-optimized GeoTIFFs
(docs/15-land-cover.md). A classification of Sentinel-1 and Sentinel-2 images made by ESA with a
machine-learning model; one file per 3° square, named after its south-west corner."""

import math

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from shapely.geometry import box, mapping
from shapely.geometry.base import BaseGeometry

from app.providers.sentinel2 import GDAL_OPTIONS

SOURCE = "ESA WorldCover 10 m 2021 v200"
URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
)
# WorldCover codes, by the names the app uses.
CLASSES = {
    10: "trees",
    20: "shrubs",
    30: "grass",
    40: "crops",
    50: "built",
    60: "bare",
    70: "snow",
    80: "water",
    90: "wetland",
    95: "mangroves",
    100: "moss",
}
PIXEL_DEGREES = 1 / 12000
EARTH_M_PER_DEGREE = 111_320


def tile_name(lat: float, lon: float) -> str:
    """The 3° file holding a point: "S36W060" covers 36°S–33°S and 60°W–57°W."""
    south, west = math.floor(lat / 3) * 3, math.floor(lon / 3) * 3
    ns = f"{'S' if south < 0 else 'N'}{abs(south):02d}"
    ew = f"{'W' if west < 0 else 'E'}{abs(west):03d}"
    return ns + ew


def tiles_for(bounds: tuple[float, float, float, float]) -> list[tuple[str, BaseGeometry]]:
    """Every file a box touches, with the 3° square it covers."""
    west, south, east, north = bounds
    found = []
    for lat in range(math.floor(south / 3) * 3, math.floor(north / 3) * 3 + 1, 3):
        for lon in range(math.floor(west / 3) * 3, math.floor(east / 3) * 3 + 1, 3):
            found.append((tile_name(lat, lon), box(lon, lat, lon + 3, lat + 3)))
    return found


def pixel_m2(lat: float) -> float:
    """Ground area of one pixel at a latitude: narrower the further from the equator."""
    side = PIXEL_DEGREES * EARTH_M_PER_DEGREE
    return side * side * math.cos(math.radians(lat))


def class_counts(area: BaseGeometry) -> dict[str, int]:
    """Pixels of each class inside an area, in degrees (EPSG:4326)."""
    counts: dict[str, int] = {}
    with rasterio.Env(**GDAL_OPTIONS):
        for tile, square in tiles_for(area.bounds):
            part = area.intersection(square)
            if part.is_empty:
                continue
            with rasterio.open(f"/vsicurl/{URL.format(tile=tile)}") as src:
                window = from_bounds(*part.bounds, transform=src.transform).round_offsets()
                window = window.round_lengths()
                if window.width < 1 or window.height < 1:
                    continue
                values = src.read(1, window=window)
                outside = geometry_mask(
                    [mapping(part)],
                    out_shape=values.shape,
                    transform=src.window_transform(window),
                    all_touched=False,
                )
                codes, n = np.unique(values[~outside], return_counts=True)
                for code, count in zip(codes.tolist(), n.tolist(), strict=True):
                    name = CLASSES.get(code)
                    if name:
                        counts[name] = counts.get(name, 0) + count
    return counts
