"""Availability against the SLA in docs/14-sla.md (SLA-01), at one-minute resolution.

A measured minute is UNAVAILABLE when no healthy target was reported (HealthyHostCount = 0) or the
5xx ratio exceeds 5 %. Minutes with no data at all (environment not running, e.g. the Learner Lab
session was stopped) are excluded from the measurement, not counted as downtime.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.services import metrics_service

TARGET_PCT = 99.5
MAX_OUTAGE_MIN = 30
ERROR_RATIO = 0.05
MAX_WINDOW = timedelta(days=7)


def _minute(ts: datetime) -> datetime:
    return ts.astimezone(UTC).replace(second=0, microsecond=0)


def classify(sample: dict) -> str | None:
    """None = available, otherwise the reason this minute counts as downtime."""
    if sample["hosts"] == 0:
        return "no healthy hosts"
    if sample["req"] > 0 and sample["err"] / sample["req"] > ERROR_RATIO:
        return "5xx ratio above 5 %"
    return None


def availability(db: Session, start: datetime, end: datetime) -> dict:
    start, end = _minute(start), _minute(end)
    if end <= start:
        raise AppError(422, "INVALID_PERIOD", "'to' must be after 'from'")
    if end - start > MAX_WINDOW:
        raise AppError(422, "INVALID_PERIOD", "Period is limited to 7 days")

    data = metrics_service.get_provider().minutes(db, start, end)
    measured = unavailable = no_data = 0
    outages: list[dict] = []
    current: dict | None = None

    t = start
    while t < end:
        sample = data.get(t)
        if sample is None:
            no_data += 1
            current = None  # a gap with no data does not extend or split an outage silently
        else:
            measured += 1
            reason = classify(sample)
            if reason:
                unavailable += 1
                if current and current["reason"] == reason and current["end"] == t:
                    current["end"] = t + timedelta(minutes=1)
                    current["minutes"] += 1
                else:
                    current = {
                        "start": t,
                        "end": t + timedelta(minutes=1),
                        "minutes": 1,
                        "reason": reason,
                    }
                    outages.append(current)
            else:
                current = None
        t += timedelta(minutes=1)

    pct = round(100 * (1 - unavailable / measured), 4) if measured else None
    longest = max((o["minutes"] for o in outages), default=0)
    breaches = []
    if pct is not None and pct < TARGET_PCT:
        breaches.append(f"availability {pct} % is below the {TARGET_PCT} % target")
    if longest > MAX_OUTAGE_MIN:
        breaches.append(f"an outage lasted {longest} consecutive minutes (limit {MAX_OUTAGE_MIN})")

    return {
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "provider": metrics_service.get_provider().name,
        "target_pct": TARGET_PCT,
        "measured_minutes": measured,
        "no_data_minutes": no_data,
        "unavailable_minutes": unavailable,
        "availability_pct": pct,
        "allowed_downtime_minutes": round(measured * (1 - TARGET_PCT / 100), 2),
        "longest_outage_minutes": longest,
        "target_met": None if pct is None else not breaches,
        "breach_reasons": breaches,
        "outages": [
            {
                "start": o["start"].isoformat(),
                "end": o["end"].isoformat(),
                "minutes": o["minutes"],
                "reason": o["reason"],
            }
            for o in outages
        ],
    }
