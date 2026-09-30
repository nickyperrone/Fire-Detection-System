import json
from datetime import UTC, datetime, timedelta

import httpx
import mapbox_vector_tile
import pytest
from sqlalchemy import func, select, text

from app.models import (
    DataQuality,
    FieldRiskEvent,
    FireEvent,
    FireEventStatus,
    Observation,
    ObservationEventLink,
    RiskStatus,
    RunStatus,
    Severity,
    Territory,
)
from app.services.data_quality import fire_quality, latest_pass, source_statuses
from app.services.field_risk import assess_active_fire_events, assess_fire_events
from app.services.fire_correlation import correlate
from app.services.fire_ingestion import ingest_firms
from app.services.territories import create_territory, load_feature_collection
from app.services.tiles import Layer, build_tile
from tests.conftest import FIXTURES
from tests.test_territories import SAMPLE
from tests.test_tiles import tile_xy

NOW = datetime(2026, 9, 28, 18, 0, tzinfo=UTC)
VERSION = "test+cfg.00000000"
KEY = "secret-map-key"


def firms_transport() -> httpx.MockTransport:
    header = (FIXTURES / "firms_modis.csv").read_text().splitlines()[0] + "\n"
    bodies = {
        "VIIRS_NOAA21_NRT": (FIXTURES / "firms_viirs_noaa21.csv").read_text(),
        "MODIS_NRT": (FIXTURES / "firms_modis.csv").read_text(),
        "VIIRS_NOAA20_NRT": header,
    }

    def respond(request: httpx.Request) -> httpx.Response:
        product = request.url.path.split("/")[5]
        if product not in bodies:
            return httpx.Response(500, text="server error")
        return httpx.Response(200, text=bodies[product])

    return httpx.MockTransport(respond)


@pytest.fixture
def pipeline(session, thresholds):
    load_feature_collection(session, "default", json.loads(SAMPLE.read_text()), 5)
    session.commit()
    with httpx.Client(transport=firms_transport()) as client:
        runs = ingest_firms(session, client, KEY, thresholds, NOW)
        second = ingest_firms(session, client, KEY, thresholds, NOW)
    changed = correlate(session, thresholds["correlation"], VERSION, NOW)
    assess_fire_events(session, changed, thresholds["field_risk"], VERSION, NOW)
    return runs, second


def territory_id(session, name):
    return session.scalar(select(Territory.id).where(Territory.name == name))


def test_ingestion_is_idempotent_and_records_every_product(pipeline, session):
    runs, second = pipeline
    by_product = {r.product: r for r in runs}
    assert by_product["VIIRS_NOAA21_NRT"].inserted == 3
    assert by_product["MODIS_NRT"].inserted == 2
    assert by_product["VIIRS_NOAA20_NRT"].status == RunStatus.SUCCESS
    assert by_product["VIIRS_NOAA20_NRT"].fetched == 0
    assert sum(r.inserted for r in second) == 0
    assert session.scalar(select(func.count()).select_from(Observation)) == 5
    failed = by_product["VIIRS_SNPP_NRT"]
    assert failed.status == RunStatus.FAILED
    assert KEY not in failed.error and "<FIRMS_MAP_KEY>" in failed.error


def test_same_fire_seen_by_two_sensors_is_one_event(pipeline, session):
    events = session.scalars(select(FireEvent).order_by(FireEvent.observation_count.desc())).all()
    assert len(events) == 3
    main = events[0]
    assert main.observation_count == 3
    assert sorted(main.sensors) == ["MODIS Aqua", "VIIRS NOAA-21"]
    assert main.confidence.value == "high"
    assert main.max_frp_mw == 18.7
    assert main.first_detected_at == datetime(2026, 9, 28, 5, 12, tzinfo=UTC)
    assert main.last_detected_at == datetime(2026, 9, 28, 14, 5, tzinfo=UTC)
    reasons = session.scalars(
        select(ObservationEventLink.reason).where(ObservationEventLink.fire_event_id == main.id)
    ).all()
    joined = [r for r in reasons if not r.get("new_event")]
    assert len(joined) == 2
    assert all(r["rule"] == "spatiotemporal_v1" and r["distance_m"] < 1000 for r in joined)


