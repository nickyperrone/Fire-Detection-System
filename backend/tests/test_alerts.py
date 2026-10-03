from datetime import UTC, datetime, timedelta

import pytest
from geoalchemy2 import WKTElement
from sqlalchemy import select

from app.config import Settings
from app.models import (
    AlertEmail,
    Confidence,
    FieldRiskEvent,
    FireEvent,
    FireEventStatus,
    LightningFlash,
    User,
)
from app.services.alerts import send_alerts
from app.services.field_risk import assess_active_fire_events
from app.services.territories import create_territory
from tests.conftest import ARGENTINA

NOW = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)
EMAIL = "primo@example.com"
# A field about 0.93 x 1.1 km, and a lot in its west half.
FIELD = (-59.10, -33.00, -59.09, -32.99)
LOT = (-59.10, -33.00, -59.095, -32.99)


def rect(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


@pytest.fixture
def field(session):
    session.add(User(email=EMAIL, locale="es"))
    field = create_territory(
        session,
        owner=EMAIL,
        name="La Esperanza",
        geometry=rect(*FIELD),
        section_tolerance_m=5,
        allowed_area=ARGENTINA,
    )
    session.commit()
    return field


def fire(session, thresholds, lon, lat=-32.995):
    event = FireEvent(
        geom=WKTElement(f"POINT({lon} {lat})", srid=4326),
        first_detected_at=NOW - timedelta(hours=2),
        last_detected_at=NOW - timedelta(hours=2),
        observation_count=1,
        confidence=Confidence.HIGH,
        sensors=["VIIRS NOAA-21"],
        status=FireEventStatus.ACTIVE,
        processing_version="test",
    )
    session.add(event)
    session.commit()
    assess_active_fire_events(session, thresholds["field_risk"], "test", NOW)
    return event


def alert(session, thresholds, outbox, send=None):
    return send_alerts(session, send or outbox.append, Settings(), thresholds, "test", NOW)


def test_a_new_fire_is_emailed_once_and_again_when_closer(session, thresholds, outbox, field):
    event = fire(session, thresholds, -59.07)  # about 1.9 km east
    assert alert(session, thresholds, outbox) == {"emails_sent": 1, "emails_failed": 0}
    email = outbox[0]
    assert email["To"] == EMAIL
    assert email["Subject"] == "La Esperanza: posible fuego a 1,9 km al E"
    body = email.get_content()
    assert "VIIRS NOAA-21 · visto hace 2 h" in body
    assert f"http://localhost:3000/?f={field.id}" in body
    assert 'apagá "Avisarme si hay peligro cerca"' in body

    alert(session, thresholds, outbox)
    assert len(outbox) == 1

    event.geom = WKTElement("POINT(-59.095 -32.995)", srid=4326)  # inside the field
    session.commit()
    assess_active_fire_events(session, thresholds["field_risk"], "test", NOW)
    alert(session, thresholds, outbox)
    assert outbox[1]["Subject"] == "La Esperanza: posible fuego dentro del campo"
    assert len(session.scalars(select(AlertEmail)).all()) == 2


def test_nothing_is_emailed_with_alerts_off_or_without_an_account(
    session, thresholds, outbox, field
):
    field.alerts = False
    session.commit()
    fire(session, thresholds, -59.07)
    alert(session, thresholds, outbox)
    create_territory(
        session,
        owner="default",
        name="Loaded from the command line",
        geometry=rect(-59.08, -33.00, -59.075, -32.99),
        section_tolerance_m=5,
        allowed_area=ARGENTINA,
    )
    session.commit()
    assess_active_fire_events(session, thresholds["field_risk"], "test", NOW)
    alert(session, thresholds, outbox)
    assert outbox == []


def test_a_fire_near_a_field_and_its_lot_is_one_line(session, thresholds, outbox, field):
    create_territory(
        session,
        owner=EMAIL,
        name="Lote 1",
        geometry=rect(*LOT),
        parent_id=field.id,
        section_tolerance_m=5,
        allowed_area=ARGENTINA,
    )
    session.commit()
    fire(session, thresholds, -59.07)
    alert(session, thresholds, outbox)
    assert outbox[0].get_content().count("posible fuego") == 1
    marks = session.scalars(select(FieldRiskEvent.notified_severity)).all()
    assert len(marks) == 2 and None not in marks


def test_lightning_is_emailed_at_most_once_an_hour(session, thresholds, outbox, field):
    for minutes in (5, 3):
        session.add(
            LightningFlash(
                native_id=f"f{minutes}",
                observed_at=NOW - timedelta(minutes=minutes),
                ingested_at=NOW,
                geom=WKTElement("POINT(-59.06 -32.995)", srid=4326),
                energy_j=1e-14,
                area_m2=1e7,
            )
        )
    session.commit()
    alert(session, thresholds, outbox)
    assert outbox[0]["Subject"] == "La Esperanza: rayos a 2,8 km en los últimos 60 min"
    alert(session, thresholds, outbox)
    assert len(outbox) == 1


def test_a_failed_send_is_retried_on_the_next_run(session, thresholds, outbox, field):
    fire(session, thresholds, -59.07)

    def down(_):
        raise ConnectionRefusedError("mail server down")

    assert alert(session, thresholds, outbox, send=down) == {"emails_sent": 0, "emails_failed": 1}
    assert alert(session, thresholds, outbox)["emails_sent"] == 1
