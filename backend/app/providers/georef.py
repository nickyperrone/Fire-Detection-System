"""Towns from Georef, the Argentine government's official place API (datos.gob.ar): fast and
free, for the search box (docs/04-frontend.md)."""

import httpx

from app.providers.photon import Place


def search_towns(client: httpx.Client, config: dict, query: str) -> list[Place]:
    response = client.get(
        config["georef_url"],
        params={
            "nombre": query,
            "max": config["limit"],
            "campos": "nombre,departamento.nombre,provincia.nombre,centroide",
        },
        timeout=config["georef_timeout_s"],
    )
    response.raise_for_status()
    half = config["town_half_degrees"]
    towns = []
    for town in response.json().get("localidades", []):
        lon, lat = town["centroide"]["lon"], town["centroide"]["lat"]
        where = [(town.get(part) or {}).get("nombre") for part in ("departamento", "provincia")]
        towns.append(
            Place(
                name=town["nombre"],
                context=", ".join(w for w in where if w),
                kind="town",
                longitude=lon,
                latitude=lat,
                bbox=(lon - half, lat - half, lon + half, lat + half),
            )
        )
    return towns