def test_one_fire_near_several_territories_gives_one_risk_event_each(pipeline, session):
    risks = session.scalars(select(FieldRiskEvent)).all()
    assert len({r.fire_event_id for r in risks}) == 1
    by_name = {session.get(Territory, r.territory_id).name: r for r in risks}
    assert set(by_name) == {"La Esperanza", "Lote 1 - Soy", "Lote 2 - Corn", "Campo Norte"}
    assert by_name["Lote 2 - Corn"].severity == Severity.HIGH
    assert by_name["Campo Norte"].severity == Severity.WATCH
    assert by_name["Lote 2 - Corn"].distance_m < by_name["Lote 1 - Soy"].distance_m
    assert by_name["La Esperanza"].factors["sensor_count"] == 2
    assert all(r.processing_version == VERSION for r in risks)


def test_fire_moving_closer_is_new_again(pipeline, session, thresholds):
    lote2 = territory_id(session, "Lote 2 - Corn")
    risk = session.scalar(select(FieldRiskEvent).where(FieldRiskEvent.territory_id == lote2))
    risk.status = RiskStatus.SEEN
    session.commit()
    session.execute(
        text(
            "UPDATE fire_event SET geom = ST_SetSRID(ST_MakePoint(-59.055, -32.965), 4326)"
            " WHERE id = :id"
        ),
        {"id": risk.fire_event_id},
    )
    assess_fire_events(session, {risk.fire_event_id}, thresholds["field_risk"], VERSION, NOW)
    session.refresh(risk)
    assert (risk.severity, risk.status, risk.distance_m) == (Severity.CRITICAL, RiskStatus.NEW, 0)


def test_events_without_new_detections_become_stale(pipeline, session, thresholds):
    correlate(session, thresholds["correlation"], VERSION, NOW + timedelta(hours=49))
    assert set(session.scalars(select(FireEvent.status))) == {FireEventStatus.STALE}


def test_fire_data_quality(pipeline, session, thresholds):
    products = thresholds["firms"]["products"]
    statuses = source_statuses(session, "firms", products)
    assert fire_quality(statuses, 12, NOW) == DataQuality.PARTIAL
    later = datetime.now(UTC) + timedelta(hours=13)
    assert fire_quality(statuses, 12, later) == DataQuality.STALE
    assert fire_quality(source_statuses(session, "goes", products), 12, NOW) == DataQuality.NO_DATA


def test_zoomed_out_fire_tile_clusters_events_and_zoomed_in_shows_them(pipeline, session):
    x, y = tile_xy(-59.0, -33.0, 5)
    clusters = mapbox_vector_tile.decode(
        build_tile(session, Layer.FIRE_EVENTS, 5, x, y, "default", NOW)
    )
    features = clusters["fire_events"]["features"]
    assert sum(f["properties"]["event_count"] for f in features) == 3
    assert len(features) < 3
    x, y = tile_xy(-59.021, -32.943, 12)
    events = mapbox_vector_tile.decode(
        build_tile(session, Layer.FIRE_EVENTS, 12, x, y, "default", NOW)
    )
    (main,) = events["fire_events"]["features"]
    assert main["properties"]["sensors"] == "VIIRS NOAA-21, MODIS Aqua"
    observations = build_tile(session, Layer.OBSERVATIONS, 12, x, y, "default", NOW)
    assert len(mapbox_vector_tile.decode(observations)["observations"]["features"]) == 3
    assert build_tile(session, Layer.OBSERVATIONS, 8, 0, 0, "default", NOW) == b""


def test_field_created_after_ingestion_gets_the_active_fire(pipeline, session, thresholds):
    field = create_territory(
        session,
        owner="default",
        name="New neighbor",
        geometry={
            "type": "Polygon",
            "coordinates": [
                [
                    [-59.03, -32.95],
                    [-59.025, -32.95],
                    [-59.025, -32.945],
                    [-59.03, -32.945],
                    [-59.03, -32.95],
                ]
            ],
        },
        section_tolerance_m=5,
    )
    session.commit()
    assess_active_fire_events(session, thresholds["field_risk"], VERSION, NOW)
    risk = session.scalar(select(FieldRiskEvent).where(FieldRiskEvent.territory_id == field.id))
    assert risk.severity == Severity.VERY_HIGH


def test_latest_pass_is_the_newest_acquisition(pipeline, session):
    newest = latest_pass(session, "firms")
    assert (newest.sensor, newest.satellite) == ("VIIRS", "NOAA-21")
    assert newest.acquired_at == datetime(2026, 9, 28, 17, 48, tzinfo=UTC)
    assert latest_pass(session, "goes") is None
