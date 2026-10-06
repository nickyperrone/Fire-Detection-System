"""Place search for the search box, with answers kept for a while: people type the same towns
and roads again and again, and Photon is a shared free service."""

import time
from collections import OrderedDict

import httpx

from app.providers.photon import Place, search_places

# Distinct searches kept; the oldest goes first.
CACHE_SIZE = 1000
_cache: OrderedDict[str, tuple[float, list[Place]]] = OrderedDict()


def find_places(client: httpx.Client, config: dict, query: str) -> list[Place]:
    key = " ".join(query.lower().split())
    if len(key) < config["min_letters"]:
        return []
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and now - cached[0] < config["cache_seconds"]:
        _cache.move_to_end(key)
        return cached[1]
    places = search_places(client, config, key)
    _cache[key] = (now, places)
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return places
