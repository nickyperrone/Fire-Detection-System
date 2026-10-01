from datetime import UTC, datetime

from shapely.geometry import shape
from sqlalchemy import select

from app.models import Confidence, Observation
from app.providers.records import FireObservation
from app.services.fire_ingestion import store_observations
from tests.conftest import ARGENTINA

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


def detection(lat: float, lon: float) -> FireObservation:
    return FireObservation(
        source="firms",
        product="VIIRS_NOAA21_NRT",
        satellite="NOAA-21",
        sensor="VIIRS",
        native_id=None,
        acquired_at=NOW,
        latitude=lat,
        longitude=lon,
        confidence_raw="h",
        confidence=Confidence.HIGH,
        frp_mw=5.0,
        brightness_k=330.0,
        day_night="D",
        raw_payload={},
    )


def test_only_detections_in_argentina_are_stored(session):
    gualeguaychu, fray_bentos = detection(-33.01, -58.52), detection(-33.12, -58.31)
    assert store_observations(session, [gualeguaychu, fray_bentos], NOW, 4, ARGENTINA) == 1
    (stored,) = session.scalars(select(Observation)).all()
    assert stored.raw_payload == {} and stored.satellite == "NOAA-21"


def test_boundary_endpoint_returns_a_light_outline(client):
    response = client.get("/boundary")
    assert response.status_code == 200
    outline = shape(response.json()["geometry"])
    assert outline.contains(shape({"type": "Point", "coordinates": [-59.0, -33.0]}))
    assert len(response.content) < 60_000
