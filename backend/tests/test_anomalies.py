from datetime import date, timedelta

import numpy as np
import pytest
import yaml
from affine import Affine
from rasterio.crs import CRS

from app.config import REPO_ROOT
from app.models import DataQuality
from app.vision.anomalies import FieldDate, field_date, find_patches

CONFIG = yaml.safe_load((REPO_ROOT / "config" / "thresholds.yaml").read_text())["anomalies"]
TODAY = date(2026, 10, 4)
# 10 m pixels in UTM zone 21S, near Larroque.
TRANSFORM = Affine(10, 0, 305000, 0, -10, 6350000)
CRS21 = CRS.from_epsg(32721)
SIZE = 80


def field_mask() -> np.ndarray:
    mask = np.zeros((SIZE, SIZE), bool)
    mask[10:70, 10:70] = True  # 36 ha
    return mask


def day(offset: int, green: float, patch: tuple[slice, slice] | None = None, **patch_values):
    """A date where the whole field has NDVI `green`, with other values in an optional patch."""
    rng = np.random.default_rng(offset)
    field = field_mask()
    values = {
        "ndvi": np.full((SIZE, SIZE), green, "float32"),
        "ndwi": np.full((SIZE, SIZE), -0.5, "float32"),
        "nbr": np.full((SIZE, SIZE), 0.4, "float32"),
    }
    for name in values:
        values[name] += rng.normal(0, 0.02, (SIZE, SIZE)).astype("float32")
        if patch and name in patch_values:
            values[name][patch] = patch_values[name]
        values[name][~field] = np.nan
    return FieldDate(TODAY - timedelta(days=offset), **values)


def history(latest: FieldDate) -> list[FieldDate]:
    # Four earlier dates as the crop grows: the whole field greens up together.
    return [day(40, 0.3), day(30, 0.45), day(20, 0.6), day(10, 0.7), latest]


def find(dates):
    return find_patches(dates, field_mask(), TRANSFORM, CRS21, TODAY, CONFIG)


def test_a_patch_drying_while_the_field_stays_green_is_found_where_it_is():
    northeast = (slice(12, 30), slice(50, 68))  # 18 x 18 pixels = 3.2 ha
    found = find(history(day(1, 0.75, northeast, ndvi=0.3)))
    assert found.data_quality == DataQuality.GOOD
    (patch,) = found.patches
    assert (patch.kind, patch.where) == ("less_green", "NE")
    assert patch.area_ha == pytest.approx(3.2, abs=0.2)
    assert patch.geometry["type"] == "Polygon"


def test_a_harvest_of_the_whole_field_is_not_unusual():
    assert find(history(day(1, 0.15))).patches == []


def test_water_and_burns_are_told_apart():
    south = (slice(50, 68), slice(20, 50))
    water = find(history(day(1, 0.7, south, ndwi=0.2, ndvi=0.1))).patches
    assert {p.kind for p in water} >= {"water"}
    burnt = find(history(day(1, 0.7, south, nbr=-0.2, ndvi=0.2))).patches
    assert {p.kind for p in burnt} >= {"burnt"}


def test_small_specks_are_not_patches():
    speck = (slice(30, 35), slice(30, 35))  # 25 pixels, a quarter hectare
    assert find(history(day(1, 0.75, speck, ndvi=0.2))).patches == []


def test_without_a_recent_clear_date_or_a_baseline_nothing_is_called_fine():
    cloudy = find([day(40, 0.3), day(30, 0.45), day(20, 0.6), day(15, 0.7)])
    assert (cloudy.data_quality, cloudy.last_clear) == (
        DataQuality.CLOUD_OBSCURED,
        TODAY - timedelta(days=15),
    )
    assert find([day(10, 0.6), day(1, 0.7)]).data_quality == DataQuality.PARTIAL
    assert find([]).data_quality == DataQuality.NO_DATA


def test_a_date_with_clouds_over_the_field_is_skipped():
    bands = {
        name: np.full((SIZE, SIZE), 1000.0, "float32") for name in ("red", "green", "nir", "swir22")
    }
    bands["scl"] = np.full((SIZE, SIZE), 4.0, "float32")  # vegetation
    assert field_date(TODAY, bands, field_mask(), CONFIG) is not None
    bands["scl"][10:40, 10:70] = 9.0  # high cloud over half the field
    assert field_date(TODAY, bands, field_mask(), CONFIG) is None
