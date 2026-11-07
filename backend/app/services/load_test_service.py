"""Controls the Locust generator over its HTTP API and records each run.

State lives in the database (not in memory) because app instances are stateless: any instance can
start a run, and whichever instance serves the next poll after the duration elapses finalizes it.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.load_test import LoadTestRun
from app.models.user import User
from app.services import cost_service, metrics_service

log = logging.getLogger("app.loadtest")
SCENARIOS: dict[str, dict] = json.loads(
    (Path(__file__).parent.parent / "config" / "scenarios.json").read_text()
)


def _locust(path: str, method: str = "GET", data: dict | None = None) -> dict:
    url = get_settings().locust_url.rstrip("/") + path
    r = httpx.request(method, url, data=data, timeout=5.0)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:
        return {}


def scenarios() -> list[dict]:
    return [
        {k: s[k] for k in ("name", "description", "users", "spawn_rate", "duration_s")}
        for s in SCENARIOS.values()
    ]


def _live() -> dict | None:
    """Current Locust numbers, or None when the generator is unreachable."""
    try:
        d = _locust("/stats/requests")
    except Exception:
        return None
    agg = next((s for s in d.get("stats", []) if s["name"] == "Aggregated"), {})
    return {
        "state": d.get("state"),
        "users": d.get("user_count", 0),
        "rps": d.get("total_rps", 0.0),
        "fail_ratio": d.get("fail_ratio", 0.0),
        "total_requests": agg.get("num_requests", 0),
        "failed_requests": agg.get("num_failures", 0),
        "avg_response_ms": agg.get("avg_response_time", 0.0),
        "p50_response_ms": agg.get("median_response_time", 0.0),
        "p95_response_ms": agg.get("response_time_percentile_0.95", 0.0),
        "endpoints": [
            {
                "name": s["name"],
                "requests": s["num_requests"],
                "failures": s["num_failures"],
                "avg_ms": round(s["avg_response_time"], 1),
                "p95_ms": s.get("response_time_percentile_0.95"),
            }
            for s in d.get("stats", [])
            if s["name"] != "Aggregated"
        ],
    }


def start(
    db: Session,
    admin: User,
    scenario: str,
    users: int | None = None,
    duration_s: int | None = None,
) -> LoadTestRun:
    cfg = SCENARIOS[scenario]
    run = LoadTestRun(
        scenario=scenario,
        status="RUNNING",
        started_by=admin.id,
        target_users=users or cfg["users"],
        spawn_rate=cfg["spawn_rate"],
        duration_seconds=duration_s or cfg["duration_s"],
        started_at=datetime.now(UTC),
        raw_stats={"peak_rps": 0.0, "peak_users": 0},
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "LOAD_TEST_ALREADY_RUNNING", "A load test is already running") from None

    try:
        _locust("/stats/reset")
        _locust(
            "/swarm",
            "POST",
            {
                "user_count": run.target_users,
                "spawn_rate": run.spawn_rate,
                "run_time": f"{run.duration_seconds}s",
                "user_classes": cfg["user_class"],
            },
        )
    except Exception as exc:
        log.warning("locust unreachable: %s", exc)
        run.status = "FAILED"
        run.ended_at = datetime.now(UTC)
        run.raw_stats = {"error": str(exc)}
        db.commit()
        raise AppError(
            503, "LOAD_GENERATOR_UNAVAILABLE", "Cannot reach the Locust load generator"
        ) from None
    return run


def _finalize(db: Session, run_id: int, status: str) -> LoadTestRun:
    """Close a run exactly once. The row lock makes concurrent finalizers safe."""
    run = db.scalars(select(LoadTestRun).where(LoadTestRun.id == run_id).with_for_update()).one()
    if run.status != "RUNNING":
        db.rollback()
        return run
    live = _live()
    try:
        _locust("/stop")
    except Exception:
        pass
    raw = dict(run.raw_stats or {})
    now = datetime.now(UTC)
    if status == "COMPLETED":
        run.ended_at = min(now, run.started_at + timedelta(seconds=run.duration_seconds))
    else:
        run.ended_at = now
    if live is None:
        run.status = "FAILED"
        raw["error"] = "load generator unreachable at finalization"
    else:
        run.status = status
        run.total_requests = live["total_requests"]
        run.failed_requests = live["failed_requests"]
        run.avg_response_ms = round(live["avg_response_ms"], 2)
        run.p95_response_ms = live["p95_response_ms"]
        elapsed = max((run.ended_at - run.started_at).total_seconds(), 1)
        # Locust has no peak RPS: use the highest polled value, never below the mean.
        run.peak_rps = round(max(raw.get("peak_rps", 0.0), live["total_requests"] / elapsed), 2)
        raw["endpoints"] = live["endpoints"]
    summary = metrics_service.safe_window_summary(db, run.started_at, run.ended_at)
    run.avg_cpu_percent = summary.get("avg_cpu")
    run.peak_cpu_percent = summary.get("peak_cpu")
    run.min_instances = summary.get("min_instances")
    run.max_instances = summary.get("max_instances")
    raw["resources"] = summary
    try:
        cost = cost_service.estimate(db, run.started_at, run.ended_at, requests=run.total_requests)
        run.estimated_cost_usd = cost["total_usd"]
        raw["orders"] = cost["orders"]
        raw["cost_items"] = cost["line_items"]
    except Exception:
        log.exception("cost estimate failed for run %s", run.id)
    run.raw_stats = raw
    db.commit()
    return run


def get_with_live(db: Session, run_id: int) -> tuple[LoadTestRun, dict | None]:
    run = db.get(LoadTestRun, run_id)
    if run is None:
        raise AppError(404, "NOT_FOUND", "Load test run not found")
    if run.status != "RUNNING":
        return run, None
    elapsed = (datetime.now(UTC) - run.started_at).total_seconds()
    if elapsed >= run.duration_seconds + 2:  # lazy finalization
        return _finalize(db, run_id, "COMPLETED"), None
    live = _live()
    if live:
        raw = dict(run.raw_stats or {})
        raw["peak_rps"] = max(raw.get("peak_rps", 0.0), live["rps"])
        raw["peak_users"] = max(raw.get("peak_users", 0), live["users"])
        run.raw_stats = raw
        db.commit()
    live_out = dict(live) if live else None
    if live_out is not None:
        live_out["elapsed_s"] = int(elapsed)
    return run, live_out


def stop(db: Session, run_id: int) -> LoadTestRun:
    run = db.get(LoadTestRun, run_id)
    if run is None:
        raise AppError(404, "NOT_FOUND", "Load test run not found")
    if run.status != "RUNNING":
        raise AppError(409, "NOT_RUNNING", f"Run {run_id} is {run.status}, not RUNNING")
    return _finalize(db, run_id, "STOPPED")


def list_runs(db: Session, page: int, page_size: int) -> tuple[list[LoadTestRun], int]:
    from sqlalchemy import func

    total = db.scalar(select(func.count()).select_from(LoadTestRun))
    rows = db.scalars(
        select(LoadTestRun)
        .order_by(LoadTestRun.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return list(rows), total
