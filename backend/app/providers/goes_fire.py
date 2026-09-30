"""GOES-19 ABI fire detections (ABI-L2-FDCF, full disk every 10 minutes)."""

from datetime import datetime

import numpy as np
from netCDF4 import Dataset

from app.models import Confidence
from app.providers.geostationary import Projection, grid_window, scan_to_latlon
from app.providers.records import FireObservation

CONFIDENCE_ORDER = [Confidence.LOW, Confidence.NOMINAL, Confidence.HIGH]


def mask_confidence(mask_codes: dict[str, list[int]]) -> dict[int, Confidence]:
    return {code: Confidence(level) for level, codes in mask_codes.items() for code in codes}


def scan_start(dataset: Dataset) -> datetime:
    # "2026-09-30T00:20:20.3Z"
    return datetime.fromisoformat(dataset.getncattr("time_coverage_start").replace("Z", "+00:00"))


def projection_of(dataset: Dataset) -> Projection:
    attrs = dataset["goes_imager_projection"]
    return Projection(
        perspective_point_height=float(attrs.perspective_point_height),
        semi_major_axis=float(attrs.semi_major_axis),
        semi_minor_axis=float(attrs.semi_minor_axis),
        longitude_of_projection_origin=float(attrs.longitude_of_projection_origin),
    )


def parse_fire_file(
    content: bytes, bbox: list[float], mask_codes: dict[str, list[int]], min_confidence: str
) -> list[FireObservation]:
    """Fire pixels inside the bounding box, at or above `min_confidence`."""
    confidence_of = mask_confidence(mask_codes)
    minimum = CONFIDENCE_ORDER.index(Confidence(min_confidence))
    kept_codes = [
        c for c, level in confidence_of.items() if CONFIDENCE_ORDER.index(level) >= minimum
    ]
    with Dataset("goes-fdc", memory=content) as dataset:
        started = scan_start(dataset)
        projection = projection_of(dataset)
        x, y = dataset["x"][:].filled(np.nan), dataset["y"][:].filled(np.nan)
        rows, cols = grid_window(x, y, bbox, projection)
        mask = dataset["Mask"][rows, cols].filled(0)
        fire_rows, fire_cols = np.nonzero(np.isin(mask, kept_codes))
        if fire_rows.size == 0:
            return []
        power = dataset["Power"][rows, cols]
        temperature = dataset["Temp"][rows, cols]
        area = dataset["Area"][rows, cols]
        lat, lon = scan_to_latlon(x[cols][fire_cols], y[rows][fire_rows], projection)

    west, south, east, north = bbox
    observations = []
    for i, (r, c) in enumerate(zip(fire_rows, fire_cols, strict=True)):
        # The window is a rectangle in scan angles; trim it to the exact bounding box.
        if not (west <= lon[i] <= east and south <= lat[i] <= north):
            continue
        row, col = int(r + rows.start), int(c + cols.start)
        code = int(mask[r, c])
        observations.append(
            FireObservation(
                source="goes",
                product="ABI-L2-FDCF",
                satellite="GOES-19",
                sensor="ABI",
                native_id=f"{started:%Y%m%dT%H%M%S}:{row}:{col}",
                acquired_at=started,
                latitude=round(float(lat[i]), 5),
                longitude=round(float(lon[i]), 5),
                confidence_raw=str(code),
                confidence=confidence_of[code],
                frp_mw=_value(power[r, c]),
                brightness_k=_value(temperature[r, c]),
                day_night=None,
                raw_payload={"mask": code, "row": row, "col": col, "area_m2": _value(area[r, c])},
            )
        )
    return observations


def _value(masked) -> float | None:
    return None if np.ma.is_masked(masked) else round(float(masked), 2)
