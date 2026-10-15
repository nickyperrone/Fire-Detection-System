"""The Telegram bot: linking chats to accounts, and a chat driven by buttons
(docs/13-notifications.md#the-bot)."""

import logging
import secrets
from datetime import datetime, timedelta
from html import escape

import httpx
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.models import FieldRiskEvent, RiskStatus, Severity, SprayStatus, Territory, User
from app.providers.telegram import Buttons, Telegram, TelegramError
from app.services.auth import _hash
from app.services.email_text import DIRECTIONS, LOCAL, _km, _when
from app.services.field_risk import compass
from app.services.notification_prefs import KINDS, preferences

log = logging.getLogger(__name__)

CODE_MINUTES = 15
# Button data: each tap says what to show or do; Telegram allows 64 bytes.
SEEN = "seen:"
FIELDS = "fields"
FIELD = "f:"
ALERTS = "alerts"
MENU = "menu"
TOGGLE = "t:"
# "Saber más": the menu's, the alerts' or a field's (with its id).
MORE = "i:"
SPRAY_PROFILE = "default"
WINDOW_HOURS = 48

TEXTS = {
    "es": {
        "linked": "✅ <b>¡Listo, estás conectado!</b>\n\n"
        "Te vamos a avisar acá, con una foto del área, cuando haya peligro cerca de tus "
        "campos.\n\n¿Qué querés ver?",
        "expired": "⌛ Ese código venció o ya se usó.\n\nEn Field Watch, tocá la 🔔 y después "
        "«Conectar Telegram» de nuevo.",
        "hello": "👋 Para recibir alertas acá, entrá a Field Watch, tocá la 🔔 y después "
        "«Conectar Telegram».",
        "stopped": "🔕 Listo, este chat ya no recibe alertas.\n\nPara volver a recibirlas, "
        "conectalo de nuevo desde la 🔔 en Field Watch.",
        "menu_text": "👋 <b>Field Watch</b>\n\n"
        "Te avisamos acá si hay 🔥 fuego, ⚡ rayos o 🌪 mal clima cerca de tus campos.\n\n"
        "¿Qué querés ver?",
        "menu": {FIELDS: "📋 Mis campos", ALERTS: "🔔 Mis alertas"},
        "more": "ℹ️ Saber más",
        "how": "ℹ️ <b>Cómo funciona</b>\n\n"
        "🛰 Miramos tus campos con satélites cada 5 a 10 minutos.\n"
        "🔥 Si aparece un fuego cerca, te llega una alerta con una foto del área.\n"
        "⚡ También rayos a menos de 10 km y 🌪 clima adverso: ráfagas fuertes o mucha lluvia.\n"
        "💨 Te decimos cuándo conviene pulverizar, hora por hora.\n\n"
        "En la web ves todo en el mapa, con fotos de cada campo.\n"
        "Para dejar de recibir alertas acá, mandá /stop.",
        "to_menu": "‹ Menú",
        "seen": "Marcado como visto",
        "seen_button": "✓ Visto",
        "already": "Ya estaba marcado como visto",
        "fields_title": "📋 <b>Tus campos</b>",
        "fields_hint": "Tocá un campo para ver más.",
        "no_fields": "🌱 Todavía no tenés campos.\n\nDibujá el primero en Field Watch con el "
        "botón +.",
        "fire_none": "✅ Sin fuego cerca",
        "fire_inside": "🔥 Posible fuego <b>adentro</b> del campo",
        "fire_near": "🔥 Fuego a <b>{km} km</b>{where}",
        "fire_where": " al {direction}",
        "spray": {
            SprayStatus.FAVORABLE: "✅ Se puede pulverizar",
            SprayStatus.CAUTION: "🟡 Pulverizar con cuidado",
            SprayStatus.UNFAVORABLE: "⛔ No conviene pulverizar",
            None: "❔ Sin pronóstico para pulverizar",
        },
        "window": "🕐 Próxima ventana para pulverizar: <b>{span}</b>",
        "no_window": "🕐 Sin ventana para pulverizar en las próximas 48 h",
        "lots": lambda n: f"{n} {'lote' if n == 1 else 'lotes'}",
        "gone": "Ese campo ya no está en tu cuenta.",
        "back": "‹ Mis campos",
        "back_field": "‹ Volver",
        "open": "🗺 Abrir Field Watch",
        "open_field": "🗺 Ver en el mapa",
        "more_title": "ℹ️ <b>{name}</b>, en detalle",
        "fire_title": "🔥 <b>Fuego</b>",
        "fire_more_none": "Ninguno a menos de 10 km. Revisamos los satélites cada 5 minutos.",
        "fire_more": "El más cercano, a {km} km{where}. Si se acerca, te avisamos.",
        "spray_title": "💨 <b>Pulverizar ahora</b>",
        "spray_ok": "Todas las condiciones están bien.",
        "weather_title": "🌤 <b>Clima ahora</b>",
        "weather_now": "🌡 {temp} °C · viento del {dir} a {wind} km/h · ráfagas de {gusts} km/h",
        "rain_24h": "🌧 {mm} mm en las próximas 24 h",
        "no_weather": "Sin pronóstico todavía.",
        "areas_title": "🔎 <b>Zonas para revisar</b>",
        "areas_none": "Ninguna en la última foto del satélite.",
        "areas": lambda n: "1 zona" if n == 1 else f"{n} zonas",
        "areas_hint": " en la última foto del satélite. Miralas en el mapa.",
        "reasons": {
            "wind_high": "💨 Viento de {v} km/h, más de lo recomendado ({l} km/h)",
            "wind_low": "🍃 Casi sin viento ({v} km/h): el producto puede quedar flotando",
            "gusts": "🌬 Ráfagas de {v} km/h (máx. {l} km/h)",
            "delta_t_low": "💧 Aire muy húmedo: las gotas quedan flotando (Delta T {v} °C)",
            "delta_t_high": "☀️ Aire muy seco: las gotas se evaporan (Delta T {v} °C)",
            "temperature": "🌡 Mucho calor: {v} °C (máx. {l} °C)",
            "rain": "🌧 Lluvia en las próximas {h} h",
            "inversion": "🌫 Posible inversión térmica: el producto puede quedar flotando",
        },
        "alerts_title": "🔔 <b>Tus alertas en este chat</b>",
        "alerts_hint": "Tocá una para prenderla ✅ o apagarla ▫️.",
        "alerts_more": "ℹ️ <b>Qué es cada alerta</b>\n\n"
        "🔥 <b>Fuego muy cerca</b>: adentro del campo o a menos de 2 km\n"
        "🔥 <b>Fuego cerca</b>: de 2 a 5 km\n"
        "🔥 <b>Fuego lejano</b>: de 5 a 10 km (suelen ser quemas)\n"
        "⚡ <b>Rayos</b>: a menos de 10 km en la última hora\n"
        "🌪 <b>Clima adverso</b>: ráfagas de 60 km/h o más, o lluvia fuerte\n"
        "📰 <b>Resumen</b>: cómo estuvo cada campo, por semana o por día\n\n"
        "Las alertas por mail se eligen en la web, en la 🔔.",
        "alerts_web": "🗺 Elegir en la web",
        "back_alerts": "‹ Mis alertas",
        "kinds": {
            "fire_high": "🔥 Fuego muy cerca",
            "fire_medium": "🔥 Fuego cerca",
            "fire_far": "🔥 Fuego lejano",
            "lightning": "⚡ Rayos",
            "weather": "🌪 Clima adverso",
            "summary": "📰 Resumen",
        },
        "on": "✅ Prendida",
        "off": "▫️ Apagada",
    },
    "en": {
        "linked": "✅ <b>Done, you are connected!</b>\n\n"
        "We will alert you here, with a photo of the area, when there is danger near your "
        "fields.\n\nWhat do you want to see?",
        "expired": "⌛ That code expired or was already used.\n\nIn Field Watch, tap the 🔔 and "
        "then “Connect Telegram” again.",
        "hello": "👋 To get alerts here, open Field Watch, tap the 🔔 and then “Connect Telegram”.",
        "stopped": "🔕 Done, this chat no longer gets alerts.\n\nTo get them again, connect it "
        "from the 🔔 in Field Watch.",
        "menu_text": "👋 <b>Field Watch</b>\n\n"
        "We alert you here when there is 🔥 fire, ⚡ lightning or 🌪 bad weather near your "
        "fields.\n\nWhat do you want to see?",
        "menu": {FIELDS: "📋 My fields", ALERTS: "🔔 My alerts"},
        "more": "ℹ️ Learn more",
        "how": "ℹ️ <b>How it works</b>\n\n"
        "🛰 We look at your fields with satellites every 5 to 10 minutes.\n"
        "🔥 If a fire shows up nearby, an alert arrives with a photo of the area.\n"
        "⚡ Also lightning within 10 km and 🌪 adverse weather: strong gusts or heavy rain.\n"
        "💨 We tell you when it is good to spray, hour by hour.\n\n"
        "On the web you see everything on the map, with photos of each field.\n"
        "To stop alerts here, send /stop.",
        "to_menu": "‹ Menu",
        "seen": "Marked as seen",
        "seen_button": "✓ Seen",
        "already": "Already marked as seen",
        "fields_title": "📋 <b>Your fields</b>",
        "fields_hint": "Tap a field to see more.",
        "no_fields": "🌱 You have no fields yet.\n\nDraw the first one in Field Watch with the + "
        "button.",
        "fire_none": "✅ No fire nearby",
        "fire_inside": "🔥 Possible fire <b>inside</b> the field",
        "fire_near": "🔥 Fire <b>{km} km</b> away{where}",
        "fire_where": " to the {direction}",
        "spray": {
            SprayStatus.FAVORABLE: "✅ Good to spray",
            SprayStatus.CAUTION: "🟡 Spray with care",
            SprayStatus.UNFAVORABLE: "⛔ Not a good time to spray",
            None: "❔ No spraying forecast",
        },
        "window": "🕐 Next spraying window: <b>{span}</b>",
        "no_window": "🕐 No spraying window in the next 48 h",
        "lots": lambda n: f"{n} {'lot' if n == 1 else 'lots'}",
        "gone": "That field is no longer in your account.",
        "back": "‹ My fields",
        "back_field": "‹ Back",
        "open": "🗺 Open Field Watch",
        "open_field": "🗺 See on the map",
        "more_title": "ℹ️ <b>{name}</b>, in detail",
        "fire_title": "🔥 <b>Fire</b>",
        "fire_more_none": "None within 10 km. We check the satellites every 5 minutes.",
        "fire_more": "The closest, {km} km away{where}. If it comes closer, we alert you.",
        "spray_title": "💨 <b>Spraying now</b>",
        "spray_ok": "Every condition is fine.",
        "weather_title": "🌤 <b>Weather now</b>",
        "weather_now": "🌡 {temp} °C · wind from the {dir} at {wind} km/h · gusts of {gusts} km/h",
        "rain_24h": "🌧 {mm} mm in the next 24 h",
        "no_weather": "No forecast yet.",
        "areas_title": "🔎 <b>Areas to check</b>",
        "areas_none": "None in the latest satellite photo.",
        "areas": lambda n: "1 area" if n == 1 else f"{n} areas",
        "areas_hint": " in the latest satellite photo. See them on the map.",
        "reasons": {
            "wind_high": "💨 Wind of {v} km/h, more than advised ({l} km/h)",
            "wind_low": "🍃 Almost no wind ({v} km/h): the product can hang in the air",
            "gusts": "🌬 Gusts of {v} km/h (max {l} km/h)",
            "delta_t_low": "💧 Very humid air: droplets hang in the air (Delta T {v} °C)",
            "delta_t_high": "☀️ Very dry air: droplets evaporate (Delta T {v} °C)",
            "temperature": "🌡 Too hot: {v} °C (max {l} °C)",
            "rain": "🌧 Rain in the next {h} h",
            "inversion": "🌫 Possible temperature inversion: the product can hang in the air",
        },
        "alerts_title": "🔔 <b>Your alerts in this chat</b>",
        "alerts_hint": "Tap one to turn it on ✅ or off ▫️.",
        "alerts_more": "ℹ️ <b>What each alert is</b>\n\n"
        "🔥 <b>Fire very close</b>: inside the field or within 2 km\n"
        "🔥 <b>Fire close</b>: 2 to 5 km away\n"
        "🔥 <b>Distant fire</b>: 5 to 10 km away (often stubble burns)\n"
        "⚡ <b>Lightning</b>: within 10 km in the last hour\n"
        "🌪 <b>Adverse weather</b>: gusts of 60 km/h or more, or heavy rain\n"
        "📰 <b>Summary</b>: how each field did, weekly or daily\n\n"
        "Email alerts are chosen on the web, under the 🔔.",
        "alerts_web": "🗺 Choose on the web",
        "back_alerts": "‹ My alerts",
        "kinds": {
            "fire_high": "🔥 Fire very close",
            "fire_medium": "🔥 Fire close",
            "fire_far": "🔥 Distant fire",
            "lightning": "⚡ Lightning",
            "weather": "🌪 Adverse weather",
            "summary": "📰 Summary",
        },
        "on": "✅ On",
        "off": "▫️ Off",
    },
}

