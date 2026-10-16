import logging
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from apscheduler.executors.debug import DebugExecutor
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler

from app.config import get_settings, get_thresholds
from app.db import session_factory
from app.logging_setup import configure_logging
from app.providers.telegram import TelegramError
from app.services.pipeline import (
    run_alert_pipeline,
    run_anomaly_pipeline,
    run_fire_pipeline,
    run_forecast_pipeline,
    run_goes_fire_pipeline,
    run_land_cover_pipeline,
    run_lightning_pipeline,
    run_snapshot_pipeline,
    run_spray_pipeline,
    run_summary_pipeline,
    run_telegram_pipeline,
    run_weather_layer_pipeline,
    run_wind_layer_pipeline,
    set_up_telegram,
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
                log.info("alerts: %s", run_alert_pipeline(session, client, settings, thresholds))

    return run


_telegram_error: list[str] = []


def telegram_job() -> None:
    settings, thresholds = get_settings(), get_thresholds()
    with session_factory()() as session, httpx.Client() as client:
        try:
            result = run_telegram_pipeline(session, client, settings, thresholds)
        except (TelegramError, httpx.HTTPError) as exc:
            # Every 5 seconds: said once, not on every run, until it changes. "Conflict" means
            # another worker answers the same bot (docs/14-deploy.md#moving-from-the-laptop).
            if _telegram_error != [str(exc)]:
                log.warning("telegram: %s", exc)
                _telegram_error[:] = [str(exc)]
            return
        _telegram_error.clear()
        if result["updates"]:
            log.info("telegram: %s", result)


def main() -> None:
    configure_logging()
    # Each job logs its own result; the scheduler's "running"/"executed" lines for every job, and
    # for the bot every 5 seconds, would bury them.
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)
    intervals = get_thresholds()["worker"]
    # One job at a time, on the main thread: FIRMS and GOES both correlate fire events and must not
    # interleave, and netCDF only silences HDF5's error printing on the main thread (in another
    # thread every GOES file logs a page of harmless diagnostics).
    # Reading Sentinel-2 for every lot and field can take many minutes, so it runs in its own
    # thread: a fire must never wait for an image. It shares nothing with the fire jobs.
    # coalesce: a job that fell behind runs once, not once per missed interval.
    # misfire_grace_time=None: a job due while another runs starts late instead of being skipped;
    # with the default of 1 s, the one-minute lightning job starved every other job.
    scheduler = BlockingScheduler(
        timezone="UTC",
        executors={"default": DebugExecutor(), "images": ThreadPoolExecutor(1)},
        job_defaults={"coalesce": True, "misfire_grace_time": None},
    )
    start = datetime.now(UTC)
    jobs = [
        (
            job("anomalies", run_anomaly_pipeline),
            intervals["anomaly_interval_minutes"],
            "images",
        ),
        (
            job("photos", run_snapshot_pipeline),
            intervals["snapshot_interval_minutes"],
            "images",
        ),
        (
            job("land cover", run_land_cover_pipeline),
            intervals["land_cover_interval_minutes"],
            "images",
        ),
        (
            job("firms", run_fire_pipeline, with_settings=True, then_alert=True),
            intervals["fire_interval_minutes"],
            "default",
        ),
        (
            job("goes fire", run_goes_fire_pipeline, then_alert=True),
            intervals["goes_fire_interval_minutes"],
            "default",
        ),
        (
            job("lightning", run_lightning_pipeline, then_alert=True),
            intervals["lightning_interval_minutes"],
            "default",
        ),
        (
            job("clouds and rain", run_weather_layer_pipeline),
            intervals["weather_layer_interval_minutes"],
            "default",
        ),
        (
            job("wind", run_wind_layer_pipeline),
            intervals["wind_interval_minutes"],
            "default",
        ),
        # A new forecast may bring adverse weather (docs/13-notifications.md#kinds).
        (
            job("spray", run_spray_pipeline, then_alert=True),
            intervals["weather_interval_minutes"],
            "default",
        ),
        (
            job("forecast", run_forecast_pipeline, with_settings=True),
            intervals["forecast_interval_minutes"],
            "default",
        ),
        (
            job("summaries", run_summary_pipeline, with_settings=True),
            intervals["summary_interval_minutes"],
            "default",
        ),
    ]
    for run, minutes, executor in jobs:
        # next_run_time=now runs each job once at startup instead of waiting a full interval.
        scheduler.add_job(run, "interval", minutes=minutes, next_run_time=start, executor=executor)
    if get_settings().telegram_bot_token:
        try:
            with httpx.Client() as client:
                set_up_telegram(client, get_settings())
        except (TelegramError, httpx.HTTPError) as exc:
            log.warning("telegram profile not set: %s", exc)
        # Quiet: it runs every few seconds and logs only when the bot got something.
        scheduler.add_job(
            telegram_job,
            "interval",
            seconds=intervals["telegram_interval_seconds"],
            next_run_time=start,
            executor="default",
        )
    scheduler.start()


if __name__ == "__main__":
    main()
