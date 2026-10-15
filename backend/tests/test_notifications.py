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
        self.buttons: list[list[list[dict]]] = []
        self.edits: list[dict] = []
        self.actions: list[str] = []

    def send_photo(self, chat_id, photo, caption, buttons=None, silent=False):
        self.sent.append(
            {"chat": chat_id, "photo": photo, "text": caption, "buttons": buttons, "silent": silent}
        )

    def send_text(
        self, chat_id, text, buttons=None, silent=False, keyboard=None, remove_keyboard=False
    ):
        self.sent.append(
            {
                "chat": chat_id,
                "photo": None,
                "text": text,
                "buttons": buttons,
                "silent": silent,
                "keyboard": keyboard,
            }
        )

    def edit_text(self, chat_id, message_id, text, buttons):
        self.edits.append({"message": message_id, "text": text, "buttons": buttons})

    def chat_action(self, chat_id, action):
        self.actions.append(action)

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


def texts(buttons):
    return [[b["text"] for b in row] for row in buttons]


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
    assert texts(message["buttons"]) == [
        ["Abrir en el mapa", "📍 Cómo llegar"],
        ["Ya lo vi", "Ver el campo"],
    ]
    assert message["buttons"][0][0]["url"] == f"https://fieldwatch.example/?f={field.id}"
    assert message["buttons"][0][1]["url"].startswith(
        "https://www.google.com/maps/search/?api=1&query=-32.995,-59.07"
    )
    assert bot.actions == ["upload_photo"] and not message["silent"]
    channels = session.scalars(select(AlertDelivery.channel)).all()
    assert sorted(channels) == ["email", "telegram"]


def test_a_local_app_url_is_left_out(session, thresholds, outbox, bot, field):
    linked(session)
    fire(session, thresholds, -59.07)
    alert(session, thresholds, outbox, bot, app_url="http://localhost:3000")
    message = bot.sent[0]
    assert "localhost" not in message["text"]
    assert texts(message["buttons"]) == [["📍 Cómo llegar"], ["Ya lo vi", "Ver el campo"]]


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
    assert texts(bot.sent[0]["buttons"]) == [["Abrir en el mapa"], ["Ver el campo"]]

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
    assert bot.sent[-1]["text"].startswith("✅ <b>¡Listo, estás conectado!</b>")
    # The menu is buttons under the message, which every Telegram app shows.
    assert texts(bot.sent[-1]["buttons"]) == [["📋 Mis campos", "🔔 Mis alertas"], ["ℹ️ Saber más"]]
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
    field_button = {"text": "Ver el campo", "callback_data": f"f:{field.id}"}
    tap = {
        "id": "q1",
        "data": f"seen:{field.id}",
        "message": {
            "message_id": 10,
            "chat": {"id": CHAT},
            "reply_markup": {
                "inline_keyboard": [
                    [url_button],
                    [{"text": "Ya lo vi", "callback_data": f"seen:{field.id}"}, field_button],
                ]
            },
        },
    }
    bot.queue = [{"update_id": 1, "callback_query": tap}]
    answer_updates(session, bot, NOW)
    assert session.scalars(select(FieldRiskEvent.status)).all() == [RiskStatus.SEEN]
    assert bot.answers == ["Marcado como visto"]
    assert bot.buttons[0] == [
        [url_button],
        [{"text": "✓ Visto", "callback_data": "seen:"}, field_button],
    ]


def test_someone_elses_field_cannot_be_marked_seen(session, thresholds, bot, field):
    session.add(User(email="otro@example.com", locale="es", telegram_chat_id=99))
    session.commit()
    fire(session, thresholds, -59.07)
    tap = {"id": "q", "data": f"seen:{field.id}", "message": {"message_id": 1, "chat": {"id": 99}}}
    bot.queue = [{"update_id": 1, "callback_query": tap}]
    answer_updates(session, bot, NOW)
    assert session.scalars(select(FieldRiskEvent.status)).all() == [RiskStatus.NEW]


def tap(data, message_id=20, photo=False):
    message = {"message_id": message_id, "chat": {"id": CHAT}}
    if photo:
        message["photo"] = [{}]
    return {
        "update_id": message_id,
        "callback_query": {"id": "q", "data": data, "message": message},
    }


def say(text, update_id=30):
    return {"update_id": update_id, "message": {"chat": {"id": CHAT}, "text": text}}


def test_mis_campos_lists_each_field_and_opens_one_in_place(session, thresholds, bot, field):
    linked(session)
    fire(session, thresholds, -59.07)
    adverse_hours(session, field.id, gusts=40)
    bot.queue = [say("/campos")]
    answer_updates(session, bot, NOW)
    listing = bot.sent[-1]
    assert listing["text"].startswith("📋 <b>Tus campos</b>\n\n🌾 <b>La Esperanza</b> · ")
    assert "🔥 Fuego a <b>1,9 km</b> al E" in listing["text"]
    assert "⛔ No conviene pulverizar" in listing["text"]
    assert texts(listing["buttons"]) == [["🔎 La Esperanza"], ["‹ Menú"]]

    # The field opens in the same message: short, with "Saber más" and the way back.
    bot.queue = [tap(f"f:{field.id}")]
    answer_updates(session, bot, NOW)
    detail = bot.edits[-1]
    assert detail["message"] == 20
    assert detail["text"].startswith("🌾 <b>La Esperanza</b> · ")
    assert "🕐" in detail["text"]
    assert texts(detail["buttons"]) == [["ℹ️ Saber más"], ["‹ Mis campos"]]

    bot.queue = [tap("fields")]
    answer_updates(session, bot, NOW)
    assert bot.edits[-1]["text"] == listing["text"]


