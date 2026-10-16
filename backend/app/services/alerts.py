"""Alerts of new danger near fields, by email and Telegram, as each account chose
(docs/09-accounts-and-alerts.md#email-alerts, docs/13-notifications.md)."""

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from geoalchemy2.shape import to_shape
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.forecast.live_weather import LOCAL_TZ
from app.models import (
    AlertDelivery,
    FieldRiskEvent,
    FireEvent,
    FireEventStatus,
    RiskStatus,
    Territory,
    User,
)
from app.providers.telegram import Telegram, TelegramBlocked, TelegramError
from app.services.email_text import Danger, alert_caption, alert_email, holds_line
from app.services.field_risk import SEVERITY_RANK, compass
from app.services.land_cover import contents_of
from app.services.lightning import nearby_lightning
from app.services.mail import SEND_ERRORS, SendEmail, message
from app.services.notification_prefs import CHANNELS, FIRE_KIND, Kind, wants
from app.services.wind import Push, Wind, push, wind_now

log = logging.getLogger(__name__)

# A field's photo for its dangers; None leaves the alert as text.
Picture = Callable[[Territory, list[Danger], tuple[float, float] | None, str], bytes | None]

HOURS_SQL = text("""
    SELECT DISTINCT ON (territory_id, valid_at) territory_id, valid_at, weather
    FROM spray_assessment
    WHERE territory_id = ANY(:ids) AND valid_at > :since AND valid_at <= :until
    ORDER BY territory_id, valid_at
""")


@dataclass
class Found:
    """A danger found this run: who hears about it, and how it is marked as announced."""

    user: User
    territory: Territory
    kind: Kind
    danger: Danger
    mark: Callable[[], None]
    # False for a lot whose field announces the same danger: marked, not repeated.
    shown: bool = True

    @property
    def group(self) -> int:
        """The field whose message carries it."""
        return self.territory.id if self.shown else self.territory.parent_id


def _rank(danger: Danger) -> tuple:
    # Worst first: fires by severity, then lightning, then the weather; closer first within each.
    severity = SEVERITY_RANK[danger.severity] if danger.severity else -1
    order = {"fire": 0, "lightning": 1, "weather": 2}[danger.kind]
    return (order, -severity, danger.distance_m)


def _alerting(session: Session) -> list[tuple[Territory, User]]:
    return session.execute(
        select(Territory, User).join(User, User.email == Territory.owner).where(Territory.alerts)
    ).all()


def _fires(session: Session) -> list[Found]:
    rows = session.execute(
        select(FieldRiskEvent, Territory, User)
        .join(Territory, FieldRiskEvent.territory_id == Territory.id)
        .join(User, User.email == Territory.owner)
        .join(FireEvent, FieldRiskEvent.fire_event_id == FireEvent.id)
        .where(
            Territory.alerts,
            FireEvent.status == FireEventStatus.ACTIVE,
            FieldRiskEvent.status != RiskStatus.RESOLVED,
        )
    ).all()
    found = []
    for risk, territory, user in rows:
        if risk.notified_severity is not None and (
            SEVERITY_RANK[risk.severity] <= SEVERITY_RANK[risk.notified_severity]
        ):
            continue
        event = risk.fire_event
        danger = Danger(
            territory_id=territory.id,
            name=territory.name,
            kind="fire",
            distance_m=risk.distance_m,
            direction=compass(risk.bearing_deg),
            severity=risk.severity,
            sensors=sorted(event.sensors),
            seen_at=event.last_detected_at,
            fire_event_id=event.id,
            bearing_deg=risk.bearing_deg,
            fire_at=_lat_lon(event),
        )
        found.append(Found(user, territory, FIRE_KIND[risk.severity], danger, _mark_fire(risk)))
    shown = {(f.territory.id, f.danger.fire_event_id) for f in found}
    for f in found:
        f.shown = (f.territory.parent_id, f.danger.fire_event_id) not in shown
    return found


def _lat_lon(event: FireEvent) -> tuple[float, float]:
    point = to_shape(event.geom).centroid
    return (round(point.y, 5), round(point.x, 5))


def _mark_fire(risk: FieldRiskEvent) -> Callable[[], None]:
    def mark() -> None:
        risk.notified_severity = risk.severity

    return mark


def _mark_at(territory: Territory, column: str, now: datetime) -> Callable[[], None]:
    def mark() -> None:
        setattr(territory, column, now)

    return mark


def _lightning(session: Session, thresholds: dict, now: datetime) -> list[Found]:
    quiet_since = now - timedelta(minutes=thresholds["alerts"]["lightning_quiet_minutes"])
    candidates = {
        t.id: (t, u)
        for t, u in _alerting(session)
        if t.lightning_notified_at is None or t.lightning_notified_at < quiet_since
    }
    nearby = nearby_lightning(session, list(candidates), thresholds["lightning"], now)
    found = []
    for territory_id, near in nearby.items():
        if near.flashes == 0:
            continue
        territory, user = candidates[territory_id]
        danger = Danger(
            territory_id=territory.id,
            name=territory.name,
            kind="lightning",
            distance_m=near.nearest_m,
            direction=None,
            severity=None,
            sensors=[],
            seen_at=None,
        )
        mark = _mark_at(territory, "lightning_notified_at", now)
        found.append(Found(user, territory, "lightning", danger, mark))
    ids = {f.territory.id for f in found}
    for f in found:
        f.shown = f.territory.parent_id not in ids
    return found


