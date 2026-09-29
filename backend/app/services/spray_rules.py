"""Spraying condition rules for one forecast hour (docs/03-rules.md#spray-conditions).

Pure functions: no database, no network, so every threshold edge is unit-tested.
"""

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.models import SprayStatus
from app.providers.records import HourlyWeather
from app.services.field_risk import compass


class RuleStatus(StrEnum):
    PASS = "PASS"
    CAUTION = "CAUTION"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RuleResult:
    rule: str
    status: RuleStatus
    value: float | None
    unit: str
    message: str
    estimated: bool = False

    def as_dict(self) -> dict:
        return {**asdict(self), "status": self.status.value}


def wet_bulb_c(temperature_c: float, relative_humidity_pct: float) -> float:
    """Stull (2011); valid for RH 5-99 % and -20 to 50 °C."""
    t, rh = temperature_c, relative_humidity_pct
    return (
        t * math.atan(0.151977 * math.sqrt(rh + 8.313659))
        + math.atan(t + rh)
        - math.atan(rh - 1.676331)
        + 0.00391838 * rh**1.5 * math.atan(0.023101 * rh)
        - 4.686035
    )


def delta_t_c(temperature_c: float, relative_humidity_pct: float) -> float:
    return temperature_c - wet_bulb_c(temperature_c, relative_humidity_pct)


def wind_rule(hour: HourlyWeather, limits: dict) -> RuleResult:
    v = hour.wind_speed_kmh
    if v is None:
        return RuleResult("wind", RuleStatus.UNKNOWN, None, "km/h", "no wind forecast")
    if v > limits["max"]:
        return RuleResult(
            "wind", RuleStatus.FAIL, v, "km/h", f"wind {v:.0f} km/h > {limits['max']}"
        )
    if v < limits["min"]:
        msg = f"wind {v:.0f} km/h < {limits['min']}: drift can hang in still air"
        return RuleResult("wind", RuleStatus.CAUTION, v, "km/h", msg)
    if v > limits["caution_from"]:
        msg = f"wind {v:.0f} km/h (caution from {limits['caution_from']})"
        return RuleResult("wind", RuleStatus.CAUTION, v, "km/h", msg)
    return RuleResult("wind", RuleStatus.PASS, v, "km/h", f"wind {v:.0f} km/h")


def gusts_rule(hour: HourlyWeather, limits: dict) -> RuleResult:
    v = hour.wind_gusts_kmh
    if v is None:
        return RuleResult("gusts", RuleStatus.UNKNOWN, None, "km/h", "no gust forecast")
    if v > limits["max"]:
        return RuleResult(
            "gusts", RuleStatus.FAIL, v, "km/h", f"gusts {v:.0f} km/h > {limits['max']}"
        )
    if v >= limits["caution_from"]:
        msg = f"gusts {v:.0f} km/h (caution from {limits['caution_from']})"
        return RuleResult("gusts", RuleStatus.CAUTION, v, "km/h", msg)
    return RuleResult("gusts", RuleStatus.PASS, v, "km/h", f"gusts {v:.0f} km/h")


def delta_t_rule(hour: HourlyWeather, limits: dict) -> RuleResult:
    if hour.temperature_c is None or hour.relative_humidity_pct is None:
        return RuleResult("delta_t", RuleStatus.UNKNOWN, None, "°C", "no temperature or humidity")
    v = round(delta_t_c(hour.temperature_c, hour.relative_humidity_pct), 1)
    if v > limits["max"]:
        msg = f"Delta T {v} °C > {limits['max']}: droplets evaporate"
        return RuleResult("delta_t", RuleStatus.FAIL, v, "°C", msg)
    if v < limits["min"]:
        msg = f"Delta T {v} °C < {limits['min']}: droplets stay suspended"
        return RuleResult("delta_t", RuleStatus.CAUTION, v, "°C", msg)
    if v > limits["caution_from"]:
        msg = f"Delta T {v} °C (caution from {limits['caution_from']})"
        return RuleResult("delta_t", RuleStatus.CAUTION, v, "°C", msg)
    return RuleResult("delta_t", RuleStatus.PASS, v, "°C", f"Delta T {v} °C")


