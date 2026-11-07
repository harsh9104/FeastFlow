from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import jwt
import pytest

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.load_test import LoadTestRun
from app.models.metrics import AppMetric
from app.services import report_service

A = "/api/v1/admin"


def minute_ago(n: int) -> datetime:
    return datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=n)


@pytest.fixture
def admin(make_user, auth_header):
    make_user("admin@x.com", role="ADMIN")
    return auth_header("admin@x.com")


def two_instances_for_an_hour():
    with SessionLocal() as db:
        db.add_all(
            [
                AppMetric(instance_id=f"i-{n}", worker=1, minute=minute_ago(m), request_count=0)
                for n in (1, 2)
                for m in range(1, 61)
            ]
        )
        db.commit()


def add_run(scenario, uid=1, **kw):
    now = datetime.now(UTC)
    vals = dict(
        scenario=scenario,
        status="COMPLETED",
        started_by=uid,
        target_users=25 if scenario == "NORMAL" else 250,
        spawn_rate=5,
        duration_seconds=600,
        started_at=now - timedelta(minutes=20),
        ended_at=now - timedelta(minutes=10),
        total_requests=1000,
        failed_requests=10,
        avg_response_ms=Decimal("40"),
        p95_response_ms=Decimal("120") if scenario == "NORMAL" else Decimal("480"),
        peak_rps=Decimal("7") if scenario == "NORMAL" else Decimal("120"),
        peak_cpu_percent=Decimal("30"),
        min_instances=2,
        max_instances=2 if scenario == "NORMAL" else 4,
        estimated_cost_usd=Decimal("0.02") if scenario == "NORMAL" else Decimal("0.05"),
        raw_stats={
            "orders": 100,
            "endpoints": [
                {"name": "GET /menu", "requests": 500, "failures": 0, "avg_ms": 10.0, "p95_ms": 30}
            ],
        },
    )
    vals.update(kw)
    with SessionLocal() as db:
        r = LoadTestRun(**vals)
        db.add(r)
        db.commit()
        return r.id


def test_requires_admin(client, make_user, auth_header):
    make_user("c@x.com")
    h = auth_header("c@x.com")
    for method, path in [
        ("get", f"{A}/costs/rates"),
        ("get", f"{A}/costs/estimate"),
        ("post", f"{A}/reports"),
        ("get", f"{A}/reports"),
        ("get", f"{A}/reports/1/download"),
    ]:
        assert getattr(client, method)(path, headers=h).status_code == 403
        assert getattr(client, method)(path).status_code == 401


def test_rates(client, admin):
    d = client.get(f"{A}/costs/rates", headers=admin).json()
    assert d["region"] == "us-east-1" and d["rates"]["ec2_t3_micro_hour"] == 0.0104


def test_estimate_one_hour_two_instances_matches_doc_baseline(client, admin):
    two_instances_for_an_hour()
    d = client.get(
        f"{A}/costs/estimate",
        params={"from": minute_ago(60).isoformat(), "to": minute_ago(0).isoformat()},
        headers=admin,
    ).json()
    items = {i["service"]: i for i in d["line_items"]}
    assert len(items) == 9
    assert items["EC2 t3.micro (app instances)"]["usage"] == pytest.approx(2.0, abs=1e-3)
    assert d["period"]["hours"] == 1.0
    # docs/12 section 12.4: about $0.13 per hour for the baseline fleet
    assert d["total_usd"] == pytest.approx(0.1309, abs=2e-4)
    assert d["total_usd"] == pytest.approx(sum(i["cost_usd"] for i in d["line_items"]), abs=1e-4)
    assert any("measured" in a for a in d["assumptions"])


def test_estimate_scales_with_instances(client, admin):
    p = {"from": minute_ago(60).isoformat(), "to": minute_ago(0).isoformat()}
    idle = client.get(f"{A}/costs/estimate", params=p, headers=admin).json()  # no data: assumed 1
    two_instances_for_an_hour()
    busy = client.get(f"{A}/costs/estimate", params=p, headers=admin).json()
    assert busy["total_usd"] > idle["total_usd"]
    assert any("assumed" in a for a in idle["assumptions"])


def test_estimate_validation_and_run(client, admin):
    now = datetime.now(UTC)
    bad = {"from": now.isoformat(), "to": (now - timedelta(hours=1)).isoformat()}
    assert client.get(f"{A}/costs/estimate", params=bad, headers=admin).status_code == 422
    huge = {"from": (now - timedelta(days=40)).isoformat(), "to": now.isoformat()}
    assert client.get(f"{A}/costs/estimate", params=huge, headers=admin).status_code == 422
    assert client.get(f"{A}/costs/estimate?run_id=999", headers=admin).status_code == 404

    rid = add_run("NORMAL", uid=1)
    d = client.get(f"{A}/costs/estimate?run_id={rid}", headers=admin).json()
    assert d["run_id"] == rid and d["requests"] == 1000
    assert d["period"]["hours"] == pytest.approx(10 / 60, abs=1e-3)