def _worst_weather(hours: list[tuple[datetime, dict]], config: dict) -> dict:
    """Gusts, rain in a day and rain in an hour over their thresholds, each at its worst."""
    worst: dict = {}
    gusts = [(w.get("wind_gusts_kmh") or 0, at) for at, w in hours]
    top, at = max(gusts, key=lambda g: g[0])
    if top >= config["gusts_kmh"]:
        worst |= {"gusts_kmh": top, "gusts_at": at.isoformat()}
    rain = [(w.get("precipitation_mm") or 0, at) for at, w in hours]
    top, at = max(rain, key=lambda r: r[0])
    if top >= config["rain_hour_mm"]:
        worst |= {"rain_hour_mm": top, "rain_hour_at": at.isoformat()}
    days: dict = defaultdict(float)
    local = ZoneInfo(LOCAL_TZ)
    for mm, at in rain:
        days[at.astimezone(local).date()] += mm
    day, top = max(days.items(), key=lambda d: d[1])
    if top >= config["rain_day_mm"]:
        noon = datetime.combine(day, datetime.min.time(), local) + timedelta(hours=12)
        worst |= {"rain_day_mm": top, "rain_day": noon.isoformat()}
    return worst


def _weather(session: Session, thresholds: dict, now: datetime) -> list[Found]:
    """Adverse weather in the next hours, once per episode: while it lasts, the mark is kept
    fresh, so it is announced again only after a quiet spell (docs/13-notifications.md#kinds)."""
    config = thresholds["alerts"]["weather"]
    quiet_since = now - timedelta(hours=thresholds["alerts"]["weather_quiet_hours"])
    alerting = {t.id: (t, u) for t, u in _alerting(session)}
    if not alerting:
        return []
    hours: dict[int, list] = defaultdict(list)
    params = {
        "ids": list(alerting),
        "since": now - timedelta(hours=1),
        "until": now + timedelta(hours=config["hours_ahead"]),
    }
    for row in session.execute(HOURS_SQL, params):
        hours[row.territory_id].append((row.valid_at, row.weather))
    found = []
    for territory_id, forecast in hours.items():
        worst = _worst_weather(forecast, config)
        if not worst:
            continue
        territory, user = alerting[territory_id]
        if territory.weather_notified_at and territory.weather_notified_at >= quiet_since:
            territory.weather_notified_at = now
            continue
        danger = Danger(
            territory_id=territory.id,
            name=territory.name,
            kind="weather",
            distance_m=0,
            direction=None,
            severity=None,
            sensors=[],
            seen_at=None,
            **worst,
        )
        mark = _mark_at(territory, "weather_notified_at", now)
        found.append(Found(user, territory, "weather", danger, mark))
    ids = {f.territory.id for f in found}
    for f in found:
        f.shown = f.territory.parent_id not in ids
    return found


def public_url(url: str) -> bool:
    """Telegram refuses buttons that link to this computer."""
    host = urlparse(url).hostname or ""
    return not (host in ("localhost", "127.0.0.1", "::1") or host.endswith((".local", ".test")))


def _log(session: Session, user: User, channel: str, dangers: list[Danger], version: str, now):
    session.add(
        AlertDelivery(
            user_id=user.id,
            channel=channel,
            sent_at=now,
            dangers=[asdict(d) | {"seen_at": d.seen_at and d.seen_at.isoformat()} for d in dangers],
            processing_version=version,
        )
    )


