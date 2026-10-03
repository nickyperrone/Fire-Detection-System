"""The words of the emails, in Spanish and English. The API returns codes and the frontend writes
sentences; emails are read outside the app, so they are written here."""

from dataclasses import dataclass
from datetime import datetime

from app.models import Severity


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
