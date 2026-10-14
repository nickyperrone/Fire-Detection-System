from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import Settings, get_thresholds
from app.models import User
from app.providers.telegram import Telegram, TelegramError
from app.routers.dependencies import (
    SESSION_COOKIE,
    HttpDep,
    MailDep,
    SessionDep,
    SettingsDep,
    UserDep,
)
from app.schemas import LoginIn, MeIn, MeOut, TelegramLinkOut, TelegramOut
from app.services.auth import create_login_link, end_session, normalize_email, use_login_link
from app.services.email_text import login_email
from app.services.mail import SEND_ERRORS, message
from app.services.notification_prefs import preferences
from app.services.summary import send_summary
from app.services.telegram_bot import bot_username, link_code

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", status_code=202)
def login(session: SessionDep, settings: SettingsDep, send: MailDep, body: LoginIn):
    """Emails a sign-in link. The answer is the same for every address (docs/09)."""
    config = get_thresholds()["auth"]
    email = normalize_email(body.email)
    token = create_login_link(session, email, body.locale, config, datetime.now(UTC))
    session.commit()
    if token is not None:
        link = f"{settings.app_url}/api/auth/callback?token={token}"
        subject, text = login_email(body.locale, link, config["link_minutes"])
        try:
            send(message(settings, email, subject, text))
        except SEND_ERRORS as exc:
            raise HTTPException(503, "the sign-in email could not be sent") from exc
    return Response(status_code=202)


@router.get("/callback")
def callback(session: SessionDep, settings: SettingsDep, token: str):
    """The link in the email: signs in and goes back to the map."""
    config = get_thresholds()["auth"]
    session_token = use_login_link(session, token, config, datetime.now(UTC))
    session.commit()
    if session_token is None:
        return RedirectResponse(f"{settings.app_url}/?signin=expired", status_code=303)
    response = RedirectResponse(f"{settings.app_url}/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=config["session_days"] * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.app_url.startswith("https://"),
    )
    return response


def _signed_in(user: User | None) -> User:
    if user is None:
        raise HTTPException(401, "not signed in")
    return user


def _me(user: User, settings: Settings) -> MeOut:
    return MeOut(
        email=user.email,
        locale=user.locale,
        summary=user.summary,
        notifications=preferences(user),
        telegram=TelegramOut(
            available=bool(settings.telegram_bot_token),
            connected=user.telegram_chat_id is not None,
        ),
    )


@router.get("/me", response_model=MeOut)
def me(settings: SettingsDep, user: UserDep):
    return _me(_signed_in(user), settings)


@router.patch("/me", response_model=MeOut)
def change_me(session: SessionDep, settings: SettingsDep, user: UserDep, body: MeIn):
    user = _signed_in(user)
    if body.summary is not None:
        user.summary = body.summary
    if body.notifications is not None:
        user.notifications = body.notifications.model_dump()
    session.commit()
    return _me(user, settings)


@router.post("/me/telegram", response_model=TelegramLinkOut)
def connect_telegram(session: SessionDep, settings: SettingsDep, http: HttpDep, user: UserDep):
    """A link that opens the bot with a one-time code (docs/13-notifications.md#telegram)."""
    user = _signed_in(user)
    if not settings.telegram_bot_token:
        raise HTTPException(503, "Telegram is not set up on this server")
    try:
        name = bot_username(Telegram(http, settings.telegram_bot_token))
    except (TelegramError, httpx.HTTPError) as exc:
        raise HTTPException(503, "Telegram could not be reached") from exc
    code = link_code(session, user, datetime.now(UTC))
    session.commit()
    return TelegramLinkOut(url=f"https://t.me/{name}?start={code}")


@router.delete("/me/telegram", response_model=MeOut)
def disconnect_telegram(session: SessionDep, settings: SettingsDep, user: UserDep):
    user = _signed_in(user)
    user.telegram_chat_id = None
    session.commit()
    return _me(user, settings)


@router.post("/me/summary", status_code=202)
def summary_now(session: SessionDep, settings: SettingsDep, send: MailDep, user: UserDep):
    """Sends the account's summary at once (docs/09-accounts-and-alerts.md#summaries)."""
    user = _signed_in(user)
    try:
        sent = send_summary(session, send, settings, get_thresholds(), user, datetime.now(UTC))
    except SEND_ERRORS as exc:
        raise HTTPException(503, "the summary could not be sent") from exc
    if not sent:
        return JSONResponse(
            status_code=422, content={"detail": "the account has no fields", "code": "no_fields"}
        )
    return Response(status_code=202)


@router.post("/logout", status_code=204)
def logout(session: SessionDep, fw_session: Annotated[str | None, Cookie()] = None):
    if fw_session:
        end_session(session, fw_session)
        session.commit()
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE)
    return response
