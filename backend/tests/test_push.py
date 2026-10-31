# ruff: noqa: F811, E501
# Fixtures come from test_notifications, and some lines carry long literals.
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models import PushSubscription, User
from app.services import unsubscribe
from app.services.alerts import send_alerts
from app.services.notification_prefs import preferences, wants
from app.services.push import PushMessage
from app.services.telegram_bot import answer_updates
from tests.test_alerts import EMAIL, NOW, fire
from tests.test_auth import sign_in
from tests.test_notifications import CHAT, bot, field, linked, say, tap  # noqa: F401

DEVICE = {
    "endpoint": "https://push.example/send/abc123456789012345",
    "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
    "auth": "tBHItJI5svbpez7KI4CCXg",
    "label": "Chrome en Android",
}


class FakePusher:
    """Records what would be pushed, and answers each device as a test says."""

    def __init__(self, answers=None):
        self.sent: list[tuple[str, PushMessage]] = []
        self.answers = answers or {}

    def __call__(self, subscription, message):
        self.sent.append((subscription.endpoint, message))
        return self.answers.get(subscription.endpoint, "sent")


def device(session, user, endpoint=DEVICE["endpoint"]):
    session.add(PushSubscription(user_id=user.id, endpoint=endpoint, p256dh="k", auth="a"))
    session.commit()
    session.refresh(user)


def user_of(session):
    return session.scalar(select(User).where(User.email == EMAIL))


def run(session, thresholds, outbox, pusher, bot=None, now=NOW):
    return send_alerts(
        session,
        outbox.append,
        Settings(app_url="https://fieldwatch.example"),
        thresholds,
        "test",
        now,
        bot,
        lambda *_: b"png",
        pusher,
    )


# --- who gets push -----------------------------------------------------------------------------


def test_push_counts_only_with_a_device_that_agreed(session, field):
    user = user_of(session)
    assert preferences(user)["fire_high"]["push"] and not wants(user, "fire_high", "push")
    device(session, user)
    assert wants(user, "fire_high", "push")
    # A distant fire and the summary are off by default, as in the other channels.
    assert not wants(user, "fire_far", "push") and not wants(user, "summary", "push")


def test_a_fire_is_pushed_to_each_device_with_where_to_open_it(session, thresholds, outbox, field):
    user = user_of(session)
    device(session, user)
    device(session, user, "https://push.example/send/second-device-0000000")
    fire(session, thresholds, -59.07)
    pusher = FakePusher()
    result = run(session, thresholds, outbox, pusher)
    assert (result["push_sent"], result["push_failed"]) == (1, 0)
    assert len(pusher.sent) == 2
    message = pusher.sent[0][1]
    assert message.title == "🔴 ¡ALERTA!"
    assert message.body.startswith("Posible fuego a 1,9 km al E de La Esperanza")
    assert message.url == f"https://fieldwatch.example/?f={field.id}"
    # One notification per field: a newer one replaces the older.
    assert message.tag == f"field-{field.id}"
    assert not message.silent
    payload = json.loads(message.payload())
    assert payload["title"] == message.title and payload["unsubscribe"] == message.unsubscribe


def test_a_device_that_unsubscribed_is_forgotten_and_a_failure_is_tried_again(
    session, thresholds, outbox, field
):
    user = user_of(session)
    gone = "https://push.example/send/gone-device-000000000"
    device(session, user, gone)
    device(session, user)
    fire(session, thresholds, -59.07)
    result = run(
        session, thresholds, outbox, FakePusher({gone: "gone", DEVICE["endpoint"]: "failed"})
    )
    session.expire_all()
    assert [s.endpoint for s in session.scalars(select(PushSubscription))] == [DEVICE["endpoint"]]
    assert result["push_sent"] == 0 and result["push_failed"] == 1
    # Email still carried it, so it is announced; push alone failing does not repeat the email.
    assert result["emails_sent"] == 1
    assert run(session, thresholds, outbox, FakePusher())["emails_sent"] == 0


def test_a_kind_turned_off_for_push_is_not_pushed(session, thresholds, outbox, field):
    user = user_of(session)
    device(session, user)
    prefs = preferences(user)
    prefs["fire_high"]["push"] = False
    user.notifications = prefs
    session.commit()
    fire(session, thresholds, -59.07)
    pusher = FakePusher()
    assert run(session, thresholds, outbox, pusher)["push_sent"] == 0
    assert pusher.sent == []


def test_every_push_carries_a_way_to_stop_that_kind(session, thresholds, outbox, field):
    user = user_of(session)
    device(session, user)
    fire(session, thresholds, -59.07)
    pusher = FakePusher()
    run(session, thresholds, outbox, pusher)
    url = pusher.sent[0][1].unsubscribe
    assert url.startswith("https://fieldwatch.example/api/unsubscribe?t=")
    found = unsubscribe.read(session, url.split("t=")[1])
    assert (found.scope, found.channel, found.user.email) == ("fire_high", "push", EMAIL)


# --- the links ---------------------------------------------------------------------------------


