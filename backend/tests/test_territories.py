import json

import pytest

from app.models import TerritoryKind
from app.services.territories import (
    TerritoryError,
    create_territory,
    list_territories,
    load_feature_collection,
)
from tests.conftest import BACKEND

SAMPLE = BACKEND.parent / "data" / "aoi" / "larroque_sample_fields.geojson"


def rect(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


@pytest.fixture
def loaded(session, thresholds):
    collection = json.loads(SAMPLE.read_text())
    tolerance = thresholds["territories"]["section_tolerance_m"]
    created = load_feature_collection(session, "default", collection, tolerance)
    session.commit()
    return created


def test_sample_file_loads_fields_sections_and_tags(loaded, session, thresholds):
    assert len(loaded) == 7
    esperanza = next(t for t in loaded if t.name == "La Esperanza")
    assert esperanza.kind == TerritoryKind.FIELD
    assert sorted(s.name for s in esperanza.sections) == ["Lote 1 - Soy", "Lote 2 - Corn"]
    # 0.025° x 0.015° at 33° S is about 2.33 km x 1.66 km.
    assert esperanza.hectares == pytest.approx(389, rel=0.01)
    assert sum(s.hectares for s in esperanza.sections) == pytest.approx(
        esperanza.hectares, rel=1e-3
    )
    again = load_feature_collection(
        session,
        "default",
        json.loads(SAMPLE.read_text()),
        thresholds["territories"]["section_tolerance_m"],
    )
    assert again == []


def test_tag_filter_requires_every_tag(loaded, session):
    def names(tags):
        return {t.name for t in list_territories(session, "default", tags)}

    assert names(["to-spray-this-week"]) == {"Campo Norte", "Lote 1 - Soy"}
    assert names(["client:Juan Perez", "zone:larroque-w"]) == {"El Ombu"}
    # A key without value matches any value of that key.
    assert names(["crop"]) == {
        "Lote 1 - Soy",
        "Lote 2 - Corn",
        "Campo Norte",
        "Lote A - Soy",
        "Lote B - Pasture",
    }


def test_section_outside_its_field_is_rejected(loaded, session):
    field = next(t for t in loaded if t.name == "Campo Norte")
    with pytest.raises(TerritoryError, match="not inside"):
        create_territory(
            session,
            owner="default",
            name="Stray lot",
            geometry=rect(-59.0, -32.9, -58.99, -32.89),
            parent_id=field.id,
            section_tolerance_m=5,
        )


def test_section_cannot_contain_sections(loaded, session):
    section = next(t for t in loaded if t.name == "Lote A - Soy")
    with pytest.raises(TerritoryError, match="only be created inside a field"):
        create_territory(
            session,
            owner="default",
            name="Nested",
            geometry=rect(-59.15, -32.995, -59.14, -32.99),
            parent_id=section.id,
            section_tolerance_m=5,
        )


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [-59.1, -32.9]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]},
        {"type": "Polygon"},
    ],
)
def test_invalid_geometries_are_rejected(session, geometry):
    with pytest.raises(TerritoryError):
        create_territory(
            session, owner="default", name="Bad", geometry=geometry, section_tolerance_m=5
        )
