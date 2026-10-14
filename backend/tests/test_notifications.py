import io
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from PIL import Image
from shapely.geometry import box
from sqlalchemy import select

from app.config import Settings, get_settings
from app.models import (
    AlertDelivery,
    DataQuality,
    FieldRiskEvent,
    RiskStatus,
    SprayAssessment,
    SprayStatus,
    User,
)
from app.services.alerts import send_alerts
from app.services.telegram_bot import answer_updates, link_code
from app.services.territories import create_territory
from app.vision.area_map import AreaMap, render
from tests.conftest import ARGENTINA
from tests.test_alerts import EMAIL, FIELD, NOW, fire, rect

CHAT = 4242


class FakeTelegram:
    """Records what the bot would send, and hands out the updates a test queues."""

    token = "test"

    def __init__(self):
        self.sent: list[dict] = []
        self.queue: list[dict] = []
        self.answers: list[str] = []
        self.buttons: list[list[dict]] = []

    def send_photo(self, chat_id, photo, caption, buttons=None):
        self.sent.append({"chat": chat_id, "photo": photo, "text": caption, "buttons": buttons})

    def send_text(self, chat_id, text, buttons=None):
        self.sent.append({"chat": chat_id, "photo": None, "text": text, "buttons": buttons})

    def updates(self, offset):
        if offset is not None:
            self.queue = [u for u in self.queue if u["update_id"] >= offset]
            return []
        return list(self.queue)

    def answer_button(self, callback_id, text):
        self.answers.append(text)

    def set_buttons(self, chat_id, message_id, buttons):
        self.buttons.append(buttons)


@pytest.fixture
def field(session):
    session.add(User(email=EMAIL, locale="es"))
    field = create_territory(
        session,
        owner=EMAIL,
        name="La Esperanza",
        geometry=rect(*FIELD),
        section_tolerance_m=5,
        allowed_area=ARGENTINA,
    )
    session.commit()
    return field


@pytest.fixture
def bot():
    return FakeTelegram()


def linked(session, **notifications):
    user = session.scalar(select(User).where(User.email == EMAIL))
    user.telegram_chat_id = CHAT
    user.notifications = notifications or None
    session.commit()
    return user


def alert(session, thresholds, outbox, bot, app_url="https://fieldwatch.example"):
    return send_alerts(
        session,
        outbox.append,
        Settings(app_url=app_url),
        thresholds,
        "test",
        NOW,
        bot,
        lambda *_: b"png",
    )


def test_a_fire_goes_by_email_and_as_a_telegram_photo(session, thresholds, outbox, bot, field):
    linked(session)
    fire(session, thresholds, -59.07)
    result = alert(session, thresholds, outbox, bot)
    assert (result["emails_sent"], result["telegram_sent"]) == (1, 1)
    message = bot.sent[0]
    assert message["chat"] == CHAT and message["photo"] == b"png"
    assert message["text"].startswith(
        "🔴 <b>ALERTA!</b>\n<b>Posible fuego a 1,9 km al E de La Esperanza</b>"
    )
    assert [b["text"] for b in message["buttons"]] == ["Abrir en el mapa", "Ya lo vi"]
    assert message["buttons"][0]["url"] == f"https://fieldwatch.example/?f={field.id}"
    channels = session.scalars(select(AlertDelivery.channel)).all()
    assert sorted(channels) == ["email", "telegram"]


def test_a_local_app_url_is_left_out(session, thresholds, outbox, bot, field):
    linked(session)
    fire(session, thresholds, -59.07)
    alert(session, thresholds, outbox, bot, app_url="http://localhost:3000")
    message = bot.sent[0]
    assert "localhost" not in message["text"]
    assert [b["text"] for b in message["buttons"]] == ["Ya lo vi"]


def test_a_kind_turned_off_is_not_sent_but_is_marked(session, thresholds, outbox, bot, field):
    off = {"email": False, "telegram": False}
    linked(session, fire_medium=off, fire_high={"email": False, "telegram": True})
    fire(session, thresholds, -59.07)  # 1.9 km: Fuego alto, by Telegram only
    alert(session, thresholds, outbox, bot)
    assert outbox == [] and len(bot.sent) == 1

    # A medium fire (2 to 5 km) is off on both channels: nothing is sent, and it is not left
    # waiting to come back when the kind is turned on.
    fire(session, thresholds, -59.05)
    alert(session, thresholds, outbox, bot)
    assert len(bot.sent) == 1
    assert None not in session.scalars(select(FieldRiskEvent.notified_severity)).all()


