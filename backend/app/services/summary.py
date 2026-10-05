"""Daily and weekly summaries by email (docs/09-accounts-and-alerts.md#summaries)."""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.forecast.dataset import weather_point
from app.forecast.live_weather import LOCAL_TZ
from app.models import SummaryFrequency, Territory, User
from app.services.email_text import summary_email
from app.services.mail import SEND_ERRORS, SendEmail, message
from app.services.portfolio import PortfolioEntry, build_portfolio

log = logging.getLogger(__name__)

SEND_HOUR = 7
PERIOD = {SummaryFrequency.DAILY: timedelta(days=1), SummaryFrequency.WEEKLY: timedelta(days=7)}
# The forecast bands worth a line in a summary.
RISKY_BANDS = ("HIGH", "VERY_HIGH")

# Detections, not fire events: a fire burning for three days is three fire days. Detections on a
# known static heat source (a steel plant) are not fires.
FIRE_DAYS_SQL = text("""
    SELECT t.id AS territory_id,
           count(DISTINCT (o.acquired_at AT TIME ZONE :tz)::date) AS days,
           min(ST_Distance(t.geom::geography, o.geom::geography)) AS closest_m,
           (array_agg(o.acquired_at ORDER BY ST_Distance(t.geom::geography, o.geom::geography)))[1]
               AS closest_at
    FROM territory t
    JOIN observation o
      ON o.geom && ST_Expand(t.geom, :radius_deg)
     AND ST_DWithin(t.geom::geography, o.geom::geography, :radius_m)
    WHERE t.id = ANY(:ids) AND o.acquired_at >= :since AND NOT o.static_source
    GROUP BY t.id
""")

FLASHES_SQL = text("""
    SELECT t.id AS territory_id, count(*) AS flashes
    FROM territory t
    JOIN lightning_flash f
      ON f.geom && ST_Expand(t.geom, :radius_deg)
     AND ST_DWithin(t.geom::geography, f.geom::geography, :radius_m)
    WHERE t.id = ANY(:ids) AND f.observed_at >= :since
    GROUP BY t.id
""")

CENTROIDS_SQL = text("""
    SELECT id, ST_Y(ST_Centroid(geom)) AS lat, ST_X(ST_Centroid(geom)) AS lon
    FROM territory WHERE id = ANY(:ids)
""")

RAIN_SQL = text("""
    SELECT latitude, longitude, sum(rain_mm) AS rain_mm
    FROM weather_day
    WHERE day >= :first AND day <= :last
    GROUP BY latitude, longitude
""")


@dataclass
class FieldSummary:
    entry: PortfolioEntry
    fire_days: int
    closest_fire_m: float | None
    closest_fire_at: datetime | None
    flashes: int
    rain_mm: float | None


def due_since(frequency: SummaryFrequency, now: datetime) -> datetime | None:
    """The last time a summary of this frequency was due: 07:00 today (or yesterday), or 07:00 on
    the last Monday. None when summaries are off."""
    if frequency == SummaryFrequency.OFF:
        return None
    local = now.astimezone(ZoneInfo(LOCAL_TZ))
    slot = local.replace(hour=SEND_HOUR, minute=0, second=0, microsecond=0)
    if local < slot:
        slot -= timedelta(days=1)
    if frequency == SummaryFrequency.WEEKLY:
        slot -= timedelta(days=slot.weekday())
    return slot


def build_summary(
    session: Session, owner: str, thresholds: dict, since: datetime, now: datetime
) -> list[FieldSummary]:
    """Every field and lot of the account, in the list's order, with the period behind it."""
    entries = build_portfolio(session, owner, thresholds, now)
    ids = [e.territory.id for e in entries]
    if not ids:
        return []
    radius_m = thresholds["field_risk"]["bands"][-1]["max_distance_m"]
    # Degrees covering the radius in any direction south to 41° S (cos 41° > 0.75).
    params = {
        "ids": ids,
        "since": since,
        "radius_m": radius_m,
        "radius_deg": radius_m / (111_320 * 0.75),
    }
    fires = {r.territory_id: r for r in session.execute(FIRE_DAYS_SQL, params | {"tz": LOCAL_TZ})}
    flashes = {r.territory_id: r.flashes for r in session.execute(FLASHES_SQL, params)}
    rain = _rain(session, ids, thresholds["forecast"]["weather_degrees"], since, now)
    return [
        FieldSummary(
            entry=e,
            fire_days=fires[e.territory.id].days if e.territory.id in fires else 0,
            closest_fire_m=fires[e.territory.id].closest_m if e.territory.id in fires else None,
            closest_fire_at=fires[e.territory.id].closest_at if e.territory.id in fires else None,
            flashes=flashes.get(e.territory.id, 0),
            rain_mm=rain.get(e.territory.id),
        )
        for e in entries
    ]


def _rain(
    session: Session, ids: list[int], degrees: float, since: datetime, now: datetime
) -> dict[int, float]:
    """Rain over the period at each field's weather point: the area's rain, not a gauge's."""
    local = ZoneInfo(LOCAL_TZ)
    first: date = since.astimezone(local).date()
    last: date = now.astimezone(local).date()
    by_point = {
        (r.latitude, r.longitude): r.rain_mm
        for r in session.execute(RAIN_SQL, {"first": first, "last": last})
    }
    out = {}
    for r in session.execute(CENTROIDS_SQL, {"ids": ids}):
        point = weather_point(r.lat, r.lon, degrees)
        if point in by_point:
            out[r.id] = round(by_point[point], 1)
    return out


def send_summary(
    session: Session,
    send: SendEmail,
    settings: Settings,
    thresholds: dict,
    user: User,
    now: datetime,
) -> bool:
    """Builds and sends one account's summary; False when it has no fields."""
    frequency = user.summary if user.summary != SummaryFrequency.OFF else SummaryFrequency.WEEKLY
    since = now - PERIOD[frequency]
    fields = build_summary(session, user.email, thresholds, since, now)
    if not fields:
        return False
    subject, body = summary_email(user.locale, frequency, fields, settings.app_url)
    send(message(settings, user.email, subject, body))
    user.summary_sent_at = now
    session.commit()
    return True


def send_due_summaries(
    session: Session, send: SendEmail, settings: Settings, thresholds: dict, now: datetime
) -> dict:
    sent = failed = 0
    users = session.scalars(select(User).where(User.summary != SummaryFrequency.OFF)).all()
    for user in users:
        slot = due_since(user.summary, now)
        if user.summary_sent_at is not None and user.summary_sent_at >= slot:
            continue
        has_fields = session.scalar(select(Territory.id).where(Territory.owner == user.email))
        if has_fields is None:
            continue
        try:
            sent += send_summary(session, send, settings, thresholds, user, now)
        except SEND_ERRORS as exc:
            # Not marked as sent, so the next check tries again.
            log.warning("summary to user %s not sent: %s", user.id, exc)
            failed += 1
    return {"summaries_sent": sent, "summaries_failed": failed}
