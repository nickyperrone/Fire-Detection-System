"""The words of the emails and Telegram messages, in Spanish and English. The API returns codes and
the frontend writes sentences; emails and messages are read outside the app, so they are written
here."""

from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.forecast.live_weather import LOCAL_TZ
from app.models import Severity, SummaryFrequency

if TYPE_CHECKING:
    from app.services.land_cover import Contents
    from app.services.summary import FieldSummary
    from app.services.wind import Push, Wind

LOCAL = ZoneInfo(LOCAL_TZ)
WEEKDAYS = {
    "es": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}
ANOMALY_KINDS = {
    "es": {"less_green": "menos verde", "water": "agua", "burnt": "quemado"},
    "en": {"less_green": "less green", "water": "water", "burnt": "burnt"},
}
BANDS = {
    "es": {"HIGH": "alto", "VERY_HIGH": "muy alto"},
    "en": {"HIGH": "high", "VERY_HIGH": "very high"},
}


@dataclass
class Danger:
    """New danger near one field, as announced in an alert."""

    territory_id: int
    name: str
    kind: str  # "fire", "lightning" or "weather"
    distance_m: float
    direction: str | None
    severity: Severity | None
    sensors: list[str]
    seen_at: datetime | None
    # Adverse weather: the worst of what is coming, each with when, as ISO times.
    gusts_kmh: float | None = None
    gusts_at: str | None = None
    rain_day_mm: float | None = None
    rain_day: str | None = None
    rain_hour_mm: float | None = None
    rain_hour_at: str | None = None
    fire_event_id: int | None = None
    bearing_deg: float | None = None
    # The fire's (lat, lon), for directions.
    fire_at: tuple[float, float] | None = None


DIRECTIONS = {
    "es": {"N": "N", "NE": "NE", "E": "E", "SE": "SE", "S": "S", "SW": "SO", "W": "O", "NW": "NO"},
    "en": {d: d for d in ("N", "NE", "E", "SE", "S", "SW", "W", "NW")},
}


def _km(distance_m: float, locale: str) -> str:
    text = f"{distance_m / 1000:.1f}"
    return text.replace(".", ",") if locale == "es" else text


def _age(then: datetime, now: datetime, locale: str) -> str:
    minutes = max(0, round((now - then).total_seconds() / 60))
    amount = f"{minutes} min" if minutes < 60 else f"{round(minutes / 60)} h"
    return f"hace {amount}" if locale == "es" else f"{amount} ago"


def login_email(locale: str, link: str, minutes: int) -> tuple[str, str]:
    if locale == "es":
        return (
            "Tu link para entrar a Field Watch",
            f"Abrí este link para entrar a Field Watch:\n\n{link}\n\n"
            f"Vence en {minutes} minutos y sirve una sola vez. "
            "Si no lo pediste, ignorá este mail.\n",
        )
    return (
        "Your Field Watch sign-in link",
        f"Open this link to sign in to Field Watch:\n\n{link}\n\n"
        f"It expires in {minutes} minutes and works once. "
        "If you did not ask for it, ignore this email.\n",
    )


def _weather_line(danger: Danger, locale: str) -> str:
    es = locale == "es"
    parts = []
    if danger.gusts_kmh is not None:
        when = _when(datetime.fromisoformat(danger.gusts_at), locale)
        parts.append(
            f"ráfagas de {danger.gusts_kmh:.0f} km/h el {when}"
            if es
            else f"gusts of {danger.gusts_kmh:.0f} km/h on {when}"
        )
    if danger.rain_day_mm is not None:
        day = _when(datetime.fromisoformat(danger.rain_day), locale, hour=False)
        mm = f"{danger.rain_day_mm:.0f}"
        parts.append(f"{mm} mm de lluvia el {day}" if es else f"{mm} mm of rain on {day}")
    if danger.rain_hour_mm is not None:
        when = _when(datetime.fromisoformat(danger.rain_hour_at), locale)
        mm = f"{danger.rain_hour_mm:.0f}"
        parts.append(
            f"lluvia fuerte ({mm} mm en una hora) el {when}"
            if es
            else f"heavy rain ({mm} mm in an hour) on {when}"
        )
    return ("clima adverso: " if es else "adverse weather: ") + ", ".join(parts)


