"""Linking Telegram chats to accounts and answering the bot (docs/13-notifications.md#telegram)."""

import logging
import secrets
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import FieldRiskEvent, RiskStatus, Territory, User
from app.providers.telegram import Telegram, TelegramError
from app.services.auth import _hash

log = logging.getLogger(__name__)

CODE_MINUTES = 15
SEEN = "seen:"

TEXTS = {
    "es": {
        "linked": "Listo: las alertas de Field Watch van a llegar a este chat. "
        "Elegí cuáles en Notificaciones, en el menú de tu cuenta. Para dejar de recibirlas acá, "
        "mandá /stop.",
        "expired": "Ese código venció o ya se usó. En Field Watch, abrí Notificaciones y tocá "
        "«Conectar Telegram» de nuevo.",
        "hello": "Hola. Para recibir alertas acá, entrá a Field Watch, abrí Notificaciones en el "
        "menú de tu cuenta y tocá «Conectar Telegram».",
        "stopped": "Listo: este chat ya no recibe alertas de Field Watch.",
        "seen": "Marcado como visto",
        "seen_button": "✓ Visto",
        "already": "Ya estaba marcado como visto",
    },
    "en": {
        "linked": "Done: Field Watch alerts will arrive in this chat. Choose which in "
        "Notifications, in your account menu. To stop them here, send /stop.",
        "expired": "That code expired or was already used. In Field Watch, open Notifications and "
        "tap “Connect Telegram” again.",
        "hello": "Hi. To get alerts here, open Field Watch, go to Notifications in your account "
        "menu and tap “Connect Telegram”.",
        "stopped": "Done: this chat no longer gets Field Watch alerts.",
        "seen": "Marked as seen",
        "seen_button": "✓ Seen",
        "already": "Already marked as seen",
    },
}


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


def _locale(user: User | None, update_from: dict) -> str:
    if user is not None:
        return user.locale
    return "en" if (update_from.get("language_code") or "es")[:2] == "en" else "es"


def _on_message(session: Session, bot: Telegram, message: dict, now: datetime) -> None:
    chat_id = message["chat"]["id"]
    words = (message.get("text") or "").split()
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
        bot.send_text(chat_id, TEXTS[user.locale]["linked"])
    elif command == "/stop":
        user = session.scalar(select(User).where(User.telegram_chat_id == chat_id))
        if user is not None:
            user.telegram_chat_id = None
            session.commit()
        bot.send_text(chat_id, TEXTS[_locale(user, sender)]["stopped"])
    else:
        user = session.scalar(select(User).where(User.telegram_chat_id == chat_id))
        if user is None:
            bot.send_text(chat_id, TEXTS[_locale(None, sender)]["hello"])


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


def _on_button(session: Session, bot: Telegram, query: dict) -> None:
    message = query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    user = session.scalar(select(User).where(User.telegram_chat_id == chat_id))
    texts = TEXTS[_locale(user, query.get("from", {}))]
    data = query.get("data") or ""
    if user is None or not data.startswith(SEEN) or not data[len(SEEN) :].isdigit():
        bot.answer_button(query["id"], texts["already"] if data == SEEN else "")
        return
    mark_seen(session, user, int(data[len(SEEN) :]))
    bot.answer_button(query["id"], texts["seen"])
    # The message says so: "Ya lo vi" becomes "✓ Visto", the link stays.
    rows = (message.get("reply_markup") or {}).get("inline_keyboard") or [[]]
    buttons = [b for b in rows[0] if "url" in b]
    buttons.append({"text": texts["seen_button"], "callback_data": SEEN})
    bot.set_buttons(chat_id, message["message_id"], buttons)


def answer_updates(session: Session, bot: Telegram, now: datetime) -> int:
    """Handles the messages and button taps waiting for the bot, then confirms them to Telegram.
    Nothing is kept between runs: an update handled but not confirmed is handled again, which
    changes nothing."""
    updates = bot.updates(None)
    for item in updates:
        try:
            if "message" in item:
                _on_message(session, bot, item["message"], now)
            elif "callback_query" in item:
                _on_button(session, bot, item["callback_query"])
        except (TelegramError, httpx.HTTPError, KeyError) as exc:
            session.rollback()
            log.warning("telegram update %s not handled: %s", item.get("update_id"), exc)
    if updates:
        bot.updates(updates[-1]["update_id"] + 1)
    return len(updates)