# The bot's profile (docs/13-notifications.md#the-bot); "" is every language but English.
PROFILE = {
    "": {
        "commands": [
            {"command": "campos", "description": "Cómo están tus campos ahora"},
            {"command": "alertas", "description": "Qué alertas te llegan acá"},
            {"command": "ayuda", "description": "Qué hace este bot"},
            {"command": "stop", "description": "Dejar de recibir alertas en este chat"},
        ],
        "description": "Alertas de Field Watch para tus campos: fuego cerca, rayos y clima "
        "adverso, con una foto del área.\n\nPara conectarlo, entrá a Field Watch, abrí "
        "Notificaciones (la campana) y tocá «Conectar Telegram».",
        "short_description": "Alertas de fuego, rayos y clima adverso para tus campos.",
    },
    "en": {
        "commands": [
            {"command": "campos", "description": "How your fields are now"},
            {"command": "alertas", "description": "Which alerts come here"},
            {"command": "ayuda", "description": "What this bot does"},
            {"command": "stop", "description": "Stop alerts in this chat"},
        ],
        "description": "Field Watch alerts for your fields: fire nearby, lightning and adverse "
        "weather, with a photo of the area.\n\nTo connect it, open Field Watch, go to "
        "Notifications (the bell) and tap “Connect Telegram”.",
        "short_description": "Fire, lightning and adverse weather alerts for your fields.",
    },
}