def test_a_failed_telegram_send_is_retried_unless_email_carried_it(
    session, thresholds, outbox, bot, field
):
    linked(session, fire_high={"email": False, "telegram": True})

    def refuse(*_, **__):
        raise httpx.ConnectError("no network")

    bot.send_photo = refuse
    fire(session, thresholds, -59.07)
    assert alert(session, thresholds, outbox, bot)["telegram_failed"] == 1
    assert session.scalars(select(FieldRiskEvent.notified_severity)).all() == [None]


def adverse_hours(session, territory_id, gusts):
    for hour in range(24):
        at = NOW + timedelta(hours=hour)
        session.add(
            SprayAssessment(
                territory_id=territory_id,
                profile="default",
                valid_at=at,
                status=SprayStatus.UNFAVORABLE,
                rules=[],
                weather={
                    "time": at.isoformat(),
                    "wind_gusts_kmh": gusts if hour == 6 else 20,
                    "wind_speed_kmh": 18,
                    "wind_direction_deg": 90,
                    "precipitation_mm": 2.0,
                },
                data_quality=DataQuality.GOOD,
                forecast_fetched_at=NOW,
                processing_version="test",
            )
        )
    session.commit()


def test_adverse_weather_is_announced_once_per_episode(session, thresholds, outbox, bot, field):
    linked(session)
    adverse_hours(session, field.id, gusts=72)
    alert(session, thresholds, outbox, bot)
    assert bot.sent[0]["text"] == (
        "🔴 <b>ALERTA!</b>\n<b>Clima adverso en La Esperanza: ráfagas de 72 km/h el sáb 3 18:00</b>"
    )
    assert outbox[0]["Subject"] == "La Esperanza: clima adverso: ráfagas de 72 km/h el sáb 3 18:00"
    # No fire to mark as seen: only the link.
    assert [b["text"] for b in bot.sent[0]["buttons"]] == ["Abrir en el mapa"]

    # Still coming an hour later: the same episode, not announced again.
    later = NOW + timedelta(hours=1)
    send_alerts(session, outbox.append, Settings(), thresholds, "test", later, bot)
    assert len(bot.sent) == 1


def test_wind_and_rain_under_the_thresholds_are_not_announced(
    session, thresholds, outbox, bot, field
):
    linked(session)
    # 40 km/h gusts, and 2 mm an hour: 24 mm on each local day.
    adverse_hours(session, field.id, gusts=40)
    alert(session, thresholds, outbox, bot)
    assert bot.sent == [] and outbox == []


def test_the_bot_links_a_chat_with_a_code_once(session, bot, field):
    user = session.scalar(select(User).where(User.email == EMAIL))
    code = link_code(session, user, NOW)
    session.commit()
    start = {"chat": {"id": CHAT}, "from": {"language_code": "es"}, "text": f"/start {code}"}
    bot.queue = [{"update_id": 1, "message": start}]
    assert answer_updates(session, bot, NOW) == 1
    assert user.telegram_chat_id == CHAT and user.telegram_code_hash is None
    assert bot.sent[-1]["text"].startswith("Listo: las alertas de Field Watch")
    assert bot.queue == []

    # The code works once; another chat using it is told so.
    other = {"chat": {"id": 7}, "from": {}, "text": f"/start {code}"}
    bot.queue = [{"update_id": 2, "message": other}]
    answer_updates(session, bot, NOW)
    assert bot.sent[-1]["chat"] == 7 and "venció" in bot.sent[-1]["text"]

    bot.queue = [{"update_id": 3, "message": {"chat": {"id": CHAT}, "text": "/stop"}}]
    answer_updates(session, bot, NOW)
    assert user.telegram_chat_id is None