def test_spraying_says_why_and_saber_mas_tells_the_rest(session, bot, field):
    linked(session)
    session.add(
        SprayAssessment(
            territory_id=field.id,
            profile="default",
            valid_at=NOW,
            status=SprayStatus.CAUTION,
            rules=[
                {"rule": "delta_t", "status": "CAUTION", "value": 1.6, "unit": "°C", "limit": 2},
                {"rule": "wind", "status": "PASS", "value": 9, "unit": "km/h", "limit": None},
            ],
            weather={
                "temperature_c": 15.2,
                "wind_speed_kmh": 9,
                "wind_direction_deg": 135,
                "wind_gusts_kmh": 17,
                "precipitation_mm": 0.0,
            },
            data_quality=DataQuality.GOOD,
            forecast_fetched_at=NOW,
            processing_version="test",
        )
    )
    session.commit()
    bot.queue = [tap(f"f:{field.id}")]
    answer_updates(session, bot, NOW)
    assert "🟡 Pulverizar con cuidado\n     💧 Aire muy húmedo" in bot.edits[-1]["text"]

    bot.queue = [tap(f"i:{field.id}")]
    answer_updates(session, bot, NOW)
    more = bot.edits[-1]
    assert more["text"].startswith("ℹ️ <b>La Esperanza</b>, en detalle")
    assert "💧 Aire muy húmedo: las gotas quedan flotando (Delta T 1,6 °C)" in more["text"]
    assert "🌡 15 °C · viento del SE a 9 km/h · ráfagas de 17 km/h" in more["text"]
    assert "Ninguno a menos de 10 km" in more["text"]
    assert texts(more["buttons"]) == [["‹ Volver"]]


def test_ver_el_campo_under_an_alert_answers_with_a_new_message(session, thresholds, bot, field):
    linked(session)
    bot.queue = [tap(f"f:{field.id}", photo=True)]
    answer_updates(session, bot, NOW)
    assert bot.edits == [] and bot.sent[-1]["text"].startswith("🌾 <b>La Esperanza</b>")


def test_mis_alertas_turns_kinds_on_and_off_from_the_chat(session, bot, field):
    user = linked(session)
    bot.queue = [say("/alertas")]
    answer_updates(session, bot, NOW)
    assert texts(bot.sent[-1]["buttons"])[2] == ["▫️  🔥 Fuego lejano"]
    bot.queue = [tap("t:fire_far")]
    answer_updates(session, bot, NOW)
    assert bot.answers[-1] == "✅ Prendida"
    assert texts(bot.edits[-1]["buttons"])[2] == ["✅  🔥 Fuego lejano"]
    assert user.notifications["fire_far"] == {"email": False, "telegram": True}
    # "Saber más" explains each kind, with the way back.
    bot.queue = [tap("i:alerts")]
    answer_updates(session, bot, NOW)
    assert "🔥 <b>Fuego lejano</b>: de 5 a 10 km" in bot.edits[-1]["text"]
    assert texts(bot.edits[-1]["buttons"]) == [["‹ Mis alertas"]]


def test_anything_else_typed_gets_the_menu(session, bot, field):
    linked(session)
    bot.queue = [say("hola")]
    answer_updates(session, bot, NOW)
    menu = bot.sent[-1]
    assert menu["text"].startswith("👋 <b>Field Watch</b>")
    assert texts(menu["buttons"]) == [["📋 Mis campos", "🔔 Mis alertas"], ["ℹ️ Saber más"]]
    bot.queue = [tap("i:menu")]
    answer_updates(session, bot, NOW)
    assert bot.edits[-1]["text"].startswith("ℹ️ <b>Cómo funciona</b>")
    # From any view, "‹ Menú" brings the menu back in the same message.
    bot.queue = [tap("menu")]
    answer_updates(session, bot, NOW)
    assert bot.edits[-1]["text"] == menu["text"]


def test_a_blocked_bot_disconnects_the_account(session, thresholds, outbox, bot, field):
    from app.providers.telegram import TelegramBlocked

    user = linked(session)

    def blocked(*_, **__):
        raise TelegramBlocked("Forbidden: bot was blocked by the user")

    bot.send_photo = blocked
    fire(session, thresholds, -59.07)
    alert(session, thresholds, outbox, bot)
    assert user.telegram_chat_id is None
    # Email carried it, so it is not retried.
    assert session.scalars(select(FieldRiskEvent.notified_severity)).all() != [None]


def test_distant_fires_alone_arrive_silently(session, thresholds, outbox, bot, field):
    linked(session, fire_far={"email": False, "telegram": True})
    fire(session, thresholds, -58.99)  # about 9.3 km: Fuego lejano
    alert(session, thresholds, outbox, bot)
    assert bot.sent[0]["silent"]


def test_telegram_asks_to_slow_down_and_the_message_waits(monkeypatch):
    from app.providers import telegram as provider

    answers = [
        httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 1}}),
        httpx.Response(200, json={"ok": True, "result": {"message_id": 1}}),
    ]
    waits = []
    monkeypatch.setattr(provider.time, "sleep", waits.append)
    client = httpx.Client(transport=httpx.MockTransport(lambda _: answers.pop(0)))
    assert provider.Telegram(client, "t").send_text(1, "hola") == {"message_id": 1}
    assert waits == [1]


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
