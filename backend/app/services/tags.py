"""Tag colors (docs/01-product.md#tags-and-colors)."""

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tag
from app.services.territories import TerritoryError

# No red and no green: those mean danger and all clear everywhere in the app.
PALETTE = (
    "#3b82f6",  # blue
    "#a855f7",  # purple
    "#f59e0b",  # amber
    "#ec4899",  # pink
    "#6366f1",  # indigo
    "#f97316",  # orange
    "#e879f9",  # light fuchsia
    "#eab308",  # yellow
)


def list_tags(session: Session, owner: str) -> list[Tag]:
    """The owner's tags, plain labels first, each with a color; new tags get the least used."""
    tags = list(session.scalars(select(Tag).where(Tag.owner == owner).order_by(Tag.id)))
    used = Counter(t.color for t in tags if t.color)
    for tag in tags:
        if tag.color is None:
            tag.color = min(PALETTE, key=lambda c: (used[c], PALETTE.index(c)))
            used[tag.color] += 1
    session.flush()
    return sorted(tags, key=lambda t: (t.value is not None, t.label.casefold()))


def set_color(session: Session, owner: str, tag_id: int, color: str) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None or tag.owner != owner:
        raise TerritoryError("tag_not_found", f"tag {tag_id} does not exist")
    if color not in PALETTE:
        raise TerritoryError("unknown_color", f"{color} is not in the tag palette")
    tag.color = color
    session.flush()
    return tag
