"""Builds LOAD_TEST / COST / COMPARISON reports and stores them in S3 (when S3_BUCKET is set)
or in a local folder. Downloads use short-lived signed links, mirroring S3 pre-signed URLs."""

import csv
import io
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import ALGO
from app.models.load_test import LoadTestRun
from app.models.report import Report
from app.models.user import User
from app.services import cost_service, metrics_service

EXT = {"JSON": "json", "CSV": "csv", "MD": "md"}
MIME = {"JSON": "application/json", "CSV": "text/csv", "MD": "text/markdown"}
URL_TTL = 300


# ------------------------------------------------------------------ storage
def _local_path(key: str) -> Path:
    root = Path(get_settings().reports_dir).resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise AppError(400, "BAD_KEY", "Invalid report key")
    return path


def _s3():
    import boto3

    return boto3.client("s3", region_name=get_settings().aws_region)


def store(key: str, data: bytes, fmt: str) -> None:
    bucket = get_settings().s3_bucket
    if bucket:
        _s3().put_object(Bucket=bucket, Key=key, Body=data, ContentType=MIME[fmt])
    else:
        path = _local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def download_url(report: Report) -> str:
    bucket = get_settings().s3_bucket
    if bucket:
        return _s3().generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": report.s3_key,
                "ResponseContentDisposition": f'attachment; filename="{Path(report.s3_key).name}"',
            },
            ExpiresIn=URL_TTL,
        )
    token = jwt.encode(
        {
            "rid": report.id,
            "purpose": "report",
            "exp": datetime.now(UTC) + timedelta(seconds=URL_TTL),
        },
        get_settings().jwt_secret,
        algorithm=ALGO,
    )
    return f"/api/v1/reports/file?t={token}"


