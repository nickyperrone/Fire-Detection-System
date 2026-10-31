"""Sending push alerts to browsers and phones (docs/13-notifications.md#push)."""

import base64
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from pywebpush import WebPushException, webpush

from app.config import Settings
from app.models import PushSubscription

log = logging.getLogger(__name__)

# What the push services allow is about 4 KB; alerts are far smaller.
MAX_PAYLOAD_BYTES = 3000
# How long a push service keeps an alert for a phone that is off: an old alert is worse than none.
TTL_SECONDS = 3 * 3600


@dataclass(frozen=True)
class PushMessage:
    """What the service worker shows: a title and a few lines, where it opens, and the one-tap
    "unsubscribe" for this kind."""

    title: str
    body: str
    url: str
    tag: str
    unsubscribe: str
    # False for a distant fire alone: it arrives without a sound, like Telegram's.
    silent: bool = False

    def payload(self) -> str:
        data = {
            "title": self.title,
            "body": self.body,
            "url": self.url,
            "tag": self.tag,
            "unsubscribe": self.unsubscribe,
            "silent": self.silent,
        }
        encoded = json.dumps(data, ensure_ascii=False)
        while len(encoded.encode()) > MAX_PAYLOAD_BYTES and len(data["body"]) > 40:
            data["body"] = data["body"][: len(data["body"]) * 3 // 4].rstrip() + "…"
            encoded = json.dumps(data, ensure_ascii=False)
        return encoded


# (subscription, payload) -> "sent", "gone" (the device unsubscribed: forget it) or "failed"
PushSender = Callable[[PushSubscription, PushMessage], str]


def make_vapid_keys() -> tuple[str, str]:
    """A new key pair as (public, private), both URL-safe base64: the public one is what browsers
    are given to subscribe, the private one signs each push."""
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid01

    vapid = Vapid01()
    vapid.generate_keys()
    raw_private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    raw_public = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    b64 = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()  # noqa: E731
    return b64(raw_public), b64(raw_private)


def available(settings: Settings) -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def web_pusher(settings: Settings) -> PushSender:
    """The real sender, signing each push with the server's VAPID key."""
    claims = {"sub": settings.vapid_subject}

    def send(subscription: PushSubscription, message: PushMessage) -> str:
        origin = urlparse(subscription.endpoint)
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=message.payload(),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={**claims, "aud": f"{origin.scheme}://{origin.netloc}"},
                ttl=TTL_SECONDS,
            )
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (404, 410):
                return "gone"
            log.warning("push to subscription %s failed: %s", subscription.id, exc)
            return "failed"
        except OSError as exc:
            log.warning("push to subscription %s failed: %s", subscription.id, exc)
            return "failed"
        return "sent"

    return send
