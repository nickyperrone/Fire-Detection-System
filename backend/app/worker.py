import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from apscheduler.executors.debug import DebugExecutor
from apscheduler.schedulers.blocking import BlockingScheduler

from app.config import get_settings, get_thresholds
from app.db import session_factory
from app.logging_setup import configure_logging
from app.services.pipeline import (
    run_alert_pipeline,
    run_fire_pipeline,
    run_forecast_pipeline,
    run_goes_fire_pipeline,
    run_lightning_pipeline,
    run_spray_pipeline,
    run_summary_pipeline,
)

log = logging.getLogger("worker")


def job(
    name: str,
    pipeline: Callable[..., dict],
    with_settings: bool = False,
    then_alert: bool = False,
) -> Callable[[], None]:
    """`then_alert`: the run may have brought new danger near fields, so alerts are checked."""

    def run() -> None:
        settings, thresholds = get_settings(), get_thresholds()
        with session_factory()() as session, httpx.Client() as client:
            args = (settings,) if with_settings else ()
            log.info("%s: %s", name, pipeline(session, client, *args, thresholds))
            if then_alert:
                log.info("alerts: %s", run_alert_pipeline(session, settings, thresholds))

    return run


def main() -> None:
    configure_logging()
    intervals = get_thresholds()["worker"]
    # One job at a time, on the main thread: FIRMS and GOES both correlate fire events and must not
    # interleave, and netCDF only silences HDF5's error printing on the main thread (in another
    # thread every GOES file logs a page of harmless diagnostics).
    # coalesce: a job that fell behind runs once, not once per missed interval.
    # misfire_grace_time=None: a job due while another runs starts late instead of being skipped;
    # with the default of 1 s, the one-minute lightning job starved every other job.
    scheduler = BlockingScheduler(
        timezone="UTC",
        executors={"default": DebugExecutor()},
        job_defaults={"coalesce": True, "misfire_grace_time": None},
    )
    start = datetime.now(UTC)
    jobs = [
        (
            job("firms", run_fire_pipeline, with_settings=True, then_alert=True),
            intervals["fire_interval_minutes"],
        ),
        (
            job("goes fire", run_goes_fire_pipeline, then_alert=True),
            intervals["goes_fire_interval_minutes"],
        ),
        (
            job("lightning", run_lightning_pipeline, then_alert=True),
            intervals["lightning_interval_minutes"],
        ),
        (job("spray", run_spray_pipeline), intervals["weather_interval_minutes"]),
        (
            job("forecast", run_forecast_pipeline, with_settings=True),
            intervals["forecast_interval_minutes"],
        ),
        (
            job("summaries", run_summary_pipeline, with_settings=True),
            intervals["summary_interval_minutes"],
        ),
    ]
    for run, minutes in jobs:
        # next_run_time=now runs each job once at startup instead of waiting a full interval.
        scheduler.add_job(run, "interval", minutes=minutes, next_run_time=start)
    scheduler.start()


if __name__ == "__main__":
    main()
