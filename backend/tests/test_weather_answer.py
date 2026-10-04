from datetime import UTC, datetime, timedelta

from app.models import DataQuality, SprayAssessment, SprayStatus
from app.services.portfolio import _weather_answer

NOW = datetime(2026, 10, 4, 15, 20, tzinfo=UTC)
QUALITY = {"weather_stale_after_hours": 3}


def hour(offset: int, rain_mm: float, chance: int) -> SprayAssessment:
    return SprayAssessment(
        valid_at=NOW.replace(minute=0) + timedelta(hours=offset),
        status=SprayStatus.FAVORABLE,
        rules=[],
        weather={
            "temperature_c": 21.5 + offset,
            "relative_humidity_pct": 58,
            "wind_speed_kmh": 12.0,
            "wind_direction_deg": 180,
            "wind_gusts_kmh": 23.0,
            "cloud_cover_pct": 40,
            "precipitation_mm": rain_mm,
            "precipitation_probability_pct": chance,
        },
        data_quality=DataQuality.GOOD,
        forecast_fetched_at=NOW - timedelta(minutes=30),
    )


def test_weather_now_and_rain_in_the_next_day():
    # Rain at hour 5 counts; rain at hour 30 is beyond the next 24 hours.
    hours = [hour(h, 2.5 if h in (5, 30) else 0.0, 70 if h == 5 else 10) for h in range(48)]
    answer = _weather_answer(hours, QUALITY, NOW)
    assert answer.data_quality == DataQuality.GOOD
    assert (answer.temperature_c, answer.wind_speed_kmh, answer.wind_gusts_kmh) == (
        21.5,
        12.0,
        23.0,
    )
    assert answer.wind_from == "S"
    assert (answer.rain_24h_mm, answer.rain_probability_pct) == (2.5, 70)


def test_old_or_missing_weather_says_so():
    old = hour(0, 0.0, 0)
    old.forecast_fetched_at = NOW - timedelta(hours=7)
    assert _weather_answer([old], QUALITY, NOW).data_quality == DataQuality.STALE
    empty = _weather_answer([], QUALITY, NOW)
    assert (empty.data_quality, empty.temperature_c) == (DataQuality.NO_DATA, None)
