from datetime import UTC, datetime

from sqlalchemy import select

from app.models import FireEvent, Observation, StaticSource
from app.services.fire_correlation import correlate
from app.services.static_sources import mark_observations, rebuild_static
from tests.conftest import FIXTURES

NOW = datetime(2026, 9, 30, 12, tzinfo=UTC)
CONFIG = {"types": [2], "grid_degrees": 0.005, "radius_m": 1000}
BBOX = [-61.0, -34.5, -57.5, -30.0]


def observation(key: str, lat: float, lon: float) -> Observation:
    return Observation(
        source="firms",
        product="VIIRS_SNPP_NRT",
        satellite="Suomi NPP",
        sensor="VIIRS",
        dedup_key=key,
        acquired_at=NOW,
        ingested_at=NOW,
        geom=f"SRID=4326;POINT({lon} {lat})",
        confidence_raw="n",
        confidence="nominal",
        raw_payload={},
    )


def test_rebuild_reads_type_2_rows_and_is_idempotent(session):
    archive = FIXTURES / "viirs-snpp_2020_Argentina.csv"
    rebuild_static(session, [archive], BBOX, CONFIG)
    rebuild_static(session, [archive], BBOX, CONFIG)
    (source,) = session.scalars(select(StaticSource)).all()
    assert (source.latitude, source.longitude, source.detections) == (-32.96, -59.05, 1)


def test_detection_next_to_industry_never_becomes_a_fire(session, thresholds):
    rebuild_static(session, [FIXTURES / "viirs-snpp_2020_Argentina.csv"], BBOX, CONFIG)
    session.add_all(
        [observation("plant", -32.9605, -59.0503), observation("field", -32.90, -59.20)]
    )
    session.commit()
    assert mark_observations(session, CONFIG["radius_m"]) == 1
    correlate(session, thresholds["correlation"], "test", NOW)
    (event,) = session.scalars(select(FireEvent)).all()
    assert event.observation_count == 1
    plant = session.scalar(select(Observation).where(Observation.dedup_key == "plant"))
    assert plant.static_source


def test_event_made_only_of_industry_is_closed(session, thresholds):
    session.add(observation("plant", -32.9605, -59.0503))
    session.commit()
    # Correlated before the source was known as static: a fire event exists.
    correlate(session, thresholds["correlation"], "test", NOW)
    rebuild_static(session, [FIXTURES / "viirs-snpp_2020_Argentina.csv"], BBOX, CONFIG)
    mark_observations(session, CONFIG["radius_m"])
    (event,) = session.scalars(select(FireEvent)).all()
    session.refresh(event)
    assert event.status.value == "CLOSED"
