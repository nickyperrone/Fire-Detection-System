import logging
from datetime import UTC, datetime

import httpx
from apscheduler.schedulers.blocking import BlockingScheduler

from app.config import get_settings, get_thresholds
from app.db import session_factory
from app.logging_setup import configure_logging
from app.services.pipeline import run_fire_pipeline, run_spray_pipeline

log = logging.getLogger("worker")


def fire_job() -> None:
    with session_factory()() as session, httpx.Client() as client:
        log.info(
            "fire pipeline: %s",
            run_fire_pipeline(session, client, get_settings(), get_thresholds()),
        )


def spray_job() -> None:
    with session_factory()() as session, httpx.Client() as client:
        log.info("spray pipeline: %s", run_spray_pipeline(session, client, get_thresholds()))


def main() -> None:
    configure_logging()
    intervals = get_thresholds()["worker"]
    scheduler = BlockingScheduler(timezone="UTC")
    # next_run_time=now runs each job once at startup instead of waiting a full interval.

    start = datetime.now(UTC)
    scheduler.add_job(
        fire_job, "interval", minutes=intervals["fire_interval_minutes"], next_run_time=start
    )
    scheduler.add_job(
        spray_job, "interval", minutes=intervals["weather_interval_minutes"], next_run_time=start
    )
    scheduler.start()


if __name__ == "__main__":
    main()