# What a typed command or a tap on the keyboard below the chat asks for.
COMMANDS = {
    "/campos": FIELDS,
    "/estado": FIELDS,
    "/status": FIELDS,
    "/alertas": ALERTS,
    "/ayuda": MENU,
    "/help": MENU,
    "/menu": MENU,
}

STATUS_SQL = text("""
    SELECT t.id, t.name, t.hectares, fire.distance_m, fire.bearing_deg, fire.severity,
           spray.status AS spray, spray.rules, spray.weather,
           (SELECT count(*) FROM territory l WHERE l.parent_id = t.id) AS lots,
           (SELECT count(*) FROM field_anomaly a JOIN territory u ON u.id = a.territory_id
            WHERE u.id = t.id OR u.parent_id = t.id) AS areas
    FROM territory t
    LEFT JOIN LATERAL (
        SELECT r.distance_m, r.bearing_deg, r.severity
        FROM field_risk_event r JOIN fire_event e ON e.id = r.fire_event_id
        WHERE r.territory_id = t.id AND e.status = 'ACTIVE' AND r.status != 'RESOLVED'
        ORDER BY r.distance_m LIMIT 1
    ) fire ON true
    LEFT JOIN LATERAL (
        SELECT a.status, a.rules, a.weather FROM spray_assessment a
        WHERE a.territory_id = t.id AND a.profile = :profile
          AND a.valid_at <= :now AND a.valid_at > :now - interval '1 hour'
        ORDER BY a.valid_at DESC LIMIT 1
    ) spray ON true
    WHERE t.owner = :owner AND t.parent_id IS NULL
    ORDER BY t.name
""")

