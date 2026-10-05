"""The words of the emails, in Spanish and English. The API returns codes and the frontend writes
sentences; emails are read outside the app, so they are written here."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.forecast.live_weather import LOCAL_TZ
from app.models import Severity, SummaryFrequency

if TYPE_CHECKING:
    from app.services.summary import FieldSummary

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
    """New danger near one field, as announced in an alert email."""

    territory_id: int
    name: str
    kind: str  # "fire" or "lightning"
    distance_m: float
    direction: str | None
    severity: Severity | None
    sensors: list[str]
    seen_at: datetime | None


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


def _line(danger: Danger, locale: str, window_minutes: int, now: datetime) -> str:
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
            'Para dejar de recibir avisos de un campo, apagá "Avisarme si hay peligro cerca" '
            "en su tarjeta."
        )
    else:
        footer = (
            "Field Watch reports what satellites detect: a hotspot can be a controlled burn, "
            "and clouds can hide others.\n"
            'To stop alerts for a field, turn off "Alert me of danger nearby" on its card.'
        )
    return subject, "\n\n".join(lines) + "\n\n" + footer + "\n"


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _when(moment: datetime, locale: str, hour: bool = True) -> str:
    local = moment.astimezone(LOCAL)
    day = f"{WEEKDAYS[locale][local.weekday()]} {local.day}"
    return f"{day} {local:%H:%M}" if hour else day


def _field_lines(item: "FieldSummary", locale: str) -> list[str]:
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
    for patch in item.entry.anomaly.patches:
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
    lines = {item.entry.territory.id: _field_lines(item, locale) for item in items}
    blocks = []
    for item in items:
        t = item.entry.territory
        if t.parent_id is not None:
            continue
        block = [f"{t.name} ({t.hectares:.0f} ha)", *(f"  {line}" for line in lines[t.id])]
        block.append(f"  {app_url}/?f={t.id}")
        # A lot that says the same as its field is named, not repeated.
        lots = [i.entry.territory for i in items if i.entry.territory.parent_id == t.id]
        same = [lot.name for lot in lots if lines[lot.id] == lines[t.id]]
        if same:
            block.append(
                ("  Lotes igual que el campo: " if es else "  Lots as the field: ")
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
        "Cambiá la frecuencia de este resumen (diario, semanal o ninguno) desde el menú de tu "
        f"cuenta: {app_url}"
        if es
        else f"Change how often this summary comes (daily, weekly or never) in your account menu: "
        f"{app_url}"
    )
    return f"{period}: {news}", "\n\n".join(blocks) + "\n\n" + footer + "\n"
