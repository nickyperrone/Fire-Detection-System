from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.boundaries import allowed_area
from app.config import Settings, get_thresholds
from app.models import Territory
from app.routers.dependencies import SessionDep, SettingsDep, TagsQuery
from app.schemas import RiskEventOut, SprayHourOut, TagsIn, TerritoryIn, TerritoryOut
from app.services.field_risk import assess_active_fire_events, compass
from app.services.fire_events import geojson, list_risk_events
from app.services.spray_conditions import list_spray_hours
from app.services.territories import create_territory, get_territory, list_territories, set_tags
from app.versioning import processing_version

router = APIRouter(prefix="/territories", tags=["territories"])


def territory_out(territory: Territory) -> TerritoryOut:
    return TerritoryOut(
        id=territory.id,
        name=territory.name,
        kind=territory.kind,
        parent_id=territory.parent_id,
        hectares=round(territory.hectares, 1),
        tags=sorted(tag.label for tag in territory.tags),
        geometry=geojson(territory.geom),
    )


def owned(session: Session, settings: Settings, territory_id: int) -> Territory:
    territory = get_territory(session, settings.owner, territory_id)
    if territory is None:
        raise HTTPException(404, "territory not found")
    return territory


@router.get("", response_model=list[TerritoryOut])
def list_(
    session: SessionDep,
    settings: SettingsDep,
    tag: TagsQuery = None,
):
    return [territory_out(t) for t in list_territories(session, settings.owner, tag or [])]


@router.post("", response_model=TerritoryOut, status_code=201)
def create(
    session: SessionDep,
    settings: SettingsDep,
    body: TerritoryIn,
):
    config = get_thresholds()["territories"]
    territory = create_territory(
        session,
        owner=settings.owner,
        name=body.name,
        geometry=body.geometry,
        parent_id=body.parent_id,
        tags=body.tags,
        section_tolerance_m=config["section_tolerance_m"],
        allowed_area=allowed_area(config["allowed_area"], config["allowed_area_tolerance_m"]),
    )
    session.commit()
    # A new field near a fire that is already active gets its answer now, not after the next ingest.
    thresholds = get_thresholds()
    assess_active_fire_events(
        session, thresholds["field_risk"], processing_version(thresholds), datetime.now(UTC)
    )
    return territory_out(territory)


@router.get("/{territory_id}", response_model=TerritoryOut)
def get(
    session: SessionDep,
    settings: SettingsDep,
    territory_id: int,
):
    return territory_out(owned(session, settings, territory_id))


@router.delete("/{territory_id}", status_code=204)
def delete(
    session: SessionDep,
    settings: SettingsDep,
    territory_id: int,
):
    session.delete(owned(session, settings, territory_id))
    session.commit()


@router.put("/{territory_id}/tags", response_model=TerritoryOut)
def replace_tags(
    session: SessionDep,
    settings: SettingsDep,
    territory_id: int,
    body: TagsIn,
):
    territory = owned(session, settings, territory_id)
    set_tags(session, territory, body.tags)
    session.commit()
    return territory_out(territory)


@router.get("/{territory_id}/risk-events", response_model=list[RiskEventOut])
def risk_events(
    session: SessionDep,
    settings: SettingsDep,
    territory_id: int,
):
    return [
        RiskEventOut(
            id=r.id,
            territory_id=r.territory_id,
            fire_event_id=r.fire_event_id,
            severity=r.severity,
            distance_m=round(r.distance_m, 1),
            direction=compass(r.bearing_deg),
            status=r.status,
            factors=r.factors,
            processing_version=r.processing_version,
            updated_at=r.updated_at,
        )
        for r in list_risk_events(session, settings.owner, territory_id)
    ]


@router.get("/{territory_id}/spray-conditions", response_model=list[SprayHourOut])
def spray_conditions(
    session: SessionDep,
    settings: SettingsDep,
    territory_id: int,
    profile: str = "default",
):
    owned(session, settings, territory_id)
    hours = list_spray_hours(session, territory_id, profile, datetime.now(UTC))
    return [SprayHourOut.model_validate(h, from_attributes=True) for h in hours]