def _line(danger: Danger, locale: str, window_minutes: int, now: datetime) -> str:
    if danger.kind == "weather":
        return _weather_line(danger, locale)
    km = _km(danger.distance_m, locale)
    where = DIRECTIONS[locale].get(danger.direction or "", "")
    if danger.kind == "lightning":
        if locale == "es":
            return f"rayos a {km} km en los últimos {window_minutes} min"
        return f"lightning {km} km away in the last {window_minutes} min"
    if danger.severity == Severity.CRITICAL:
        what = (
            "posible fuego dentro del campo" if locale == "es" else "possible fire inside the field"
        )
    elif locale == "es":
        what = f"posible fuego a {km} km" + (f" al {where}" if where else "")
    else:
        what = f"possible fire {km} km" + (f" {where}" if where else "")
    details = [what]
    if danger.sensors:
        details.append(", ".join(danger.sensors))
    if danger.seen_at:
        seen = _age(danger.seen_at, now, locale)
        details.append(f"visto {seen}" if locale == "es" else f"seen {seen}")
    return " · ".join(details)


def alert_email(
    locale: str, dangers: list[Danger], app_url: str, window_minutes: int, now: datetime
) -> tuple[str, str]:
    """Subject and body for one user's new dangers, which come worst first."""
    first = dangers[0]
    names = {d.territory_id for d in dangers}
    if len(names) > 1:
        subject = (
            f"Peligro cerca de {len(names)} campos"
            if locale == "es"
            else f"Danger near {len(names)} fields"
        )
    else:
        line = _line(first, locale, window_minutes, now).split(" · ")[0]
        subject = f"{first.name}: {line}"
    lines = [
        f"{d.name}: {_line(d, locale, window_minutes, now)}\n{app_url}/?f={d.territory_id}"
        for d in dangers
    ]
    if locale == "es":
        footer = (
            "Field Watch avisa lo que detectan los satélites: un foco puede ser una quema "
            "controlada, y las nubes pueden ocultar otros.\n"
            'Para dejar de recibir alertas de un campo, apagá "Avisarme si hay peligro cerca" '
            "en sus Ajustes. Para elegir qué alertas te llegan y por dónde, abrí Notificaciones "
            f"(la campana): {app_url}/?view=notifications"
        )
    else:
        footer = (
            "Field Watch reports what satellites detect: a hotspot can be a controlled burn, "
            "and clouds can hide others.\n"
            'To stop alerts for a field, turn off "Alert me of danger nearby" in its Settings. '
            "To choose which alerts you get and where, open Notifications (the bell): "
            f"{app_url}/?view=notifications"
        )
    return subject, "\n\n".join(lines) + "\n\n" + footer + "\n"


def _headline(danger: Danger, what: str, locale: str) -> str:
    """The line of an alert with the field's name in it: "Posible fuego a 1,9 km al E de …"."""
    es = locale == "es"
    place = escape(danger.name)
    if danger.kind == "weather":
        kind, rest = what.split(": ", 1)
        sentence = f"{kind} {'en' if es else 'at'} {place}: {rest}"
    elif danger.kind == "lightning":
        km = _km(danger.distance_m, locale)
        sentence = f"rayos a {km} km de {place}" if es else f"lightning {km} km from {place}"
    elif danger.severity == Severity.CRITICAL:
        sentence = f"posible fuego dentro de {place}" if es else f"possible fire inside {place}"
    else:
        sentence = f"{what} {'de' if es else 'from'} {place}"
    return sentence[0].upper() + sentence[1:]


