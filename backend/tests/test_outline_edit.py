from datetime import UTC, datetime

import pytest
from geoalchemy2 import WKTElement
from sqlalchemy import select

from app.models import Confidence, FieldRiskEvent, FireEvent, FireEventStatus

# A 0.01° square field (about 0.93 x 1.1 km, 103 ha) with one lot in its west half.
FIELD = (-59.10, -33.00, -59.09, -32.99)
LOT = (-59.10, -33.00, -59.095, -32.99)


def rect(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


@pytest.fixture
def field(client):
    created = client.post("/territories", json={"name": "Field", "geometry": rect(*FIELD)}).json()
    client.post(
        "/territories", json={"name": "Lot", "geometry": rect(*LOT), "parent_id": created["id"]}
    )
    return created


def edit(client, territory_id, operation, piece, preview=False):
    return client.patch(
        f"/territories/{territory_id}/outline",
        json={"operation": operation, "geometry": rect(*piece), "preview": preview},
    )


def test_adding_and_removing_pieces_changes_the_outline_and_hectares(client, field):
    east = (-59.09, -33.00, -59.08, -32.99)
    grown = edit(client, field["id"], "add", east).json()
    assert grown["hectares"] == pytest.approx(2 * field["hectares"], rel=1e-3)
    assert grown["geometry"]["type"] == "MultiPolygon"

    shrunk = edit(client, field["id"], "remove", (-59.085, -33.01, -59.07, -32.98)).json()
    assert shrunk["hectares"] == pytest.approx(1.5 * field["hectares"], rel=1e-3)
    assert client.get(f"/territories/{field['id']}").json()["hectares"] == shrunk["hectares"]


def test_preview_answers_without_saving(client, field):
    preview = edit(client, field["id"], "add", (-59.09, -33.00, -59.08, -32.99), preview=True)
    assert preview.json()["hectares"] == pytest.approx(2 * field["hectares"], rel=1e-3)
    assert client.get(f"/territories/{field['id']}").json()["hectares"] == field["hectares"]


@pytest.mark.parametrize(
    ("operation", "piece", "code"),
    [
        ("remove", (-59.05, -33.00, -59.04, -32.99), "no_overlap"),
        ("remove", (-59.11, -33.01, -59.08, -32.98), "nothing_left"),
        ("add", (-59.098, -32.998, -59.092, -32.992), "no_change"),
        # The lot is in the west half: cutting the west edge leaves part of it outside.
        ("remove", (-59.11, -33.01, -59.098, -32.98), "cuts_lots"),
        ("add", (-58.0, -35.0, -57.0, -34.0), "outside_country"),  # the river and Uruguay
    ],
)
def test_edits_that_break_the_field_are_refused(client, field, operation, piece, code):
    response = edit(client, field["id"], operation, piece)
    assert (response.status_code, response.json()["code"]) == (422, code)


def test_a_lot_must_stay_inside_its_field(client, field):
    lot = next(t for t in client.get("/territories").json() if t["name"] == "Lot")
    response = edit(client, lot["id"], "add", (-59.11, -33.00, -59.10, -32.99))
    assert response.json()["code"] == "outside_parent"
    assert edit(client, lot["id"], "remove", (-59.10, -33.00, -59.098, -32.99)).status_code == 200


def test_fire_risk_follows_the_new_outline(client, field, session):
    now = datetime.now(UTC)
    fire = FireEvent(
        # About 13 km east of the field, beyond the widest risk band.
        geom=WKTElement("POINT(-58.95 -32.995)", srid=4326),
        first_detected_at=now,
        last_detected_at=now,
        observation_count=1,
        confidence=Confidence.HIGH,
        sensors=["VIIRS"],
        status=FireEventStatus.ACTIVE,
        processing_version="test",
    )
    session.add(fire)
    session.commit()
    reach = (-59.09, -33.00, -58.94, -32.99)

    def severities():
        return list(
            session.scalars(
                select(FieldRiskEvent.severity).where(FieldRiskEvent.territory_id == field["id"])
            )
        )

    edit(client, field["id"], "add", reach)
    assert [s.value for s in severities()] == ["CRITICAL"]
    edit(client, field["id"], "remove", reach)
    assert severities() == []