HOURS_SQL = text("""
    SELECT valid_at, status FROM spray_assessment
    WHERE territory_id = :id AND profile = :profile
      AND valid_at > :now - interval '1 hour' AND valid_at <= :until
    ORDER BY valid_at
""")


RAIN_SQL = text("""
    SELECT sum((weather->>'precipitation_mm')::float) FROM spray_assessment
    WHERE territory_id = :id AND profile = :profile
      AND valid_at > :now AND valid_at <= :now + interval '24 hours'
""")


def configure_bot(bot: Telegram) -> None:
    """Sets the bot's commands and descriptions from the repository, on every worker start."""
    for language, profile in PROFILE.items():
        bot.set_profile(
            language, profile["commands"], profile["description"], profile["short_description"]
        )
    bot.show_commands_menu()


_usernames: dict[str, str] = {}


def bot_username(bot: Telegram) -> str:
    """The bot's @name, asked once per token."""
    if bot.token not in _usernames:
        _usernames[bot.token] = bot.username()
    return _usernames[bot.token]


def link_code(session: Session, user: User, now: datetime) -> str:
    """A one-time code for `https://t.me/<bot>?start=<code>`; only its hash is kept."""
    code = secrets.token_urlsafe(24)
    user.telegram_code_hash = _hash(code)
    user.telegram_code_expires_at = now + timedelta(minutes=CODE_MINUTES)
    return code


