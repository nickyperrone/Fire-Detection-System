"""Place search for the search box: towns from Georef and streets and addresses from Photon,
asked at once, with answers kept for a while: people type the same towns and roads again and
again, and both are shared free services (docs/04-frontend.md)."""

import logging
import time
import unicodedata
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.providers.georef import search_towns
from app.providers.photon import Place, search_places

log = logging.getLogger(__name__)
_pool = ThreadPoolExecutor(max_workers=8)

# Distinct searches kept; the oldest goes first.
CACHE_SIZE = 1000
_cache: OrderedDict[str, tuple[float, list[Place]]] = OrderedDict()


def find_places(
    client: httpx.Client, config: dict, query: str, source: str | None = None
) -> list[Place]:
    """`source`: "towns" (Georef, fast), "streets" (Photon, can be slow), or both. The page asks
    for the two apart, so towns show at once and streets join when they come."""
    text_ = " ".join(query.lower().split())
    if len(text_) < config["min_letters"]:
        return []
    key = f"{source or 'both'}:{text_}"
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and now - cached[0] < config["cache_seconds"]:
        _cache.move_to_end(key)
        return cached[1]
    if source == "towns":
        places = _unique(search_towns(client, config, text_))
    elif source == "streets":
        places = search_places(client, config, text_)
    else:
        places = _search_both(client, config, text_)
    _cache[key] = (now, places)
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return places


def _plain(name: str) -> str:
    """ "Gualeguaychú" and "gualeguaychu" are the same town."""
    folded = unicodedata.normalize("NFKD", name.lower())
    return "".join(c for c in folded if not unicodedata.combining(c))


def _search_both(client: httpx.Client, config: dict, query: str) -> list[Place]:
    """Towns first, then Photon's streets and addresses that are not those towns again. One
    source failing or late leaves the other; both failing is an error."""
    towns_job = _pool.submit(search_towns, client, config, query)
    photon_job = _pool.submit(search_places, client, config, query)
    answers = []
    for name, job in (("georef", towns_job), ("photon", photon_job)):
        try:
            answers.append(job.result())
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.info("place search through %s failed: %s", name, exc)
            answers.append(None)
    towns, others = answers
    if towns is None and others is None:
        raise httpx.HTTPError("no place source answered")
    towns, others = _unique(towns or []), others or []
    known = {_plain(t.name) for t in towns}
    rest = [p for p in others if not (p.kind in TOWN_KINDS and _plain(p.name) in known)]
    return (towns + rest)[: config["limit"] + 2]


# OpenStreetMap kinds that are the same thing as a Georef town.
TOWN_KINDS = {"city", "town", "village", "hamlet", "locality", "suburb", "administrative"}


def _unique(places: list[Place]) -> list[Place]:
    """Georef lists some towns twice under the same department; one is enough."""
    seen, out = set(), []
    for place in places:
        key = (_plain(place.name), place.context)
        if key not in seen:
            seen.add(key)
            out.append(place)
    return out
