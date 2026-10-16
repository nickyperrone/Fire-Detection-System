"""The scheduled jobs. The worker and the CLI both call these."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import REPO_ROOT, Settings
from app.forecast.dataset import weather_point
from app.forecast.live_weather import LOCAL_TZ, refresh_weather
from app.forecast.recent_fires import PROVIDER as RECENT_PROVIDER
from app.forecast.recent_fires import top_up
from app.forecast.serve import cells_of, forecast_grid, forecast_territories, issue_forecast
from app.models import IngestionRun, RunStatus
from app.providers.telegram import Telegram
from app.services.alerts import public_url, send_alerts
from app.services.anomalies import check_fields
from app.services.area_picture import area_picture
from app.services.field_risk import assess_active_fire_events
from app.services.fire_correlation import correlate
from app.services.fire_ingestion import ingest_firms
from app.services.goes_ingestion import ingest_goes_fire, ingest_lightning
from app.services.land_cover import refresh_land_cover
from app.services.mail import smtp_sender
from app.services.snapshots import PHOTO_ROOT, take_snapshots
from app.services.spray_conditions import assess_spray
from app.services.static_sources import mark_observations
from app.services.summary import send_due_summaries
from app.services.telegram_bot import answer_updates, configure_bot
from app.services.weather_layer import WEATHER_ROOT, refresh_weather_layer
from app.versioning import processing_version

# Each field's Sentinel-2 boxes, shared by the unusual-patches check and the photos.
SENTINEL2_FIELDS = REPO_ROOT / "data" / "cache" / "sentinel2" / "fields"


def _summary(run: IngestionRun) -> tuple:
    return (run.product, run.status.value, run.fetched, run.inserted, run.error)


def _derive_fire_events(session: Session, thresholds: dict, now: datetime) -> dict:
    version = processing_version(thresholds)
    mark_observations(session, thresholds["static_sources"]["radius_m"])
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


def run_weather_layer_pipeline(_: Session, client: httpx.Client, thresholds: dict) -> dict:
    """GOES-19's newest clouds and rain over the region, as an image for the map."""
    return refresh_weather_layer(client, thresholds, WEATHER_ROOT, datetime.now(UTC))


# The FIRMS archive top-up only changes once a day.
RECENT_FIRES_EVERY = timedelta(hours=20)


def run_forecast_pipeline(
    session: Session, client: httpx.Client, settings: Settings, thresholds: dict
) -> dict:
    """Weather up to today, recent fires topped up (daily), then the forecast for every cell and
    field (docs/05-fire-forecast.md#live-data)."""
    config = thresholds["forecast"]
    today = datetime.now(ZoneInfo(LOCAL_TZ)).date()
    grid = forecast_grid(
        tuple(thresholds["region"]["bbox"]),
        config["cell_degrees"],
        thresholds["territories"]["allowed_area"],
    )
    points = sorted(
        {weather_point(*grid.center(r, c), config["weather_degrees"]) for r, c in cells_of(grid)}
    )
    runs = refresh_weather(session, client, points, config, REPO_ROOT, today)
    last_top_up = session.scalar(
        select(IngestionRun.finished_at)
        .where(IngestionRun.provider == RECENT_PROVIDER, IngestionRun.status == RunStatus.SUCCESS)
        .order_by(IngestionRun.finished_at.desc())
        .limit(1)
    )
    if last_top_up is None or datetime.now(UTC) - last_top_up > RECENT_FIRES_EVERY:
        runs.append(
            top_up(
                session,
                client,
                settings.firms_map_key,
                config,
                thresholds["region"]["bbox"],
                thresholds["firms"]["dedup_coordinate_decimals"],
                today,
                thresholds["history"]["keep_types"],
                thresholds["static_sources"]["radius_m"],
            )
        )
    issued = issue_forecast(session, thresholds, REPO_ROOT, today, processing_version(thresholds))
    return {"runs": [_summary(r) for r in runs], **issued}