def _locale(user: User | None, sender: dict) -> str:
    if user is not None:
        return user.locale
    return "en" if (sender.get("language_code") or "es")[:2] == "en" else "es"


def menu_buttons(locale: str) -> Buttons:
    """Under the message, so they show on every device without opening anything."""
    texts = TEXTS[locale]
    return [
        [
            {"text": texts["menu"][FIELDS], "callback_data": FIELDS},
            {"text": texts["menu"][ALERTS], "callback_data": ALERTS},
        ],
        [{"text": texts["more"], "callback_data": f"{MORE}{MENU}"}],
    ]


def menu_view(user: User) -> tuple[str, Buttons]:
    return TEXTS[user.locale]["menu_text"], menu_buttons(user.locale)


def how_view(user: User, app_url: str | None) -> tuple[str, Buttons]:
    texts = TEXTS[user.locale]
    buttons = [[{"text": texts["open"], "url": app_url}]] if app_url else []
    return texts["how"], [*buttons, [{"text": texts["to_menu"], "callback_data": MENU}]]


def _number(value: float, digits: int, locale: str) -> str:
    text_ = f"{value:.{digits}f}"
    return text_.replace(".", ",") if locale == "es" else text_


def _hectares(value: float, locale: str) -> str:
    """5666 → "5.666 ha" in Spanish, "5,666 ha" in English."""
    text_ = f"{value:,.0f}"
    return (text_.replace(",", ".") if locale == "es" else text_) + " ha"


def _where(bearing_deg: float | None, texts: dict, locale: str) -> str:
    direction = DIRECTIONS[locale].get(compass(bearing_deg) or "", "")
    return texts["fire_where"].format(direction=direction) if direction else ""


def _fire_line(row, texts: dict, locale: str) -> str:
    if row.distance_m is None:
        return texts["fire_none"]
    if row.severity == Severity.CRITICAL:
        return texts["fire_inside"]
    where = _where(row.bearing_deg, texts, locale)
    return texts["fire_near"].format(km=_km(row.distance_m, locale), where=where)


def _spray_line(row, texts: dict) -> str:
    return texts["spray"][SprayStatus(row.spray) if row.spray else None]


def reasons(rules: list[dict], locale: str) -> list[str]:
    """Why spraying is not fine this hour, one plain line per rule that is not."""
    texts = TEXTS[locale]["reasons"]
    lines = []
    for rule in rules:
        if rule.get("status") not in ("CAUTION", "FAIL"):
            continue
        name, value, limit = rule["rule"], rule.get("value"), rule.get("limit")
        if name == "inversion":
            lines.append(texts["inversion"])
            continue
        if value is None:
            continue
        digits = 1 if rule.get("unit") == "°C" else 0
        v = _number(value, digits, locale)
        lim = _number(limit, digits, locale) if limit is not None else ""
        below = limit is not None and value < limit
        if name == "wind":
            lines.append(texts["wind_low" if below else "wind_high"].format(v=v, l=lim))
        elif name == "delta_t":
            lines.append(texts["delta_t_low" if below else "delta_t_high"].format(v=v))
        elif name == "rain":
            lines.append(texts["rain"].format(h=rule.get("window_h") or 2))
        elif name in ("gusts", "temperature"):
            lines.append(texts[name].format(v=v, l=lim))
    return lines


