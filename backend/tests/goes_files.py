"""Small synthetic GOES netCDF files with the same variables and attributes as the real ones."""

import numpy as np
from netCDF4 import Dataset

from app.providers.geostationary import Projection, latlon_to_scan

GOES_EAST = Projection(
    perspective_point_height=35786023.0,
    semi_major_axis=6378137.0,
    semi_minor_axis=6356752.31414,
    longitude_of_projection_origin=-75.0,
)
SIZE = 60
# About 1.5 degrees around Larroque; the region bbox of the tests lies inside it.
AREA = (-60.0, -34.0, -58.0, -32.0)


def grid() -> tuple[np.ndarray, np.ndarray]:
    west, south, east, north = AREA
    xs, ys = latlon_to_scan(np.array([south, north]), np.array([west, east]), GOES_EAST)
    return np.linspace(xs.min(), xs.max(), SIZE), np.linspace(ys.max(), ys.min(), SIZE)


def fire_file(
    mask_pixels: dict[tuple[int, int], int], start: str = "2026-09-30T14:20:20.3Z"
) -> bytes:
    """An ABI-L2-FDCF file whose Mask has the given codes at (row, col); everything else is 100."""
    x, y = grid()
    ds = Dataset("fdc", "w", memory=1024)
    ds.setncattr("time_coverage_start", start)
    ds.createDimension("x", SIZE)
    ds.createDimension("y", SIZE)
    ds.createVariable("x", "f8", ("x",))[:] = x
    ds.createVariable("y", "f8", ("y",))[:] = y
    projection = ds.createVariable("goes_imager_projection", "i4")
    for name in ("perspective_point_height", "semi_major_axis", "semi_minor_axis"):
        projection.setncattr(name, getattr(GOES_EAST, name))
    projection.setncattr("longitude_of_projection_origin", GOES_EAST.longitude_of_projection_origin)
    mask = np.full((SIZE, SIZE), 100, dtype="i2")
    for (row, col), code in mask_pixels.items():
        mask[row, col] = code
    ds.createVariable("Mask", "i2", ("y", "x"))[:] = mask
    for name, value in (("Power", 42.5), ("Temp", 600.0), ("Area", 1500.0)):
        variable = ds.createVariable(name, "f4", ("y", "x"), fill_value=-999.0)
        data = np.full((SIZE, SIZE), -999.0, dtype="f4")
        for row, col in mask_pixels:
            data[row, col] = value
        variable[:] = np.ma.masked_equal(data, -999.0)
    return bytes(ds.close())


def lightning_file(
    flashes: list[tuple[float, float, int]], start: str = "2026-09-30T14:21:00.0Z"
) -> bytes:
    """A GLM-L2-LCFA file with flashes given as (lat, lon, quality flag)."""
    ds = Dataset("glm", "w", memory=1024)
    ds.setncattr("time_coverage_start", start)
    ds.createDimension("number_of_flashes", len(flashes))
    columns = {
        "flash_lat": ("f4", [f[0] for f in flashes]),
        "flash_lon": ("f4", [f[1] for f in flashes]),
        "flash_quality_flag": ("i2", [f[2] for f in flashes]),
        "flash_id": ("i2", list(range(1, len(flashes) + 1))),
        "flash_time_offset_of_first_event": ("f4", [1.5] * len(flashes)),
        "flash_energy": ("f4", [2e-15] * len(flashes)),
        "flash_area": ("f4", [1.2e8] * len(flashes)),
    }
    for name, (dtype, values) in columns.items():
        ds.createVariable(name, dtype, ("number_of_flashes",))[:] = values
    return bytes(ds.close())
