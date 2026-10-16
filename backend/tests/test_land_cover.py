from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text

from app.models import FieldRiskEvent, LandCover, Severity
from app.providers.worldcover import Classes, tile_name, tiles_for
from app.services.email_text import holds_line
from app.services.field_risk import assess_fire_events
from app.services.land_cover import contents, refresh_land_cover
from tests.test_fire_pipeline import VERSION, pipeline, territory_id  # noqa: F401

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
CONFIG = {"ring_m": 300, "per_run": 50}


def farm():
    """A reader that sees a field of crops with a grove and a farmstead, and a neighbor's house in
    the ring around it: the field is read first, then its ring."""
    reads = []

    def read(area, outlines=False) -> Classes:
        reads.append(area)
        if len(reads) % 2:
            grove = {"type": "Feature", "properties": {"kind": "trees"}, "geometry": {}}
            return Classes({"crops": 700, "trees": 250, "built": 50}, [grove])
        return Classes({"crops": 900, "built": 4})

    return read


def test_files_are_named_after_their_south_west_corner():
    assert tile_name(-33.02, -59.04) == "S36W060"
    assert tile_name(-32.9, -57.5) == "S33W060"
    # A box across 33°S needs two files.
    assert [name for name, _ in tiles_for((-59.1, -33.05, -59.0, -32.98))] == ["S36W060", "S33W060"]


def test_each_field_gets_its_cover_once_until_redrawn(pipeline, session):  # noqa: F811
    count = farm()
    first = refresh_land_cover(session, CONFIG, NOW, count)
    fields = session.scalar(text("SELECT count(*) FROM territory"))
    assert first["land_cover_done"] == fields
    assert refresh_land_cover(session, CONFIG, NOW, count)["land_cover_done"] == 0
    north = territory_id(session, "Campo Norte")
    session.execute(
        text("UPDATE territory SET geom = ST_Multi(ST_Buffer(geom, 0.001)) WHERE id = :id"),
        {"id": north},
    )
    session.commit()
    assert refresh_land_cover(session, CONFIG, NOW, count)["land_cover_done"] == 1
    row = session.get(LandCover, north)
    assert row.shares == {"built": 0.05, "crops": 0.7, "trees": 0.25}
    assert row.features[0]["properties"]["kind"] == "trees"
    assert row.built_m2 > 2000 and 0 < row.built_nearby_m2 < row.built_m2


def test_a_wooded_field_with_houses_hears_of_a_fire_sooner(pipeline, session, thresholds):  # noqa: F811
    north = territory_id(session, "Campo Norte")
    risk = session.scalar(select(FieldRiskEvent).where(FieldRiskEvent.territory_id == north))
    assert risk.severity == Severity.WATCH
    refresh_land_cover(session, CONFIG, NOW, farm())
    assess_fire_events(session, {risk.fire_event_id}, thresholds["field_risk"], VERSION, NOW)
    session.refresh(risk)
    assert risk.severity == Severity.HIGH
    assert risk.factors["land_raised_by"] == 1 and risk.factors["trees_share"] == 0.25


def test_an_alert_says_what_is_in_the_field(pipeline, session, thresholds):  # noqa: F811
    refresh_land_cover(session, CONFIG, NOW, farm())
    holds = contents(session.get(LandCover, territory_id(session, "Campo Norte")))
    line = holds_line(holds, thresholds["field_risk"]["land_cover"], "es")
    assert line == "🏠 Hay construcciones en el campo · 🌳 Árboles 25 % · 🌾 Cultivo 70 %"


def passes(session, field_id, means):
    from datetime import date

    from app.models import FieldSnapshot

    for i, mean in enumerate(means):
        session.add(
            FieldSnapshot(
                territory_id=field_id,
                acquired_on=date(2026, 1 + i, 10),
                box_key="k",
                width=1,
                height=1,
                grid={},
                cloud_share=0,
                ndvi_means={str(field_id): mean},
                processing_version="test",
            )
        )
    session.commit()


def explained(session, thresholds, means):
    from app.models import Territory
    from app.services.land_cover import explain

    refresh_land_cover(session, CONFIG, NOW, farm())
    field = session.get(Territory, territory_id(session, "Campo Norte"))
    passes(session, field.id, means)
    row = session.get(LandCover, field.id)
    return explain(session, field, row, thresholds["land_cover"])


@pytest.mark.usefixtures("pipeline")
def test_it_is_called_planted_only_when_the_map_and_the_greenness_agree(session, thresholds):
    said = explained(session, thresholds, [0.2, 0.7, 0.35])
    assert said["use"] == "cultivated"
    map_, cycle = said["reasons"]
    assert map_ == {"code": "map_crops", "share": 0.7}
    assert (cycle["code"], cycle["low"], cycle["high"], cycle["passes"]) == (
        "greenness_cycle",
        0.2,
        0.7,
        3,
    )


@pytest.mark.usefixtures("pipeline")
def test_crops_on_the_map_with_flat_greenness_are_only_maybe_planted(session, thresholds):
    said = explained(session, thresholds, [0.55, 0.6, 0.58])
    assert said["use"] == "maybe_cultivated"
    assert said["reasons"][1]["code"] == "greenness_flat"
