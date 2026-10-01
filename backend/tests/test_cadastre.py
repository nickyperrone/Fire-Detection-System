import httpx
import mapbox_vector_tile
import pytest
from sqlalchemy import func, select

from app.models import CadastralParcel, CadastralTile
from app.services.cadastre import ensure_tile, parcel_at, tile_bbox, tile_of
from app.services.tiles import Layer, build_tile

CONFIG = {
    "tile_zoom": 13,
    "refresh_days": 90,
    "sources": [
        {
            "province": "Entre Ríos",
            "bbox": [-60.85, -34.1, -57.75, -30.1],
            "wfs_url": "https://cadastre.test/ows",
            "layer": "sit_catastro:vwm_parcelario_base",
            "page_size": 2,
        }
    ],
}


def square(lon: float, lat: float, size: float) -> dict:
    ring = [[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat]]
    return {"type": "Polygon", "coordinates": [ring]}


def feature(partida: int, geometry: dict) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "departamento": 7,
            "partida": partida,
            "plano": 100 + partida,
            "estado": "ok",
        },
        "geometry": geometry,
    }


class FakeWfs:
    """Three features in two pages; parcel 1 comes as two pieces, like the real service does."""

    def __init__(self):
        self.requests = 0
        self.features = [
            feature(1, square(-59.105, -32.948, 0.004)),
            feature(1, square(-59.100, -32.948, 0.001)),
            feature(2, square(-59.110, -32.960, 0.02)),
        ]

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        start = int(request.url.params["startIndex"])
        count = int(request.url.params["count"])
        return httpx.Response(200, json={"features": self.features[start : start + count]})


@pytest.fixture
def wfs():
    fake = FakeWfs()
    with httpx.Client(transport=httpx.MockTransport(fake.handle)) as client:
        yield fake, client


def test_tile_math_round_trips():
    x, y = tile_of(-32.9452, -59.1036, 13)
    west, south, east, north = tile_bbox(13, x, y)
    assert west <= -59.1036 <= east and south <= -32.9452 <= north


def test_tile_is_fetched_once_and_pieces_are_merged(session, wfs):
    fake, client = wfs
    x, y = tile_of(-32.9452, -59.1036, 13)
    assert ensure_tile(session, client, CONFIG, 13, x, y) == 3
    assert fake.requests == 2  # two pages of two
    # A deeper tile inside the same zoom-13 tile uses the cache.
    assert ensure_tile(session, client, CONFIG, 15, x * 4 + 1, y * 4 + 2) == 0
    assert fake.requests == 2
    assert session.scalar(select(func.count()).select_from(CadastralParcel)) == 2
    first = session.scalar(select(CadastralParcel).where(CadastralParcel.partida == 1))
    assert session.scalar(select(func.ST_NumGeometries(first.geom))) == 2
    assert session.get(CadastralTile, ("Entre Ríos", 13, x, y)).parcels == 3


def test_parcel_at_point_and_property_line_tiles(session, wfs):
    _, client = wfs
    found = parcel_at(session, client, CONFIG, -32.946, -59.103)
    assert found["properties"]["partida"] == 1
    assert found["geometry"]["type"] == "MultiPolygon"
    assert parcel_at(session, client, CONFIG, -32.90, -59.20) is None

    x, y = tile_of(-32.946, -59.103, 14)
    tile = mapbox_vector_tile.decode(build_tile(session, Layer.PARCELS, 14, x, y, "default", None))
    assert {f["properties"]["partida"] for f in tile["parcels"]["features"]} >= {1}
    assert build_tile(session, Layer.PARCELS, 12, x // 4, y // 4, "default", None) == b""
