"""Parcels from a provincial cadastre's WFS (OGC WFS 2.0, GeoJSON output)."""

from collections.abc import Callable
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Parcel:
    department: int
    partida: int
    plano: int | None
    status: str | None
    geometry: dict  # GeoJSON MultiPolygon or Polygon, EPSG:4326


def fetch_parcels(client: httpx.Client, source: dict, bbox: list[float]) -> list[Parcel]:
    """Every parcel that touches `bbox` (west, south, east, north), page by page."""
    west, south, east, north = bbox
    parcels: list[Parcel] = []
    start = 0
    while True:
        response = client.get(
            source["wfs_url"],
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": source["layer"],
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                # WFS 2.0 with an EPSG URN takes latitude first.
                "bbox": f"{south},{west},{north},{east},urn:ogc:def:crs:EPSG::4326",
                "count": source["page_size"],
                "startIndex": start,
                # Stable paging needs a sort order.
                "sortBy": source["sort_by"],
            },
            timeout=120,
        )
        response.raise_for_status()
        features = response.json().get("features", [])
        read = READERS[source["format"]]
        parcels += [p for f in features if f.get("geometry") and (p := read(f)) is not None]
        if len(features) < source["page_size"]:
            return parcels
        start += len(features)


def _ater(feature: dict) -> Parcel | None:
    """Entre Ríos: department, tax account (partida) and survey plan in their own fields."""
    props = feature["properties"]
    return Parcel(
        department=int(props["departamento"]),
        partida=int(props["partida"]),
        plano=int(props["plano"]) if props.get("plano") is not None else None,
        status=props.get("estado"),
        geometry=feature["geometry"],
    )


def _arba(feature: dict) -> Parcel | None:
    """Buenos Aires: `pda` is the district (partido, 3 digits) followed by the tax account."""
    props = feature["properties"]
    pda = props.get("pda")
    if not pda or len(pda) < 4 or not pda.isdigit():
        return None
    return Parcel(
        department=int(pda[:3]),
        partida=int(pda[3:]),
        plano=None,
        status=props.get("tpa"),
        geometry=feature["geometry"],
    )


def _idecor(feature: dict) -> Parcel | None:
    """Córdoba: the department is the first two digits of the cadastral designation."""
    props = feature["properties"]
    account, designation = props.get("Nro_Cuenta"), props.get("Nomenclatura")
    if account is None or not designation:
        return None
    return Parcel(
        department=int(designation[:2]),
        partida=int(account),
        plano=None,
        status=props.get("Estado"),
        geometry=feature["geometry"],
    )


# Each province names its fields differently; parcels without a tax account are skipped.
READERS: dict[str, Callable[[dict], Parcel | None]] = {
    "ater": _ater,
    "arba": _arba,
    "idecor": _idecor,
}