def temperature_rule(hour: HourlyWeather, limits: dict) -> RuleResult:
    v = hour.temperature_c
    if v is None:
        return RuleResult("temperature", RuleStatus.UNKNOWN, None, "°C", "no temperature")
    if v > limits["max"]:
        msg = f"temperature {v:.0f} °C > {limits['max']}"
        return RuleResult("temperature", RuleStatus.FAIL, v, "°C", msg)
    if v >= limits["caution_from"]:
        msg = f"temperature {v:.0f} °C (caution from {limits['caution_from']})"
        return RuleResult("temperature", RuleStatus.CAUTION, v, "°C", msg)
    return RuleResult("temperature", RuleStatus.PASS, v, "°C", f"temperature {v:.0f} °C")


def rain_rule(window: list[HourlyWeather], limits: dict) -> RuleResult:
    """`window` is this hour and the following ones up to the lookahead."""
    amounts = [h.precipitation_mm for h in window if h.precipitation_mm is not None]
    if not amounts:
        return RuleResult("rain", RuleStatus.UNKNOWN, None, "mm", "no rain forecast")
    total = round(sum(amounts), 1)
    hours = limits["lookahead_hours"]
    if total >= limits["max_mm"]:
        return RuleResult(
            "rain", RuleStatus.FAIL, total, "mm", f"{total} mm of rain in the next {hours} h"
        )
    probabilities = [
        h.precipitation_probability_pct
        for h in window
        if h.precipitation_probability_pct is not None
    ]
    if probabilities and max(probabilities) >= limits["caution_probability_pct"]:
        msg = f"{max(probabilities):.0f} % chance of rain in the next {hours} h"
        return RuleResult("rain", RuleStatus.CAUTION, total, "mm", msg)
    return RuleResult(
        "rain", RuleStatus.PASS, total, "mm", f"no rain expected in the next {hours} h"
    )


def inversion_rule(hour: HourlyWeather, sunrises: list[datetime], limits: dict) -> RuleResult:
    """Estimated from weather only. It can raise CAUTION, never FAIL."""
    if hour.wind_speed_kmh is None or hour.cloud_cover_pct is None or hour.is_day is None:
        return RuleResult(
            "inversion", RuleStatus.UNKNOWN, None, "", "not enough data", estimated=True
        )
    after_sunrise = timedelta(hours=limits["hours_after_sunrise"])
    early_morning = any(s <= hour.time < s + after_sunrise for s in sunrises)
    flagged = (
        hour.wind_speed_kmh < limits["max_wind_kmh"]
        and hour.cloud_cover_pct < limits["max_cloud_cover_pct"]
        and (not hour.is_day or early_morning)
    )
    if flagged:
        msg = "estimated inversion risk: calm, clear, night or early morning"
        return RuleResult("inversion", RuleStatus.CAUTION, None, "", msg, estimated=True)
    return RuleResult(
        "inversion", RuleStatus.PASS, None, "", "no inversion risk estimated", estimated=True
    )


def evaluate_hour(
    hour: HourlyWeather, window: list[HourlyWeather], sunrises: list[datetime], profile: dict
) -> tuple[SprayStatus, list[RuleResult]]:
    rules = [
        wind_rule(hour, profile["wind_kmh"]),
        gusts_rule(hour, profile["gusts_kmh"]),
        delta_t_rule(hour, profile["delta_t_c"]),
        temperature_rule(hour, profile["temperature_c"]),
        rain_rule(window, profile["rain"]),
        inversion_rule(hour, sunrises, profile["inversion"]),
    ]
    statuses = {r.status for r in rules}
    if RuleStatus.FAIL in statuses:
        return SprayStatus.UNFAVORABLE, rules
    # UNKNOWN never counts as PASS: an hour we cannot fully check is at best CAUTION.
    if statuses & {RuleStatus.CAUTION, RuleStatus.UNKNOWN}:
        return SprayStatus.CAUTION, rules
    return SprayStatus.FAVORABLE, rules


def drift_direction(wind_from_deg: float | None) -> str | None:
    """Wind direction is where the wind comes from; drift goes the opposite way."""
    return None if wind_from_deg is None else compass((wind_from_deg + 180) % 360)
