import json
from datetime import UTC, datetime

import numpy as np
import pytest

from app.main import app
from app.providers.goes_weather import Grid, read_grid
from app.routers.dependencies import weather_root
from app.services import weather_layer
from app.services.weather_layer import META, refresh_weather_layer
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


def test_clouds_are_a_veil_and_rain_stands_out(config):
    heights = np.zeros((3, 3))
    heights[1, 1] = 12000.0
    rain = np.zeros((3, 3))
    rain[2, 2] = 3.0
    image = paint(heights, rain, config | {"cloud_blur_cells": 0})
    assert image[0, 0, 3] == 0
    # Even the highest cloud leaves the map readable; rain is far more opaque.
    assert 0 < image[1, 1, 3] < 80
    assert tuple(image[2, 2, :3]) == RAIN_RGB[1] and image[2, 2, 3] > 200


def test_the_loop_keeps_the_newest_scans_and_drops_older_ones(thresholds, tmp_path, monkeypatch):
    config = thresholds["goes"]["weather_layer"] | {"frames_kept": 2}
    goes = thresholds["goes"] | {"weather_layer": config}
    times = [datetime(2026, 10, 6, 21, m, tzinfo=UTC) for m in (30, 40, 50)]
    monkeypatch.setattr(weather_layer, "scans", lambda *_: {t: f"key-{t:%H%M}" for t in times})
    monkeypatch.setattr(weather_layer, "download", lambda *_: b"")
    blank = Grid(np.zeros((2, 2), "float32"), times[0])
    monkeypatch.setattr(weather_layer, "read_grid", lambda *_, **__: blank)

    stale = weather_layer.frame_path(tmp_path, datetime(2026, 10, 6, 19, tzinfo=UTC))
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"old")
    result = refresh_weather_layer(None, thresholds | {"goes": goes}, tmp_path, times[-1])
    assert result == {"frames": 2, "added": 2}
    assert sorted(p.name for p in (tmp_path / "frames").iterdir()) == [
        "20261006T214000.png",
        "20261006T215000.png",
    ]
    # Nothing new on the next run.
    again = refresh_weather_layer(None, thresholds | {"goes": goes}, tmp_path, times[-1])
    assert again == {"frames": 2, "added": 0}


def test_the_api_lists_and_serves_the_frames(client, tmp_path):
    app.dependency_overrides[weather_root] = lambda: tmp_path
    assert client.get("/weather-layer").status_code == 404
    scan = datetime(2026, 10, 6, 21, 40, 21, tzinfo=UTC)
    path = weather_layer.frame_path(tmp_path, scan)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\x89PNG")
    meta = {"bbox": [-66.0, -39.0, -53.0, -26.0], "frames": [scan.isoformat()]}
    (tmp_path / META).write_text(json.dumps(meta))
    body = client.get("/weather-layer").json()
    assert body["frames"] == [{"scanned_at": "2026-10-06T21:40:21Z", "id": "20261006T214021"}]
    image = client.get("/weather-layer/20261006T214021.png")
    assert image.headers["content-type"] == "image/png"
    assert client.get("/weather-layer/20261006T214022.png").status_code == 404
    assert client.get("/weather-layer/latest.png").status_code == 404
