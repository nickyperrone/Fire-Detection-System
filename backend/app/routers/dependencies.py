from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Cookie, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models import User
from app.services.auth import user_for_session
from app.services.mail import SendEmail, smtp_sender
from app.services.snapshots import PHOTO_ROOT

SESSION_COOKIE = "fw_session"

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
TagsQuery = Annotated[list[str] | None, Query(description="key:value; every tag must match")]


def current_user(
    session: SessionDep, fw_session: Annotated[str | None, Cookie()] = None
) -> User | None:
    return user_for_session(session, fw_session, datetime.now(UTC)) if fw_session else None


def require_owner(user: Annotated[User | None, Depends(current_user)]) -> str:
    """The signed-in user's address, which owns their fields and tags."""
    if user is None:
        raise HTTPException(401, "sign in to see and change fields")
    return user.email


def mail_sender(settings: SettingsDep) -> SendEmail:
    return smtp_sender(settings)


def http_client() -> Iterator[httpx.Client]:
    """For requests to outside services; tests replace it with one that answers locally."""
    with httpx.Client() as client:
        yield client


def photo_root() -> Path:
    """Where field photos are kept (docs/12-field-page.md); tests use a temporary folder."""
    return PHOTO_ROOT


HttpDep = Annotated[httpx.Client, Depends(http_client)]
UserDep = Annotated[User | None, Depends(current_user)]
OwnerDep = Annotated[str, Depends(require_owner)]
MailDep = Annotated[SendEmail, Depends(mail_sender)]
PhotoRootDep = Annotated[Path, Depends(photo_root)]
