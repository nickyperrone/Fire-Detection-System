"""The scheduled jobs. The worker and the CLI both call these."""

from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import IngestionRun
from app.services.field_risk import assess_active_fire_events
from app.services.fire_correlation import correlate
from app.services.fire_ingestion import ingest_firms
from app.services.goes_ingestion import ingest_goes_fire, ingest_lightning
from app.services.spray_conditions import assess_spray
from app.versioning import processing_version


def _summary(run: IngestionRun) -> tuple:
    return (run.product, run.status.value, run.fetched, run.inserted, run.error)


def _derive_fire_events(session: Session, thresholds: dict, now: datetime) -> dict:
    version = processing_version(thresholds)
    changed = correlate(session, thresholds["correlation"], version, now)
    # All active events, not only the changed ones: fields created since the last run need them too.
    touched = assess_active_fire_events(session, thresholds["field_risk"], version, now)
    return {
        "fire_events_changed": len(changed),
        "field_risk_events_touched": touched,
        "processing_version": version,
    }


def run_fire_pipeline(
    session: Session, client: httpx.Client, settings: Settings, thresholds: dict
) -> dict:
    now = datetime.now(UTC)
    runs = ingest_firms(session, client, settings.firms_map_key, thresholds, now)
    return {"runs": [_summary(r) for r in runs], **_derive_fire_events(session, thresholds, now)}


def run_goes_fire_pipeline(session: Session, client: httpx.Client, thresholds: dict) -> dict:
    now = datetime.now(UTC)
    run = ingest_goes_fire(session, client, thresholds, now)
    return {"runs": [_summary(run)], **_derive_fire_events(session, thresholds, now)}


def run_lightning_pipeline(session: Session, client: httpx.Client, thresholds: dict) -> dict:
    return {"runs": [_summary(ingest_lightning(session, client, thresholds, datetime.now(UTC)))]}


def run_spray_pipeline(session: Session, client: httpx.Client, thresholds: dict) -> dict:
    run = assess_spray(
        session, client, thresholds, processing_version(thresholds), datetime.now(UTC)
    )
    return {"status": run.status.value, "assessments": run.inserted, "error": run.error}
