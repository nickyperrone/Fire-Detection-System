from datetime import UTC, date, datetime, timedelta

import pytest
from geoalchemy2 import WKTElement

from app.config import Settings
from app.models import (
    Confidence,
    LightningFlash,
    Observation,
    SummaryFrequency,
    User,
    WeatherDay,
)
from app.services.summary import due_since, send_due_summaries
from app.services.territories import create_territory
from tests.conftest import ARGENTINA

EMAIL = "primo@example.com"
# Monday 5 October 2026, 08:00 in Argentina (UTC-3).
MONDAY_8 = datetime(2026, 10, 5, 11, 0, tzinfo=UTC)


def rect(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


@pytest.mark.parametrize(
    ("frequency", "now", "expected"),
    [
        (SummaryFrequency.DAILY, MONDAY_8, datetime(2026, 10, 5, 10, tzinfo=UTC)),
        # Before 07:00 the last daily one was yesterday's.
        (
            SummaryFrequency.DAILY,
            MONDAY_8 - timedelta(hours=2),
            datetime(2026, 10, 4, 10, tzinfo=UTC),
        ),
        # On Wednesday the last weekly one was Monday's.
        (
            SummaryFrequency.WEEKLY,
            MONDAY_8 + timedelta(days=2),
            datetime(2026, 10, 5, 10, tzinfo=UTC),
        ),
        # Monday before 07:00: still last week's.
        (
            SummaryFrequency.WEEKLY,
            MONDAY_8 - timedelta(hours=2),
            datetime(2026, 9, 28, 10, tzinfo=UTC),
        ),
        (SummaryFrequency.OFF, MONDAY_8, None),
    ],
)
def test_when_a_summary_is_due(frequency, now, expected):
    assert due_since(frequency, now) == expected


def observation(key: str, lon: float, when: datetime, static: bool = False) -> Observation:
    return Observation(
        source="firms",
        product="VIIRS_NOAA21_NRT",
        satellite="NOAA-21",
        sensor="VIIRS",
        dedup_key=key,
        acquired_at=when,
        ingested_at=when,
        geom=WKTElement(f"POINT({lon} -32.995)", srid=4326),
        confidence_raw="h",
        confidence=Confidence.HIGH,
        raw_payload={},
        static_source=static,
    )


@pytest.fixture
def account(session):
    user = User(
        email=EMAIL,
        locale="es",
        summary=SummaryFrequency.WEEKLY,
        summary_sent_at=MONDAY_8 - timedelta(days=7, hours=1),
    )
    session.add(user)
    field = create_territory(
        session,
        owner=EMAIL,
        name="La Esperanza",
        geometry=rect(-59.10, -33.00, -59.09, -32.99),
        section_tolerance_m=5,
        allowed_area=ARGENTINA,
    )
    create_territory(
        session,
        owner=EMAIL,
        name="Lote 1",
        # The east half: the same fires at the same distances as the whole field.
        geometry=rect(-59.095, -33.00, -59.09, -32.99),
        parent_id=field.id,
        section_tolerance_m=5,
        allowed_area=ARGENTINA,
    )
    session.add_all(
        [
            # Two days with fire 1.9 and 3.8 km east, and a steel plant that does not count.
            observation("a", -59.07, MONDAY_8 - timedelta(days=2)),
            observation("b", -59.07, MONDAY_8 - timedelta(days=2, hours=3)),
            observation("c", -59.05, MONDAY_8 - timedelta(days=4)),
            observation("d", -59.08, MONDAY_8 - timedelta(days=1), static=True),
            # Before the week: not in this summary.
            observation("e", -59.07, MONDAY_8 - timedelta(days=9)),
            LightningFlash(
                native_id="f1",
                observed_at=MONDAY_8 - timedelta(days=1),
                ingested_at=MONDAY_8,
                geom=WKTElement("POINT(-59.06 -32.995)", srid=4326),
                energy_j=1e-14,
                area_m2=1e7,
            ),
            WeatherDay(
                latitude=-33.0,
                longitude=-59.0,
                day=date(2026, 10, 3),
                source="test",
                tmax_c=25,
                rh_pct=60,
                wind_kmh=10,
                rain_mm=12.0,
                updated_at=MONDAY_8,
            ),
            WeatherDay(
                latitude=-33.0,
                longitude=-59.0,
                day=date(2026, 10, 4),
                source="test",
                tmax_c=25,
                rh_pct=60,
                wind_kmh=10,
                rain_mm=3.5,
                updated_at=MONDAY_8,
            ),
        ]
    )
    session.commit()
    return user


def test_a_weekly_summary_lists_the_week_per_field_once(session, thresholds, outbox, account):
    result = send_due_summaries(session, outbox.append, Settings(), thresholds, MONDAY_8)
    assert result == {"summaries_sent": 1, "summaries_failed": 0}
    email = outbox[0]
    assert (email["To"], email["Subject"]) == (EMAIL, "Resumen semanal: 1 campo con fuego cerca")
    body = email.get_content()
    assert "La Esperanza (104 ha)" in body
    assert "Fuego: 2 días con fuego a menos de 10 km; el más cercano a 1,9 km" in body
    assert "Rayos: 1 rayo a menos de 10 km." in body
    assert "Lluvia en la zona: 15,5 mm." in body
    assert "menú de tu cuenta" in body
    # Its lot says the same, so it is named once instead of repeated.
    assert "Lotes igual que el campo: Lote 1." in body

    assert (
        send_due_summaries(session, outbox.append, Settings(), thresholds, MONDAY_8)[
            "summaries_sent"
        ]
        == 0
    )


def test_no_summary_when_off_or_without_fields(session, thresholds, outbox, account):
    account.summary = SummaryFrequency.OFF
    session.add(
        User(email="nadie@example.com", locale="es", summary_sent_at=MONDAY_8 - timedelta(days=30))
    )
    session.commit()
    assert (
        send_due_summaries(session, outbox.append, Settings(), thresholds, MONDAY_8)[
            "summaries_sent"
        ]
        == 0
    )
    assert outbox == []


def test_the_account_menu_changes_the_frequency_and_sends_one_now(anonymous, outbox):
    from tests.test_auth import sign_in

    sign_in(anonymous, outbox, "uno@example.com")
    assert anonymous.patch("/auth/me", json={"summary": "DAILY"}).json()["summary"] == "DAILY"
    empty = anonymous.post("/auth/me/summary")
    assert (empty.status_code, empty.json()["code"]) == (422, "no_fields")
    anonymous.post(
        "/territories", json={"name": "A", "geometry": rect(-59.10, -33.00, -59.09, -32.99)}
    )
    assert anonymous.post("/auth/me/summary").status_code == 202
    assert outbox[-1]["Subject"].startswith("Resumen del día")
