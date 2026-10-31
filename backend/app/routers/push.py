"""Push devices, and the one-tap "unsubscribe" of every alert (docs/13-notifications.md)."""

from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import delete, select

from app.models import PushSubscription
from app.routers.dependencies import SessionDep, SettingsDep, UserDep
from app.schemas import PushSubscribeIn, PushUnsubscribeIn
from app.services import unsubscribe

router = APIRouter(tags=["push"])

# A phone or two and a laptop: more than this is a script filling the table.
MAX_DEVICES = 10


@router.post("/push/subscribe", status_code=204)
def subscribe(session: SessionDep, user: UserDep, body: PushSubscribeIn):
    """This browser agrees to push alerts. The same device again only refreshes its keys; a device
    that was another account's moves to this one."""
    if user is None:
        raise HTTPException(401, "not signed in")
    found = session.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    if found is None:
        if len(user.push_subscriptions) >= MAX_DEVICES:
            raise HTTPException(409, "too many devices")
        found = PushSubscription(endpoint=body.endpoint)
        session.add(found)
    found.user_id = user.id
    found.p256dh, found.auth, found.label = body.p256dh, body.auth, body.label
    session.commit()
    return Response(status_code=204)


@router.post("/push/unsubscribe", status_code=204)
def forget(session: SessionDep, user: UserDep, body: PushUnsubscribeIn):
    """This browser no longer wants push alerts; only the account's own devices can be forgotten."""
    if user is None:
        raise HTTPException(401, "not signed in")
    session.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user.id
        )
    )
    session.commit()
    return Response(status_code=204)


PAGE = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="same-origin"><meta name="robots" content="noindex">
<title>Field Watch</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0e13;color:#e2e8f0;
font:16px/1.5 system-ui,-apple-system,sans-serif}}
main{{width:min(380px,calc(100vw - 32px));padding:28px;border-radius:24px;background:#11151c;
border:1px solid rgb(255 255 255/.08);text-align:center}}
img{{width:56px;height:56px;border-radius:14px}}
h1{{margin:16px 0 6px;font-size:21px;letter-spacing:-.01em}}
p{{margin:0 0 20px;color:#94a3b8;font-size:14px}}
button,a.b{{display:block;box-sizing:border-box;width:100%;height:48px;line-height:48px;border:0;
border-radius:16px;background:#22d3ee;color:#020617;font:600 16px/48px system-ui,sans-serif;
cursor:pointer;text-decoration:none}}
a.s{{display:block;margin-top:14px;color:#22d3ee;font-size:14px}}
</style></head>
<body><main>
<img src="/icon.svg" alt="">
<h1>{title}</h1><p>{body}</p>
{action}
</main></body></html>"""

TEXT = {
    "es": {
        "kinds": {
            "fire_high": "los avisos de fuego muy cerca",
            "fire_medium": "los avisos de fuego cerca",
            "fire_far": "los avisos de fuego lejano",
            "lightning": "los avisos de rayos",
            "weather": "los avisos de clima adverso",
            "summary": "el resumen",
            "alerts": "todos los avisos de peligro",
        },
        "channels": {"email": "por mail", "telegram": "por Telegram", "push": "como notificación"},
        "ask": "¿Dejar de recibir {what} {channel}?",
        "ask_body": "Cuenta de {email}. Lo podés reactivar cuando quieras en Notificaciones.",
        "button": "Sí, dejar de recibirlos",
        "done": "Listo, no te avisamos más",
        "done_body": "Dejaste de recibir {what} {channel}. Podés cambiarlo en Notificaciones.",
        "open": "Abrir Notificaciones",
        "bad": "Este link no sirve",
        "bad_body": "Puede estar incompleto. Entrá a Field Watch y elegí tus avisos.",
    },
    "en": {
        "kinds": {
            "fire_high": "very close fire alerts",
            "fire_medium": "close fire alerts",
            "fire_far": "distant fire alerts",
            "lightning": "lightning alerts",
            "weather": "adverse weather alerts",
            "summary": "the summary",
            "alerts": "all danger alerts",
        },
        "channels": {"email": "by email", "telegram": "by Telegram", "push": "as notifications"},
        "ask": "Stop receiving {what} {channel}?",
        "ask_body": "Account {email}. You can turn it back on any time in Notifications.",
        "button": "Yes, stop them",
        "done": "Done, we will not alert you",
        "done_body": "You stopped receiving {what} {channel}. You can change it in Notifications.",
        "open": "Open Notifications",
        "bad": "This link does not work",
        "bad_body": "It may be incomplete. Open Field Watch and choose your alerts.",
    },
}


def _page(lang: str, title: str, body: str, action: str) -> HTMLResponse:
    html = PAGE.format(lang=lang, title=escape(title), body=escape(body), action=action)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.get("/unsubscribe", response_class=HTMLResponse)
def confirm_unsubscribe(session: SessionDep, settings: SettingsDep, t: str = ""):
    """The link in an alert: a page with a button. Opening it changes nothing, so a mail scanner
    that opens every link does not unsubscribe anyone."""
    found = unsubscribe.read(session, t)
    if found is None:
        text = TEXT["es"]
        return _page("es", text["bad"], text["bad_body"], "")
    text = TEXT[found.user.locale if found.user.locale in TEXT else "es"]
    what, channel = text["kinds"][found.scope], text["channels"][found.channel]
    return _page(
        found.user.locale,
        text["ask"].format(what=what, channel=channel),
        text["ask_body"].format(email=found.user.email),
        f'<form method="post" action="unsubscribe?t={escape(t, quote=True)}">'
        f'<button type="submit">{escape(text["button"])}</button></form>',
    )


@router.post("/unsubscribe", response_class=HTMLResponse)
async def do_unsubscribe(request: Request, session: SessionDep, settings: SettingsDep, t: str = ""):
    """The page's button, a mail app's one-tap unsubscribe (RFC 8058, the token in the address)
    and the notification's own button: turns that kind off for that channel."""
    token = t
    if not token:
        body = (await request.body()).decode(errors="replace")
        token = next((v for k, _, v in (p.partition("=") for p in body.split("&")) if k == "t"), "")
    found = unsubscribe.read(session, token)
    if found is None:
        raise HTTPException(400, "not a valid unsubscribe link")
    unsubscribe.apply(session, found)
    text = TEXT[found.user.locale if found.user.locale in TEXT else "es"]
    what, channel = text["kinds"][found.scope], text["channels"][found.channel]
    return _page(
        found.user.locale,
        text["done"],
        text["done_body"].format(what=what, channel=channel),
        f'<a class="b" href="{escape(settings.app_url, quote=True)}/?view=notifications">'
        f"{escape(text['open'])}</a>",
    )
