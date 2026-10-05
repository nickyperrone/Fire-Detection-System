from datetime import UTC, date, datetime

import numpy as np
import pytest
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from sqlalchemy import select

from app.main import app
from app.models import FieldSnapshot
from app.providers.sentinel2 import Box
from app.routers.dependencies import photo_root
from app.services import snapshots
from app.services.anomalies import field_bounds
from app.services.snapshots import snapshot_field
from app.services.territories import DEFAULT_OWNER, create_territory, edit_outline
from app.vision.snapshots import CLOUD_GRAY, greenness, pass_stats, true_color
from tests.conftest import ARGENTINA

NOW = datetime(2026, 10, 5, 12, tzinfo=UTC)
PIXEL_DEG = 0.0001


def rect(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def bands(shape, red=500, green=700, blue=400, nir=3500, cloudy=None) -> dict[str, np.ndarray]:
    """A crop in full green; `cloudy` rows are under cloud."""
    values = {"red": red, "green": green, "blue": blue, "nir": nir, "swir22": 1500, "scl": 4}
    out = {name: np.full(shape, value, "float32") for name, value in values.items()}
    if cloudy is not None:
        out["scl"][cloudy] = 9
    return out


def box_over(field, **kwargs) -> Box:
    west, south, east, north = field_bounds(field)
    shape = (round((north - south) / PIXEL_DEG), round((east - west) / PIXEL_DEG))
    transform = from_bounds(west, south, east, north, shape[1], shape[0])
    return Box(bands(shape, **kwargs), transform, CRS.from_epsg(4326))


@pytest.fixture
def config(thresholds):
    return thresholds["snapshots"]


def test_every_date_has_the_same_brightness_and_greenness_scale(config):
    shape = (4, 4)
    # The same ground on two dates is the same color: photos are never stretched one by one.
    assert np.array_equal(true_color(bands(shape), config), true_color(bands(shape), config))
    bare, crop = greenness(bands(shape, nir=600), config), greenness(bands(shape), config)
    assert bare[0, 0, 1] < crop[0, 0, 1] or bare[0, 0, 0] > crop[0, 0, 0]
    clouded = greenness(bands(shape, cloudy=np.s_[:2]), config)
    assert tuple(clouded[0, 0]) == CLOUD_GRAY
    assert tuple(clouded[3, 3]) != CLOUD_GRAY


def test_pass_stats_count_only_the_field():
    shape = (10, 10)
    field = np.zeros(shape, bool)
    field[:, :5] = True
    stats = pass_stats(bands(shape, cloudy=np.s_[:, 5:]), field)
    assert stats.cloud_share == 0
    assert stats.ndvi_mean == pytest.approx((3500 - 500) / 4000, abs=1e-3)
    assert pass_stats(bands(shape, cloudy=np.s_[:]), field).ndvi_mean is None


@pytest.fixture
def field(session):
    field = create_territory(
        session,
        owner=DEFAULT_OWNER,
        name="La Esperanza",
        geometry=rect(-59.10, -33.00, -59.09, -32.99),
        section_tolerance_m=5,
        allowed_area=ARGENTINA,
    )
    for number, (w, e) in enumerate([(-59.10, -59.095), (-59.095, -59.09)], start=1):
        create_territory(
            session,
            owner=DEFAULT_OWNER,
            name=f"Lote {number}",
            geometry=rect(w, -33.00, e, -32.99),
            parent_id=field.id,
            section_tolerance_m=5,
            allowed_area=ARGENTINA,
        )
    session.commit()
    return field


def take(session, field, config, tmp_path, monkeypatch, passes):
    monkeypatch.setattr(
        snapshots,
        "field_boxes",
        lambda client, territory, *_: [(d, b(territory)) for d, b in passes],
    )
    return snapshot_field(
        session, None, field, config, "v", NOW.date(), tmp_path, tmp_path / "photos"
    )


def test_clear_passes_are_kept_once_and_cloudy_ones_skipped(
    session, field, config, tmp_path, monkeypatch
):
    passes = [
        (date(2026, 9, 24), lambda t: box_over(t)),
        # Clouds over most of the field: not a photo worth keeping.
        (date(2026, 9, 29), lambda t: box_over(t, cloudy=np.s_[:])),
        (date(2026, 10, 4), lambda t: box_over(t, cloudy=np.s_[:30])),
    ]
    assert take(session, field, config, tmp_path, monkeypatch, passes) == 2
    rows = session.scalars(select(FieldSnapshot).order_by(FieldSnapshot.acquired_on)).all()
    assert [r.acquired_on for r in rows] == [date(2026, 9, 24), date(2026, 10, 4)]
    assert 0 < rows[1].cloud_share <= config["max_field_cloud_share"]
    assert (tmp_path / "photos" / str(field.id) / "2026-10-04-greenness.png").exists()
    # Already kept: nothing new on the next run.
    assert take(session, field, config, tmp_path, monkeypatch, passes) == 0

    # An edited outline is another box: the old photos go.
    edit_outline(
        session,
        field,
        operation="add",
        piece=rect(-59.09, -33.00, -59.088, -32.99),
        section_tolerance_m=5,
        allowed_area=ARGENTINA,
    )
    session.commit()
    assert take(session, field, config, tmp_path, monkeypatch, passes[:1]) == 1
    assert session.scalar(select(FieldSnapshot.acquired_on)) == date(2026, 9, 24)
    assert not (tmp_path / "photos" / str(field.id) / "2026-10-04-true_color.png").exists()


def test_a_lot_shows_its_fields_photos_with_every_outline(
    session, client, field, config, tmp_path, monkeypatch
):
    take(session, field, config, tmp_path, monkeypatch, [(date(2026, 10, 4), box_over)])
    app.dependency_overrides[photo_root] = lambda: tmp_path / "photos"
    lot = field.sections[0]
    answer = client.get(f"/territories/{lot.id}/snapshots").json()
    assert answer["field_id"] == field.id
    assert (answer["width"], answer["height"]) == (140, 140)
    assert [o["name"] for o in answer["outlines"]] == ["La Esperanza", "Lote 1", "Lote 2"]
    # The field's outline sits inside the image, 20 pixels (the box's margin) from its edges.
    first = answer["outlines"][0]["path"]
    assert first.startswith("M20.0 120.0")
    assert answer["snapshots"] == [{"date": "2026-10-04", "cloud_share": 0.0, "ndvi_mean": 0.75}]

    image = client.get(f"/territories/{field.id}/snapshots/2026-10-04/true_color.png")
    assert (image.status_code, image.headers["content-type"]) == (200, "image/png")
    assert (
        client.get(f"/territories/{field.id}/snapshots/2026-10-03/true_color.png").status_code
        == 404
    )
    assert (
        client.get(f"/territories/{field.id}/snapshots/2026-10-04/infrared.png").status_code == 422
    )