def test_ya_lo_vi_marks_the_fires_near_the_field_as_seen(session, thresholds, bot, field):
    linked(session)
    fire(session, thresholds, -59.07)
    url_button = {"text": "Abrir en el mapa", "url": "https://fieldwatch.example/"}
    tap = {
        "id": "q1",
        "data": f"seen:{field.id}",
        "message": {
            "message_id": 10,
            "chat": {"id": CHAT},
            "reply_markup": {"inline_keyboard": [[url_button, {"text": "Ya lo vi"}]]},
        },
    }
    bot.queue = [{"update_id": 1, "callback_query": tap}]
    answer_updates(session, bot, NOW)
    assert session.scalars(select(FieldRiskEvent.status)).all() == [RiskStatus.SEEN]
    assert bot.answers == ["Marcado como visto"]
    assert bot.buttons[0] == [url_button, {"text": "✓ Visto", "callback_data": "seen:"}]


def test_someone_elses_field_cannot_be_marked_seen(session, thresholds, bot, field):
    session.add(User(email="otro@example.com", locale="es", telegram_chat_id=99))
    session.commit()
    fire(session, thresholds, -59.07)
    tap = {"id": "q", "data": f"seen:{field.id}", "message": {"message_id": 1, "chat": {"id": 99}}}
    bot.queue = [{"update_id": 1, "callback_query": tap}]
    answer_updates(session, bot, NOW)
    assert session.scalars(select(FieldRiskEvent.status)).all() == [RiskStatus.NEW]


def test_the_area_picture_is_drawn_over_the_tiles(thresholds):
    tile = io.BytesIO()
    Image.new("RGB", (256, 256), (40, 90, 40)).save(tile, "PNG")
    tiles = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=tile.getvalue()))
    )
    area = AreaMap(
        field=box(-59.10, -33.00, -59.09, -32.99),
        fires=[(-59.07, -32.995)],
        distance=((-59.07, -32.995), (-59.09, -32.995), "1,9 km"),
        wind=(90, "viento 18 km/h"),
    )
    png = render(area, tiles, thresholds["alerts"]["area_map"], "{km} km")
    image = Image.open(io.BytesIO(png))
    assert image.size == (800, 600)
    # The fire is drawn red somewhere over the green tiles.
    assert any(r > 200 and g < 100 for r, g, _ in image.getdata())


def test_the_account_chooses_kinds_and_channels(anonymous, outbox):
    from tests.test_auth import sign_in

    sign_in(anonymous, outbox, "uno@example.com")
    me = anonymous.get("/auth/me").json()
    assert me["notifications"]["fire_far"] == {"email": False, "telegram": False}
    assert me["notifications"]["summary"] == {"email": True, "telegram": False}
    choices = me["notifications"] | {"weather": {"email": False, "telegram": True}}
    changed = anonymous.patch("/auth/me", json={"notifications": choices}).json()
    assert changed["notifications"]["weather"] == {"email": False, "telegram": True}
    assert changed["summary"] == "WEEKLY"


def test_connecting_telegram_needs_a_bot_on_the_server(anonymous, outbox):
    from app.main import app
    from tests.test_auth import sign_in

    app.dependency_overrides[get_settings] = lambda: Settings(telegram_bot_token="")
    sign_in(anonymous, outbox, "uno@example.com")
    assert anonymous.get("/auth/me").json()["telegram"] == {"available": False, "connected": False}
    assert anonymous.post("/auth/me/telegram").status_code == 503


def test_connecting_telegram_gives_a_link_with_a_code(anonymous, outbox, session):
    from app.main import app
    from app.routers.dependencies import http_client
    from tests.test_auth import sign_in

    app.dependency_overrides[get_settings] = lambda: Settings(telegram_bot_token="t")
    getme = {"ok": True, "result": {"username": "fieldwatch_bot"}}
    app.dependency_overrides[http_client] = lambda: httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=getme))
    )
    sign_in(anonymous, outbox, "uno@example.com")
    url = anonymous.post("/auth/me/telegram").json()["url"]
    assert url.startswith("https://t.me/fieldwatch_bot?start=")
    user = session.scalar(select(User).where(User.email == "uno@example.com"))
    assert user.telegram_code_expires_at > datetime.now(UTC)