def run_spray_pipeline(session: Session, client: httpx.Client, thresholds: dict) -> dict:
    run = assess_spray(
        session, client, thresholds, processing_version(thresholds), datetime.now(UTC)
    )
    return {"status": run.status.value, "assessments": run.inserted, "error": run.error}


def telegram_bot(client: httpx.Client, settings: Settings) -> Telegram | None:
    """None when the server has no bot (docs/13-notifications.md#telegram)."""
    return Telegram(client, settings.telegram_bot_token) if settings.telegram_bot_token else None


def run_alert_pipeline(
    session: Session, client: httpx.Client, settings: Settings, thresholds: dict
) -> dict:
    """Alerts of new danger near fields, after each fire, lightning or forecast run (docs/13)."""
    now = datetime.now(UTC)

    def picture(territory, dangers, wind, locale):
        return area_picture(session, client, territory, dangers, wind, thresholds, locale, now)

    return send_alerts(
        session,
        smtp_sender(settings),
        settings,
        thresholds,
        processing_version(thresholds),
        now,
        telegram_bot(client, settings),
        picture,
    )


def run_telegram_pipeline(
    session: Session, client: httpx.Client, settings: Settings, thresholds: dict
) -> dict:
    """Messages and button taps sent to the bot (docs/13-notifications.md#telegram)."""
    bot = telegram_bot(client, settings)
    if bot is None:
        return {"updates": 0}
    app_url = settings.app_url if public_url(settings.app_url) else None
    return {"updates": answer_updates(session, bot, datetime.now(UTC), app_url)}


def set_up_telegram(client: httpx.Client, settings: Settings) -> None:
    """The bot's commands and descriptions, from the repository (docs/13-notifications.md)."""
    bot = telegram_bot(client, settings)
    if bot is not None:
        configure_bot(bot)


def answer_territories(
    session: Session, client: httpx.Client, thresholds: dict, territory_ids: list[int]
) -> dict:
    """Spray conditions and fire forecast for fields just drawn or reshaped, so they have answers
    at once instead of after the next hourly run."""
    version = processing_version(thresholds)
    spray = assess_spray(session, client, thresholds, version, datetime.now(UTC), territory_ids)
    config = thresholds["forecast"]
    grid = forecast_grid(
        tuple(thresholds["region"]["bbox"]),
        config["cell_degrees"],
        thresholds["territories"]["allowed_area"],
    )
    forecasts = forecast_territories(session, grid, config, version, territory_ids)
    session.commit()
    return {"spray": spray.status.value, "forecast_fields": forecasts}


def run_summary_pipeline(
    session: Session, client: httpx.Client, settings: Settings, thresholds: dict
) -> dict:
    """Daily and weekly summaries of the accounts that are due (docs/09)."""
    return send_due_summaries(
        session,
        smtp_sender(settings),
        settings,
        thresholds,
        datetime.now(UTC),
        telegram_bot(client, settings),
    )


def run_anomaly_pipeline(session: Session, client: httpx.Client, thresholds: dict) -> dict:
    """Every field against its latest Sentinel-2 scenes (docs/11-field-anomalies.md)."""
    return check_fields(
        session,
        client,
        thresholds["anomalies"],
        processing_version(thresholds),
        datetime.now(UTC),
        SENTINEL2_FIELDS,
    )


def run_land_cover_pipeline(session: Session, client: httpx.Client, thresholds: dict) -> dict:
    """Trees, crops and buildings in and around new or redrawn fields (docs/15-land-cover.md)."""
    return refresh_land_cover(session, thresholds["land_cover"], datetime.now(UTC))


def run_snapshot_pipeline(session: Session, client: httpx.Client, thresholds: dict) -> dict:
    """A photo of every clear pass over each field (docs/12-field-page.md)."""
    return take_snapshots(
        session,
        client,
        thresholds["snapshots"],
        processing_version(thresholds),
        datetime.now(UTC),
        SENTINEL2_FIELDS,
        PHOTO_ROOT,
    )
