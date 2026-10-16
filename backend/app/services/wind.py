"""Wind at each field and what it does to a fire nearby (docs/03-rules.md#wind)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

# The hour of the forecast that holds `now`, per field.
WIND_NOW_SQL = text("""
    SELECT DISTINCT ON (territory_id) territory_id, weather
    FROM spray_assessment
    WHERE territory_id = ANY(:ids) AND valid_at > :since AND valid_at <= :until
    ORDER BY territory_id, valid_at DESC
""")


@dataclass(frozen=True)
class Wind:
    speed_kmh: float
    from_deg: float


@dataclass(frozen=True)
class Push:
    """What the wind does to one fire near one field."""

    toward: bool
    # Severity bands the fire moves up: 0, 1 or 2.
    raise_by: int
    # Rough hours until the fire front reaches the field, when the wind carries it there.
    arrival_h: float | None


def wind_now(session: Session, ids: list[int], now: datetime) -> dict[int, Wind]:
    """The wind at each field in the current hour of its forecast, where there is one."""
    if not ids:
        return {}
    rows = session.execute(
        WIND_NOW_SQL, {"ids": ids, "since": now - timedelta(hours=1), "until": now}
    )
    wind = {}
    for row in rows:
        speed, origin = row.weather.get("wind_speed_kmh"), row.weather.get("wind_direction_deg")
        if speed is not None and origin is not None:
            wind[row.territory_id] = Wind(speed, origin)
    return wind


def wind_toward(bearing_deg: float, wind_from_deg: float, within_deg: float = 45) -> bool:
    """Whether the wind blows from the fire's side toward the field: the bearing from the field to
    the fire within `within_deg` of where the wind comes from."""
    return abs((bearing_deg - wind_from_deg + 180) % 360 - 180) <= within_deg


def push(wind: Wind | None, bearing_deg: float | None, distance_m: float, config: dict) -> Push:
    """Wind from the fire toward the field raises the danger, more the stronger it blows, and
    gives a rough time of arrival: a grass fire runs at about a tenth of the wind speed."""
    if (
        wind is None
        or bearing_deg is None
        or wind.speed_kmh < config["min_kmh"]
        or not wind_toward(bearing_deg, wind.from_deg, config["toward_within_deg"])
    ):
        return Push(toward=False, raise_by=0, arrival_h=None)
    raise_by = sum(
        wind.speed_kmh >= config[key] for key in ("raise_one_from_kmh", "raise_two_from_kmh")
    )
    speed = wind.speed_kmh * config["spread_share"]
    return Push(toward=True, raise_by=raise_by, arrival_h=round(distance_m / 1000 / speed, 1))
