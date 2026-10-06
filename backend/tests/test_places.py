import httpx
import pytest

from app.main import app
from app.routers.dependencies import http_client
from app.services import places

TOWN = {
    "geometry": {"type": "Point", "coordinates": [-58.9986, -33.0339]},
    "properties": {
        "name": "Larroque",
        "osm_value": "village",
        "county": "Distrito Pehuajó al Sur",
        "state": "Entre Ríos",
        "extent": [-59.04, -32.98, -58.93, -33.08],
    },
}
ADDRESS = {
    "geometry": {"type": "Point", "coordinates": [-58.51, -33.01]},
    "properties": {
        "street": "San Martín",
        "housenumber": "450",
        "osm_value": "house",
        "city": "Gualeguaychú",
        "state": "Entre Ríos",
    },
}


@pytest.fixture
def photon(anonymous):
    """The API with Photon answering two places, counting the calls that reach it."""
    places._cache.clear()
    calls = []

    def answer(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params["q"])
        return httpx.Response(200, json={"features": [TOWN, ADDRESS]})

    client = httpx.Client(transport=httpx.MockTransport(answer))
    app.dependency_overrides[http_client] = lambda: client
    return calls


def test_places_come_with_where_they_are_and_their_area(anonymous, photon):
    town, address = anonymous.get("/places", params={"q": "Larroque"}).json()
    assert (town["name"], town["context"]) == ("Larroque", "Distrito Pehuajó al Sur, Entre Ríos")
    # Photon's extent is west, north, east, south; the API answers west, south, east, north.
    assert town["bbox"] == [-59.04, -33.08, -58.93, -32.98]
    assert (address["name"], address["context"], address["bbox"]) == (
        "San Martín 450",
        "Gualeguaychú, Entre Ríos",
        None,
    )


def test_the_same_search_is_answered_from_memory(anonymous, photon):
    anonymous.get("/places", params={"q": "Larroque"})
    anonymous.get("/places", params={"q": "  larroque "})
    assert photon == ["larroque"]
    # Too short to search: Photon is not asked.
    assert anonymous.get("/places", params={"q": "la"}).json() == []
    assert photon == ["larroque"]


def test_photon_down_is_503(anonymous):
    places._cache.clear()
    # The test client answers 503 to every outside call.
    assert anonymous.get("/places", params={"q": "Larroque"}).status_code == 503
