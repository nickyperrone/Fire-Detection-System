import json
import shutil
from datetime import date

import httpx
import pytest
from sqlalchemy import func, select

from app.models import HistoricalDetection, RunStatus
from app.providers.firms_archive import read_detections
from app.services.fire_history import field_history, load_history
from app.services.territories import load_feature_collection
from tests.conftest import ARGENTINA, FIXTURES
from tests.test_territories import SAMPLE

ARCHIVE = FIXTURES / "viirs-snpp_2020_Argentina.csv"


def test_archive_keeps_vegetation_fires_inside_the_region(thresholds):
    rows = list(read_detections(ARCHIVE, "viirs-snpp", thresholds["region"]["bbox"], [0]))
    # The industrial source (type 2) and the Chaco row outside the region are dropped.
    assert len(rows) == 3
    assert rows[2].acquired_at.isoformat() == "2020-09-03T04:12:00+00:00"


@pytest.fixture
def history_config(thresholds, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    # Pre-seeded cache: the loader must use it and not download.
    shutil.copy(ARCHIVE, cache / ARCHIVE.name)
    return {**thresholds["history"], "first_year": 2020, "last_year": 2021, "cache_dir": str(cache)}


def test_load_is_idempotent_and_records_each_year(session, thresholds, history_config, tmp_path):
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    bbox, decimals = thresholds["region"]["bbox"], thresholds["firms"]["dedup_coordinate_decimals"]
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        first = load_history(session, client, history_config, bbox, decimals, tmp_path)
        again = load_history(session, client, history_config, bbox, decimals, tmp_path)
    by_year = {r.product: r for r in first}
    assert (by_year["viirs-snpp_2020"].status, by_year["viirs-snpp_2020"].inserted) == (
        RunStatus.SUCCESS,
        3,
    )
    # 2021 is not cached and the server answers 404: a failed year, not a crash.
    assert by_year["viirs-snpp_2021"].status == RunStatus.FAILED
    assert sum(r.inserted for r in again) == 0
    assert session.scalar(select(func.count()).select_from(HistoricalDetection)) == 3


def test_field_history_counts_fire_days(session, thresholds, history_config, tmp_path):
    load_feature_collection(session, "default", json.loads(SAMPLE.read_text()), 5, ARGENTINA)
    session.commit()
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as client:
        load_history(
            session,
            client,
            history_config,
            thresholds["region"]["bbox"],
            thresholds["firms"]["dedup_coordinate_decimals"],
            tmp_path,
        )
    history = field_history(session, 1, history_config)  # La Esperanza
    # Two detections on 12 Aug are one fire day; 3 Sep is a day inside the field.
    assert history.fire_days == 2
    assert history.inside_days == 1
    assert history.days_per_year == {2020: 2}
    assert history.days_per_month[7] == 1 and history.days_per_month[8] == 1
    # 04:12 UTC on 3 Sep is 01:12 in Argentina, still 3 Sep.
    assert history.nearest.day == date(2020, 9, 3) and history.nearest.distance_m == 0
    assert history.latest.day == date(2020, 9, 3)
    assert history.years_loaded == [2020]
