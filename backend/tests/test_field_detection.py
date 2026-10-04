from datetime import date

import numpy as np
import pytest
from affine import Affine
from rasterio.crs import CRS
from shapely.geometry import shape

from app.providers.sentinel2 import Window
from app.routers import fields
from app.vision.field_detection import (
    CropHistory,
    Detection,
    DetectionError,
    crop_history,
    grow_field,
    outline,
)

CONFIG = {
    "max_window_cloud_share": 0.05,
    "smoothing_sigma": 0.7,
    "similarity": 0.1,
    "opening_px": 2,
    "closing_px": 3,
    "simplify_m": 20,
    "rectangle_fill": 0.9,
}
# A year of NDVI for three kinds of land: soy, wheat then soy, and pasture.
SOY = [0.2, 0.2, 0.3, 0.6, 0.85, 0.8, 0.4, 0.2]
WHEAT_SOY = [0.7, 0.8, 0.3, 0.2, 0.5, 0.8, 0.7, 0.3]
PASTURE = [0.5, 0.5, 0.55, 0.6, 0.6, 0.55, 0.5, 0.5]


def landscape() -> np.ndarray:
    """60 x 60 pixels of pasture, with a soy field and a wheat-soy field side by side."""
    ndvi = np.empty((len(SOY), 60, 60), dtype="float32")
    ndvi[:] = np.array(PASTURE)[:, None, None]
    ndvi[:, 15:45, 10:30] = np.array(SOY)[:, None, None]
    ndvi[:, 15:45, 30:50] = np.array(WHEAT_SOY)[:, None, None]
    rng = np.random.default_rng(0)
    return ndvi + rng.normal(0, 0.02, ndvi.shape).astype("float32")


def test_the_field_under_the_tap_is_found_and_not_its_neighbor():
    field = grow_field(landscape(), (30, 20), CONFIG)
    expected = np.zeros((60, 60), bool)
    expected[15:45, 10:30] = True
    assert (field & expected).sum() / (field | expected).sum() > 0.9


def test_land_without_a_boundary_around_the_tap_is_not_a_field():
    with pytest.raises(DetectionError) as error:
        grow_field(landscape(), (5, 5), CONFIG)
    assert error.value.code == "no_field_found"


def test_cloudy_dates_are_dropped():
    clear = Window(
        np.full((4, 4), 100.0),
        np.full((4, 4), 300.0),
        np.full((4, 4), 4.0),
        Affine.identity(),
        CRS.from_epsg(32720),
    )
    cloudy = Window(clear.red, clear.nir, np.full((4, 4), 9.0), clear.transform, clear.crs)
    history = crop_history([(date(2026, 1, 5), cloudy), (date(2026, 2, 4), clear)], CONFIG)
    assert history.dates == [date(2026, 2, 4)]
    assert history.ndvi[0, 0, 0] == pytest.approx(0.5)
    with pytest.raises(DetectionError) as error:
        crop_history([(date(2026, 1, 5), cloudy)], CONFIG)
    assert error.value.code == "no_images"


def test_the_outline_has_no_holes():
    mask = np.zeros((60, 60), bool)
    mask[10:50, 10:50] = True
    mask[25:35, 25:35] = False  # a lagoon in the middle of the field
    history = CropHistory(
        np.zeros((1, 60, 60)),
        [date(2026, 1, 1)],
        Affine(10, 0, 305000, 0, -10, 6350000),
        CRS.from_epsg(32721),
    )
    assert len(outline(mask, history, CONFIG)["coordinates"]) == 1


def test_the_outline_is_a_polygon_in_degrees_with_the_field_area():
    mask = np.zeros((60, 60), bool)
    mask[15:45, 10:30] = True
    # 10 m pixels in UTM zone 21S, near Larroque.
    history = CropHistory(
        np.zeros((1, 60, 60)),
        [date(2026, 1, 1)],
        Affine(10, 0, 305000, 0, -10, 6350000),
        CRS.from_epsg(32721),
    )
    geometry = outline(mask, history, CONFIG)
    assert geometry["type"] == "Polygon"
    # A rectangle of pixels comes back as its four corners, closed.
    assert len(geometry["coordinates"][0]) == 5
    lon, lat = geometry["coordinates"][0][0]
    assert all(len(f"{c:.10f}".rstrip("0").split(".")[1]) <= 7 for c in (lon, lat))
    assert -60 < lon < -58 and -34 < lat < -32
    # 30 x 20 pixels of 100 m2: 6 ha, checked on the equal-area UTM grid via a rough degree scale.
    polygon = shape(geometry)
    hectares = polygon.area * (111_320**2) * np.cos(np.radians(lat)) / 10_000
    assert hectares == pytest.approx(6, rel=0.05)


def test_detect_needs_a_session_and_answers_codes(anonymous, client, monkeypatch):
    found = Detection(
        {
            "type": "Polygon",
            "coordinates": [[[-59.1, -33.0], [-59.09, -33.0], [-59.09, -32.99], [-59.1, -33.0]]],
        },
        [date(2025, 11, 2), date(2026, 9, 18)],
    )
    monkeypatch.setattr(fields, "detect_field", lambda *args: found)
    answer = client.post("/fields/detect", json={"lat": -32.995, "lon": -59.095}).json()
    assert (answer["dates"], answer["first"], answer["last"]) == (2, "2025-11-02", "2026-09-18")

    def nothing(*args):
        raise DetectionError("no_field_found")

    monkeypatch.setattr(fields, "detect_field", nothing)
    response = client.post("/fields/detect", json={"lat": -32.995, "lon": -59.095})
    assert (response.status_code, response.json()["code"]) == (422, "no_field_found")
