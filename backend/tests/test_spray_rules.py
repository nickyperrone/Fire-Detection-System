from datetime import UTC, datetime, timedelta

import pytest

from app.models import SprayAssessment, SprayStatus
from app.providers.records import HourlyWeather
from app.services.portfolio import next_favorable_window
from app.services.spray_rules import (
    RuleStatus,
    delta_t_c,
    drift_direction,
    evaluate_hour,
    gusts_rule,
    inversion_rule,
    rain_rule,
    wind_rule,
)

NOON = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)
SUNRISE = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)


def hour(**overrides) -> HourlyWeather:
    values = {
        "time": NOON,
        "temperature_c": 22.0,
        "relative_humidity_pct": 60.0,
        "precipitation_mm": 0.0,
        "precipitation_probability_pct": 5.0,
        "wind_speed_kmh": 9.0,
        "wind_direction_deg": 225.0,
        "wind_gusts_kmh": 14.0,
        "cloud_cover_pct": 40.0,
        "is_day": True,
    }
    return HourlyWeather(**{**values, **overrides})


@pytest.fixture
def profile(thresholds):
    return thresholds["spray"]["profiles"]["default"]


def test_good_afternoon_is_favorable(profile):
    status, rules = evaluate_hour(hour(), [hour()], [SUNRISE], profile)
    assert status == SprayStatus.FAVORABLE
    assert {r.status for r in rules} == {RuleStatus.PASS}


@pytest.mark.parametrize(
    ("speed", "expected"),
    [
        (2.9, RuleStatus.CAUTION),
        (3, RuleStatus.PASS),
        (13, RuleStatus.PASS),
        (13.5, RuleStatus.CAUTION),
        (15, RuleStatus.CAUTION),
        (15.1, RuleStatus.FAIL),
    ],
)
def test_wind_edges(profile, speed, expected):
    assert wind_rule(hour(wind_speed_kmh=speed), profile["wind_kmh"]).status == expected


@pytest.mark.parametrize(
    ("gust", "expected"),
    [
        (16.9, RuleStatus.PASS),
        (17, RuleStatus.CAUTION),
        (20, RuleStatus.CAUTION),
        (20.1, RuleStatus.FAIL),
    ],
)
def test_gust_edges(profile, gust, expected):
    assert gusts_rule(hour(wind_gusts_kmh=gust), profile["gusts_kmh"]).status == expected


def test_one_failed_rule_makes_the_hour_unfavorable_and_says_why(profile):
    status, rules = evaluate_hour(hour(wind_gusts_kmh=27), [hour()], [SUNRISE], profile)
    assert status == SprayStatus.UNFAVORABLE
    failed = [r for r in rules if r.status == RuleStatus.FAIL]
    assert [r.rule for r in failed] == ["gusts"]
    assert "27 km/h > 20" in failed[0].message


def test_missing_input_is_never_a_pass(profile):
    status, rules = evaluate_hour(hour(wind_gusts_kmh=None), [hour()], [SUNRISE], profile)
    assert status == SprayStatus.CAUTION
    assert next(r for r in rules if r.rule == "gusts").status == RuleStatus.UNKNOWN


def test_delta_t_matches_reference_values():
    # Reference: 25 °C and 50 % RH has a wet bulb of about 18 °C.
    assert delta_t_c(25, 50) == pytest.approx(7.0, abs=0.3)
    assert delta_t_c(30, 20) > 10
    assert delta_t_c(15, 95) < 2


def test_rain_in_the_lookahead_window_fails(profile):
    window = [hour(), hour(precipitation_mm=0.3)]
    assert rain_rule(window, profile["rain"]).status == RuleStatus.FAIL
    likely = [hour(), hour(precipitation_probability_pct=60)]
    assert rain_rule(likely, profile["rain"]).status == RuleStatus.CAUTION


def test_inversion_is_an_estimate_and_never_fails(profile):
    calm_clear_night = hour(
        wind_speed_kmh=2,
        cloud_cover_pct=5,
        is_day=False,
        time=datetime(2026, 10, 1, 6, 0, tzinfo=UTC),
    )
    result = inversion_rule(calm_clear_night, [SUNRISE], profile["inversion"])
    assert result.status == RuleStatus.CAUTION
    assert result.estimated
    early = hour(wind_speed_kmh=2, cloud_cover_pct=5, time=SUNRISE + timedelta(hours=1))
    assert inversion_rule(early, [SUNRISE], profile["inversion"]).status == RuleStatus.CAUTION
    windy_night = hour(wind_speed_kmh=12, cloud_cover_pct=5, is_day=False)
    assert inversion_rule(windy_night, [SUNRISE], profile["inversion"]).status == RuleStatus.PASS


def test_drift_goes_opposite_to_wind_origin():
    assert drift_direction(225) == "NE"
    assert drift_direction(0) == "S"
    assert drift_direction(None) is None


def test_next_favorable_window_is_the_first_run_of_favorable_hours():
    statuses = ["UNFAVORABLE", "CAUTION", "FAVORABLE", "FAVORABLE", "CAUTION", "FAVORABLE"]
    assessments = [
        SprayAssessment(valid_at=NOON + timedelta(hours=i), status=SprayStatus(s))
        for i, s in enumerate(statuses)
    ]
    assert next_favorable_window(assessments) == (
        NOON + timedelta(hours=2),
        NOON + timedelta(hours=4),
    )
    assert next_favorable_window(assessments[:2]) is None
