"""Photos of a field from one Sentinel-2 pass (docs/12-field-page.md#satellite-photos).

Every date uses the same brightness and the same greenness scale, so photos of different dates can
be compared: a field that looks browner really is browner.
"""

import warnings
from dataclasses import dataclass

import numpy as np
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile

from app.providers.sentinel2 import CLOUDY_CLASSES

# Greenness from bare soil to dense crop, as (position on the scale, RGB).
GREENNESS_RAMP = [
    (0.0, (120, 92, 62)),
    (0.3, (196, 170, 104)),
    (0.55, (142, 182, 84)),
    (0.8, (58, 140, 66)),
    (1.0, (22, 88, 48)),
]
CLOUD_GRAY = (150, 155, 162)


@dataclass
class PassStats:
    cloud_share: float
    # Mean NDVI of the clear part of the field; None when nothing of it is clear.
    ndvi_mean: float | None


def _ndvi(bands: dict[str, np.ndarray]) -> np.ndarray:
    nir, red = bands["nir"].astype("float32"), bands["red"].astype("float32")
    return (nir - red) / np.maximum(nir + red, 1)


def pass_stats(bands: dict[str, np.ndarray], field: np.ndarray) -> PassStats:
    cloudy = np.isin(bands["scl"], CLOUDY_CLASSES)
    clear = field & ~cloudy
    return PassStats(
        cloud_share=round(float(cloudy[field].mean()), 3),
        ndvi_mean=round(float(_ndvi(bands)[clear].mean()), 3) if clear.any() else None,
    )


def true_color(bands: dict[str, np.ndarray], config: dict) -> np.ndarray:
    """Red, green and blue as the eye would see them, as an (height, width, 3) uint8 array."""
    rgb = np.stack([bands[name] for name in ("red", "green", "blue")], axis=-1)
    scaled = np.clip(rgb.astype("float32") / 10_000 * config["true_color_gain"], 0, 1)
    return (scaled ** (1 / config["true_color_gamma"]) * 255).round().astype("uint8")


def greenness(bands: dict[str, np.ndarray], config: dict) -> np.ndarray:
    """NDVI painted on the ramp above; clouds and their shadows in gray."""
    low, high = config["greenness_min"], config["greenness_max"]
    position = np.clip((_ndvi(bands) - low) / (high - low), 0, 1)
    stops = [stop for stop, _ in GREENNESS_RAMP]
    rgb = np.stack(
        [np.interp(position, stops, [color[i] for _, color in GREENNESS_RAMP]) for i in range(3)],
        axis=-1,
    )
    rgb[np.isin(bands["scl"], CLOUDY_CLASSES)] = CLOUD_GRAY
    return rgb.round().astype("uint8")


def png(rgb: np.ndarray) -> bytes:
    height, width, _ = rgb.shape
    # A plain picture: it has no place on Earth, and that is fine.
    with warnings.catch_warnings(), MemoryFile() as memory:
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with memory.open(driver="PNG", width=width, height=height, count=3, dtype="uint8") as image:
            image.write(np.moveaxis(rgb, -1, 0))
        return memory.read()
