from app.models import Severity
from app.services.field_risk import compass, severity_for
from app.versioning import processing_version


def test_severity_bands(thresholds):
    bands = thresholds["field_risk"]["bands"]
    assert severity_for(0, True, bands) == Severity.CRITICAL
    assert severity_for(1999, False, bands) == Severity.VERY_HIGH
    assert severity_for(2000, False, bands) == Severity.HIGH
    assert severity_for(4999, False, bands) == Severity.HIGH
    assert severity_for(9999, False, bands) == Severity.WATCH
    assert severity_for(10000, False, bands) is None


def test_compass():
    assert [compass(d) for d in (0, 44, 46, 180, 359)] == ["N", "NE", "NE", "S", "N"]
    assert compass(None) is None


def test_processing_version_changes_with_any_threshold(thresholds):
    changed = {**thresholds, "correlation": {**thresholds["correlation"], "max_distance_m": 1500}}
    assert processing_version(thresholds) != processing_version(changed)
    assert processing_version(thresholds) == processing_version(dict(reversed(thresholds.items())))
    assert processing_version(thresholds).startswith("0.1.0+cfg.")
