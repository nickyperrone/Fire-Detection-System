from sqlalchemy import select

from app.models import DataQuality, FieldRiskEvent, Severity, SprayAssessment, SprayStatus
from app.services.email_text import arrival
from app.services.field_risk import assess_fire_events, raised
from app.services.wind import Wind, push
from tests.test_fire_pipeline import NOW, VERSION, pipeline, territory_id  # noqa: F401


def test_wind_from_the_fire_raises_the_danger_and_gives_a_time(thresholds):
    config = thresholds["field_risk"]["wind"]
    # The fire is to the east and the wind comes from the east at 20 km/h: it runs at ~2 km/h.
    pushed = push(Wind(20, 80), 90, 5000, config)
    assert (pushed.toward, pushed.raise_by, pushed.arrival_h) == (True, 1, 2.5)
    assert push(Wind(35, 90), 90, 5000, config).raise_by == 2
    # From the other side, or too calm to carry it anywhere: no change.
    assert not push(Wind(20, 270), 90, 5000, config).toward
    assert not push(Wind(3, 90), 90, 5000, config).toward
    assert not push(None, 90, 5000, config).toward


def test_wind_never_makes_a_fire_outside_the_field_critical():
    assert raised(Severity.WATCH, 1) == Severity.HIGH
    assert raised(Severity.WATCH, 2) == Severity.VERY_HIGH
    assert raised(Severity.HIGH, 2) == Severity.VERY_HIGH


def test_arrival_is_said_as_an_estimate():
    assert arrival(0.4, "es") == "Si avanza con el viento, llegaría en ~25 min (estimado)."
    assert "~2,4 h" in arrival(2.4, "es")
    assert "~5 h" in arrival(5.2, "en")


def test_a_far_fire_upwind_of_a_field_is_raised(pipeline, session, thresholds):  # noqa: F811
    north = territory_id(session, "Campo Norte")
    risk = session.scalar(select(FieldRiskEvent).where(FieldRiskEvent.territory_id == north))
    assert risk.severity == Severity.WATCH
    session.add(
        SprayAssessment(
            territory_id=north,
            profile="default",
            valid_at=NOW,
            status=SprayStatus.UNFAVORABLE,
            rules=[],
            weather={"wind_speed_kmh": 22, "wind_direction_deg": risk.bearing_deg},
            data_quality=DataQuality.GOOD,
            forecast_fetched_at=NOW,
            processing_version="test",
        )
    )
    session.commit()
    assess_fire_events(session, {risk.fire_event_id}, thresholds["field_risk"], VERSION, NOW)
    session.refresh(risk)
    assert risk.severity == Severity.HIGH
    assert risk.factors["wind_toward"] and risk.factors["wind_raised_by"] == 1
    assert risk.factors["arrival_h"] == round(risk.distance_m / 1000 / 2.2, 1)