def test_a_link_is_for_one_account_one_kind_and_one_channel(session, field):
    user = user_of(session)
    token = unsubscribe.sign(user, "fire_high", "email")
    assert unsubscribe.read(session, token).scope == "fire_high"
    user_id, scope, channel, signature = token.split(".")
    for forged in (
        f"{user_id}.fire_medium.email.{signature}",
        f"{user_id}.fire_high.push.{signature}",
        f"{int(user_id) + 1}.fire_high.email.{signature}",
        f"{user_id}.fire_high.email.{'0' * 32}",
        f"{user_id}.everything.email.{signature}",
        "garbage",
        "",
    ):
        assert unsubscribe.read(session, forged) is None


def test_opening_the_link_changes_nothing_and_the_button_turns_the_kind_off(
    anonymous, outbox, session
):
    sign_in(anonymous, outbox, "uno@example.com")
    anonymous.cookies.clear()
    user = session.scalar(select(User).where(User.email == "uno@example.com"))
    token = unsubscribe.sign(user, "lightning", "email")
    page = anonymous.get(f"/unsubscribe?t={token}")
    assert (
        page.status_code == 200 and "los avisos de rayos" in page.text and "por mail" in page.text
    )
    session.refresh(user)
    assert preferences(user)["lightning"]["email"]
    done = anonymous.post(f"/unsubscribe?t={token}")
    assert done.status_code == 200 and "Listo" in done.text
    session.refresh(user)
    assert not preferences(user)["lightning"]["email"]
    # Only that kind, only that channel; and doing it again is harmless.
    assert preferences(user)["lightning"]["telegram"] and preferences(user)["weather"]["email"]
    assert anonymous.post(f"/unsubscribe?t={token}").status_code == 200


