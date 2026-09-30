import json
import math

import mapbox_vector_tile
import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.services.territories import load_feature_collection
from tests.test_territories import SAMPLE

# Center of La Esperanza. Its longitude is exactly a tile edge from zoom 7 up, so the field is
# split between tile x - 1 (Lote 1) and tile x (Lote 2).
LON, LAT = -59.0625, -32.9675


def tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


@pytest.fixture
def client(session):
    load_feature_collection(session, "default", json.loads(SAMPLE.read_text()), 5)
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_territory_tile_carries_ids_and_names_only(client):
    x, y = tile_xy(LON, LAT, 12)
    features = []
    for tile_x in (x - 1, x):
        response = client.get(f"/tiles/territories/12/{tile_x}/{y}.pbf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/vnd.mapbox-vector-tile"
        features += mapbox_vector_tile.decode(response.content)["territories"]["features"]
    names = {f["properties"]["name"] for f in features}
    assert {"La Esperanza", "Lote 1 - Soy", "Lote 2 - Corn"} <= names
    assert all(isinstance(f["id"], int) for f in features)
    assert set(features[0]["properties"]) <= {"name", "kind", "parent_id"}
    anchors = [
        f["properties"]["name"]
        for tile_x in (x - 1, x)
        for f in mapbox_vector_tile.decode(
            client.get(f"/tiles/territories/12/{tile_x}/{y}.pbf").content
        )["territory_labels"]["features"]
        if all(0 <= c < 4096 for c in f["geometry"]["coordinates"])
    ]
    # Label points near an edge are repeated in the neighbor's buffer, but each anchor lies
    # inside exactly one tile, even for La Esperanza, whose center is on the tile edge.
    for name in ("La Esperanza", "Lote 1 - Soy", "Lote 2 - Corn"):
        assert anchors.count(name) == 1


def test_empty_tile_is_204(client):
    x, y = tile_xy(10.0, 50.0, 12)
    assert client.get(f"/tiles/territories/12/{x}/{y}.pbf").status_code == 204


def test_tile_outside_zoom_level_is_404(client):
    assert client.get("/tiles/territories/2/4/0.pbf").status_code == 404
    assert client.get("/tiles/rivers/2/1/1.pbf").status_code == 422