def alert_caption(
    locale: str,
    dangers: list[Danger],
    wind: "Wind | None",
    pushed: "Push | None",
    holds: str | None,
    window_minutes: int,
    now: datetime,
) -> str:
    """The Telegram message of one field's new dangers, worst first, in Telegram's HTML.
    `wind` is the wind now at the field and `pushed` what it does to the closest fire
    (docs/03-rules.md#wind); `holds` says what is in the field (docs/15-land-cover.md). The link to
    the field is a button, not part of the text."""
    es = locale == "es"
    lines = ["🔴 <b>ALERTA!</b>" if es else "🔴 <b>ALERT!</b>"]
    for i, danger in enumerate(dangers):
        what, *details = _line(danger, locale, window_minutes, now).split(" · ")
        lines.append(
            f"<b>{_headline(danger, what, locale)}</b>"
            if i == 0
            else _headline(danger, what, locale)
        )
        if details:
            lines.append(escape(" · ".join(details)))
    if wind and pushed and pushed.toward:
        speed = f"{wind.speed_kmh:.0f} km/h"
        lines.append(
            f"💨 Viento de {speed} desde el fuego hacia el campo."
            if es
            else f"💨 Wind of {speed} blowing from the fire toward the field."
        )
        if pushed.arrival_h is not None:
            lines.append(f"⏱️ {arrival(pushed.arrival_h, locale)}")
    if holds:
        lines.append(escape(holds))
    return "\n".join(lines)[:1024]


def arrival(hours: float, locale: str) -> str:
    """A rough time for the fire front to reach the field, said as an estimate."""
    es = locale == "es"
    if hours < 1:
        span = f"~{max(5, round(hours * 60 / 5) * 5)} min"
    else:
        span = (
            f"~{hours:.0f} h" if hours >= 3 else f"~{hours:.1f} h".replace(".", "," if es else ".")
        )
    return (
        f"Si avanza con el viento, llegaría en {span} (estimado)."
        if es
        else f"If it runs with the wind, it would arrive in {span} (estimate)."
    )


def holds_line(holds: "Contents | None", config: dict, locale: str) -> str | None:
    """What is in the field, for an alert: "🏠 Hay construcciones cerca · 🌳 Árboles 22 % · 🌾
    Cultivo 70 %". Buildings first: they are what matters most when a fire comes."""
    if holds is None:
        return None
    es = locale == "es"
    parts = []
    if holds.built_m2 >= config["built_m2"]:
        parts.append("🏠 Hay construcciones en el campo" if es else "🏠 Buildings in the field")
    elif holds.has_buildings(config):
        parts.append("🏠 Hay construcciones cerca" if es else "🏠 Buildings nearby")
    for share, es_name, en_name, icon in (
        (holds.trees_share, "Árboles", "Trees", "🌳"),
        (holds.crops_share, "Cultivo", "Crops", "🌾"),
        (holds.grass_share, "Pasto", "Grass", "🌱"),
    ):
        if share >= 0.05:
            parts.append(f"{icon} {es_name if es else en_name} {share * 100:.0f} %")
    return " · ".join(parts) or None


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _when(moment: datetime, locale: str, hour: bool = True) -> str:
    local = moment.astimezone(LOCAL)
    day = f"{WEEKDAYS[locale][local.weekday()]} {local.day}"
    return f"{day} {local:%H:%M}" if hour else day