def test_a_mail_apps_one_tap_and_the_notifications_button_work_without_signing_in(
    anonymous, outbox, session
):
    sign_in(anonymous, outbox, "uno@example.com")
    anonymous.cookies.clear()
    user = session.scalar(select(User).where(User.email == "uno@example.com"))
    # RFC 8058: a POST with the token in the address and a fixed body, from no browser.
    token = unsubscribe.sign(user, "alerts", "email")
    sent = anonymous.post(
        f"/unsubscribe?t={token}",
        content="List-Unsubscribe=One-Click",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert sent.status_code == 200
    session.refresh(user)
    prefs = preferences(user)
    assert not any(prefs[k]["email"] for k in unsubscribe.ALERT_KINDS)
    # The summary is its own thing: "alerts" does not touch it.
    assert prefs["summary"]["email"]
    summary = unsubscribe.sign(user, "summary", "email")
    anonymous.post(
        "/unsubscribe",
        content=f"t={summary}",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    session.refresh(user)
    assert not preferences(user)["summary"]["email"]


def test_a_bad_link_does_nothing(anonymous):
    assert anonymous.post("/unsubscribe?t=1.alerts.email.nope").status_code == 400
    assert anonymous.get("/unsubscribe?t=nope").status_code == 200
    assert anonymous.post("/unsubscribe").status_code == 400


def test_alert_and_summary_emails_have_the_one_tap_way_out(session, thresholds, outbox, field):
    fire(session, thresholds, -59.07)
    run(session, thresholds, outbox, None)
    email = outbox[0]
    link = email["List-Unsubscribe"].strip("<>")
    assert link.startswith("https://fieldwatch.example/api/unsubscribe?t=")
    assert email["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert f"Dejar de recibir estos avisos por mail con un toque: {link}" in email.get_content()


# --- devices -----------------------------------------------------------------------------------


def test_a_browser_subscribes_and_unsubscribes_only_when_signed_in(anonymous, outbox, session):
    assert anonymous.post("/push/subscribe", json=DEVICE).status_code == 401
    sign_in(anonymous, outbox, "uno@example.com")
    assert anonymous.post("/push/subscribe", json=DEVICE).status_code == 204
    me = anonymous.get("/auth/me").json()
    assert me["push"]["devices"] == 1 and "available" in me["push"]
    # The same device again only refreshes it.
    assert anonymous.post("/push/subscribe", json=DEVICE | {"label": "Otro"}).status_code == 204
    assert session.scalar(select(PushSubscription.label)) == "Otro"
    assert anonymous.get("/auth/me").json()["push"]["devices"] == 1
    assert (
        anonymous.post("/push/unsubscribe", json={"endpoint": DEVICE["endpoint"]}).status_code
        == 204
    )
    assert anonymous.get("/auth/me").json()["push"]["devices"] == 0


def test_nobody_forgets_another_accounts_device_and_endpoints_must_be_https(
    anonymous, outbox, session
):
    sign_in(anonymous, outbox, "uno@example.com")
    anonymous.post("/push/subscribe", json=DEVICE)
    anonymous.cookies.clear()
    sign_in(anonymous, outbox, "dos@example.com")
    anonymous.post("/push/unsubscribe", json={"endpoint": DEVICE["endpoint"]})
    assert session.scalar(select(PushSubscription.endpoint)) == DEVICE["endpoint"]
    bad = anonymous.post("/push/subscribe", json=DEVICE | {"endpoint": "http://push.example/x" * 3})
    assert bad.status_code == 422


def test_there_is_a_limit_of_devices_per_account(anonymous, outbox):
    sign_in(anonymous, outbox, "uno@example.com")
    for n in range(10):
        endpoint = f"https://push.example/send/device-number-{n:02d}-0000"
        assert (
            anonymous.post("/push/subscribe", json=DEVICE | {"endpoint": endpoint}).status_code
            == 204
        )
    over = anonymous.post(
        "/push/subscribe", json=DEVICE | {"endpoint": "https://push.example/one-more-device-000"}
    )
    assert over.status_code == 409


def test_a_page_that_does_not_know_push_leaves_it_as_it_was(anonymous, outbox):
    sign_in(anonymous, outbox, "uno@example.com")
    me = anonymous.get("/auth/me").json()
    old_page = {
        k: {"email": v["email"], "telegram": v["telegram"]} for k, v in me["notifications"].items()
    }
    changed = anonymous.patch("/auth/me", json={"notifications": old_page}).json()
    assert changed["notifications"] == me["notifications"]


# --- Telegram ----------------------------------------------------------------------------------


def test_the_mute_button_in_a_telegram_alert_turns_that_kind_off_there(session, bot, field):  # noqa: F811
    user = linked(session)
    bot.queue = [tap("mute:fire_high")]
    answer_updates(session, bot, NOW)
    assert "no te aviso más" in bot.answers[-1]
    session.refresh(user)
    prefs = preferences(user)
    assert not prefs["fire_high"]["telegram"] and prefs["fire_high"]["email"]
    assert prefs["fire_medium"]["telegram"]


def test_push_text_is_short_and_says_the_wind_and_what_the_field_holds(session, field):
    from app.services.email_text import alert_push
    from app.services.wind import Push
    from tests.test_alerts import alert  # noqa: F401

    dangers = []
    title, body = alert_push(
        "es", dangers, Push(True, 1, 2.5), "🏠 Hay construcciones cerca", 60, NOW
    )
    assert title == "🔴 ¡ALERTA!"
    assert body.splitlines() == [
        "💨 Viento hacia el campo.",
        "⏱️ Si avanza con el viento, llegaría en ~2,5 h (estimado).",
        "🏠 Hay construcciones cerca",
    ]
    long = PushMessage("t", "x" * 5000, "https://a", "tag", "https://u")
    assert len(long.payload().encode()) <= 3100
    assert timedelta  # keeps the import used


def test_the_keys_made_for_push_can_sign_and_are_the_size_browsers_expect():
    import base64

    from py_vapid import Vapid

    from app.services.push import make_vapid_keys

    public, private = make_vapid_keys()
    unpad = lambda text: base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))  # noqa: E731
    assert len(unpad(public)) == 65 and unpad(public)[0] == 4
    assert len(unpad(private)) == 32
    # The server reads the private key the way it is configured, and signs for a push service.
    headers = Vapid.from_string(private).sign(
        {"sub": "mailto:a@b.example", "aud": "https://push.example"}
    )
    assert headers["Authorization"].startswith("vapid ")
    assert public != make_vapid_keys()[0]


class FakePushService:
    """A push service on this computer: it answers with the status a test gives and keeps what
    it was sent."""

    def __init__(self, status):
        import http.server
        import threading

        received = self.received = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("content-length", 0))
                received.append((dict(self.headers), self.rfile.read(length)))
                self.send_response(status)
                self.end_headers()

            def log_message(self, *_):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}/send/device"

    def close(self):
        self.server.shutdown()


def browser_keys():
    """What a browser gives when it subscribes: its public key and a secret to share."""
    import base64
    import os

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    b64 = lambda raw: base64.urlsafe_b64encode(raw).rstrip(b"=").decode()  # noqa: E731
    return b64(public), b64(os.urandom(16))


@pytest.mark.parametrize(
    ("status", "outcome"), [(201, "sent"), (410, "gone"), (404, "gone"), (500, "failed")]
)
def test_the_real_sender_encrypts_signs_and_reads_the_push_services_answer(status, outcome):
    from app.services.push import make_vapid_keys, web_pusher

    public, private = make_vapid_keys()
    p256dh, auth = browser_keys()
    service = FakePushService(status)
    try:
        sender = web_pusher(
            Settings(
                vapid_public_key=public, vapid_private_key=private, vapid_subject="mailto:a@b.co"
            )
        )
        device = PushSubscription(id=1, endpoint=service.endpoint, p256dh=p256dh, auth=auth)
        message = PushMessage(
            "🔴 ¡ALERTA!", "Posible fuego", "https://a/?f=1", "field-1", "https://u"
        )
        assert sender(device, message) == outcome
    finally:
        service.close()
    headers, body = service.received[0]
    headers = {k.lower(): v for k, v in headers.items()}
    # Signed as the server (VAPID), kept for hours not days, and the text is encrypted.
    assert headers["authorization"].startswith("vapid ")
    assert headers["ttl"] == "10800" and headers["content-encoding"] == "aes128gcm"
    assert b"ALERTA" not in body and len(body) > 100
