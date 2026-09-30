"""GOES-19 GLM lightning flashes (GLM-L2-LCFA, one file every 20 seconds)."""

from datetime import timedelta

import numpy as np
from netCDF4 import Dataset

from app.providers.goes_fire import scan_start
from app.providers.records import LightningFlash

GOOD_QUALITY = 0


def parse_lightning_file(content: bytes, bbox: list[float]) -> list[LightningFlash]:
    """Good-quality flashes inside the bounding box. Groups and events are not kept."""
    west, south, east, north = bbox
    with Dataset("goes-glm", memory=content) as dataset:
        started = scan_start(dataset)
        lat = dataset["flash_lat"][:].filled(np.nan)
        lon = dataset["flash_lon"][:].filled(np.nan)
        quality = dataset["flash_quality_flag"][:].filled(-1)
        keep = (
            (quality == GOOD_QUALITY)
            & (lon >= west)
            & (lon <= east)
            & (lat >= south)
            & (lat <= north)
        )
        ids = dataset["flash_id"][:][keep]
        offsets = dataset["flash_time_offset_of_first_event"][:][keep]
        energy = dataset["flash_energy"][:][keep]
        area = dataset["flash_area"][:][keep]
        lat, lon = lat[keep], lon[keep]
    return [
        LightningFlash(
            native_id=f"{started:%Y%m%dT%H%M%S}:{int(ids[i])}",
            observed_at=started + timedelta(seconds=float(offsets[i])),
            latitude=round(float(lat[i]), 5),
            longitude=round(float(lon[i]), 5),
            energy_j=float(energy[i]),
            area_m2=float(area[i]),
        )
        for i in range(len(ids))
    ]
