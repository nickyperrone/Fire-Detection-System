"""Signing in with a link by email, and sessions (docs/09-accounts-and-alerts.md)."""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import LoginLink, User, UserSession


def _hash(token: str) -> str:
    # Only hashes are stored: a copy of the database cannot be used to sign in.
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_login_link(
    session: Session, email: str, locale: str, config: dict, now: datetime
) -> str | None:
    """A new one-time token for `email`, or None when it already got the hourly maximum."""
    recent = session.scalar(
        select(func.count())
        .select_from(LoginLink)
        .where(LoginLink.email == email, LoginLink.created_at > now - timedelta(hours=1))
    )
    if recent >= config["login_links_per_hour"]:
        return None
    token = secrets.token_urlsafe(32)
    session.add(
        LoginLink(
            email=email,
            locale=locale,
            token_hash=_hash(token),
            created_at=now,
            expires_at=now + timedelta(minutes=config["link_minutes"]),
        )
    )
    session.flush()
    return token


def use_login_link(session: Session, token: str, config: dict, now: datetime) -> str | None:
    """Uses up a link and returns a new session token, creating the account on its first
    sign-in. None when the link is unknown, used or expired."""
    link = session.scalar(
        select(LoginLink).where(LoginLink.token_hash == _hash(token)).with_for_update()
    )
    if link is None or link.used_at is not None or link.expires_at <= now:
        return None
    link.used_at = now
    user = session.scalar(select(User).where(User.email == link.email))
    if user is None:
        user = User(email=link.email, locale=link.locale)
        session.add(user)
    user.locale = link.locale
    user.last_login_at = now
    session.flush()
    session_token = secrets.token_urlsafe(32)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=_hash(session_token),
            created_at=now,
            expires_at=now + timedelta(days=config["session_days"]),
        )
    )
    session.flush()
    return session_token


def user_for_session(session: Session, token: str, now: datetime) -> User | None:
    found = session.scalar(
        select(UserSession).where(
            UserSession.token_hash == _hash(token), UserSession.expires_at > now
        )
    )
    return found.user if found else None


def end_session(session: Session, token: str) -> None:
    session.execute(delete(UserSession).where(UserSession.token_hash == _hash(token)))
