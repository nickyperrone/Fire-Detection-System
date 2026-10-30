"""Closing an account: everything that belongs to it goes
(docs/09-accounts-and-alerts.md#closing-an-account)."""

import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import LoginLink, Tag, Territory, User


@dataclass(frozen=True)
class AccountContents:
    """What closing an account would remove, to say it before doing it."""

    email: str
    fields: int
    lots: int
    telegram: bool


def contents(session: Session, user: User) -> AccountContents:
    rows = session.execute(
        select(Territory.parent_id.is_(None), func.count())
        .where(Territory.owner == user.email)
        .group_by(Territory.parent_id.is_(None))
    ).all()
    counts = {is_field: n for is_field, n in rows}
    return AccountContents(
        email=user.email,
        fields=counts.get(True, 0),
        lots=counts.get(False, 0),
        telegram=user.telegram_chat_id is not None,
    )


def find_users(session: Session, like: str = "") -> list[User]:
    """The accounts whose email contains some text, oldest first."""
    pattern = f"%{like.lower()}%"
    return list(
        session.scalars(select(User).where(User.email.like(pattern)).order_by(User.created_at))
    )


def delete_account(session: Session, user: User, photo_root: Path | None = None) -> None:
    """The account, its fields and lots with everything derived from them (the database cascades:
    risk events, spray assessments, forecasts, photos' rows, land cover), its tags, sign-in links,
    sessions, alert log and push devices, and the photos kept as files. The Telegram link goes with
    the account row; the chat itself is the user's."""
    email = user.email
    ids = list(session.scalars(select(Territory.id).where(Territory.owner == email)))
    session.execute(delete(Territory).where(Territory.owner == email))
    session.execute(delete(Tag).where(Tag.owner == email))
    session.execute(delete(LoginLink).where(LoginLink.email == email))
    session.execute(delete(User).where(User.id == user.id))
    session.commit()
    if photo_root is not None:
        for territory_id in ids:
            shutil.rmtree(photo_root / str(territory_id), ignore_errors=True)
