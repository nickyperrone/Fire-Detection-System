"""GOES-19 cloud top height (ABI-L2-ACHAF) and rainfall rate (ABI-L2-RRQPEF) on a lat/lon grid,
for the clouds and rain layer of the map (docs/06-goes.md#clouds-and-rain-on-the-map)."""

from dataclasses import dataclass
from datetime import datetime

import numpy as np
from netCDF4 import Dataset
from scipy import ndimage

from app.providers.geostationary import grid_window, latlon_to_scan
from app.providers.goes_fire import projection_of, scan_start

VARIABLE = {"ABI-L2-ACHAF": "HT", "ABI-L2-RRQPEF": "RRQPE"}


@dataclass
class Grid:
    """Values over the box, north row first; NaN where the product has none. Columns are even in
    longitude and rows even in Web Mercator, as the map stretches an image between its corners
    in that projection: rows even in latitude would put rain tens of km off mid-box."""

    values: np.ndarray
    scanned_at: datetime


def _mercator_y(lat: np.ndarray | float) -> np.ndarray:
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


def grid_latitudes(bbox: list[float], cell: float) -> np.ndarray:
    """Row centers, north first, about `cell` degrees apart and evenly spaced in Web Mercator."""
    _, south, _, north = bbox
    rows = round((north - south) / cell)
    top, bottom = _mercator_y(north), _mercator_y(south)
    y = top - (np.arange(rows) + 0.5) * (top - bottom) / rows
    return np.degrees(2 * np.arctan(np.exp(y)) - np.pi / 2)


def read_grid(
    content: bytes, product: str, bbox: list[float], cell: float, clear: float | None = None
) -> Grid:
    """The product's variable on the grid: from the nearest satellite pixel, or, given a `clear`
    value for pixels without one, interpolated between pixels, for coarse products whose
    pixels would otherwise show as squares."""
    with Dataset(product, memory=content) as dataset:
        started = scan_start(dataset)
        projection = projection_of(dataset)
        x, y = dataset["x"][:].filled(np.nan), dataset["y"][:].filled(np.nan)
        rows, cols = grid_window(x, y, bbox, projection)
        window = dataset[VARIABLE[product]][rows, cols].astype("float32").filled(np.nan)
        xs, ys = x[cols], y[rows]

    west, _, east, _ = bbox
    lats = grid_latitudes(bbox, cell)
    lons = west + (np.arange(round((east - west) / cell)) + 0.5) * cell
    height, width = lats.size, lons.size
    lat, lon = np.meshgrid(lats, lons, indexing="ij")
    scan_x, scan_y = latlon_to_scan(lat, lon, projection)
    # Scan angles are evenly spaced (y decreasing to the south): a pixel index is a division.
    col = (scan_x - xs[0]) / (xs[1] - xs[0])
    row = (scan_y - ys[0]) / (ys[1] - ys[0])
    if clear is not None:
        filled = np.where(np.isnan(window), clear, window)
        values = ndimage.map_coordinates(filled, [row, col], order=1, cval=clear)
        return Grid(values.astype("float32"), started)
    col, row = np.rint(col).astype(int), np.rint(row).astype(int)
    inside = (col >= 0) & (col < xs.size) & (row >= 0) & (row < ys.size)
    values = np.full((height, width), np.nan, "float32")
    values[inside] = window[row[inside], col[inside]]
    return Grid(values, started)
