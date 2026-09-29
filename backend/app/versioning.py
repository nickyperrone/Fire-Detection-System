import hashlib
import json
from importlib.metadata import version

from app.config import get_thresholds


def processing_version(thresholds: dict | None = None) -> str:
    """Package version plus a hash of the thresholds, stored on every derived row."""
    thresholds = get_thresholds() if thresholds is None else thresholds
    canonical = json.dumps(thresholds, sort_keys=True, separators=(",", ":"))
    config_hash = hashlib.sha256(canonical.encode()).hexdigest()[:8]
    return f"{version('field-watch')}+cfg.{config_hash}"
