from datetime import UTC, datetime

from sqlalchemy import select, text

from app.models import FieldRiskEvent, LandCover, Severity
from app.providers.worldcover import tile_name, tiles_for
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

    def count(area) -> dict[str, int]:
        reads.append(area)
        if len(reads) % 2:
            return {"crops": 700, "trees": 250, "built": 50}
        return {"crops": 900, "built": 4}

    return count


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
