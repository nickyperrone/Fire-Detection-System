"""Which dangers an account hears about, and through which channels
(docs/13-notifications.md)."""

from typing import Literal, get_args

from app.models import Severity, User

Kind = Literal["fire_high", "fire_medium", "fire_far", "lightning", "weather", "summary"]
Channel = Literal["email", "telegram"]
KINDS: tuple[Kind, ...] = get_args(Kind)
CHANNELS: tuple[Channel, ...] = get_args(Channel)

DEFAULTS: dict[Kind, dict[Channel, bool]] = {
    "fire_high": {"email": True, "telegram": True},
    "fire_medium": {"email": True, "telegram": True},
    "fire_far": {"email": False, "telegram": False},
    "lightning": {"email": True, "telegram": True},
    "weather": {"email": True, "telegram": True},
    "summary": {"email": True, "telegram": False},
}

FIRE_KIND: dict[Severity, Kind] = {
    Severity.CRITICAL: "fire_high",
    Severity.VERY_HIGH: "fire_high",
    Severity.HIGH: "fire_medium",
    Severity.WATCH: "fire_far",
}


def preferences(user: User) -> dict[Kind, dict[Channel, bool]]:
    """The account's choices over the defaults, so a kind added later starts at its default."""
    saved = user.notifications or {}
    return {
        kind: {
            channel: bool(saved.get(kind, {}).get(channel, default))
            for channel, default in DEFAULTS[kind].items()
        }
        for kind in KINDS
    }


def wants(user: User, kind: Kind, channel: Channel) -> bool:
    """Whether this kind goes through this channel; Telegram also needs a linked chat."""
    if channel == "telegram" and user.telegram_chat_id is None:
        return False
    return preferences(user)[kind][channel]
