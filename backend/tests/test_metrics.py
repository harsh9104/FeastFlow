from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.db.session import SessionLocal
from app.models.metrics import AppMetric
from app.services import metrics_service as ms
from app.services.metrics_collector import Collector

C = "/api/v1/admin/cloud"


def minute_ago(n: int) -> datetime:
    return datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=n)


def add_rows(rows):
    with SessionLocal() as db:
        db.add_all([AppMetric(**r) for r in rows])
        db.commit()


def row(minute, inst="i-1", worker=1, req=100, err=0, p50=20.0, p90=80.0, cpu=30.0, mem=40.0):
    return dict(
        instance_id=inst,
        worker=worker,
        minute=minute,
        request_count=req,
        error_5xx=err,
        latency_sum_ms=req * p50,
        p50_ms=p50,
        p90_ms=p90,
        cpu_pct=cpu,
        mem_pct=mem,
    )


@pytest.fixture
def admin(make_user, auth_header):
    make_user("admin@x.com", role="ADMIN")
    return auth_header("admin@x.com")


def test_requires_admin(client, make_user, auth_header):
    make_user("c@x.com")
    h = auth_header("c@x.com")
    for p in ("metrics", "instances", "alarms", "scaling-activities"):
        assert client.get(f"{C}/{p}", headers=h).status_code == 403
        assert client.get(f"{C}/{p}").status_code == 401


def test_metrics_empty_has_all_series(client, admin):
    d = client.get(f"{C}/metrics?range=15m", headers=admin).json()
    assert d["provider"] == "local" and d["period_s"] == 60
    assert set(d["series"]) == set(ms.SERIES)
    assert "rds_cpu" in d["unavailable"]
    assert len(d["series"]["cpu_avg"]["points"]) == 16
    assert all(p["v"] is None for p in d["series"]["cpu_avg"]["points"])
    assert all(p["v"] == 0 for p in d["series"]["request_count"]["points"])


def test_invalid_range(client, admin):
    r = client.get(f"{C}/metrics?range=9y", headers=admin)
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_RANGE"


def test_metrics_aggregate_workers_and_instances(client, admin):
    m = minute_ago(2)
    add_rows(
        [
            row(m, "i-1", 1, req=100, err=2, p50=10.0, p90=50.0, cpu=20.0, mem=30.0),
            row(m, "i-1", 2, req=300, err=0, p50=30.0, p90=90.0, cpu=40.0, mem=50.0),
            row(m, "i-2", 1, req=100, err=3, p50=20.0, p90=60.0, cpu=60.0, mem=70.0),
        ]
    )
    d = client.get(f"{C}/metrics?range=15m", headers=admin).json()["series"]
    pt = {k: next(p["v"] for p in s["points"] if p["t"] == m.isoformat()) for k, s in d.items()}
    assert pt["request_count"] == 500 and pt["http_5xx"] == 5
    # request-weighted latency: (10*100 + 30*300 + 20*100) / 500 ms, reported in seconds
    assert pt["target_response_time_p50"] == pytest.approx(0.024, abs=1e-4)
    assert pt["cpu_avg"] == pytest.approx(40.0) and pt["mem_used_pct"] == pytest.approx(50.0)
    assert pt["healthy_hosts"] == 2 and pt["in_service_instances"] == 2
    assert pt["unhealthy_hosts"] == 0


def test_longer_ranges_rebucket(client, admin):
    add_rows([row(minute_ago(5), req=10), row(minute_ago(6), "i-1", 1, req=20)])
    d = client.get(f"{C}/metrics?range=3h", headers=admin).json()
    assert d["period_s"] == 300
    assert sum(p["v"] for p in d["series"]["request_count"]["points"]) == 30


def test_instances(client, admin):
    add_rows([row(minute_ago(1), "i-live"), row(minute_ago(30), "i-old")])
    got = {i["instance_id"]: i for i in client.get(f"{C}/instances", headers=admin).json()}
    assert got["i-live"]["lifecycle_state"] == "InService"
    assert got["i-live"]["health_status"] == "Healthy"
    assert got["i-old"]["lifecycle_state"] == "Offline"