def _field_lines(item: "FieldSummary", locale: str, patches: bool = True) -> list[str]:
    """`patches` is False for a lot: its field already lists them, naming the lot."""
    es = locale == "es"
    lines = []
    if item.fire_days:
        closest = f"{_km(item.closest_fire_m, locale)} km"
        when = _when(item.closest_fire_at, locale, hour=False)
        if es:
            days = _count(item.fire_days, "día", "días")
            line = f"Fuego: {days} con fuego a menos de 10 km; el más cercano a {closest} ({when})."
        else:
            days = _count(item.fire_days, "day", "days")
            line = f"Fire: {days} with fire within 10 km; the closest {closest} away ({when})."
        lines.append(line)
    else:
        lines.append("Fuego: ninguno a menos de 10 km." if es else "Fire: none within 10 km.")
    if item.flashes:
        lines.append(
            f"Rayos: {_count(item.flashes, 'rayo', 'rayos')} a menos de 10 km."
            if es
            else f"Lightning: {_count(item.flashes, 'flash', 'flashes')} within 10 km."
        )
    if item.rain_mm is not None:
        mm = f"{item.rain_mm:.1f}".replace(".", ",") if es else f"{item.rain_mm:.1f}"
        lines.append(f"Lluvia en la zona: {mm} mm." if es else f"Rain in the area: {mm} mm.")
    window = item.entry.spray.next_favorable
    if window:
        span = f"{_when(window[0], locale)}–{window[1].astimezone(LOCAL):%H:%M}"
        lines.append(
            f"Pulverizar: próxima ventana {span}." if es else f"Spraying: next window {span}."
        )
    elif item.entry.spray.status:
        lines.append(
            "Pulverizar: sin ventanas buenas en las próximas 48 h."
            if es
            else "Spraying: no good window in the next 48 h."
        )
    for patch in item.entry.anomaly.patches if patches else []:
        what = ANOMALY_KINDS[locale][patch.kind]
        where = "" if patch.where == "center" else DIRECTIONS[locale].get(patch.where, "")
        place = (
            ("en el centro" if es else "in the center")
            if patch.where == "center"
            else (f"al {where}" if es else f"to the {where}")
        )
        area = f"{patch.area_ha:.1f}".replace(".", ",") if es else f"{patch.area_ha:.1f}"
        seen = _when(
            datetime.combine(item.entry.anomaly.observed_on, datetime.min.time(), LOCAL),
            locale,
            hour=False,
        )
        if patch.lot:
            place = f"{place} de {patch.lot}" if es else f"{place} of {patch.lot}"
        lines.append(
            f"Algo raro: {what} en {area} ha {place} ({seen})."
            if es
            else f"Something unusual: {what} in {area} ha {place} ({seen})."
        )
    risky = [d for d in item.entry.forecast.days if d.band in BANDS[locale]]
    if risky:
        day = risky[0]
        band, chance = BANDS[locale][day.band], f"{day.probability:.0%}"
        if es:
            within = _count(day.horizon_days, "día", "días")
            lines.append(f"Riesgo de fuego {band} en {within} ({chance}).")
        else:
            within = _count(day.horizon_days, "day", "days")
            lines.append(f"Fire risk {band} within {within} ({chance}).")
    return lines


def summary_email(
    locale: str, frequency: SummaryFrequency, items: list["FieldSummary"], app_url: str
) -> tuple[str, str]:
    """Every field in the list's order; its lots listed in full only where they differ."""
    es = locale == "es"
    fields = [i for i in items if i.entry.territory.parent_id is None]
    with_fire = sum(1 for i in fields if i.fire_days)
    period = (
        ("Resumen semanal" if es else "Weekly summary")
        if frequency == SummaryFrequency.WEEKLY
        else ("Resumen del día" if es else "Daily summary")
    )
    if with_fire:
        news = (
            f"{_count(with_fire, 'campo', 'campos')} con fuego cerca"
            if es
            else f"{_count(with_fire, 'field', 'fields')} with fire nearby"
        )
    else:
        news = (
            f"sin fuegos cerca de tus {len(fields)} campos"
            if es
            else f"no fires near your {len(fields)} fields"
        )
    # Without patches: a field lists its lots' patches once, naming the lot, so lots are
    # compared with their field on everything else.
    lines = {item.entry.territory.id: _field_lines(item, locale, patches=False) for item in items}
    blocks = []
    for item in items:
        t = item.entry.territory
        if t.parent_id is not None:
            continue
        block = [f"{t.name} ({t.hectares:.0f} ha)"]
        block += [f"  {line}" for line in _field_lines(item, locale)]
        block.append(f"  {app_url}/?f={t.id}")
        # A lot that says the same as its field is named, not repeated.
        lots = [i.entry.territory for i in items if i.entry.territory.parent_id == t.id]
        same = [lot.name for lot in lots if lines[lot.id] == lines[t.id]]
        if same:
            block.append(
                ("  Lotes igual que el campo: " if es else "  Lots same as the field: ")
                + ", ".join(same)
                + "."
            )
        for lot in lots:
            if lines[lot.id] != lines[t.id]:
                block += [
                    f"    {lot.name} ({lot.hectares:.0f} ha)",
                    *(f"      {line}" for line in lines[lot.id]),
                ]
                block.append(f"      {app_url}/?f={lot.id}")
        blocks.append("\n".join(block))
    footer = (
        "Cambiá cada cuánto llega este resumen (diario, semanal o nunca) y por dónde en "
        f"Notificaciones (la campana): {app_url}/?view=notifications"
        if es
        else "Change how often this summary comes (daily, weekly or never) and where in "
        f"Notifications (the bell): {app_url}/?view=notifications"
    )
    return f"{period}: {news}", "\n\n".join(blocks) + "\n\n" + footer + "\n"
