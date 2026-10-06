"""Clouds and rain painted for the map (docs/06-goes.md#clouds-and-rain-on-the-map): clouds as a
faint veil, a little stronger the higher their tops, and rain on top in blues and violet, which
is what stands out."""

import numpy as np
from scipy import ndimage

CLOUD_RGB = (240, 244, 248)
# Opacity of the lowest and of the highest clouds: enough to see where it is cloudy, never a
# gray sheet over the map.
VEIL_ALPHA = (0.08, 0.26)
# One color per rain band, lightest first, each with its opacity.
RAIN_RGB = [(96, 165, 250), (37, 99, 235), (168, 85, 247)]
RAIN_ALPHA = [0.7, 0.85, 0.9]


def paint(cloud_height_m: np.ndarray, rain_mm_h: np.ndarray, config: dict) -> np.ndarray:
    """An (height, width, 4) uint8 RGBA image; transparent where it is clear and dry.
    `cloud_height_m` is 0 where it is clear, and in between at the edges of clouds."""
    low, high = VEIL_ALPHA
    tops = np.clip(cloud_height_m / config["cloud_full_height_m"], 0, 1)
    # The edge of a cloud fades from nothing instead of starting at the veil.
    edge = np.clip(cloud_height_m / config["cloud_edge_height_m"], 0, 1)
    cloud = edge * (low + (high - low) * tops)
    cloud = ndimage.gaussian_filter(cloud, config["cloud_blur_cells"])

    rgba = np.zeros((*cloud.shape, 4), "float32")
    rgba[..., :3] = CLOUD_RGB
    rgba[..., 3] = cloud
    rain = np.nan_to_num(rain_mm_h)
    for start, color, alpha in zip(config["rain_bands_mm_h"], RAIN_RGB, RAIN_ALPHA, strict=True):
        band = rain >= start
        rgba[band, :3] = color
        rgba[band, 3] = alpha
    rgba[..., 3] *= 255
    return rgba.round().astype("uint8")
