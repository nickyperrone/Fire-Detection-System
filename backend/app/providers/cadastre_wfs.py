"""Parcels from a provincial cadastre's WFS (OGC WFS 2.0, GeoJSON output)."""

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
                "sortBy": "partida",
            },
            timeout=120,
        )
        response.raise_for_status()
        features = response.json().get("features", [])
        parcels += [_parcel(f) for f in features if f.get("geometry")]
        if len(features) < source["page_size"]:
            return parcels
        start += len(features)


def _parcel(feature: dict) -> Parcel:
    props = feature["properties"]
    return Parcel(
        department=int(props["departamento"]),
        partida=int(props["partida"]),
        plano=int(props["plano"]) if props.get("plano") is not None else None,
        status=props.get("estado"),
        geometry=feature["geometry"],
    )