def _window(session: Session, field_id: int, now: datetime) -> tuple[datetime, datetime] | None:
    """The first run of favorable hours from now, as (start, end)."""
    rows = session.execute(
        HOURS_SQL,
        {
            "id": field_id,
            "profile": SPRAY_PROFILE,
            "now": now,
            "until": now + timedelta(hours=WINDOW_HOURS),
        },
    ).all()
    start = end = None
    for row in rows:
        if row.status == SprayStatus.FAVORABLE:
            start = start or row.valid_at
            end = row.valid_at + timedelta(hours=1)
        elif start:
            break
    return (start, end) if start else None


def _field_row(session: Session, user: User, field_id: int, now: datetime):
    rows = session.execute(
        STATUS_SQL, {"owner": user.email, "now": now, "profile": SPRAY_PROFILE}
    ).all()
    return next((r for r in rows if r.id == field_id), None)


def fields_view(
    session: Session, user: User, now: datetime, app_url: str | None
) -> tuple[str, Buttons]:
    """Every field: one line on fire and one on spraying, and a button to open each one."""
    texts = TEXTS[user.locale]
    rows = session.execute(
        STATUS_SQL, {"owner": user.email, "now": now, "profile": SPRAY_PROFILE}
    ).all()
    link = [[{"text": texts["open"], "url": app_url}]] if app_url else []
    link.append([{"text": texts["to_menu"], "callback_data": MENU}])
    if not rows:
        return texts["no_fields"], link
    blocks = [
        f"🌾 <b>{escape(r.name)}</b> · {_hectares(r.hectares, user.locale)}\n"
        f"{_fire_line(r, texts, user.locale)}\n{_spray_line(r, texts)}"
        for r in rows
    ]
    body = f"{texts['fields_title']}\n\n" + "\n\n".join(blocks) + f"\n\n{texts['fields_hint']}"
    buttons = [[{"text": f"🔎 {r.name}", "callback_data": f"{FIELD}{r.id}"}] for r in rows]
    return body, buttons + link


def field_view(
    session: Session, user: User, field_id: int, now: datetime, app_url: str | None
) -> tuple[str, Buttons]:
    """One field, straight to the point: fire, spraying and why, the next window to spray."""
    texts = TEXTS[user.locale]
    back = [[{"text": texts["back"], "callback_data": FIELDS}]]
    row = _field_row(session, user, field_id, now)
    if row is None:
        return texts["gone"], back
    window = _window(session, field_id, now)
    if window:
        span = f"{_when(window[0], user.locale)}–{window[1].astimezone(LOCAL):%H:%M}"
        window_line = texts["window"].format(span=span)
    else:
        window_line = texts["no_window"]
    size = _hectares(row.hectares, user.locale)
    if row.lots:
        size += f" · {texts['lots'](row.lots)}"
    why = reasons(row.rules or [], user.locale)
    lines = [
        f"🌾 <b>{escape(row.name)}</b> · {size}",
        "",
        _fire_line(row, texts, user.locale),
        _spray_line(row, texts) + (f"\n     {why[0]}" if why else ""),
        window_line,
    ]
    buttons: Buttons = [[{"text": texts["more"], "callback_data": f"{MORE}{field_id}"}]]
    if app_url:
        buttons.append([{"text": texts["open_field"], "url": f"{app_url}/?f={field_id}"}])
    return "\n".join(lines), [*buttons, *back]


def field_more_view(
    session: Session, user: User, field_id: int, now: datetime, app_url: str | None
) -> tuple[str, Buttons]:
    """ "Saber más" on a field: every reason, the weather now and the areas to check."""
    texts = TEXTS[user.locale]
    locale = user.locale
    back = [[{"text": texts["back_field"], "callback_data": f"{FIELD}{field_id}"}]]
    row = _field_row(session, user, field_id, now)
    if row is None:
        return texts["gone"], [[{"text": texts["back"], "callback_data": FIELDS}]]
    if row.distance_m is None:
        fire = texts["fire_more_none"]
    elif row.severity == Severity.CRITICAL:
        fire = texts["fire_inside"]
    else:
        where = _where(row.bearing_deg, texts, locale)
        fire = texts["fire_more"].format(km=_km(row.distance_m, locale), where=where)
    why = reasons(row.rules or [], locale)
    spray = "\n".join(why) if why else texts["spray_ok"]
    weather = row.weather or {}
    if weather.get("temperature_c") is not None:
        direction = DIRECTIONS[locale].get(compass(weather.get("wind_direction_deg")) or "", "?")
        now_line = texts["weather_now"].format(
            temp=_number(weather["temperature_c"], 0, locale),
            dir=direction,
            wind=_number(weather.get("wind_speed_kmh") or 0, 0, locale),
            gusts=_number(weather.get("wind_gusts_kmh") or 0, 0, locale),
        )
        rain = session.scalar(RAIN_SQL, {"id": field_id, "profile": SPRAY_PROFILE, "now": now})
        clima = f"{now_line}\n{texts['rain_24h'].format(mm=_number(rain or 0, 1, locale))}"
    else:
        clima = texts["no_weather"]
    areas = row.areas or 0
    areas_line = (texts["areas"](areas) + texts["areas_hint"]) if areas else texts["areas_none"]
    body = "\n".join(
        [
            texts["more_title"].format(name=escape(row.name)),
            "",
            texts["fire_title"],
            fire,
            "",
            texts["spray_title"],
            spray,
            "",
            texts["weather_title"],
            clima,
            "",
            texts["areas_title"],
            areas_line,
        ]
    )
    buttons: Buttons = []
    if app_url:
        buttons.append([{"text": texts["open_field"], "url": f"{app_url}/?f={field_id}"}])
    return body, [*buttons, *back]


