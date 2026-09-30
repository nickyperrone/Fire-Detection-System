import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler

from app.config import get_settings, get_thresholds
from app.db import session_factory
from app.logging_setup import configure_logging
from app.services.pipeline import (
    run_fire_pipeline,
    run_goes_fire_pipeline,
    run_lightning_pipeline,
    run_spray_pipeline,
)

log = logging.getLogger("worker")


def job(
    name: str, pipeline: Callable[..., dict], with_settings: bool = False
) -> Callable[[], None]:
    def run() -> None:
        with session_factory()() as session, httpx.Client() as client:
            args = (get_settings(),) if with_settings else ()
            log.info("%s: %s", name, pipeline(session, client, *args, get_thresholds()))

    return run


def main() -> None:
    configure_logging()
    intervals = get_thresholds()["worker"]
    # One job at a time: FIRMS and GOES both correlate fire events and must not interleave.
    # coalesce: a job that fell behind runs once, not once per missed interval.
    scheduler = BlockingScheduler(
        timezone="UTC",
        executors={"default": ThreadPoolExecutor(1)},
        job_defaults={"coalesce": True, "max_instances": 1},
    )
    start = datetime.now(UTC)
    jobs = [
        (job("firms", run_fire_pipeline, with_settings=True), intervals["fire_interval_minutes"]),
        (job("goes fire", run_goes_fire_pipeline), intervals["goes_fire_interval_minutes"]),
        (job("lightning", run_lightning_pipeline), intervals["lightning_interval_minutes"]),
        (job("spray", run_spray_pipeline), intervals["weather_interval_minutes"]),
    ]
    for run, minutes in jobs:
        # next_run_time=now runs each job once at startup instead of waiting a full interval.
        scheduler.add_job(run, "interval", minutes=minutes, next_run_time=start)
    scheduler.start()


if __name__ == "__main__":
    main()
