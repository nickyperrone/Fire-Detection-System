import json

import numpy as np
import pytest

from app.main import app
from app.providers.goes_weather import read_grid
from app.routers.dependencies import weather_root
from app.services.weather_layer import IMAGE, META
from app.vision.weather_layer import RAIN_RGB, paint
from tests.goes_files import SIZE, abi_file

BBOX = [-59.6, -33.6, -58.4, -32.4]
CELL = 0.02


@pytest.fixture
def config(thresholds):
    return thresholds["goes"]["weather_layer"]


def test_rain_lands_where_it_falls():
    # Rain only in the east half of the satellite window.
    rain = np.zeros((SIZE, SIZE))
    rain[:, SIZE // 2 :] = 5.0
    grid = read_grid(abi_file("RRQPE", rain), "ABI-L2-RRQPEF", BBOX, CELL)
    assert grid.scanned_at.isoformat().startswith("2026-10-05T16:30:21")
    west, east = grid.values[:, :5], grid.values[:, -5:]
    assert np.all(west == 0) and np.all(east == 5)


def test_cloud_edges_are_interpolated_not_square():
    heights = np.full((SIZE, SIZE), np.nan)
    heights[:, SIZE // 2 :] = 8000.0
    grid = read_grid(abi_file("HT", heights), "ABI-L2-ACHAF", BBOX, CELL, clear=0)
    row = grid.values[grid.values.shape[0] // 2]
    assert row[0] == 0 and row[-1] == 8000
    # Between the clear and the cloudy side there are heights in between.
    assert np.any((row > 0) & (row < 8000))


def test_clear_and_dry_is_transparent_and_rain_is_blue(config):
    heights = np.zeros((3, 3))
    heights[1, 1] = 12000.0
    rain = np.zeros((3, 3))
    rain[2, 2] = 3.0
    image = paint(heights, rain, config | {"cloud_blur_cells": 0})
    assert image[0, 0, 3] == 0
    assert image[1, 1, 3] > 150
    assert tuple(image[2, 2, :3]) == RAIN_RGB[1]


def test_the_api_serves_the_newest_image(client, tmp_path):
    app.dependency_overrides[weather_root] = lambda: tmp_path
    assert client.get("/weather-layer").status_code == 404
    (tmp_path / IMAGE).write_bytes(b"\x89PNG")
    meta = {
        "keys": {},
        "clouds_at": "2026-10-05T16:30:21Z",
        "rain_at": "2026-10-05T16:30:21Z",
        "bbox": [-66.0, -39.0, -53.0, -26.0],
    }
    (tmp_path / META).write_text(json.dumps(meta))
    body = client.get("/weather-layer").json()
    assert body["bbox"] == meta["bbox"] and body["clouds_at"] == "2026-10-05T16:30:21Z"
    assert client.get("/weather-layer.png").headers["content-type"] == "image/png"
