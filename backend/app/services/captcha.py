"""Keeping bots off the sign-in form (docs/09-accounts-and-alerts.md#bots)."""

import threading
import time
from collections import defaultdict, deque

import httpx

SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def turnstile_passed(client: httpx.Client, secret: str, token: str | None, ip: str | None) -> bool:
    """Whether Cloudflare says the token comes from a person who just passed the check. Any
    failure to ask counts as not passed: the form stays closed rather than open to bots."""
    if not token:
        return False
    data = {"secret": secret, "response": token}
    if ip:
        data["remoteip"] = ip
    try:
        response = client.post(SITEVERIFY, data=data, timeout=10)
        return bool(response.json().get("success"))
    except (httpx.HTTPError, ValueError):
        return False


class RateLimit:
    """At most `limit` hits per key in a sliding hour, kept in memory: one API process serves the
    app (docs/14-deploy.md), and a restart only forgets the last hour."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - 3600:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


login_requests = RateLimit()


def client_ip(headers, fallback: str | None) -> str | None:
    """The visitor's address: Cloudflare's header in production, the proxy's otherwise."""
    if headers.get("cf-connecting-ip"):
        return headers["cf-connecting-ip"].strip()
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return fallback
