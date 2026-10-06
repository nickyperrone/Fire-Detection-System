"""Places by name from OpenStreetMap, through Photon (komoot), made for search as you type."""

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Place:
    name: str
    # Where it is, to tell apart places with the same name: "Gualeguaychú, Entre Ríos".
    context: str
    kind: str
    longitude: float
    latitude: float
    # west, south, east, north, for areas such as towns; None for a street or an address.
    bbox: tuple[float, float, float, float] | None


def _name(properties: dict) -> str:
    street = properties.get("street")
    if properties.get("housenumber") and street:
        return f"{street} {properties['housenumber']}"
    return properties.get("name") or street or ""


def _context(properties: dict, name: str) -> str:
    parts = [properties.get(k) for k in ("city", "county", "state")]
    seen = [name]
    out = []
    for part in parts:
        if part and part not in seen:
            out.append(part)
            seen.append(part)
    return ", ".join(out)


def search_places(client: httpx.Client, config: dict, query: str) -> list[Place]:
    response = client.get(
        config["url"],
        params={
            "q": query,
            "limit": config["limit"],
            "bbox": ",".join(str(v) for v in config["bbox"]),
        },
        headers={"User-Agent": "FieldWatch (github.com/nickyperrone/Fire-Detection-System)"},
        timeout=10,
    )
    response.raise_for_status()
    places = []
    for feature in response.json()["features"]:
        properties = feature["properties"]
        name = _name(properties)
        if not name:
            continue
        longitude, latitude = feature["geometry"]["coordinates"]
        # Photon gives an extent as west, north, east, south.
        extent = properties.get("extent")
        bbox = (extent[0], extent[3], extent[2], extent[1]) if extent else None
        places.append(
            Place(
                name=name,
                context=_context(properties, name),
                kind=properties.get("osm_value", ""),
                longitude=longitude,
                latitude=latitude,
                bbox=bbox,
            )
        )
    return places