def send_alerts(
    session: Session,
    send: SendEmail,
    settings: Settings,
    thresholds: dict,
    version: str,
    now: datetime,
    telegram: Telegram | None = None,
    picture: Picture | None = None,
) -> dict:
    """Per account: one email with every field whose danger started or grew, and one Telegram
    photo per field, each with the kinds the account wants by that channel."""
    window_minutes = thresholds["lightning"]["window_minutes"]
    found = (
        _fires(session) + _lightning(session, thresholds, now) + _weather(session, thresholds, now)
    )
    by_user: dict[int, list[Found]] = defaultdict(list)
    for f in found:
        by_user[f.user.id].append(f)
    groups = list({f.group for f in found})
    wind = wind_now(session, groups, now)
    cover = contents_of(session, groups)
    cover_config = thresholds["field_risk"]["land_cover"]
    counts = {"emails_sent": 0, "emails_failed": 0, "telegram_sent": 0, "telegram_failed": 0}

    for items in by_user.values():
        user = items[0].user
        # Which (channel, field) got through; a danger is marked once any channel carried it.
        delivered: set[tuple[str, int | None]] = set()

        emailed = sorted(
            (f.danger for f in items if f.shown and wants(user, f.kind, "email")), key=_rank
        )
        if emailed:
            subject, body = alert_email(user.locale, emailed, settings.app_url, window_minutes, now)
            try:
                send(message(settings, user.email, subject, body))
            except SEND_ERRORS as exc:
                log.warning("alert email to user %s not sent: %s", user.id, exc)
                counts["emails_failed"] += 1
            else:
                delivered.add(("email", None))
                _log(session, user, "email", emailed, version, now)
                counts["emails_sent"] += 1

        by_field: dict[int, list[Found]] = defaultdict(list)
        for f in items:
            if f.shown and telegram and wants(user, f.kind, "telegram"):
                by_field[f.territory.id].append(f)
        for territory_id, field_items in by_field.items():
            territory = field_items[0].territory
            dangers = sorted((f.danger for f in field_items), key=_rank)
            # Distant fires alone arrive without sound; anything closer rings, and so does any fire
            # near a field with buildings: people may be there (docs/15-land-cover.md).
            holds = cover.get(territory_id)
            silent = all(f.kind == "fire_far" for f in field_items) and not (
                holds and holds.has_buildings(cover_config)
            )
            here = wind.get(territory_id)
            fire = next((d for d in dangers if d.kind == "fire"), None)
            pushed = fire and push(
                here, fire.bearing_deg, fire.distance_m, thresholds["field_risk"]["wind"]
            )
            result = _send_telegram(
                telegram,
                picture,
                settings,
                user,
                territory,
                dangers,
                here,
                pushed or None,
                holds_line(holds, cover_config, user.locale) if fire else None,
                window_minutes,
                now,
                silent,
            )
            if result == "blocked":
                # The user blocked the bot or deleted the chat: disconnected, as with /stop.
                log.info("user %s blocked the bot; telegram disconnected", user.id)
                user.telegram_chat_id = None
                counts["telegram_failed"] += 1
                break
            if result == "sent":
                delivered.add(("telegram", territory_id))
                _log(session, user, "telegram", dangers, version, now)
                counts["telegram_sent"] += 1
            else:
                counts["telegram_failed"] += 1

        for f in items:
            wanted = [c for c in CHANNELS if wants(user, f.kind, c)]
            carried = ("email", None) in delivered and "email" in wanted
            carried |= ("telegram", f.group) in delivered and "telegram" in wanted
            # Not wanted by any channel: marked too, so turning a kind on later does not bring
            # back old dangers. Wanted but not carried: left for the next run to try again.
            if carried or not wanted:
                f.mark()
    session.commit()
    return counts


def _send_telegram(
    telegram: Telegram,
    picture: Picture | None,
    settings: Settings,
    user: User,
    territory: Territory,
    dangers: list[Danger],
    wind: Wind | None,
    pushed: Push | None,
    holds: str | None,
    window_minutes: int,
    now: datetime,
    silent: bool,
) -> str:
    """One field's photo alert; "sent", "failed" (retried on the next run) or "blocked"."""
    es = user.locale == "es"
    chat = user.telegram_chat_id
    fire = next((d for d in dangers if d.kind == "fire"), None)
    caption = alert_caption(user.locale, dangers, wind, pushed, holds, window_minutes, now)
    links = []
    # Only to a public address: a link to this computer would not open on a phone, and Telegram
    # refuses it in a button.
    if public_url(settings.app_url):
        links.append(
            {
                "text": "Abrir en el mapa" if es else "Open in the map",
                "url": f"{settings.app_url}/?f={territory.id}",
            }
        )
    if fire and fire.fire_at:
        lat, lon = fire.fire_at
        links.append(
            {
                "text": "📍 Cómo llegar" if es else "📍 Directions",
                "url": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}",
            }
        )
    see = "Ver el campo" if es else "See the field"
    actions = [{"text": see, "callback_data": f"f:{territory.id}"}]
    if fire:
        actions.insert(
            0, {"text": "Ya lo vi" if es else "Seen it", "callback_data": f"seen:{territory.id}"}
        )
    buttons = [row for row in (links, actions) if row]
    try:
        telegram.chat_action(chat, "upload_photo")
    except (TelegramError, httpx.HTTPError):
        pass  # only the "sending photo…" hint; the alert goes on
    try:
        photo = picture(territory, dangers, wind, user.locale) if picture else None
    except Exception:  # noqa: BLE001 — a failed picture must not hold back the alert
        log.exception("area picture for territory %s failed", territory.id)
        photo = None
    try:
        if photo:
            telegram.send_photo(chat, photo, caption, buttons, silent=silent)
        else:
            telegram.send_text(chat, caption, buttons, silent=silent)
    except TelegramBlocked:
        return "blocked"
    except (TelegramError, httpx.HTTPError, ValueError) as exc:
        log.warning("telegram alert to user %s not sent: %s", user.id, exc)
        return "failed"
    return "sent"
