from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest
import yaml
from affine import Affine
from geoalchemy2 import WKTElement
from rasterio.crs import CRS
from sqlalchemy import select

from app.config import REPO_ROOT, Settings
from app.models import Confidence, DataQuality, Observation, User
from app.services.anomalies import confirm_burns, store_finding
from app.services.summary import send_summary
from app.vision.anomalies import FieldDate, Finding, Patch, field_date, find_patches

CONFIG = yaml.safe_load((REPO_ROOT / "config" / "thresholds.yaml").read_text())["anomalies"]
TODAY = date(2026, 10, 4)
# 10 m pixels in UTM zone 21S, near Larroque.
TRANSFORM = Affine(10, 0, 305000, 0, -10, 6350000)
CRS21 = CRS.from_epsg(32721)
SIZE = 80


def field_mask() -> np.ndarray:
    mask = np.zeros((SIZE, SIZE), bool)
    mask[10:70, 10:70] = True  # 36 ha
    return mask


def day(offset: int, green: float, patch: tuple[slice, slice] | None = None, **patch_values):
    """A date where the whole field has NDVI `green`, with other values in an optional patch."""
    rng = np.random.default_rng(offset)
    field = field_mask()
    values = {
        "ndvi": np.full((SIZE, SIZE), green, "float32"),
        "ndwi": np.full((SIZE, SIZE), -0.5, "float32"),
        "nbr": np.full((SIZE, SIZE), 0.4, "float32"),
    }
    for name in values:
        values[name] += rng.normal(0, 0.02, (SIZE, SIZE)).astype("float32")
        if patch and name in patch_values:
            values[name][patch] = patch_values[name]
        values[name][~field] = np.nan
    return FieldDate(TODAY - timedelta(days=offset), **values)


def history(latest: FieldDate) -> list[FieldDate]:
    # Four earlier dates as the crop grows: the whole field greens up together.
    return [day(40, 0.3), day(30, 0.45), day(20, 0.6), day(10, 0.7), latest]


def find(dates):
    return find_patches(dates, field_mask(), TRANSFORM, CRS21, TODAY, CONFIG)


def test_a_patch_drying_while_the_field_stays_green_is_found_where_it_is():
    northeast = (slice(12, 30), slice(50, 68))  # 18 x 18 pixels = 3.2 ha
    found = find(history(day(1, 0.75, northeast, ndvi=0.3)))
    assert found.data_quality == DataQuality.GOOD
    (patch,) = found.patches
    assert (patch.kind, patch.where) == ("less_green", "NE")
    assert patch.area_ha == pytest.approx(3.2, abs=0.2)
    assert patch.geometry["type"] == "Polygon"


def test_a_harvest_of_the_whole_field_is_not_unusual():
    assert find(history(day(1, 0.15))).patches == []


def test_water_and_burns_are_told_apart():
    south = (slice(50, 68), slice(20, 50))
    water = find(history(day(1, 0.7, south, ndwi=0.2, ndvi=0.1))).patches
    assert {p.kind for p in water} >= {"water"}
    burnt = find(history(day(1, 0.7, south, nbr=-0.2, ndvi=0.2))).patches
    assert {p.kind for p in burnt} >= {"burnt"}


def test_small_specks_are_not_patches():
    speck = (slice(30, 35), slice(30, 35))  # 25 pixels, a quarter hectare
    assert find(history(day(1, 0.75, speck, ndvi=0.2))).patches == []


def test_without_a_recent_clear_date_or_a_baseline_nothing_is_called_fine():
    cloudy = find([day(40, 0.3), day(30, 0.45), day(20, 0.6), day(15, 0.7)])
    assert (cloudy.data_quality, cloudy.last_clear) == (
        DataQuality.CLOUD_OBSCURED,
        TODAY - timedelta(days=15),
    )
    assert find([day(10, 0.6), day(1, 0.7)]).data_quality == DataQuality.PARTIAL
    assert find([]).data_quality == DataQuality.NO_DATA


