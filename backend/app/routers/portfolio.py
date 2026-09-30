from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter

from app.config import get_thresholds
from app.routers.dependencies import SessionDep, SettingsDep, TagsQuery
from app.schemas import PortfolioEntryOut
from app.services.portfolio import build_portfolio

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio", response_model=list[PortfolioEntryOut])
def portfolio(
    session: SessionDep,
    settings: SettingsDep,
    tag: TagsQuery = None,
    profile: str = "default",
):
    entries = build_portfolio(
        session, settings.owner, get_thresholds(), datetime.now(UTC), tag or [], profile
    )
    return [
        PortfolioEntryOut(
            territory_id=e.territory.id,
            name=e.territory.name,
            kind=e.territory.kind,
            parent_id=e.territory.parent_id,
            hectares=round(e.territory.hectares, 1),
            tags=sorted(tag.label for tag in e.territory.tags),
            fire=asdict(e.fire),
            spray=asdict(e.spray),
            lightning=asdict(e.lightning),
            anomaly=asdict(e.anomaly),
        )
        for e in entries
    ]