def test_cost_report_all_formats_and_download(client, admin):
    two_instances_for_an_hour()
    body = {
        "report_type": "COST",
        "from": minute_ago(60).isoformat(),
        "to": minute_ago(0).isoformat(),
    }
    out = {}
    for fmt in ("JSON", "CSV", "MD"):
        r = client.post(f"{A}/reports", json={**body, "format": fmt}, headers=admin)
        assert r.status_code == 201, r.text
        assert r.json()["s3_key"].startswith("reports/") and r.json()["s3_key"].endswith(
            {"JSON": ".json", "CSV": ".csv", "MD": ".md"}[fmt]
        )
        d = client.get(f"{A}/reports/{r.json()['report_id']}/download", headers=admin).json()
        assert d["expires_in"] == 300 and d["url"].startswith("/api/v1/reports/file?t=")
        f = client.get(d["url"])  # signed link needs no Authorization header
        assert f.status_code == 200 and "attachment" in f.headers["content-disposition"]
        out[fmt] = f.text
    assert '"total_usd"' in out["JSON"]
    assert out["CSV"].splitlines()[0] == "service,usage,unit,rate_usd,cost_usd"
    assert out["CSV"].strip().splitlines()[-1].startswith("TOTAL")
    assert "# FeastFlow cost estimate" in out["MD"] and "**Total: $" in out["MD"]
    assert client.get(f"{A}/reports", headers=admin).json()["total"] == 3


def test_download_link_security(client, admin):
    rid = client.post(f"{A}/reports", json={"report_type": "COST"}, headers=admin).json()[
        "report_id"
    ]
    assert client.get("/api/v1/reports/file?t=garbage").status_code == 401
    secret = get_settings().jwt_secret
    other = jwt.encode(
        {"rid": rid, "purpose": "login", "exp": datetime.now(UTC) + timedelta(minutes=1)},
        secret,
        "HS256",
    )
    assert client.get(f"/api/v1/reports/file?t={other}").status_code == 401
    expired = jwt.encode(
        {"rid": rid, "purpose": "report", "exp": datetime.now(UTC) - timedelta(seconds=5)},
        secret,
        "HS256",
    )
    assert client.get(f"/api/v1/reports/file?t={expired}").status_code == 401
    assert client.get(f"{A}/reports/9999/download", headers=admin).status_code == 404


def test_load_test_report(client, admin):
    rid = add_run("FESTIVAL")
    for fmt, needle in (("MD", "## Endpoints"), ("CSV", "endpoint,requests"), ("JSON", '"run_id"')):
        r = client.post(
            f"{A}/reports",
            json={"report_type": "LOAD_TEST", "run_ids": [rid], "format": fmt},
            headers=admin,
        )
        assert r.status_code == 201
        url = client.get(f"{A}/reports/{r.json()['report_id']}/download", headers=admin).json()[
            "url"
        ]
        assert needle in client.get(url).text
    assert client.get(f"{A}/reports", headers=admin).json()["items"][0]["load_test_run_id"] == rid

    assert (
        client.post(f"{A}/reports", json={"report_type": "LOAD_TEST"}, headers=admin).status_code
        == 422
    )
    assert (
        client.post(
            f"{A}/reports", json={"report_type": "LOAD_TEST", "run_ids": [999]}, headers=admin
        ).status_code
        == 404
    )
    running = add_run("NORMAL", status="RUNNING", ended_at=None)
    r = client.post(
        f"{A}/reports", json={"report_type": "LOAD_TEST", "run_ids": [running]}, headers=admin
    )
    assert r.status_code == 409


def test_comparison_report(client, admin):
    body = {"report_type": "COMPARISON", "format": "MD"}
    r = client.post(f"{A}/reports", json=body, headers=admin)
    assert r.status_code == 422 and r.json()["error"]["code"] == "NEED_TWO_SCENARIOS"

    n, f = add_run("NORMAL"), add_run("FESTIVAL")
    r = client.post(f"{A}/reports", json=body, headers=admin)
    assert r.status_code == 201
    url = client.get(f"{A}/reports/{r.json()['report_id']}/download", headers=admin).json()["url"]
    md = client.get(url).text
    assert "| Metric | Normal | Festival | Delta |" in md
    assert "| p95 latency (ms) | 120 | 480 | 360 |" in md
    assert "| Instances min -> max | 2 -> 2 | 2 -> 4 | n/a |" in md
    assert "| Cost per 1,000 orders (USD) | 0.2 | 0.5 | 0.3 |" in md
    assert "| Scaling events | n/a | n/a | n/a |" in md  # local provider cannot know

    r = client.post(
        f"{A}/reports", json={**body, "format": "JSON", "run_ids": [n, f]}, headers=admin
    )
    assert r.status_code == 201
    j = client.get(
        client.get(f"{A}/reports/{r.json()['report_id']}/download", headers=admin).json()["url"]
    ).json()
    assert j["normal"]["run_id"] == n and j["festival"]["run_id"] == f
    row = next(x for x in j["rows"] if x["metric"] == "Peak RPS")
    assert (row["normal"], row["festival"], row["delta"]) == (7.0, 120.0, 113.0)

    assert (
        client.post(f"{A}/reports", json={**body, "run_ids": [n, n]}, headers=admin).status_code
        == 422
    )
    assert (
        client.post(f"{A}/reports", json={**body, "run_ids": [n]}, headers=admin).status_code == 422
    )


def test_s3_storage_branch(monkeypatch):
    s3 = MagicMock()
    s3.generate_presigned_url.return_value = "https://s3.example/signed"
    monkeypatch.setattr(report_service, "_s3", lambda: s3)
    monkeypatch.setattr(get_settings(), "s3_bucket", "my-bucket")
    report_service.store("reports/2026/11/x.json", b"{}", "JSON")
    s3.put_object.assert_called_once()
    assert s3.put_object.call_args.kwargs["Bucket"] == "my-bucket"
    rep = MagicMock(id=1, s3_key="reports/2026/11/x.json")
    assert report_service.download_url(rep) == "https://s3.example/signed"
    assert s3.generate_presigned_url.call_args.kwargs["ExpiresIn"] == 300


def test_report_key_cannot_escape_folder():
    with pytest.raises(Exception):  # noqa: B017
        report_service._local_path("../../etc/passwd")
