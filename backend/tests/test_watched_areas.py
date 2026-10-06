import pytest

from app.services.territories import DEFAULT_OWNER, create_territory
from app.services.watched_areas import merge_boxes, watched_areas
from tests.conftest import ARGENTINA

REGION = (-61.0, -34.5, -57.5, -30.0)


def rect(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def test_boxes_that_touch_become_one():
    a, b, far = (0, 0, 2, 2), (1, 1, 3, 3), (10, 10, 11, 11)
    assert merge_boxes([a, far, b]) == [(0, 0, 3, 3), far]
    # A box joining two others pulls all three together.
    assert merge_boxes([(0, 0, 1, 1), (2, 0, 3, 1), (0.5, 0, 2.5, 1)]) == [(0, 0, 3, 1)]


def add_field(session, name, geometry):
    create_territory(
        session,
        owner=DEFAULT_OWNER,
        name=name,
        geometry=geometry,
        section_tolerance_m=5,
        allowed_area=ARGENTINA,
    )
    session.commit()


def test_a_field_far_from_the_region_is_watched_in_its_own_box(session, thresholds):
    assert watched_areas(session, thresholds) == [REGION]
    # Inside the region: nothing new to read.
    add_field(session, "Larroque", rect(-59.1, -33.0, -59.09, -32.99))
    assert watched_areas(session, thresholds) == [REGION]

    add_field(session, "Formosa", rect(-59.34, -26.31, -59.32, -26.29))
    m = thresholds["region"]["field_margin_degrees"]
    region, formosa = watched_areas(session, thresholds)
    assert formosa == pytest.approx((-59.34 - m, -26.31 - m, -59.32 + m, -26.29 + m))
    assert region == REGION
