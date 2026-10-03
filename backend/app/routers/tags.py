from fastapi import APIRouter

from app.routers.dependencies import OwnerDep, SessionDep
from app.schemas import TagColorIn, TagOut, TagsOut
from app.services.tags import PALETTE, list_tags, set_color

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=TagsOut)
def list_(session: SessionDep, owner: OwnerDep):
    tags = list_tags(session, owner)
    # Colors given to new tags are kept, so a tag never changes color between two reads.
    session.commit()
    return TagsOut(
        palette=list(PALETTE),
        tags=[TagOut(id=t.id, label=t.label, color=t.color) for t in tags],
    )


@router.patch("/{tag_id}", response_model=TagOut)
def change_color(session: SessionDep, owner: OwnerDep, tag_id: int, body: TagColorIn):
    tag = set_color(session, owner, tag_id, body.color)
    session.commit()
    return TagOut(id=tag.id, label=tag.label, color=tag.color)
