import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from app.boundaries import allowed_area
from app.config import REPO_ROOT, get_settings, get_thresholds
from app.db import session_factory
from app.logging_setup import configure_logging
from app.models import DataQuality
from app.services.fire_history import load_history
from app.services.pipeline import (
    run_fire_pipeline,
    run_goes_fire_pipeline,
    run_lightning_pipeline,
    run_spray_pipeline,
)
from app.services.portfolio import FireAnswer, PortfolioEntry, SprayAnswer, build_portfolio
from app.services.territories import load_feature_collection

LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def age(then: datetime | None, now: datetime) -> str:
    if then is None:
        return "unknown"
    minutes = int((now - then).total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 48 * 60:
        return f"{minutes // 60} h ago"
    return f"{minutes // 1440} d ago"


def local_hour(moment: datetime) -> str:
    return moment.astimezone(LOCAL_TZ).strftime("%a %H:%M")


NO_FIRE_DATA = {
    DataQuality.NO_DATA: "no fire data: FIRMS has not been read successfully",
    DataQuality.STALE: "fire data is stale: last successful FIRMS read {last_read}",
    DataQuality.PARTIAL: "no detections within 10 km, but some FIRMS sensors failed",
}


def fire_line(fire: FireAnswer, now: datetime) -> str:
    if fire.severity is None:
        # "No detections" is only said when FIRMS was actually read.
        message = NO_FIRE_DATA.get(fire.data_quality, "no detections within 10 km")
        return f"{fire.data_quality.value:<12}" + message.format(
            last_read=age(fire.last_read_at, now)
        )
    parts = [
        f"Possible fire {fire.distance_m / 1000:.1f} km {fire.direction or ''}".rstrip(),
        ", ".join(fire.sensors),
        fire.confidence,
        f"acquired {age(fire.acquired_at, now)}, received {age(fire.received_at, now)}",
    ]
    if fire.other_fires:
        parts.append(f"+{fire.other_fires} more")
    if fire.data_quality != DataQuality.GOOD:
        parts.append(f"data {fire.data_quality.value}")
    return f"{fire.severity.value:<12}" + " · ".join(p for p in parts if p)


def spray_line(spray: SprayAnswer) -> str:
    if spray.status is None:
        return f"{spray.data_quality.value:<12}no forecast"
    parts = [problem["message"] for problem in spray.problems[:2]] or ["all rules pass"]
    if spray.drift_toward:
        parts.append(f"drift toward {spray.drift_toward}")
    if spray.status.value != "FAVORABLE":
        window = spray.next_favorable
        parts.append(
            f"next favorable {local_hour(window[0])}–{window[1].astimezone(LOCAL_TZ):%H:%M}"
            if window
            else "no favorable window in the forecast"
        )
    return f"{spray.status.value:<12}" + " · ".join(parts)


def print_entry(entry: PortfolioEntry, listed_ids: set[int], now: datetime) -> None:
    t = entry.territory
    under_parent = t.parent_id in listed_ids
    indent = "  " if under_parent else ""
    name = t.name if under_parent or t.parent is None else f"{t.parent.name} / {t.name}"
    tags = "  ".join(sorted(tag.label for tag in t.tags))
    print(f"{indent}{name} ({t.hectares:,.0f} ha)    {tags}")
    print(f"{indent}  Fire   {fire_line(entry.fire, now)}")
    print(f"{indent}  Spray  {spray_line(entry.spray)}")
    print(f"{indent}  Weird  {entry.anomaly.data_quality.value:<12}{entry.anomaly.message}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="field-watch")
    commands = parser.add_subparsers(dest="command", required=True)
    load = commands.add_parser("load-territories", help="load fields and sections from GeoJSON")
    load.add_argument("path", type=Path)
    commands.add_parser("ingest-fires", help="read FIRMS and derive fire events and field risk")
    commands.add_parser("ingest-goes", help="read new GOES-19 fire scans and lightning files")
    commands.add_parser("update-spray", help="read the forecast and assess spraying conditions")
    commands.add_parser("load-history", help="download and load the FIRMS fire archive")
    commands.add_parser("run-once", help="ingest-fires, ingest-goes and update-spray")
    portfolio = commands.add_parser("portfolio", help="every field and section with its answers")
    portfolio.add_argument("--tag", action="append", default=[], help="key:value, repeatable")
    args = parser.parse_args()

    configure_logging()
    settings, thresholds = get_settings(), get_thresholds()
    with session_factory()() as session, httpx.Client() as client:
        if args.command == "load-territories":
            config = thresholds["territories"]
            created = load_feature_collection(
                session,
                settings.owner,
                json.loads(args.path.read_text()),
                config["section_tolerance_m"],
                allowed_area(config["allowed_area"], config["allowed_area_tolerance_m"]),
            )
            session.commit()
            print(f"loaded {len(created)} territories")
        if args.command in ("ingest-fires", "run-once"):
            print(json.dumps(run_fire_pipeline(session, client, settings, thresholds), indent=2))
        if args.command in ("ingest-goes", "run-once"):
            for pipeline in (run_goes_fire_pipeline, run_lightning_pipeline):
                print(json.dumps(pipeline(session, client, thresholds), indent=2, default=str))
        if args.command in ("update-spray", "run-once"):
            print(json.dumps(run_spray_pipeline(session, client, thresholds), indent=2))
        if args.command == "load-history":
            runs = load_history(
                session,
                client,
                thresholds["history"],
                thresholds["region"]["bbox"],
                thresholds["firms"]["dedup_coordinate_decimals"],
                REPO_ROOT,
            )
            for run in runs:
                print(run.product, run.status.value, run.fetched, run.inserted, run.error or "")
        if args.command == "portfolio":
            now = datetime.now(UTC)
            entries = build_portfolio(session, settings.owner, thresholds, now, args.tag)
            listed_ids = {e.territory.id for e in entries}
            for entry in entries:
                print_entry(entry, listed_ids, now)


if __name__ == "__main__":
    main()