def test_alarms(client, admin):
    states = {a["name"]: a["state"] for a in client.get(f"{C}/alarms", headers=admin).json()}
    assert states["feastflow-high-cpu"] == "INSUFFICIENT_DATA"

    add_rows(
        [row(minute_ago(i), cpu=90.0, mem=10.0, p90=2000.0, req=100, err=10) for i in (1, 2, 3)]
    )
    states = {a["name"]: a["state"] for a in client.get(f"{C}/alarms", headers=admin).json()}
    assert states["feastflow-high-cpu"] == "ALARM"
    assert states["feastflow-high-latency"] == "ALARM"
    assert states["feastflow-5xx-rate"] == "ALARM"
    assert states["feastflow-high-memory"] == "OK"
    assert states["feastflow-unhealthy-hosts"] == "OK"


def test_scaling_activities_empty_locally(client, admin):
    assert client.get(f"{C}/scaling-activities", headers=admin).json() == []


def test_collector_flush_roundtrip():
    c = Collector()
    now = datetime.now(UTC)
    for v in (10, 20, 30, 40, 1000):
        c.record(200, v, now)
    c.record(500, 5, now)
    c.flush(now)
    c.record(200, 1, now)  # same minute again: flush overwrites the worker's own row
    c.flush(now)
    with SessionLocal() as db:
        r = db.query(AppMetric).one()
        assert r.request_count == 7 and r.error_5xx == 1
        assert r.p90_ms == 1000


def test_window_summary():
    add_rows(
        [
            row(minute_ago(3), "i-1", cpu=20.0),
            row(minute_ago(2), "i-1", cpu=80.0),
            row(minute_ago(2), "i-2", cpu=60.0),
        ]
    )
    with SessionLocal() as db:
        s = ms.LocalProvider().window_summary(db, minute_ago(4), datetime.now(UTC))
    assert s["peak_cpu"] == 70.0 and s["avg_cpu"] == pytest.approx(45.0)
    assert s["min_instances"] == 1 and s["max_instances"] == 2


def test_cloudwatch_provider_parses_results():
    prov = ms.CloudWatchProvider.__new__(ms.CloudWatchProvider)
    prov.s = ms.get_settings()
    prov.cw = MagicMock()
    t = datetime(2026, 1, 1, tzinfo=UTC)

    def fake(**kw):
        return {
            "MetricDataResults": [
                {"Id": q["Id"], "Timestamps": [t + timedelta(minutes=1), t], "Values": [2.0, 1.0]}
                for q in kw["MetricDataQueries"]
            ]
        }

    prov.cw.get_metric_data.side_effect = fake
    out = prov.metrics(None, "1h")
    assert out["provider"] == "cloudwatch"
    pts = out["series"]["cpu_avg"]["points"]
    assert [p["v"] for p in pts] == [1.0, 2.0]  # sorted ascending
    assert set(out["series"]) == set(ms.SERIES)
    queries = prov.cw.get_metric_data.call_args.kwargs["MetricDataQueries"]
    stats = {q["MetricStat"]["Stat"] for q in queries}
    assert {"p50", "p90", "Sum", "Average"} <= stats
    s = prov.window_summary(None, t, t + timedelta(minutes=5))
    assert s["peak_cpu"] == 2.0 and s["min_instances"] == 1 and s["max_instances"] == 2


def test_load_test_run_gets_resource_columns(client, admin, monkeypatch):
    from app.services import load_test_service as lt

    stats = {
        "state": "running",
        "stats": [
            {
                "name": "Aggregated",
                "num_requests": 5,
                "num_failures": 0,
                "avg_response_time": 1.0,
                "median_response_time": 1,
                "response_time_percentile_0.95": 2,
            }
        ],
    }
    monkeypatch.setattr(lt, "_locust", lambda *a, **k: stats)
    body = {"scenario": "NORMAL"}
    rid = client.post("/api/v1/admin/load-tests", json=body, headers=admin).json()["run_id"]
    add_rows([row(minute_ago(0), "i-1", cpu=55.0), row(minute_ago(0), "i-2", cpu=65.0)])
    run = client.post(f"/api/v1/admin/load-tests/{rid}/stop", headers=admin).json()["run"]
    assert run["status"] == "STOPPED"
    assert run["peak_cpu_percent"] == 60.0 and run["max_instances"] == 2
    assert run["estimated_cost_usd"] is not None  # ~1 s run rounds to $0.0000