def alerts_view(user: User) -> tuple[str, Buttons]:
    """Each kind of alert as a button that turns it on or off in this chat."""
    texts = TEXTS[user.locale]
    chosen = preferences(user)
    buttons = [
        [
            {
                "text": f"{'✅' if chosen[kind]['telegram'] else '▫️'}  {texts['kinds'][kind]}",
                "callback_data": f"{TOGGLE}{kind}",
            }
        ]
        for kind in KINDS
    ]
    buttons.append(
        [
            {"text": texts["more"], "callback_data": f"{MORE}{ALERTS}"},
            {"text": texts["to_menu"], "callback_data": MENU},
        ]
    )
    return f"{texts['alerts_title']}\n\n{texts['alerts_hint']}", buttons


def alerts_more_view(user: User, app_url: str | None) -> tuple[str, Buttons]:
    texts = TEXTS[user.locale]
    buttons: Buttons = []
    if app_url:
        web = f"{app_url}/?view=notifications"
        buttons.append([{"text": texts["alerts_web"], "url": web}])
    return texts["alerts_more"], [
        *buttons,
        [{"text": texts["back_alerts"], "callback_data": ALERTS}],
    ]


def _linked_user(session: Session, chat_id: int) -> User | None:
    return session.scalar(select(User).where(User.telegram_chat_id == chat_id))


def _on_message(
    session: Session, bot: Telegram, message: dict, now: datetime, app_url: str | None
) -> None:
    chat_id = message["chat"]["id"]
    typed = (message.get("text") or "").strip()
    words = typed.split()
    command = words[0].split("@")[0] if words else ""
    sender = message.get("from", {})
    if command == "/start" and len(words) > 1:
        user = session.scalar(
            select(User).where(
                User.telegram_code_hash == _hash(words[1]),
                User.telegram_code_expires_at > now,
            )
        )
        if user is None:
            bot.send_text(chat_id, TEXTS[_locale(None, sender)]["expired"])
            return
        # One account per chat: a chat linked to another account moves to this one.
        session.execute(
            update(User).where(User.telegram_chat_id == chat_id).values(telegram_chat_id=None)
        )
        user.telegram_chat_id = chat_id
        user.telegram_code_hash = None
        user.telegram_code_expires_at = None
        session.commit()
        bot.send_text(chat_id, TEXTS[user.locale]["linked"], menu_buttons(user.locale))
        return
    user = _linked_user(session, chat_id)
    if command == "/stop":
        if user is not None:
            user.telegram_chat_id = None
            session.commit()
        bot.send_text(chat_id, TEXTS[_locale(user, sender)]["stopped"], remove_keyboard=True)
        return
    if user is None:
        bot.send_text(chat_id, TEXTS[_locale(None, sender)]["hello"], remove_keyboard=True)
        return
    action = COMMANDS.get(command) or MENU
    if action == FIELDS:
        bot.send_text(chat_id, *fields_view(session, user, now, app_url))
    elif action == ALERTS:
        bot.send_text(chat_id, *alerts_view(user))
    else:
        bot.send_text(chat_id, *menu_view(user))