def test_a_date_with_clouds_over_the_field_is_skipped():
    bands = {
        name: np.full((SIZE, SIZE), 1000.0, "float32") for name in ("red", "green", "nir", "swir22")
    }
    bands["scl"] = np.full((SIZE, SIZE), 4.0, "float32")  # vegetation
    assert field_date(TODAY, bands, field_mask(), CONFIG) is not None
    bands["scl"][10:40, 10:70] = 9.0  # high cloud over half the field
    assert field_date(TODAY, bands, field_mask(), CONFIG) is None


def patch(kind: str, west: float) -> Patch:
    ring = [
        [west, -33.0],
        [west + 0.004, -33.0],
        [west + 0.004, -32.996],
        [west, -32.996],
        [west, -33.0],
    ]
    return Patch(kind, 15.0, 0.4, "S", {"type": "Polygon", "coordinates": [ring]})


def finding(*patches: Patch) -> Finding:
    return Finding(DataQuality.GOOD, TODAY, list(patches), TODAY - timedelta(days=8))


def detection(session, lon: float, when: datetime) -> None:
    session.add(
        Observation(
            source="firms",
            product="VIIRS_NOAA21_NRT",
            satellite="NOAA-21",
            sensor="VIIRS",
            dedup_key=f"{lon}{when}",
            acquired_at=when,
            ingested_at=when,
            geom=WKTElement(f"POINT({lon} -32.998)", srid=4326),
            confidence_raw="h",
            confidence=Confidence.HIGH,
            raw_payload={},
        )
    )
    session.commit()


def test_a_burn_needs_a_fire_detection_between_the_two_dates(session):
    burnt, less_green = patch("burnt", -59.10), patch("less_green", -59.10)
    # No fire seen: the less-green patch over the same ground is the only report.
    assert [p.kind for p in confirm_burns(session, finding(burnt, less_green), 1000).patches] == [
        "less_green"
    ]
    # Alone, an unconfirmed burn is still reported, as less green.
    assert [p.kind for p in confirm_burns(session, finding(burnt), 1000).patches] == ["less_green"]
    # A fire detected next to it between the two dates confirms it, and it replaces the other.
    detection(session, -59.098, datetime(2026, 9, 30, 15, tzinfo=UTC))
    assert [p.kind for p in confirm_burns(session, finding(burnt, less_green), 1000).patches] == [
        "burnt"
    ]


def test_a_stored_patch_reaches_the_field_its_lots_the_map_and_the_summary(
    client, session, thresholds, outbox
):
    field = client.post(
        "/territories",
        json={"name": "La Esperanza", "geometry": rect(-59.10, -33.00, -59.09, -32.99)},
    ).json()
    west = client.post(
        "/territories",
        json={
            "name": "Oeste",
            "geometry": rect(-59.10, -33.00, -59.095, -32.99),
            "parent_id": field["id"],
        },
    ).json()
    east = client.post(
        "/territories",
        json={
            "name": "Este",
            "geometry": rect(-59.095, -33.00, -59.09, -32.99),
            "parent_id": field["id"],
        },
    ).json()
    # A dry patch in the west half only.
    dry = Patch("less_green", 12.0, 3.1, "W", rect(-59.099, -32.998, -59.096, -32.994))
    store_finding(
        session, field["id"], Finding(DataQuality.GOOD, TODAY, [dry]), datetime.now(UTC), "test"
    )

    answers = {e["name"]: e["anomaly"] for e in client.get("/portfolio").json()}
    assert answers["La Esperanza"]["patches"] == [
        {"kind": "less_green", "area_ha": 12.0, "where": "W"}
    ]
    assert len(answers["Oeste"]["patches"]) == 1
    assert (answers["Este"]["patches"], answers["Este"]["data_quality"]) == ([], "GOOD")

    features = client.get(f"/territories/{west['id']}/anomalies").json()["features"]
    assert features[0]["properties"]["kind"] == "less_green"
    assert client.get(f"/territories/{east['id']}/anomalies").json()["features"] == []

    session.add(User(email="default", locale="es", summary_sent_at=datetime.now(UTC)))
    session.commit()
    user = session.scalar(select(User).where(User.email == "default"))
    send_summary(session, outbox.append, Settings(), thresholds, user, datetime.now(UTC))
    assert "Algo raro: menos verde en 12,0 ha al O" in outbox[-1].get_content()


def rect(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}
