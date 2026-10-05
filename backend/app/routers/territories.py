from dataclasses import asdict
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.boundaries import allowed_area
from app.config import get_thresholds
from app.models import Territory
from app.routers.dependencies import HttpDep, OwnerDep, PhotoRootDep, SessionDep, TagsQuery
from app.schemas import (
    FireHistoryOut,
    OutlineIn,
    RiskEventOut,
    SettingsIn,
    SnapshotsOut,
    SprayHourOut,
    TagsIn,
    TerritoryIn,
    TerritoryOut,
)
from app.services.anomalies import field_anomaly_features
from app.services.field_risk import assess_active_fire_events, compass, reassess_territory
from app.services.fire_events import geojson, list_risk_events
from app.services.fire_history import field_history
from app.services.pipeline import answer_territories
from app.services.snapshots import View, field_snapshots, photo_path
from app.services.spray_conditions import list_spray_hours
from app.services.territories import (
    create_territory,
    edit_outline,
    get_territory,
    list_territories,
    set_tags,
)
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
        alerts=territory.alerts,
        visible=territory.visible,
        priority=territory.priority,
        geometry=geojson(territory.geom),
    )


def owned(session: Session, owner: str, territory_id: int) -> Territory:
    territory = get_territory(session, owner, territory_id)
    if territory is None:
        raise HTTPException(404, "territory not found")
    return territory


@router.get("", response_model=list[TerritoryOut])
def list_(
    session: SessionDep,
    owner: OwnerDep,
    tag: TagsQuery = None,
):
    return [territory_out(t) for t in list_territories(session, owner, tag or [])]


@router.post("", response_model=TerritoryOut, status_code=201)
def create(
    session: SessionDep,
    owner: OwnerDep,
    http: HttpDep,
    body: TerritoryIn,
):
    config = get_thresholds()["territories"]
    territory = create_territory(
        session,
        owner=owner,
        name=body.name,
        geometry=body.geometry,
        parent_id=body.parent_id,
        tags=body.tags,
        attributes={"cadastre": body.cadastre} if body.cadastre else None,
        section_tolerance_m=config["section_tolerance_m"],
        allowed_area=allowed_area(config["allowed_area"], config["allowed_area_tolerance_m"]),
    )
    session.commit()
    # A new field near a fire that is already active gets its answer now, not after the next ingest.
    thresholds = get_thresholds()
    assess_active_fire_events(
        session, thresholds["field_risk"], processing_version(thresholds), datetime.now(UTC)
    )
    answer_territories(session, http, thresholds, [territory.id])
    return territory_out(territory)


@router.get("/{territory_id}", response_model=TerritoryOut)
def get(
    session: SessionDep,
    owner: OwnerDep,
    territory_id: int,
):
    return territory_out(owned(session, owner, territory_id))


@router.delete("/{territory_id}", status_code=204)
def delete(
    session: SessionDep,
    owner: OwnerDep,
    territory_id: int,
):
    session.delete(owned(session, owner, territory_id))
    session.commit()


@router.patch("/{territory_id}/outline", response_model=TerritoryOut)
def change_outline(
    session: SessionDep,
    owner: OwnerDep,
    territory_id: int,
    http: HttpDep,
    body: OutlineIn,
):
    territory = owned(session, owner, territory_id)
    config = get_thresholds()["territories"]
    edit_outline(
        session,
        territory,
        operation=body.operation,
        piece=body.geometry,
        section_tolerance_m=config["section_tolerance_m"],
        allowed_area=allowed_area(config["allowed_area"], config["allowed_area_tolerance_m"]),
    )
    result = territory_out(territory)
    if body.preview:
        session.rollback()
        return result
    session.commit()
    thresholds = get_thresholds()
    reassess_territory(
        session,
        territory.id,
        thresholds["field_risk"],
        processing_version(thresholds),
        datetime.now(UTC),
    )
    # A reshaped field has another centroid and other cells within its radius.
    answer_territories(session, http, thresholds, [territory.id])
    return result


@router.patch("/{territory_id}/settings", response_model=TerritoryOut)
def change_settings(
    session: SessionDep,
    owner: OwnerDep,
    territory_id: int,
    body: SettingsIn,
):
    territory = owned(session, owner, territory_id)
    for name, value in body.model_dump(exclude_none=True).items():
        setattr(territory, name, value)
    session.commit()
    return territory_out(territory)


@router.put("/{territory_id}/tags", response_model=TerritoryOut)
def replace_tags(
    session: SessionDep,
    owner: OwnerDep,
    territory_id: int,
    body: TagsIn,
):
    territory = owned(session, owner, territory_id)
    set_tags(session, territory, body.tags)
    session.commit()
    return territory_out(territory)


@router.get("/{territory_id}/risk-events", response_model=list[RiskEventOut])
def risk_events(
    session: SessionDep,
    owner: OwnerDep,
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
        for r in list_risk_events(session, owner, territory_id)
    ]


@router.get("/{territory_id}/anomalies")
def anomalies(session: SessionDep, owner: OwnerDep, territory_id: int) -> dict:
    """The field's unusual patches as GeoJSON, to draw on the map (docs/11)."""
    owned(session, owner, territory_id)
    return field_anomaly_features(session, territory_id)


@router.get("/{territory_id}/snapshots", response_model=SnapshotsOut)
def snapshots(session: SessionDep, owner: OwnerDep, territory_id: int):
    """The field's satellite photos, or a lot's field's (docs/12-field-page.md)."""
    return field_snapshots(session, owned(session, owner, territory_id))


@router.get("/{territory_id}/snapshots/{day}/{view}.png", response_class=FileResponse)
def snapshot_image(
    session: SessionDep,
    owner: OwnerDep,
    root: PhotoRootDep,
    territory_id: int,
    day: date,
    view: View,
):
    owned(session, owner, territory_id)
    path = photo_path(root, territory_id, day, view)
    if not path.exists():
        raise HTTPException(404, "no photo of that field on that date")
    # A pass never changes once kept: the browser can keep it.
    return FileResponse(path, headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.get("/{territory_id}/fire-history", response_model=FireHistoryOut)
def fire_history(session: SessionDep, owner: OwnerDep, territory_id: int):
    owned(session, owner, territory_id)
    return asdict(field_history(session, territory_id, get_thresholds()["history"]))


@router.get("/{territory_id}/spray-conditions", response_model=list[SprayHourOut])
def spray_conditions(
    session: SessionDep,
    owner: OwnerDep,
    territory_id: int,
    profile: str = "default",
):
    owned(session, owner, territory_id)
    hours = list_spray_hours(session, territory_id, profile, datetime.now(UTC))
    return [SprayHourOut.model_validate(h, from_attributes=True) for h in hours]