def mark_seen(session: Session, user: User, territory_id: int) -> int:
    """Every new fire near the field and its lots, as seen by its owner."""
    ids = select(Territory.id).where(
        Territory.owner == user.email,
        (Territory.id == territory_id) | (Territory.parent_id == territory_id),
    )
    result = session.execute(
        update(FieldRiskEvent)
        .where(FieldRiskEvent.territory_id.in_(ids), FieldRiskEvent.status == RiskStatus.NEW)
        .values(status=RiskStatus.SEEN)
    )
    session.commit()
    return result.rowcount


def _toggle(session: Session, user: User, kind: str) -> bool:
    """Turns Telegram on or off for one kind; True when it is now on."""
    chosen = preferences(user)
    chosen[kind]["telegram"] = not chosen[kind]["telegram"]
    user.notifications = chosen
    session.commit()
    return chosen[kind]["telegram"]


def _on_button(
    session: Session, bot: Telegram, query: dict, now: datetime, app_url: str | None
) -> None:
    message = query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    user = _linked_user(session, chat_id)
    texts = TEXTS[_locale(user, query.get("from", {}))]
    data = query.get("data") or ""
    if user is None:
        bot.answer_button(query["id"], "")
        return
    if data == MENU:
        bot.answer_button(query["id"], "")
        bot.edit_text(chat_id, message_id, *menu_view(user))
    elif data == FIELDS:
        bot.answer_button(query["id"], "")
        bot.edit_text(chat_id, message_id, *fields_view(session, user, now, app_url))
    elif data.startswith(FIELD) and data[len(FIELD) :].isdigit():
        bot.answer_button(query["id"], "")
        view = field_view(session, user, int(data[len(FIELD) :]), now, app_url)
        # Tapped under an alert's photo: the field opens as a new message below it.
        if message.get("photo"):
            bot.send_text(chat_id, *view)
        else:
            bot.edit_text(chat_id, message_id, *view)
    elif data == ALERTS:
        bot.answer_button(query["id"], "")
        bot.edit_text(chat_id, message_id, *alerts_view(user))
    elif data.startswith(MORE):
        bot.answer_button(query["id"], "")
        target = data[len(MORE) :]
        if target == MENU:
            view = how_view(user, app_url)
        elif target == ALERTS:
            view = alerts_more_view(user, app_url)
        elif target.isdigit():
            view = field_more_view(session, user, int(target), now, app_url)
        else:
            return
        bot.edit_text(chat_id, message_id, *view)
    elif data.startswith(TOGGLE) and data[len(TOGGLE) :] in KINDS:
        on = _toggle(session, user, data[len(TOGGLE) :])
        bot.answer_button(query["id"], texts["on"] if on else texts["off"])
        bot.edit_text(chat_id, message_id, *alerts_view(user))
    elif data.startswith(SEEN) and data[len(SEEN) :].isdigit():
        mark_seen(session, user, int(data[len(SEEN) :]))
        bot.answer_button(query["id"], texts["seen"])
        # The message says so: "Ya lo vi" becomes "✓ Visto", the other buttons stay.
        rows = (message.get("reply_markup") or {}).get("inline_keyboard") or []
        seen = {"text": texts["seen_button"], "callback_data": SEEN}
        buttons = [
            [seen if (b.get("callback_data") or "").startswith(SEEN) else b for b in row]
            for row in rows
        ]
        bot.set_buttons(chat_id, message_id, buttons)
    else:
        bot.answer_button(query["id"], texts["already"] if data == SEEN else "")


def answer_updates(
    session: Session, bot: Telegram, now: datetime, app_url: str | None = None
) -> int:
    """Handles the messages and button taps waiting for the bot, then confirms them to Telegram.
    Nothing is kept between runs: an update handled but not confirmed is handled again, which
    changes nothing. `app_url` is the app's public address, for buttons; None when local."""
    updates = bot.updates(None)
    for item in updates:
        try:
            if "message" in item:
                _on_message(session, bot, item["message"], now, app_url)
            elif "callback_query" in item:
                _on_button(session, bot, item["callback_query"], now, app_url)
        except (TelegramError, httpx.HTTPError, KeyError) as exc:
            session.rollback()
            log.warning("telegram update %s not handled: %s", item.get("update_id"), exc)
    if updates:
        bot.updates(updates[-1]["update_id"] + 1)
    return len(updates)
