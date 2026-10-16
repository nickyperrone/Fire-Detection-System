import json
from datetime import UTC, datetime

import httpx

from app.services.wind_layer import grid_points, read_wind_layer, refresh_wind_layer

CONFIG = {"bbox": [-60.0, -34.0, -58.0, -32.0], "step_degrees": 1.0}
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def api(speeds):
    def respond(request: httpx.Request) -> httpx.Response:
        n = len(request.url.params["latitude"].split(","))
        # Wind from the west (270°) at 10 km/h blows toward the east.
        point = {"current": {"wind_speed_10m": 10, "wind_direction_10m": 270}}
        body = [dict(point) for _ in range(n)]
        for i, speed in speeds.items():
            body[i] = {"current": {"wind_speed_10m": speed, "wind_direction_10m": None}}
        return httpx.Response(200, content=json.dumps(body))

    return httpx.MockTransport(respond)


def test_the_grid_runs_west_to_east_and_north_to_south():
    lons, lats = grid_points(CONFIG)
    assert (lons, lats) == ([-60.0, -59.0, -58.0], [-32.0, -33.0, -34.0])


def test_wind_is_stored_as_east_and_north_components(tmp_path):
    with httpx.Client(transport=api({})) as client:
        result = refresh_wind_layer(client, CONFIG, tmp_path, NOW)
    grid = read_wind_layer(tmp_path)
    assert result["wind_points"] == 9 and (grid["nx"], grid["ny"]) == (3, 3)
    assert grid["bbox"] == [-60.0, -34.0, -58.0, -32.0]
    assert grid["u"][0] == 10.0 and abs(grid["v"][0]) < 0.01


def test_a_missing_point_takes_its_neighbors_wind_and_too_many_keep_the_old_grid(tmp_path):
    with httpx.Client(transport=api({1: 5})) as client:
        refresh_wind_layer(client, CONFIG, tmp_path, NOW)
    assert read_wind_layer(tmp_path)["u"][1] == 10.0
    before = read_wind_layer(tmp_path)
    with httpx.Client(transport=api({i: 5 for i in range(5)})) as client:
        result = refresh_wind_layer(client, CONFIG, tmp_path, NOW)
    assert result["wind_points"] == 0 and read_wind_layer(tmp_path) == before
