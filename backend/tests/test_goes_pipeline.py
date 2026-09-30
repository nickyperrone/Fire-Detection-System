import json
from datetime import UTC, datetime, timedelta

import httpx
import mapbox_vector_tile
import numpy as np
import pytest
from sqlalchemy import func, select

from app.models import FireEvent, LightningFlash, Observation, RunStatus
from app.providers.geostationary import latlon_to_scan
from app.services.fire_correlation import correlate
from app.services.goes_ingestion import ingest_goes_fire, ingest_lightning
from app.services.lightning import nearby_lightning
from app.services.territories import load_feature_collection
from app.services.tiles import Layer, build_tile
from tests.goes_files import GOES_EAST, fire_file, grid, lightning_file
from tests.test_territories import SAMPLE
from tests.test_tiles import tile_xy

NOW = datetime(2026, 9, 30, 14, 45, tzinfo=UTC)
FIRE_PREFIX = "ABI-L2-FDCF/2026/273/14/"
GLM_PREFIX = "GLM-L2-LCFA/2026/273/14/"


def pixel_near(lat: float, lon: float) -> tuple[int, int]:
    x, y = grid()
    xs, ys = latlon_to_scan(np.array([lat]), np.array([lon]), GOES_EAST)
    return int(np.abs(y - ys[0]).argmin()), int(np.abs(x - xs[0]).argmin())


def listing(keys: list[str]) -> str:
    contents = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys)
    return (
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f"{contents}</ListBucketResult>"
    )


class FakeBucket:
    """Serves ListObjectsV2 and GET for a dict of key -> bytes, and counts downloads."""

    def __init__(self, files: dict[str, bytes]):
        self.files = files
        self.downloads: list[str] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        prefix = request.url.params.get("prefix")
        if prefix is not None:
            return httpx.Response(
                200, text=listing([k for k in self.files if k.startswith(prefix)])
            )
        key = request.url.path.lstrip("/")
        self.downloads.append(key)
        return httpx.Response(200, content=self.files[key])

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle))


@pytest.fixture
def fields(session):
    load_feature_collection(session, "default", json.loads(SAMPLE.read_text()), 5)
    session.commit()


def test_goes_fire_ingestion_follows_the_cursor(session, thresholds):
    row, col = pixel_near(-32.943, -59.021)
    bucket = FakeBucket(
        {
            f"{FIRE_PREFIX}OR_ABI-L2-FDCF-M6_G19_s20262731420203.nc": fire_file(
                {(row, col): 10}, start="2026-09-30T14:20:20.3Z"
            ),
            f"{FIRE_PREFIX}OR_ABI-L2-FDCF-M6_G19_s20262731430203.nc": fire_file(
                {(row, col): 13}, start="2026-09-30T14:30:20.3Z"
            ),
        }
    )
    with bucket.client() as client:
        first = ingest_goes_fire(session, client, thresholds, NOW)
        second = ingest_goes_fire(session, client, thresholds, NOW)
    assert (first.status, first.inserted) == (RunStatus.SUCCESS, 2)
    assert first.cursor.endswith("s20262731430203.nc")
    # The second run finds nothing after the cursor and downloads nothing.
    assert (second.fetched, second.inserted) == (0, 0)
    assert len(bucket.downloads) == 2
    sources = session.scalars(select(Observation.source)).all()
    assert sources == ["goes", "goes"]


def test_goes_detection_joins_a_viirs_fire_2_km_away(session, thresholds):
    # A VIIRS event first, then a GOES pixel whose center is about 2.5 km from it.
    viirs = Observation(
        source="firms",
        product="VIIRS_NOAA21_NRT",
        satellite="NOAA-21",
        sensor="VIIRS",
        dedup_key="viirs-1",
        acquired_at=NOW - timedelta(minutes=30),
        ingested_at=NOW,
        geom="SRID=4326;POINT(-59.021 -32.943)",
        confidence_raw="h",
        confidence="high",
        raw_payload={},
    )
    goes = Observation(
        source="goes",
        product="ABI-L2-FDCF",
        satellite="GOES-19",
        sensor="ABI",
        native_id="20260930T142020:1:1",
        dedup_key="goes-1",
        acquired_at=NOW - timedelta(minutes=20),
        ingested_at=NOW,
        geom="SRID=4326;POINT(-59.021 -32.965)",
        confidence_raw="10",
        confidence="high",
        raw_payload={},
    )
    session.add_all([viirs, goes])
    session.commit()
    correlate(session, thresholds["correlation"], "test", NOW)
    (event,) = session.scalars(select(FireEvent)).all()
    assert sorted(event.sensors) == ["ABI GOES-19", "VIIRS NOAA-21"]


def test_lightning_near_a_field_and_on_the_map(session, thresholds, fields):
    bucket = FakeBucket(
        {
            f"{GLM_PREFIX}OR_GLM-L2-LCFA_G19_s20262731440000.nc": lightning_file(
                # Next to La Esperanza, 40 km away, and one of bad quality.
                [(-32.95, -59.06, 0), (-32.60, -59.40, 0), (-32.95, -59.06, 1)],
                start="2026-09-30T14:40:00.0Z",
            )
        }
    )
    with bucket.client() as client:
        run = ingest_lightning(session, client, thresholds, NOW)
    assert run.inserted == 2
    ids = session.scalars(select(LightningFlash.id)).all()
    assert len(ids) == 2
    esperanza_id = 1
    nearby = nearby_lightning(session, [esperanza_id, 2], thresholds["lightning"], NOW)
    assert nearby[esperanza_id].flashes == 1
    assert nearby[esperanza_id].nearest_m < 2000
    # An hour later the flash is out of the window.
    assert (
        nearby_lightning(session, [esperanza_id], thresholds["lightning"], NOW + timedelta(hours=2))
        == {}
    )
    x, y = tile_xy(-59.06, -32.95, 10)
    tile = mapbox_vector_tile.decode(build_tile(session, Layer.LIGHTNING, 10, x, y, "default", NOW))
    assert [f["properties"]["age_minutes"] for f in tile["lightning"]["features"]] == [5]


def test_old_flashes_are_deleted(session, thresholds):
    bucket = FakeBucket({})
    session.add(
        LightningFlash(
            native_id="old:1",
            observed_at=NOW - timedelta(days=8),
            ingested_at=NOW - timedelta(days=8),
            geom="SRID=4326;POINT(-59 -33)",
            energy_j=1e-15,
            area_m2=1e8,
        )
    )
    session.commit()
    with bucket.client() as client:
        ingest_lightning(session, client, thresholds, NOW)
    assert session.scalar(select(func.count()).select_from(LightningFlash)) == 0
