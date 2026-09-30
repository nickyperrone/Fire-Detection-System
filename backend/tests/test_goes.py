from datetime import UTC, datetime

import numpy as np
import pytest

from app.models import Confidence
from app.providers.geostationary import latlon_to_scan, scan_to_latlon
from app.providers.goes_fire import parse_fire_file
from app.providers.goes_lightning import parse_lightning_file
from app.providers.goes_s3 import hour_prefixes
from tests.goes_files import GOES_EAST, fire_file, grid, lightning_file

BBOX = [-59.5, -33.5, -58.5, -32.5]
CODES = {"high": [10, 11, 13, 30, 31, 33], "nominal": [12, 14, 32, 34], "low": [15, 35]}


def test_projection_matches_the_product_user_guide_example():
    # GOES-R PUG vol. 3, 4.2.8.1: 33.846162 N, 84.690932 W with the satellite at 75 W.
    x, y = latlon_to_scan(np.array([33.846162]), np.array([-84.690932]), GOES_EAST)
    assert x[0] == pytest.approx(-0.024052, abs=1e-6)
    assert y[0] == pytest.approx(0.095340, abs=1e-6)
    lat, lon = scan_to_latlon(x, y, GOES_EAST)
    assert (lat[0], lon[0]) == pytest.approx((33.846162, -84.690932), abs=1e-5)


def test_points_off_the_earth_are_nan():
    lat, lon = scan_to_latlon(np.array([0.2]), np.array([0.2]), GOES_EAST)
    assert np.isnan(lat[0]) and np.isnan(lon[0])


def test_fire_pixels_inside_the_bbox_become_observations():
    x, y = grid()
    center = (30, 30)
    content = fire_file({center: 10, (30, 32): 14, (31, 30): 15, (0, 0): 10})
    observations = parse_fire_file(content, BBOX, CODES, "nominal")
    # (31, 30) is low confidence and dropped; (0, 0) is outside the bbox.
    assert len(observations) == 2
    first = next(o for o in observations if o.raw_payload["col"] == 30)
    expected_lat, expected_lon = scan_to_latlon(np.array([x[30]]), np.array([y[30]]), GOES_EAST)
    assert (first.latitude, first.longitude) == pytest.approx(
        (expected_lat[0], expected_lon[0]), abs=1e-4
    )
    assert first.confidence == Confidence.HIGH
    assert (first.frp_mw, first.brightness_k) == (42.5, 600.0)
    assert first.native_id == "20260930T142020:30:30"
    assert first.acquired_at == datetime(2026, 9, 30, 14, 20, 20, 300000, tzinfo=UTC)
    assert (first.source, first.satellite, first.sensor) == ("goes", "GOES-19", "ABI")


def test_scan_without_fires_gives_nothing():
    assert parse_fire_file(fire_file({}), BBOX, CODES, "nominal") == []


def test_lightning_keeps_good_flashes_inside_the_bbox():
    content = lightning_file([(-33.0, -59.0, 0), (-33.1, -59.1, 1), (-25.0, -55.0, 0)])
    (flash,) = parse_lightning_file(content, BBOX)
    assert (flash.latitude, flash.longitude) == pytest.approx((-33.0, -59.0))
    assert flash.native_id == "20260930T142100:1"
    assert flash.observed_at == datetime(2026, 9, 30, 14, 21, 1, 500000, tzinfo=UTC)


def test_hour_prefixes_cross_midnight_and_year_days():
    now = datetime(2026, 1, 1, 0, 5, tzinfo=UTC)
    assert hour_prefixes("GLM-L2-LCFA", now) == [
        "GLM-L2-LCFA/2025/365/23/",
        "GLM-L2-LCFA/2026/001/00/",
    ]
