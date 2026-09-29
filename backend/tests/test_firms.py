from datetime import UTC, datetime

import httpx
import pytest

from app.models import Confidence
from app.providers import firms
from tests.conftest import FIXTURES

MODIS_THRESHOLDS = {"nominal_from": 30, "high_from": 80}


def test_viirs_rows_are_normalized():
    text = (FIXTURES / "firms_viirs_noaa21.csv").read_text()
    first, second, third = firms.parse_csv(text, "VIIRS_NOAA21_NRT", MODIS_THRESHOLDS)
    assert first.satellite == "NOAA-21"
    assert first.sensor == "VIIRS"
    assert first.acquired_at == datetime(2026, 9, 28, 5, 12, tzinfo=UTC)
    assert first.confidence == Confidence.HIGH
    assert second.confidence == Confidence.NOMINAL
    assert third.confidence == Confidence.LOW
    assert first.brightness_k == 338.45
    assert first.frp_mw == 12.4
    assert first.raw_payload["bright_ti5"] == "293.11"


def test_modis_confidence_uses_configured_thresholds():
    text = (FIXTURES / "firms_modis.csv").read_text()
    high, low = firms.parse_csv(text, "MODIS_NRT", MODIS_THRESHOLDS)
    assert (high.sensor, high.satellite, high.brightness_k) == ("MODIS", "Aqua", 321.4)
    assert high.confidence == Confidence.HIGH
    assert low.confidence == Confidence.LOW
    assert firms.modis_confidence_level(30, MODIS_THRESHOLDS) == Confidence.NOMINAL
    assert firms.modis_confidence_level(79, MODIS_THRESHOLDS) == Confidence.NOMINAL


@pytest.mark.parametrize(
    ("raw", "expected"), [("512", "05:12"), ("0005", "00:05"), ("2359", "23:59")]
)
def test_acq_time_without_leading_zeros(raw, expected):
    assert firms.parse_acquired_at("2026-09-28", raw).strftime("%H:%M") == expected


def test_plain_text_answer_is_an_error():
    with pytest.raises(firms.FirmsError, match="Invalid MAP_KEY"):
        firms.parse_csv("Invalid MAP_KEY.", "MODIS_NRT", MODIS_THRESHOLDS)


def test_header_only_means_no_detections():
    header = (FIXTURES / "firms_modis.csv").read_text().splitlines()[0]
    assert firms.parse_csv(header + "\n", "MODIS_NRT", MODIS_THRESHOLDS) == []


def test_fetch_builds_the_area_url():
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text=(FIXTURES / "firms_modis.csv").read_text())

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        rows = firms.fetch_observations(
            client, "KEY", "MODIS_NRT", [-59.35, -33.25, -58.8, -32.7], 2, MODIS_THRESHOLDS
        )
    assert len(rows) == 2
    assert seen == [f"{firms.AREA_URL.split('{key}')[0]}KEY/MODIS_NRT/-59.35,-33.25,-58.8,-32.7/2"]
