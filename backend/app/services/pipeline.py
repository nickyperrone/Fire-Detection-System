"""The two scheduled jobs. The worker and the CLI both call these."""

from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.config import Settings
from app.services.field_risk import assess_active_fire_events
from app.services.fire_correlation import correlate
from app.services.fire_ingestion import ingest_firms
from app.services.spray_conditions import assess_spray
from app.versioning import processing_version


def run_fire_pipeline(
    session: Session, client: httpx.Client, settings: Settings, thresholds: dict
) -> dict:
    now = datetime.now(UTC)
    version = processing_version(thresholds)
    runs = ingest_firms(session, client, settings.firms_map_key, thresholds, now)
    changed = correlate(session, thresholds["correlation"], version, now)
    # All active events, not only the changed ones: fields created since the last run need them too.
    touched = assess_active_fire_events(session, thresholds["field_risk"], version, now)
    return {
        "runs": [(r.product, r.status.value, r.fetched, r.inserted, r.error) for r in runs],
        "fire_events_changed": len(changed),
        "field_risk_events_touched": touched,
        "processing_version": version,
    }


def run_spray_pipeline(session: Session, client: httpx.Client, thresholds: dict) -> dict:
    run = assess_spray(
        session, client, thresholds, processing_version(thresholds), datetime.now(UTC)
    )
    return {"status": run.status.value, "assessments": run.inserted, "error": run.error}
