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
SPRAY_PROFILE = "default"
WINDOW_HOURS = 48

TEXTS = {
    "es": {
        "linked": "✅ <b>Telegram conectado</b>\n\n"
        "Te vamos a avisar acá cuando haya fuego, rayos o clima adverso cerca de tus campos, "
        "con una foto del área.\n\n¿Qué querés ver?",
        "expired": "Ese código venció o ya se usó. En Field Watch, abrí Notificaciones (la "
        "campana) y tocá «Conectar Telegram» de nuevo.",
        "hello": "Para recibir alertas acá, entrá a Field Watch, abrí Notificaciones (la "
        "campana) y tocá «Conectar Telegram».",
        "stopped": "Listo: este chat ya no recibe alertas de Field Watch. Para volver a "
        "recibirlas, conectalo de nuevo desde Notificaciones.",
        "menu_text": "<b>Field Watch</b>\n\n"
        "Vigilamos tus campos y te avisamos acá si hay fuego, rayos o clima adverso cerca.\n\n"
        "<b>Mis campos</b>: cómo está cada uno ahora.\n"
        "<b>Mis alertas</b>: cuáles te llegan a este chat.",
        "menu": {FIELDS: "📋 Mis campos", ALERTS: "🔔 Mis alertas"},
        "to_menu": "‹ Menú",
        "seen": "Marcado como visto",
        "seen_button": "✓ Visto",
        "already": "Ya estaba marcado como visto",
        "fields_title": "📋 <b>Tus campos</b>",
        "fields_hint": "Tocá un campo para ver el detalle.",
        "no_fields": "Todavía no tenés campos. Agregalos en Field Watch con el botón +.",
        "fire_inside": "🔥 Posible fuego dentro del campo",
        "fire_near": "🔥 Posible fuego a {km} km{where}",
        "fire_where": " al {direction}",
        "no_fire": "Sin fuegos a menos de 10 km",
        "spray": {
            SprayStatus.FAVORABLE: "🟢 Pulverizar ahora: conviene",
            SprayStatus.CAUTION: "🟡 Pulverizar ahora: con precaución",
            SprayStatus.UNFAVORABLE: "🔴 Pulverizar ahora: no conviene",
            None: "Pulverizar ahora: sin pronóstico",
        },
        "window": "Próxima ventana para pulverizar: {span}",
        "no_window": "Sin ventanas para pulverizar en las próximas 48 h",
        "lots": lambda n: f"{n} {'lote' if n == 1 else 'lotes'}",
        "gone": "Ese campo ya no está en tu cuenta.",
        "back": "‹ Mis campos",
        "open": "Abrir Field Watch",
        "open_field": "Abrir en el mapa",
        "alerts_title": "🔔 <b>Alertas en este chat</b>",
        "alerts_hint": "Tocá un tipo para prenderlo o apagarlo. Las alertas por mail se eligen "
        "en Field Watch, en Notificaciones.",
        "kinds": {
            "fire_high": "Fuego muy cerca",
            "fire_medium": "Fuego cerca",
            "fire_far": "Fuego lejano",
            "lightning": "Rayos",
            "weather": "Clima adverso",
            "summary": "Resumen",
        },
        "on": "Prendida",
        "off": "Apagada",
    },
    "en": {
        "linked": "✅ <b>Telegram connected</b>\n\n"
        "We will alert you here when there is fire, lightning or adverse weather near your "
        "fields, with a photo of the area.\n\nWhat do you want to see?",
        "expired": "That code expired or was already used. In Field Watch, open Notifications "
        "(the bell) and tap “Connect Telegram” again.",
        "hello": "To get alerts here, open Field Watch, go to Notifications (the bell) and tap "
        "“Connect Telegram”.",
        "stopped": "Done: this chat no longer gets Field Watch alerts. To get them again, "
        "connect it from Notifications.",
        "menu_text": "<b>Field Watch</b>\n\n"
        "We watch your fields and alert you here when there is fire, lightning or adverse "
        "weather nearby.\n\n"
        "<b>My fields</b>: how each one is now.\n"
        "<b>My alerts</b>: which ones come to this chat.",
        "menu": {FIELDS: "📋 My fields", ALERTS: "🔔 My alerts"},
        "to_menu": "‹ Menu",
        "seen": "Marked as seen",
        "seen_button": "✓ Seen",
        "already": "Already marked as seen",
        "fields_title": "📋 <b>Your fields</b>",
        "fields_hint": "Tap a field to see it in detail.",
        "no_fields": "You have no fields yet. Add them in Field Watch with the + button.",
        "fire_inside": "🔥 Possible fire inside the field",
        "fire_near": "🔥 Possible fire {km} km{where}",
        "fire_where": " {direction}",
        "no_fire": "No fires within 10 km",
        "spray": {
            SprayStatus.FAVORABLE: "🟢 Spraying now: good",
            SprayStatus.CAUTION: "🟡 Spraying now: with caution",
            SprayStatus.UNFAVORABLE: "🔴 Spraying now: not advised",
            None: "Spraying now: no forecast",
        },
        "window": "Next spraying window: {span}",
        "no_window": "No spraying window in the next 48 h",
        "lots": lambda n: f"{n} {'lot' if n == 1 else 'lots'}",
        "gone": "That field is no longer in your account.",
        "back": "‹ My fields",
        "open": "Open Field Watch",
        "open_field": "Open in the map",
        "alerts_title": "🔔 <b>Alerts in this chat</b>",
        "alerts_hint": "Tap a kind to turn it on or off. Email alerts are chosen in Field Watch, "
        "in Notifications.",
        "kinds": {
            "fire_high": "Fire very close",
            "fire_medium": "Fire close",
            "fire_far": "Distant fire",
            "lightning": "Lightning",
            "weather": "Adverse weather",
            "summary": "Summary",
        },
        "on": "On",
        "off": "Off",
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
           spray.status AS spray,
           (SELECT count(*) FROM territory l WHERE l.parent_id = t.id) AS lots
    FROM territory t
    LEFT JOIN LATERAL (
        SELECT r.distance_m, r.bearing_deg, r.severity
        FROM field_risk_event r JOIN fire_event e ON e.id = r.fire_event_id
        WHERE r.territory_id = t.id AND e.status = 'ACTIVE' AND r.status != 'RESOLVED'
        ORDER BY r.distance_m LIMIT 1
    ) fire ON true
    LEFT JOIN LATERAL (
        SELECT a.status FROM spray_assessment a
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
    menu = TEXTS[locale]["menu"]
    return [
        [
            {"text": menu[FIELDS], "callback_data": FIELDS},
            {"text": menu[ALERTS], "callback_data": ALERTS},
        ]
    ]


def menu_view(user: User) -> tuple[str, Buttons]:
    return TEXTS[user.locale]["menu_text"], menu_buttons(user.locale)


def _fire_line(row, texts: dict, locale: str) -> str:
    if row.distance_m is None:
        return texts["no_fire"]
    if row.severity == Severity.CRITICAL:
        return texts["fire_inside"]
    direction = DIRECTIONS[locale].get(compass(row.bearing_deg) or "", "")
    where = texts["fire_where"].format(direction=direction) if direction else ""
    return texts["fire_near"].format(km=_km(row.distance_m, locale), where=where)


def _spray_line(row, texts: dict) -> str:
    return texts["spray"][SprayStatus(row.spray) if row.spray else None]


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


def fields_view(
    session: Session, user: User, now: datetime, app_url: str | None
) -> tuple[str, Buttons]:
    """Every field, a line on fire and one on spraying each, and a button to open each one."""
    texts = TEXTS[user.locale]
    rows = session.execute(
        STATUS_SQL, {"owner": user.email, "now": now, "profile": SPRAY_PROFILE}
    ).all()
    link = [[{"text": texts["open"], "url": app_url}]] if app_url else []
    link.append([{"text": texts["to_menu"], "callback_data": MENU}])
    if not rows:
        return texts["no_fields"], link
    blocks = [
        f"<b>{escape(r.name)}</b> · {r.hectares:.0f} ha\n"
        f"{_fire_line(r, texts, user.locale)}\n{_spray_line(r, texts)}"
        for r in rows
    ]
    body = f"{texts['fields_title']}\n\n" + "\n\n".join(blocks) + f"\n\n{texts['fields_hint']}"
    buttons = [[{"text": f"{r.name} ›", "callback_data": f"{FIELD}{r.id}"}] for r in rows]
    return body, buttons + link


def field_view(
    session: Session, user: User, field_id: int, now: datetime, app_url: str | None
) -> tuple[str, Buttons]:
    """One field in detail: the closest fire, spraying now and the next window to spray."""
    texts = TEXTS[user.locale]
    back = [[{"text": texts["back"], "callback_data": FIELDS}]]
    rows = session.execute(
        STATUS_SQL, {"owner": user.email, "now": now, "profile": SPRAY_PROFILE}
    ).all()
    row = next((r for r in rows if r.id == field_id), None)
    if row is None:
        return texts["gone"], back
    window = _window(session, field_id, now)
    if window:
        span = f"{_when(window[0], user.locale)}–{window[1].astimezone(LOCAL):%H:%M}"
        window_line = texts["window"].format(span=span)
    else:
        window_line = texts["no_window"]
    lines = [
        f"<b>{escape(row.name)}</b>",
        f"{row.hectares:.0f} ha" + (f" · {texts['lots'](row.lots)}" if row.lots else ""),
        "",
        _fire_line(row, texts, user.locale),
        _spray_line(row, texts),
        window_line,
    ]
    buttons = back
    if app_url:
        buttons = [[{"text": texts["open_field"], "url": f"{app_url}/?f={field_id}"}], *back]
    return "\n".join(lines), buttons


def alerts_view(user: User) -> tuple[str, Buttons]:
    """Each kind of alert as a button that turns it on or off in this chat."""
    texts = TEXTS[user.locale]
    chosen = preferences(user)
    buttons = [
        [
            {
                "text": f"{'✅' if chosen[kind]['telegram'] else '▫️'} {texts['kinds'][kind]}",
                "callback_data": f"{TOGGLE}{kind}",
            }
        ]
        for kind in KINDS
    ]
    buttons.append([{"text": texts["to_menu"], "callback_data": MENU}])
    return f"{texts['alerts_title']}\n\n{texts['alerts_hint']}", buttons


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
