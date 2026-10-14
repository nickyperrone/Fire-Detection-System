"""Nobody reads or changes another account's fields, tags or fires, and nobody signed out makes the
server fetch from outside services."""

from sqlalchemy import select

from app.models import FieldRiskEvent, RiskStatus, Tag, Territory
from tests.test_alerts import fire
from tests.test_auth import rect, sign_in


def two_accounts(anonymous, outbox):
    """uno@ draws a field with a tag; then dos@ is the one signed in."""
    sign_in(anonymous, outbox, "uno@example.com")
    field = anonymous.post(
        "/territories", json={"name": "Ajeno", "geometry": rect(-59.1), "tags": ["cliente:A"]}
    ).json()
    anonymous.cookies.clear()
    sign_in(anonymous, outbox, "dos@example.com")
    return field


def test_another_accounts_field_cannot_be_changed_or_read(anonymous, outbox, session):
    field = two_accounts(anonymous, outbox)
    fid = field["id"]
    piece = {"type": "Polygon", "coordinates": rect(-59.1)["coordinates"]}
    attempts = [
        anonymous.patch(
            f"/territories/{fid}/outline", json={"operation": "remove", "geometry": piece}
        ),
        anonymous.patch(f"/territories/{fid}/settings", json={"alerts": False}),
        anonymous.put(f"/territories/{fid}/tags", json={"tags": ["mio"]}),
        anonymous.delete(f"/territories/{fid}"),
        anonymous.get(f"/territories/{fid}/risk-events"),
        anonymous.get(f"/territories/{fid}/snapshots"),
        anonymous.get(f"/territories/{fid}/spray-conditions"),
        anonymous.get(f"/territories/{fid}/fire-history"),
    ]
    assert [r.status_code for r in attempts] == [404] * len(attempts)
    territory = session.get(Territory, fid)
    session.refresh(territory)
    assert territory.alerts and [t.label for t in territory.tags] == ["cliente:A"]


def test_a_lot_cannot_go_inside_another_accounts_field(anonymous, outbox):
    field = two_accounts(anonymous, outbox)
    lot = {"name": "Lote", "geometry": rect(-59.1), "parent_id": field["id"]}
    assert anonymous.post("/territories", json=lot).status_code in (404, 422)


def test_another_accounts_tag_and_fire_cannot_be_changed(anonymous, outbox, session, thresholds):
    field = two_accounts(anonymous, outbox)
    fire(session, thresholds, -59.07)
    risk = session.scalar(select(FieldRiskEvent).where(FieldRiskEvent.territory_id == field["id"]))
    tag = session.scalar(select(Tag).where(Tag.owner == "uno@example.com"))
    assert anonymous.get("/tags").json()["tags"] == []
    assert anonymous.patch(f"/tags/{tag.id}", json={"color": "#ef4444"}).status_code in (404, 422)
    answer = anonymous.patch(f"/risk-events/{risk.id}", json={"status": "SEEN"})
    assert answer.status_code == 404
    session.refresh(risk)
    assert risk.status == RiskStatus.NEW


def test_signed_out_nobody_reaches_the_province_or_the_satellites(anonymous):
    assert anonymous.get("/cadastre/parcel?lat=-33&lon=-59").status_code == 401
    snap = {"geometry": rect(-59.1)}
    assert anonymous.post("/cadastre/snap", json=snap).status_code == 401
    assert anonymous.post("/fields/detect", json={"lat": -33, "lon": -59}).status_code == 401
