from collections.abc import Sequence

from geoalchemy2 import Geography, WKTElement
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.prepared import PreparedGeometry
from sqlalchemy import cast, delete, func, select
from sqlalchemy.orm import Session

from app.models import Tag, Territory, TerritoryKind, TerritoryTag


class TerritoryError(ValueError):
    """Invalid geometry, hierarchy or tag supplied by the user.

    `code` is stable and translated by the frontend; the message is for logs and the CLI.
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def parse_tag(label: str) -> tuple[str, str | None]:
    key, _, value = label.strip().partition(":")
    if not key:
        raise TerritoryError("empty_tag", f"empty tag: {label!r}")
    return key.strip(), (value.strip() or None)


def to_multipolygon(geometry: dict) -> MultiPolygon:
    try:
        geom = shape(geometry)
    except (KeyError, TypeError, ValueError) as exc:
        raise TerritoryError("invalid_geometry", f"invalid GeoJSON geometry: {exc}") from exc
    if isinstance(geom, Polygon):
        geom = MultiPolygon([geom])
    if not isinstance(geom, MultiPolygon):
        raise TerritoryError(
            "not_a_polygon", f"a territory must be a Polygon or MultiPolygon, got {geom.geom_type}"
        )
    if not geom.is_valid:
        raise TerritoryError(
            "invalid_polygon", "the polygon is not valid (self-intersecting or open ring)"
        )
    return geom


def create_territory(
    session: Session,
    *,
    owner: str,
    name: str,
    geometry: dict,
    parent_id: int | None = None,
    tags: Sequence[str] = (),
    attributes: dict | None = None,
    section_tolerance_m: float,
    allowed_area: PreparedGeometry,
) -> Territory:
    polygon = to_multipolygon(geometry)
    if not allowed_area.covers(polygon):
        raise TerritoryError("outside_country", "fields can only be drawn inside Argentina")
    geom = WKTElement(polygon.wkt, srid=4326)
    parent = None
    if parent_id is not None:
        parent = session.get(Territory, parent_id)
        if parent is None or parent.owner != owner:
            raise TerritoryError("parent_not_found", f"field {parent_id} does not exist")
        if parent.kind != TerritoryKind.FIELD:
            raise TerritoryError("parent_not_field", "sections can only be created inside a field")
        _check_inside(session, geom, parent, section_tolerance_m)

    territory = Territory(
        owner=owner,
        name=name,
        kind=TerritoryKind.SECTION if parent else TerritoryKind.FIELD,
        parent_id=parent_id,
        geom=geom,
        hectares=session.scalar(select(func.ST_Area(cast(geom, Geography)) / 10_000)),
        attributes=attributes or {},
    )
    session.add(territory)
    session.flush()
    set_tags(session, territory, tags)
    return territory


def _check_inside(
    session: Session, geom: WKTElement, parent: Territory, tolerance_m: float
) -> None:
    # Compared in SQL against the stored row: parent.geom may be WKB or WKT depending on
    # whether the parent was loaded or created in this session.
    covered = session.scalar(
        select(
            func.ST_CoveredBy(
                cast(geom, Geography),
                func.ST_Buffer(cast(Territory.geom, Geography), tolerance_m),
            )
        ).where(Territory.id == parent.id)
    )
    if not covered:
        raise TerritoryError("outside_parent", f"the section is not inside field {parent.name!r}")


def set_tags(session: Session, territory: Territory, labels: Sequence[str]) -> None:
    session.execute(delete(TerritoryTag).where(TerritoryTag.territory_id == territory.id))
    for label in dict.fromkeys(labels):
        tag = get_or_create_tag(session, territory.owner, label)
        session.add(TerritoryTag(territory_id=territory.id, tag_id=tag.id))
    session.flush()
    session.refresh(territory, ["tags"])


def get_or_create_tag(session: Session, owner: str, label: str) -> Tag:
    key, value = parse_tag(label)
    tag = session.scalar(
        select(Tag).where(
            Tag.owner == owner,
            Tag.key == key,
            Tag.value.is_(None) if value is None else Tag.value == value,
        )
    )
    if tag is None:
        tag = Tag(owner=owner, key=key, value=value)
        session.add(tag)
        session.flush()
    return tag


def list_territories(session: Session, owner: str, tags: Sequence[str] = ()) -> list[Territory]:
    """Territories that carry every tag in `tags`, fields before their sections."""
    query = select(Territory).where(Territory.owner == owner)
    for label in tags:
        key, value = parse_tag(label)
        tag_filter = select(TerritoryTag.territory_id).join(Tag).where(Tag.key == key)
        if value is not None:
            tag_filter = tag_filter.where(Tag.value == value)
        query = query.where(Territory.id.in_(tag_filter))
    query = query.order_by(
        func.coalesce(Territory.parent_id, Territory.id),
        Territory.parent_id.nulls_first(),
        Territory.name,
    )
    return list(session.scalars(query))


def load_feature_collection(
    session: Session,
    owner: str,
    collection: dict,
    section_tolerance_m: float,
    allowed_area: PreparedGeometry,
) -> list[Territory]:
    """Load fields, then sections (matched to their field by the `parent` name).

    Features whose name already exists for the same owner and parent are skipped, so loading
    the same file twice does nothing.
    """
    features = collection.get("features", [])
    fields = [f for f in features if not f["properties"].get("parent")]
    sections = [f for f in features if f["properties"].get("parent")]
    created: list[Territory] = []
    by_name: dict[str, Territory] = {
        t.name: t
        for t in session.scalars(
            select(Territory).where(Territory.owner == owner, Territory.parent_id.is_(None))
        )
    }
    for feature in fields + sections:
        props = feature["properties"]
        parent = by_name.get(props["parent"]) if props.get("parent") else None
        if props.get("parent") and parent is None:
            raise TerritoryError(
                "parent_not_found",
                f"section {props['name']!r} refers to unknown field {props['parent']!r}",
            )
        if _exists(session, owner, props["name"], parent):
            continue
        territory = create_territory(
            session,
            owner=owner,
            name=props["name"],
            geometry=feature["geometry"],
            parent_id=parent.id if parent else None,
            tags=props.get("tags", []),
            attributes={
                k: v for k, v in props.items() if k not in {"name", "kind", "parent", "tags"}
            },
            section_tolerance_m=section_tolerance_m,
            allowed_area=allowed_area,
        )
        if parent is None:
            by_name[territory.name] = territory
        created.append(territory)
    return created


def _exists(session: Session, owner: str, name: str, parent: Territory | None) -> bool:
    parent_filter = (
        Territory.parent_id.is_(None) if parent is None else Territory.parent_id == parent.id
    )
    return (
        session.scalar(
            select(Territory.id).where(
                Territory.owner == owner, Territory.name == name, parent_filter
            )
        )
        is not None
    )


def get_territory(session: Session, owner: str, territory_id: int) -> Territory | None:
    territory = session.get(Territory, territory_id)
    return territory if territory is not None and territory.owner == owner else None
