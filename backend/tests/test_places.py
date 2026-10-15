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


GEOREF_TOWN = {
    "nombre": "Larroque",
    "departamento": {"nombre": "Gualeguaychú"},
    "provincia": {"nombre": "Entre Ríos"},
    "centroide": {"lon": -59.0, "lat": -33.04},
}


def sources(photon_answer=None, georef_answer=None):
    """Georef and Photon answering, or failing with None, and the searches each one got."""
    calls = {"photon": [], "georef": []}

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.host == "apis.datos.gob.ar":
            calls["georef"].append(request.url.params["nombre"])
            if georef_answer is None:
                return httpx.Response(503)
            return httpx.Response(200, json={"localidades": georef_answer})
        calls["photon"].append(request.url.params["q"])
        if photon_answer is None:
            return httpx.Response(503)
        return httpx.Response(200, json={"features": photon_answer})

    places._cache.clear()
    client = httpx.Client(transport=httpx.MockTransport(answer))
    app.dependency_overrides[http_client] = lambda: client
    return calls


@pytest.fixture
def both(anonymous):
    return sources([TOWN, ADDRESS], [GEOREF_TOWN])


def test_towns_come_from_georef_and_streets_from_photon(anonymous, both):
    town, address = anonymous.get("/places", params={"q": "Larroque"}).json()
    # Photon's Larroque is the same town: shown once, from Georef, framed around its center.
    assert (town["name"], town["context"], town["kind"]) == (
        "Larroque",
        "Gualeguaychú, Entre Ríos",
        "town",
    )
    assert town["bbox"] == pytest.approx([-59.03, -33.07, -58.97, -33.01])
    assert (address["name"], address["context"], address["bbox"]) == (
        "San Martín 450",
        "Gualeguaychú, Entre Ríos",
        None,
    )


def test_the_same_search_is_answered_from_memory(anonymous, both):
    anonymous.get("/places", params={"q": "Larroque"})
    anonymous.get("/places", params={"q": "  larroque "})
    assert both == {"photon": ["larroque"], "georef": ["larroque"]}
    # Too short to search: nobody is asked.
    assert anonymous.get("/places", params={"q": "la"}).json() == []
    assert both["photon"] == ["larroque"]


def test_photon_late_or_down_leaves_the_towns(anonymous):
    sources(None, [GEOREF_TOWN])
    answer = anonymous.get("/places", params={"q": "Larroque"})
    assert [p["name"] for p in answer.json()] == ["Larroque"]


def test_georef_down_leaves_photon(anonymous):
    sources([TOWN, ADDRESS], None)
    names = [p["name"] for p in anonymous.get("/places", params={"q": "Larroque"}).json()]
    assert names == ["Larroque", "San Martín 450"]


def test_both_down_is_503(anonymous):
    places._cache.clear()
    # The test client answers 503 to every outside call.
    assert anonymous.get("/places", params={"q": "Larroque"}).status_code == 503


def test_towns_and_streets_can_be_asked_apart(anonymous):
    calls = sources([TOWN, ADDRESS], [GEOREF_TOWN, GEOREF_TOWN])
    towns = anonymous.get("/places", params={"q": "Larroque", "source": "towns"}).json()
    # Georef's repeated town is shown once.
    assert [t["name"] for t in towns] == ["Larroque"] and calls["photon"] == []
    streets = anonymous.get("/places", params={"q": "Larroque", "source": "streets"}).json()
    assert [s["name"] for s in streets] == ["Larroque", "San Martín 450"]
    assert calls == {"photon": ["larroque"], "georef": ["larroque"]}
