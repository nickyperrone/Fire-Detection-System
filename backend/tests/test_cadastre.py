import httpx
import mapbox_vector_tile
import pytest
from sqlalchemy import func, select

from app.models import CadastralParcel, CadastralTile
from app.providers.cadastre_wfs import READERS
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
            "format": "ater",
            "sort_by": "partida",
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
    lines = tile["parcels"]["features"]
    # Only the lines: no tax account numbers in public tiles.
    assert lines and all(f["properties"] == {} for f in lines)
    # From zoom 12, the distance to start drawing a field; above it, a solid mesh.
    assert build_tile(session, Layer.PARCELS, 12, x // 4, y // 4, "default", None) != b""
    assert build_tile(session, Layer.PARCELS, 11, x // 8, y // 8, "default", None) == b""


def test_each_province_is_read_from_its_own_fields():
    geometry = square(-60.0, -34.0, 0.01)
    arba = READERS["arba"](
        {"properties": {"pda": "133050545", "tpa": "Rural"}, "geometry": geometry}
    )
    assert (arba.department, arba.partida, arba.plano, arba.status) == (133, 50545, None, "Rural")
    idecor = READERS["idecor"](
        {
            "properties": {
                "Nomenclatura": "1804265890407816",
                "Nro_Cuenta": 180440540196,
                "Estado": "BALDIO",
            },
            "geometry": geometry,
        }
    )
    assert (idecor.department, idecor.partida, idecor.status) == (18, 180440540196, "BALDIO")
    # Without a tax account a parcel cannot be told apart from its neighbors: it is skipped.
    assert READERS["arba"]({"properties": {"pda": None}, "geometry": geometry}) is None
    assert READERS["idecor"]({"properties": {"Nro_Cuenta": None}, "geometry": geometry}) is None


def test_zoom_12_fetches_its_four_cache_tiles_once(session, wfs):
    fake, client = wfs
    x, y = tile_of(-32.9452, -59.1036, 12)
    ensure_tile(session, client, CONFIG, 12, x, y)
    asked = fake.requests
    assert session.query(CadastralTile).count() == 4
    ensure_tile(session, client, CONFIG, 12, x, y)
    assert fake.requests == asked


def test_a_parcel_that_crosses_itself_is_stored_valid(session):
    from datetime import UTC, datetime

    from app.providers.cadastre_wfs import Parcel
    from app.services.cadastre import _store

    # A bow tie: its two halves touch at the middle, which PostGIS cannot intersect with.
    bow_tie = {
        "type": "Polygon",
        "coordinates": [
            [[-59.0, -33.0], [-58.99, -32.99], [-58.99, -33.0], [-59.0, -32.99], [-59.0, -33.0]]
        ],
    }
    _store(session, "Entre Ríos", [Parcel(1, 7, None, None, bow_tie)], datetime.now(UTC))
    session.commit()
    valid, area = session.execute(
        select(func.ST_IsValid(CadastralParcel.geom), func.ST_Area(CadastralParcel.geom))
    ).one()
    assert valid and area > 0


def tile_extent(tile: bytes) -> tuple[float, float]:
    """Width and height, in tile units, of everything a parcel tile draws."""
    decoded = mapbox_vector_tile.decode(tile)["parcels"]["features"]

    def points(geometry):
        if isinstance(geometry, (int, float)):
            return
        if isinstance(geometry[0], (int, float)):
            yield geometry
        else:
            for part in geometry:
                yield from points(part)

    found = [p for f in decoded for p in points(f["geometry"]["coordinates"])]
    xs, ys = [p[0] for p in found], [p[1] for p in found]
    return max(xs) - min(xs), max(ys) - min(ys)


def test_the_open_field_shows_only_the_property_lines_inside_it(session, wfs):
    from app.services.territories import create_territory
    from tests.conftest import ARGENTINA

    _, client = wfs
    ensure_tile(session, client, CONFIG, 13, *tile_of(-32.9452, -59.1036, 13))
    field = create_territory(
        session,
        owner="default",
        name="Small",
        geometry=square(-59.1045, -32.9465, 0.002),
        section_tolerance_m=0,
        allowed_area=ARGENTINA,
    )
    session.commit()
    x, y = tile_of(-32.946, -59.1035, 14)

    whole = build_tile(session, Layer.PARCELS, 14, x, y, "default", None)
    inside = build_tile(session, Layer.PARCELS, 14, x, y, "default", None, within=field.id)
    assert inside != b""
    # A territory of 0.002° is a few hundred units on a tile of 4,096; the parcels around it
    # span far more.
    assert tile_extent(inside)[0] < 600 < tile_extent(whole)[0]
    # Only the owner's own territory: someone else's, or nobody, gets nothing.
    assert build_tile(session, Layer.PARCELS, 14, x, y, "other", None, within=field.id) == b""
    assert build_tile(session, Layer.PARCELS, 14, x, y, None, None, within=field.id) == b""
