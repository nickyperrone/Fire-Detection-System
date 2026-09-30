"""GOES fixed-grid projection: scan angles (radians) <-> latitude/longitude (degrees).

Formulas from the GOES-R Product User Guide, volume 3, section 4.2.8.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Projection:
    """The `goes_imager_projection` attributes of an ABI file."""

    perspective_point_height: float
    semi_major_axis: float
    semi_minor_axis: float
    longitude_of_projection_origin: float

    @property
    def distance_to_center(self) -> float:
        return self.perspective_point_height + self.semi_major_axis


def scan_to_latlon(x: np.ndarray, y: np.ndarray, p: Projection) -> tuple[np.ndarray, np.ndarray]:
    """Pixel scan angles to latitude and longitude. Points off the Earth come back as NaN."""
    r_eq, r_pol, h = p.semi_major_axis, p.semi_minor_axis, p.distance_to_center
    ratio = r_eq**2 / r_pol**2
    a = np.sin(x) ** 2 + np.cos(x) ** 2 * (np.cos(y) ** 2 + ratio * np.sin(y) ** 2)
    b = -2 * h * np.cos(x) * np.cos(y)
    c = h**2 - r_eq**2
    with np.errstate(invalid="ignore"):
        r_s = (-b - np.sqrt(b**2 - 4 * a * c)) / (2 * a)
    s_x = r_s * np.cos(x) * np.cos(y)
    s_y = -r_s * np.sin(x)
    s_z = r_s * np.cos(x) * np.sin(y)
    lat = np.degrees(np.arctan(ratio * s_z / np.sqrt((h - s_x) ** 2 + s_y**2)))
    lon = p.longitude_of_projection_origin - np.degrees(np.arctan(s_y / (h - s_x)))
    return lat, lon


def latlon_to_scan(
    lat: np.ndarray, lon: np.ndarray, p: Projection
) -> tuple[np.ndarray, np.ndarray]:
    """Latitude and longitude to scan angles; used to find the grid window of a bounding box."""
    r_eq, r_pol, h = p.semi_major_axis, p.semi_minor_axis, p.distance_to_center
    e2 = 1 - r_pol**2 / r_eq**2
    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon - p.longitude_of_projection_origin)
    lat_c = np.arctan(r_pol**2 / r_eq**2 * np.tan(lat_rad))
    r_c = r_pol / np.sqrt(1 - e2 * np.cos(lat_c) ** 2)
    s_x = h - r_c * np.cos(lat_c) * np.cos(lon_rad)
    s_y = -r_c * np.cos(lat_c) * np.sin(lon_rad)
    s_z = r_c * np.sin(lat_c)
    x = np.arcsin(-s_y / np.sqrt(s_x**2 + s_y**2 + s_z**2))
    y = np.arctan(s_z / s_x)
    return x, y


def grid_window(
    x: np.ndarray, y: np.ndarray, bbox: list[float], p: Projection, margin: int = 2
) -> tuple[slice, slice]:
    """Row and column slices of the grid that cover a bounding box (west, south, east, north).

    `x` grows to the east and `y` shrinks to the south, as in ABI files.
    """
    west, south, east, north = bbox
    lats = np.array([south, south, north, north])
    lons = np.array([west, east, west, east])
    xs, ys = latlon_to_scan(lats, lons, p)
    cols = np.searchsorted(x, [xs.min(), xs.max()])
    # y is descending; search it reversed and map the indexes back.
    rows = len(y) - np.searchsorted(y[::-1], [ys.max(), ys.min()])
    row_start, row_stop = max(0, rows.min() - margin), min(len(y), rows.max() + margin)
    col_start, col_stop = max(0, cols.min() - margin), min(len(x), cols.max() + margin)
    return slice(int(row_start), int(row_stop)), slice(int(col_start), int(col_stop))