def read_via_token(db: Session, token: str) -> tuple[Report, bytes]:
    try:
        claims = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGO])
        if claims.get("purpose") != "report":
            raise jwt.InvalidTokenError("wrong purpose")
        report = db.get(Report, int(claims["rid"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise AppError(401, "UNAUTHORIZED", "Invalid or expired download link") from None
    path = _local_path(report.s3_key) if report else None
    if report is None or not path.is_file():
        raise AppError(404, "NOT_FOUND", "Report file not found")
    return report, path.read_bytes()


# ------------------------------------------------------------------ data
def _window(run: LoadTestRun) -> tuple[datetime, datetime]:
    return run.started_at, run.ended_at or datetime.now(UTC)


def run_summary(run: LoadTestRun) -> dict:
    raw = run.raw_stats or {}
    total, failed = run.total_requests, run.failed_requests
    orders = raw.get("orders")
    cost = float(run.estimated_cost_usd) if run.estimated_cost_usd is not None else None

    def f(v):
        return float(v) if v is not None else None

    return {
        "run_id": run.id,
        "scenario": run.scenario,
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "duration_seconds": run.duration_seconds,
        "peak_users": run.target_users,
        "total_requests": total,
        "failed_requests": failed,
        "error_rate_pct": round(100 * failed / total, 3) if total else None,
        "avg_response_ms": f(run.avg_response_ms),
        "p95_response_ms": f(run.p95_response_ms),
        "peak_rps": f(run.peak_rps),
        "avg_cpu_pct": f(run.avg_cpu_percent),
        "peak_cpu_pct": f(run.peak_cpu_percent),
        "min_instances": run.min_instances,
        "max_instances": run.max_instances,
        "orders_in_window": orders,
        "estimated_cost_usd": cost,
        "cost_per_1000_orders_usd": round(cost / orders * 1000, 4)
        if cost is not None and orders
        else None,
        "endpoints": raw.get("endpoints", []),
    }


def _scaling_events(db: Session, run: LoadTestRun) -> int | None:
    provider = metrics_service.get_provider()
    if provider.name == "local":
        return None
    start, end = _window(run)
    return sum(
        1
        for a in provider.scaling_activities(db)
        if start <= datetime.fromisoformat(a["start_time"]) <= end + timedelta(minutes=30)
    )


def _delta(a, b):
    return round(b - a, 4) if isinstance(a, int | float) and isinstance(b, int | float) else None


def comparison_data(db: Session, normal: LoadTestRun, festival: LoadTestRun) -> dict:
    n, f = run_summary(normal), run_summary(festival)
    n_scale, f_scale = _scaling_events(db, normal), _scaling_events(db, festival)

    def rng(s):
        if s["min_instances"] is None:
            return None
        return f"{s['min_instances']} -> {s['max_instances']}"

    rows = [
        ("Peak users", n["peak_users"], f["peak_users"]),
        ("Peak RPS", n["peak_rps"], f["peak_rps"]),
        ("Total requests", n["total_requests"], f["total_requests"]),
        ("p95 latency (ms)", n["p95_response_ms"], f["p95_response_ms"]),
        ("Error rate (%)", n["error_rate_pct"], f["error_rate_pct"]),
        ("Avg CPU (%)", n["avg_cpu_pct"], f["avg_cpu_pct"]),
        ("Peak CPU (%)", n["peak_cpu_pct"], f["peak_cpu_pct"]),
        ("Instances min -> max", rng(n), rng(f)),
        ("Scaling events", n_scale, f_scale),
        ("Estimated cost (USD)", n["estimated_cost_usd"], f["estimated_cost_usd"]),
        (
            "Cost per 1,000 orders (USD)",
            n["cost_per_1000_orders_usd"],
            f["cost_per_1000_orders_usd"],
        ),
    ]
    return {
        "normal": n,
        "festival": f,
        "metrics_provider": metrics_service.get_provider().name,
        "rows": [
            {"metric": m, "normal": a, "festival": b, "delta": _delta(a, b)} for m, a, b in rows
        ],
    }


def _pick_runs(db: Session, run_ids: list[int] | None) -> tuple[LoadTestRun, LoadTestRun]:
    if run_ids:
        runs = [db.get(LoadTestRun, i) for i in run_ids]
        if any(r is None for r in runs):
            raise AppError(404, "NOT_FOUND", "Load test run not found")
        by = {r.scenario: r for r in runs}
        if len(runs) != 2 or set(by) != {"NORMAL", "FESTIVAL"}:
            raise AppError(
                422, "NEED_TWO_SCENARIOS", "Provide exactly one NORMAL and one FESTIVAL run"
            )
    else:
        by = {}
        for sc in ("NORMAL", "FESTIVAL"):
            r = db.scalar(
                select(LoadTestRun)
                .where(LoadTestRun.scenario == sc, LoadTestRun.status.in_(["COMPLETED", "STOPPED"]))
                .order_by(LoadTestRun.id.desc())
                .limit(1)
            )
            if r is None:
                raise AppError(
                    422,
                    "NEED_TWO_SCENARIOS",
                    f"No finished {sc} run yet. Run both scenarios first.",
                )
            by[sc] = r
    return by["NORMAL"], by["FESTIVAL"]


# ------------------------------------------------------------------ rendering
def _fmt(v) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:,.4f}".rstrip("0").rstrip(".")
    return str(v)


def _md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(_fmt(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _csv(rows: list[list], header: list[str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows([["" if c is None else c for c in r] for r in rows])
    return buf.getvalue()


def render(report_type: str, fmt: str, data: dict) -> bytes:
    if fmt == "JSON":
        return json.dumps(data, indent=2, default=str).encode()

    if report_type == "COMPARISON":
        rows = [[r["metric"], r["normal"], r["festival"], r["delta"]] for r in data["rows"]]
        if fmt == "CSV":
            return _csv(rows, ["metric", "normal", "festival", "delta"]).encode()
        md = (
            f"# FeastFlow: Normal day vs Festival day\n\nGenerated {data['generated_at']} "
            f"(metrics: {data['metrics_provider']}).\n\n"
            + _md_table(["Metric", "Normal", "Festival", "Delta"], rows)
            + f"\n\nNormal = run #{data['normal']['run_id']}, Festival = run #{data['festival']['run_id']}.\n"
        )
        return md.encode()

    if report_type == "COST":
        rows = [
            [i["service"], i["usage"], i["unit"], i["rate_usd"], i["cost_usd"]]
            for i in data["line_items"]
        ]
        if fmt == "CSV":
            rows.append(["TOTAL", "", "", "", data["total_usd"]])
            return _csv(rows, ["service", "usage", "unit", "rate_usd", "cost_usd"]).encode()
        p = data["period"]
        md = (
            f"# FeastFlow cost estimate\n\nPeriod: {p['from']} to {p['to']} ({p['hours']} h)\n\n"
            + _md_table(["Service", "Usage", "Unit", "Rate (USD)", "Cost (USD)"], rows)
            + f"\n\n**Total: ${data['total_usd']}**"
            + (
                f" · {data['orders']} orders · ${data['cost_per_1000_orders_usd']} per 1,000 orders"
                if data["orders"]
                else ""
            )
            + "\n\n## Assumptions\n"
            + "\n".join(f"- {a}" for a in data["assumptions"])
            + "\n"
        )
        return md.encode()

    # LOAD_TEST
    run = data["run"]
    scalars = [[k, v] for k, v in run.items() if k != "endpoints"]
    if fmt == "CSV":
        out = _csv(scalars, ["field", "value"])
        out += "\n" + _csv(
            [
                [e["name"], e["requests"], e["failures"], e["avg_ms"], e["p95_ms"]]
                for e in run["endpoints"]
            ],
            ["endpoint", "requests", "failures", "avg_ms", "p95_ms"],
        )
        return out.encode()
    md = f"# Load test run #{run['run_id']} ({run['scenario']})\n\n" + _md_table(
        ["Field", "Value"], scalars
    )
    if run["endpoints"]:
        md += "\n\n## Endpoints\n\n" + _md_table(
            ["Endpoint", "Requests", "Failures", "Avg ms", "p95 ms"],
            [
                [e["name"], e["requests"], e["failures"], e["avg_ms"], e["p95_ms"]]
                for e in run["endpoints"]
            ],
        )
    return (md + "\n").encode()


# ------------------------------------------------------------------ public API
def create_report(
    db: Session,
    admin: User,
    report_type: str,
    fmt: str,
    run_ids: list[int] | None,
    start: datetime | None,
    end: datetime | None,
) -> Report:
    now = datetime.now(UTC)
    run_ref: int | None = None
    if report_type == "LOAD_TEST":
        if not run_ids or len(run_ids) != 1:
            raise AppError(422, "RUN_REQUIRED", "LOAD_TEST reports need exactly one run_id")
        run = db.get(LoadTestRun, run_ids[0])
        if run is None:
            raise AppError(404, "NOT_FOUND", "Load test run not found")
        if run.status == "RUNNING":
            raise AppError(409, "RUN_IN_PROGRESS", "Wait for the run to finish")
        run_ref = run.id
        data = {"generated_at": now.isoformat(), "run": run_summary(run)}
    elif report_type == "COST":
        end = end or now
        start = start or end - timedelta(hours=1)
        data = {"generated_at": now.isoformat(), **cost_service.estimate(db, start, end)}
    else:
        normal, festival = _pick_runs(db, run_ids)
        data = {"generated_at": now.isoformat(), **comparison_data(db, normal, festival)}

    key = f"reports/{now:%Y/%m}/{report_type.lower()}-{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.{EXT[fmt]}"
    store(key, render(report_type, fmt, data), fmt)
    report = Report(
        report_type=report_type,
        load_test_run_id=run_ref,
        created_by=admin.id,
        s3_key=key,
        format=fmt,
    )
    db.add(report)
    db.commit()
    return report
