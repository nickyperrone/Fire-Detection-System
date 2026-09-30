"""Mapbox Vector Tiles built in PostGIS (docs/04-frontend.md#progressive-map-loading)."""

from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.orm import Session

# Display settings, not analysis thresholds: they do not change any stored result, so they stay
# out of config/thresholds.yaml and out of processing_version.
EXTENT = 4096
BUFFER = 64
CLUSTER_BELOW_ZOOM = 9
CLUSTER_CELLS_PER_TILE = 8
OBSERVATIONS_FROM_ZOOM = 11
WEB_MERCATOR_WIDTH_M = 40_075_016.686


class Layer(StrEnum):
    TERRITORIES = "territories"
    FIRE_EVENTS = "fire_events"
    OBSERVATIONS = "observations"
    LIGHTNING = "lightning"


def tile_width_m(z: int) -> float:
    return WEB_MERCATOR_WIDTH_M / 2**z


# Polygons are clipped per tile, so labels come as a separate point layer with one point per
# territory; otherwise a field split by a tile edge gets one label per piece. Points near an edge
# go into both tiles (within the buffer) and MapLibre keeps a single copy.
TERRITORIES_SQL = text("""
    WITH bounds AS (SELECT ST_TileEnvelope(:z, :x, :y) AS env),
    shapes AS (
        SELECT t.id, t.name, t.kind, t.parent_id,
               ST_AsMVTGeom(
                   ST_SimplifyPreserveTopology(ST_Transform(t.geom, 3857), :tolerance_m),
                   bounds.env, :extent, :buffer, true
               ) AS geom
        FROM territory t, bounds
        WHERE t.owner = :owner AND ST_Intersects(t.geom, ST_Transform(bounds.env, 4326))
    ),
    labels AS (
        SELECT t.id, t.name, t.kind,
               ST_AsMVTGeom(
                   ST_Transform(ST_PointOnSurface(t.geom), 3857), bounds.env, :extent, :buffer
               ) AS geom
        FROM territory t, bounds
        WHERE t.owner = :owner
          AND ST_Intersects(
              ST_Transform(ST_PointOnSurface(t.geom), 3857), ST_Expand(bounds.env, :buffer_m)
          )
    )
    SELECT (SELECT ST_AsMVT(shapes, 'territories', :extent, 'geom', 'id')
            FROM shapes WHERE geom IS NOT NULL)
        || (SELECT ST_AsMVT(labels, 'territory_labels', :extent, 'geom', 'id')
            FROM labels WHERE geom IS NOT NULL)
""")

FIRE_EVENTS_SQL = text("""
    WITH bounds AS (SELECT ST_TileEnvelope(:z, :x, :y) AS env)
    SELECT ST_AsMVT(mvt, 'fire_events', :extent, 'geom', 'id') FROM (
        SELECT fe.id, fe.confidence, fe.observation_count, fe.max_frp_mw,
               array_to_string(fe.sensors, ', ') AS sensors,
               EXTRACT(EPOCH FROM fe.last_detected_at)::bigint AS last_detected_at,
               ST_AsMVTGeom(ST_Transform(fe.geom, 3857), bounds.env, :extent, :buffer, true) AS geom
        FROM fire_event fe, bounds
        WHERE fe.status = 'ACTIVE' AND ST_Intersects(fe.geom, ST_Transform(bounds.env, 4326))
    ) AS mvt
    WHERE geom IS NOT NULL
""")

# At low zoom, events in the same grid cell become one point with a count, like map clusters.
FIRE_CLUSTERS_SQL = text("""
    WITH bounds AS (SELECT ST_TileEnvelope(:z, :x, :y) AS env),
    events AS (
        SELECT fe.*, ST_Transform(ST_Centroid(fe.geom), 3857) AS center
        FROM fire_event fe, bounds
        WHERE fe.status = 'ACTIVE' AND ST_Intersects(fe.geom, ST_Transform(bounds.env, 4326))
    )
    SELECT ST_AsMVT(mvt, 'fire_events', :extent, 'geom') FROM (
        SELECT count(*) AS event_count,
               sum(observation_count) AS observation_count,
               bool_or(confidence = 'high') AS any_high_confidence,
               EXTRACT(EPOCH FROM max(last_detected_at))::bigint AS last_detected_at,
               ST_AsMVTGeom(ST_Centroid(ST_Collect(center)), bounds.env, :extent, :buffer, true)
                   AS geom
        FROM events, bounds
        GROUP BY ST_SnapToGrid(center, :cell_m), bounds.env
    ) AS mvt
    WHERE geom IS NOT NULL
""")

OBSERVATIONS_SQL = text("""
    WITH bounds AS (SELECT ST_TileEnvelope(:z, :x, :y) AS env)
    SELECT ST_AsMVT(mvt, 'observations', :extent, 'geom', 'id') FROM (
        SELECT o.id, o.sensor, o.satellite, o.confidence, o.frp_mw, l.fire_event_id,
               EXTRACT(EPOCH FROM o.acquired_at)::bigint AS acquired_at,
               ST_AsMVTGeom(ST_Transform(o.geom, 3857), bounds.env, :extent, :buffer, true) AS geom
        FROM observation o
        JOIN observation_event_link l ON l.observation_id = o.id
        JOIN fire_event fe ON fe.id = l.fire_event_id AND fe.status = 'ACTIVE',
        bounds
        WHERE ST_Intersects(o.geom, ST_Transform(bounds.env, 4326))
    ) AS mvt
    WHERE geom IS NOT NULL
""")


LIGHTNING_SQL = text("""
    WITH bounds AS (SELECT ST_TileEnvelope(:z, :x, :y) AS env)
    SELECT ST_AsMVT(mvt, 'lightning', :extent, 'geom') FROM (
        SELECT round(EXTRACT(EPOCH FROM (:now - f.observed_at)) / 60)::int AS age_minutes,
               ST_AsMVTGeom(ST_Transform(f.geom, 3857), bounds.env, :extent, :buffer, true) AS geom
        FROM lightning_flash f, bounds
        WHERE f.observed_at >= :since AND ST_Intersects(f.geom, ST_Transform(bounds.env, 4326))
    ) AS mvt
    WHERE geom IS NOT NULL
""")


def build_tile(
    session: Session,
    layer: Layer,
    z: int,
    x: int,
    y: int,
    owner: str,
    now: datetime,
    lightning_window_minutes: int = 60,
) -> bytes:
    params = {"z": z, "x": x, "y": y, "extent": EXTENT, "buffer": BUFFER}
    if layer == Layer.TERRITORIES:
        # About one screen pixel on a 512 px tile: invisible, but zoomed-out tiles get much smaller.
        statement = TERRITORIES_SQL
        params |= {
            "owner": owner,
            "tolerance_m": tile_width_m(z) / 512,
            "buffer_m": tile_width_m(z) * BUFFER / EXTENT,
        }
    elif layer == Layer.FIRE_EVENTS and z < CLUSTER_BELOW_ZOOM:
        statement = FIRE_CLUSTERS_SQL
        params["cell_m"] = tile_width_m(z) / CLUSTER_CELLS_PER_TILE
    elif layer == Layer.FIRE_EVENTS:
        statement = FIRE_EVENTS_SQL
    elif layer == Layer.LIGHTNING:
        statement = LIGHTNING_SQL
        params |= {"now": now, "since": now - timedelta(minutes=lightning_window_minutes)}
    elif z >= OBSERVATIONS_FROM_ZOOM:
        statement = OBSERVATIONS_SQL
    else:
        return b""
    return bytes(session.scalar(statement, params) or b"")
