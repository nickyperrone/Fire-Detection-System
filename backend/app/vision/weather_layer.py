"""Clouds and rain painted for the map (docs/06-goes.md#clouds-and-rain-on-the-map): white
clouds, more opaque the higher their tops, and rain on top in blues and violet."""

import numpy as np
from scipy import ndimage

CLOUD_RGB = (236, 240, 245)
# Faintest and most opaque cloud.
CLOUD_ALPHA = (0.22, 0.8)
# One color per rain band, lightest first, and how opaque rain is drawn.
RAIN_RGB = [(125, 185, 255), (37, 99, 235), (147, 51, 234)]
RAIN_ALPHA = 0.85


def paint(cloud_height_m: np.ndarray, rain_mm_h: np.ndarray, config: dict) -> np.ndarray:
    """An (height, width, 4) uint8 RGBA image; transparent where it is clear and dry.
    `cloud_height_m` is 0 where it is clear, and in between at the edges of clouds."""
    low, high = CLOUD_ALPHA
    tops = np.clip(cloud_height_m / config["cloud_full_height_m"], 0, 1)
    # The edge of a cloud fades from nothing instead of starting at the faintest cloud.
    edge = np.clip(cloud_height_m / config["cloud_edge_height_m"], 0, 1)
    cloud = edge * (low + (high - low) * tops)
    cloud = ndimage.gaussian_filter(cloud, config["cloud_blur_cells"])

    rgba = np.zeros((*cloud.shape, 4), "float32")
    rgba[..., :3] = CLOUD_RGB
    rgba[..., 3] = cloud
    rain = np.nan_to_num(rain_mm_h)
    for start, color in zip(config["rain_bands_mm_h"], RAIN_RGB, strict=True):
        band = rain >= start
        rgba[band, :3] = color
        rgba[band, 3] = RAIN_ALPHA
    rgba[..., 3] *= 255
    return rgba.round().astype("uint8")
