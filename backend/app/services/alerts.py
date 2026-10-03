"""Email alerts for new danger near fields (docs/09-accounts-and-alerts.md#email-alerts)."""

import logging
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    AlertEmail,
    FieldRiskEvent,
    FireEvent,
    FireEventStatus,
    RiskStatus,
    Territory,
    User,
)
from app.services.email_text import Danger, alert_email
from app.services.field_risk import SEVERITY_RANK, compass
from app.services.lightning import nearby_lightning
from app.services.mail import SEND_ERRORS, SendEmail, message

log = logging.getLogger(__name__)


def _rank(danger: Danger) -> tuple:
    # Worst first: fires by severity, then lightning; closer first within each.
    severity = SEVERITY_RANK[danger.severity] if danger.severity else -1
    return (danger.kind != "fire", -severity, danger.distance_m)


def _new_fire_risks(session: Session) -> list[tuple[FieldRiskEvent, Territory, User]]:
    rows = session.execute(
        select(FieldRiskEvent, Territory, User)
        .join(Territory, FieldRiskEvent.territory_id == Territory.id)
        .join(User, User.email == Territory.owner)
        .join(FireEvent, FieldRiskEvent.fire_event_id == FireEvent.id)
        .where(
            Territory.alerts,
            FireEvent.status == FireEventStatus.ACTIVE,
            FieldRiskEvent.status != RiskStatus.RESOLVED,
        )
    ).all()
    return [
        (risk, territory, user)
        for risk, territory, user in rows
        if risk.notified_severity is None
        or SEVERITY_RANK[risk.severity] > SEVERITY_RANK[risk.notified_severity]
    ]


def _new_lightning(
    session: Session, config: dict, quiet_minutes: int, now: datetime
) -> list[tuple[Territory, User, float]]:
    rows = session.execute(
        select(Territory, User).join(User, User.email == Territory.owner).where(Territory.alerts)
    ).all()
    quiet_since = now - timedelta(minutes=quiet_minutes)
    candidates = {
        t.id: (t, u)
        for t, u in rows
        if t.lightning_notified_at is None or t.lightning_notified_at < quiet_since
    }
    nearby = nearby_lightning(session, list(candidates), config, now)
    return [
        (*candidates[territory_id], found.nearest_m)
        for territory_id, found in nearby.items()
        if found.flashes > 0
    ]


def send_alerts(
    session: Session,
    send: SendEmail,
    settings: Settings,
    thresholds: dict,
    version: str,
    now: datetime,
) -> dict:
    """One email per user with every field whose danger started or grew since the last email."""
    lightning_config = thresholds["lightning"]
    per_user: dict[int, list[Danger]] = defaultdict(list)
    users: dict[int, User] = {}
    fire_marks: dict[int, list[FieldRiskEvent]] = defaultdict(list)
    lightning_marks: dict[int, list[Territory]] = defaultdict(list)
    fire_seen: set[tuple[int, int]] = set()
    lightning_seen: set[int] = set()

    fires = _new_fire_risks(session)
    lightning = _new_lightning(
        session, lightning_config, thresholds["alerts"]["lightning_quiet_minutes"], now
    )
    for risk, territory, user in fires:
        users[user.id] = user
        fire_marks[user.id].append(risk)
        fire_seen.add((territory.id, risk.fire_event_id))
    for territory, user, _ in lightning:
        users[user.id] = user
        lightning_marks[user.id].append(territory)
        lightning_seen.add(territory.id)

    # A lot is announced only when its field is not: the same fire near a field and its four
    # lots is one line, not five. The lots are still marked as announced.
    for risk, territory, user in fires:
        if (territory.parent_id, risk.fire_event_id) in fire_seen:
            continue
        event = risk.fire_event
        per_user[user.id].append(
            Danger(
                territory_id=territory.id,
                name=territory.name,
                kind="fire",
                distance_m=risk.distance_m,
                direction=compass(risk.bearing_deg),
                severity=risk.severity,
                sensors=sorted(event.sensors),
                seen_at=event.last_detected_at,
            )
        )
    for territory, user, nearest_m in lightning:
        if territory.parent_id in lightning_seen:
            continue
        per_user[user.id].append(
            Danger(
                territory_id=territory.id,
                name=territory.name,
                kind="lightning",
                distance_m=nearest_m,
                direction=None,
                severity=None,
                sensors=[],
                seen_at=None,
            )
        )

    sent = failed = 0
    for user_id, dangers in per_user.items():
        user = users[user_id]
        dangers.sort(key=_rank)
        subject, body = alert_email(
            user.locale, dangers, settings.app_url, lightning_config["window_minutes"], now
        )
        try:
            send(message(settings, user.email, subject, body))
        except SEND_ERRORS as exc:
            # Nothing is marked, so the next run tries again.
            log.warning("alert email to user %s not sent: %s", user_id, exc)
            failed += 1
            continue
        for risk in fire_marks[user_id]:
            risk.notified_severity = risk.severity
        for territory in lightning_marks[user_id]:
            territory.lightning_notified_at = now
        session.add(
            AlertEmail(
                user_id=user_id,
                sent_at=now,
                dangers=[
                    asdict(d) | {"seen_at": d.seen_at and d.seen_at.isoformat()} for d in dangers
                ],
                processing_version=version,
            )
        )
        session.commit()
        sent += 1
    return {"emails_sent": sent, "emails_failed": failed}
