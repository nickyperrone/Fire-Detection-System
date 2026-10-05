from datetime import UTC, datetime

import pytest

from app.models import IngestionRun, RunStatus


def rect(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def test_create_field_and_section_then_filter_by_tag(client):
    field = client.post(
        "/territories",
        json={
            "name": "Test field",
            "geometry": rect(-59.1, -32.95, -59.08, -32.94),
            "tags": ["client:Ana"],
        },
    )
    assert field.status_code == 201
    assert field.json()["hectares"] == pytest.approx(207, rel=0.02)
    section = client.post(
        "/territories",
        json={
            "name": "North half",
            "geometry": rect(-59.1, -32.945, -59.08, -32.94),
            "parent_id": field.json()["id"],
            "tags": ["crop:soy"],
        },
    )
    assert section.json()["kind"] == "SECTION"
    assert [t["name"] for t in client.get("/territories", params={"tag": "crop:soy"}).json()] == [
        "North half"
    ]
    portfolio = client.get("/portfolio").json()
    assert [e["name"] for e in portfolio] == ["Test field", "North half"]
    assert portfolio[0]["fire"]["data_quality"] == "NO_DATA"
    assert portfolio[0]["spray"]["data_quality"] == "NO_DATA"


def test_invalid_geometry_is_a_422_with_the_reason(client):
    response = client.post(
        "/territories", json={"name": "Dot", "geometry": {"type": "Point", "coordinates": [0, 0]}}
    )
    assert response.status_code == 422
    assert "Polygon" in response.json()["detail"]
    assert response.json()["code"] == "not_a_polygon"
    outside = client.post(
        "/territories", json={"name": "Madrid", "geometry": rect(-3.71, 40.41, -3.70, 40.42)}
    )
    assert (outside.status_code, outside.json()["code"]) == (422, "outside_country")


def test_unknown_territory_is_404(client):
    assert client.get("/territories/999").status_code == 404
    assert client.patch("/risk-events/999", json={"status": "SEEN"}).status_code == 404


def test_health_reports_every_source(client):
    body = client.get("/health").json()
    assert body["fire_data_quality"] == "NO_DATA"
    assert {s["product"] for s in body["sources"]} >= {"MODIS_NRT", "forecast"}
    assert body["latest_scan"] is None


def test_health_says_when_goes_last_looked_even_without_fires(client, session):
    # A GOES run that read a scan and found no fire: the region was still looked at.
    now = datetime(2026, 10, 5, 16, 40, tzinfo=UTC)
    session.add(
        IngestionRun(
            provider="goes",
            product="ABI-L2-FDCF",
            started_at=now,
            finished_at=now,
            status=RunStatus.SUCCESS,
            cursor="ABI-L2-FDCF/2026/278/16/OR_ABI-L2-FDCF-M6_G19_s20262781630211_e1_c1.nc",
        )
    )
    session.commit()
    scan = client.get("/health").json()["latest_scan"]
    assert (scan["satellite"], scan["acquired_at"]) == ("GOES-19", "2026-10-05T16:30:21Z")
