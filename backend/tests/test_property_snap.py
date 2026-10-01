import httpx
import pytest
from shapely.geometry import Polygon, shape

from app.services.property_snap import snap_to_property_lines
from tests.test_cadastre import CONFIG, feature, square

SNAP = {
    **CONFIG,
    "snap": {
        "parcel_cover_share": 0.5,
        "max_shape_change": 0.35,
        "edge_tolerance_m": 30,
        "close_gaps_m": 20,
    },
}
# Two 0.01° (~ 1 km) parcels side by side with a ~20 m road between them, and a big one south.
WEST = square(-59.120, -32.950, 0.01)
EAST = square(-59.1098, -32.950, 0.01)
SOUTH = square(-59.120, -32.990, 0.03)


@pytest.fixture
def client():
    features = [feature(1, WEST), feature(2, EAST), feature(3, SOUTH)]

    def handle(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["startIndex"])
        return httpx.Response(200, json={"features": features[start : start + 1000]})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        yield client


def polygon(coords: list[tuple[float, float]]) -> dict:
    return {"type": "Polygon", "coordinates": [[*coords, coords[0]]]}


def test_rough_outline_of_two_parcels_becomes_their_union(session, client):
    # Drawn a bit outside the two parcels and across the road.
    rough = polygon(
        [(-59.1205, -32.9504), (-59.0995, -32.9503), (-59.0996, -32.9397), (-59.1204, -32.9396)]
    )
    result = snap_to_property_lines(session, client, SNAP, rough)
    assert result.method == "parcels"
    assert sorted(p["partida"] for p in result.parcels) == [1, 2]
    fitted = shape(result.geometry)
    assert isinstance(fitted, Polygon)  # the road gap is closed: one piece
    assert fitted.covers(shape(WEST).buffer(-1e-6)) and fitted.covers(shape(EAST).buffer(-1e-6))


def test_lot_inside_a_parcel_snaps_only_its_near_edges(session, client):
    # The south half of the big parcel, its south edge drawn ~15 m inside the property line;
    # its north edge is in the middle of the parcel, far from any line.
    lot = polygon(
        [(-59.1199, -32.98987), (-59.0901, -32.98987), (-59.0901, -32.975), (-59.1199, -32.975)]
    )
    result = snap_to_property_lines(session, client, SNAP, lot)
    assert result.method == "edges"
    ys = sorted({round(y, 5) for _, y in shape(result.geometry).exterior.coords})
    assert ys[0] == -32.99  # moved onto the parcel's south line
    assert ys[-1] == -32.975  # stayed where it was drawn


def test_shape_far_from_lines_is_kept(session, client):
    middle = polygon([(-59.11, -32.98), (-59.10, -32.98), (-59.10, -32.97), (-59.11, -32.97)])
    result = snap_to_property_lines(session, client, SNAP, middle)
    assert (result.method, result.geometry) == ("none", middle)
