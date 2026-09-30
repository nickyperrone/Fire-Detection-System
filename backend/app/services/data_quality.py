"""Whether each answer rests on fresh, complete data (docs/03-rules.md#data-quality)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DataQuality, IngestionRun, Observation, RunStatus, SprayAssessment


@dataclass(frozen=True)
class SourceStatus:
    provider: str
    product: str
    last_run_at: datetime | None
    last_run_status: RunStatus | None
    last_success_at: datetime | None
    last_error: str | None


def source_statuses(session: Session, provider: str, products: list[str]) -> list[SourceStatus]:
    statuses = []
    for product in products:
        last_run = session.scalar(
            select(IngestionRun)
            .where(IngestionRun.provider == provider, IngestionRun.product == product)
            .order_by(IngestionRun.finished_at.desc())
            .limit(1)
        )
        last_success = session.scalar(
            select(IngestionRun.finished_at)
            .where(
                IngestionRun.provider == provider,
                IngestionRun.product == product,
                IngestionRun.status == RunStatus.SUCCESS,
            )
            .order_by(IngestionRun.finished_at.desc())
            .limit(1)
        )
        statuses.append(
            SourceStatus(
                provider=provider,
                product=product,
                last_run_at=last_run.finished_at if last_run else None,
                last_run_status=last_run.status if last_run else None,
                last_success_at=last_success,
                last_error=last_run.error
                if last_run and last_run.status == RunStatus.FAILED
                else None,
            )
        )
    return statuses


def fire_quality(
    statuses: list[SourceStatus], stale_after_hours: float, now: datetime
) -> DataQuality:
    successes = [s.last_success_at for s in statuses if s.last_success_at is not None]
    if not successes:
        return DataQuality.NO_DATA
    if now - max(successes) > timedelta(hours=stale_after_hours):
        return DataQuality.STALE
    if any(s.last_run_status != RunStatus.SUCCESS for s in statuses):
        return DataQuality.PARTIAL
    return DataQuality.GOOD


def spray_quality(
    assessment: SprayAssessment | None, stale_after_hours: float, now: datetime
) -> DataQuality:
    if assessment is None:
        return DataQuality.NO_DATA
    if now - assessment.forecast_fetched_at > timedelta(hours=stale_after_hours):
        return DataQuality.STALE
    return assessment.data_quality


@dataclass(frozen=True)
class LatestPass:
    sensor: str
    satellite: str
    acquired_at: datetime
    ingested_at: datetime


def latest_pass(session: Session, source: str) -> LatestPass | None:
    """The newest satellite pass we hold data from. FIRMS only lists passes with detections,
    so this is the latest pass that saw a fire somewhere in the region."""
    newest = session.scalar(
        select(Observation)
        .where(Observation.source == source)
        .order_by(Observation.acquired_at.desc())
        .limit(1)
    )
    if newest is None:
        return None
    return LatestPass(newest.sensor, newest.satellite, newest.acquired_at, newest.ingested_at)
