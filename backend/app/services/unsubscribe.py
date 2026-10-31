"""One-tap "unsubscribe" links in every alert, which work without signing in
(docs/13-notifications.md#unsubscribing)."""

import hashlib
import hmac
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User
from app.services.notification_prefs import CHANNELS, KINDS, Channel, preferences

# "alerts" stands for every kind of danger alert at once, but not the summary.
ALERT_KINDS = tuple(kind for kind in KINDS if kind != "summary")
SCOPES = (*KINDS, "alerts")


@dataclass(frozen=True)
class Unsubscribe:
    user: User
    scope: str
    channel: Channel


def _signature(user: User, scope: str, channel: str) -> str:
    message = f"{user.id}|{scope}|{channel}".encode()
    return hmac.new(user.alert_key.encode(), message, hashlib.sha256).hexdigest()[:32]


def sign(user: User, scope: str, channel: Channel) -> str:
    """ "7.fire_high.push.<signature>": made with the account's own key, so it cannot be made up for
    another account, and cannot be used for another kind or channel."""
    return f"{user.id}.{scope}.{channel}.{_signature(user, scope, channel)}"


def link(settings: Settings, user: User, scope: str, channel: Channel) -> str:
    return f"{settings.app_url}/api/unsubscribe?t={sign(user, scope, channel)}"


def read(session: Session, token: str) -> Unsubscribe | None:
    """The account, scope and channel a token is for, if it is genuine."""
    parts = token.split(".")
    if len(parts) != 4 or not parts[0].isdigit():
        return None
    user_id, scope, channel, signature = parts
    if scope not in SCOPES or channel not in CHANNELS:
        return None
    user = session.get(User, int(user_id))
    if user is None or not hmac.compare_digest(signature, _signature(user, scope, channel)):
        return None
    return Unsubscribe(user, scope, channel)  # type: ignore[arg-type]


def apply(session: Session, found: Unsubscribe) -> None:
    """Turns the scope off for that channel. Nothing else changes, and doing it twice is the same
    as once."""
    prefs = preferences(found.user)
    kinds = ALERT_KINDS if found.scope == "alerts" else (found.scope,)
    for kind in kinds:
        prefs[kind][found.channel] = False
    found.user.notifications = prefs
    session.commit()
