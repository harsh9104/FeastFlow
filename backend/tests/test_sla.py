from datetime import UTC, datetime, timedelta

import pytest

from app.db.session import SessionLocal
from app.models.metrics import AppMetric
from app.services import sla_service

URL = "/api/v1/admin/sla/availability"
BASE = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def at(n: int) -> datetime:
    return BASE + timedelta(minutes=n)


def add(minute_offsets, req=100, err=0, inst="i-1"):
    with SessionLocal() as db:
        db.add_all(
            [
                AppMetric(
                    instance_id=inst, worker=1, minute=at(m), request_count=req, error_5xx=err
                )
                for m in minute_offsets
            ]
        )
        db.commit()


def check(start=0, end=100):
    with SessionLocal() as db:
        return sla_service.availability(db, at(start), at(end))


@pytest.fixture
def admin(make_user, auth_header):
    make_user("admin@x.com", role="ADMIN")
    return auth_header("admin@x.com")


def test_perfect_availability():
    add(range(100))
    r = check()
    assert r["measured_minutes"] == 100 and r["unavailable_minutes"] == 0
    assert r["availability_pct"] == 100.0 and r["target_met"] is True
    assert r["breach_reasons"] == [] and r["outages"] == []


def test_a_few_bad_minutes_stay_within_target():
    # 1000 measured minutes with 3 bad ones = 99.7 % (>= 99.5): target met
    add(range(1000))
    add([10, 11, 12], req=100, err=50, inst="i-bad")  # extra worker row pushes the ratio up
    # i-1 gives 100 req / 0 err and i-bad 100 / 50 per minute => 25 % errors in minutes 10-12
    r = check(0, 1000)
    assert r["unavailable_minutes"] == 3
    assert r["availability_pct"] == 99.7 and r["target_met"] is True
    assert r["longest_outage_minutes"] == 3
    assert r["outages"][0]["reason"] == "5xx ratio above 5 %"


def test_availability_below_target_is_a_breach():
    add(range(100))
    add(range(10, 20), req=100, err=100, inst="i-bad")  # 10 bad minutes of 100 => 90 %
    r = check()
    assert r["availability_pct"] == 90.0 and r["target_met"] is False
    assert "below the 99.5 % target" in r["breach_reasons"][0]
    assert r["allowed_downtime_minutes"] == 0.5


def test_long_single_outage_is_a_breach_even_if_percentage_is_fine():
    add(range(1000))
    add(range(100, 135), req=100, err=100, inst="i-bad")  # 35 consecutive bad minutes
    r = check(0, 1000)
    assert r["longest_outage_minutes"] == 35
    assert r["availability_pct"] == pytest.approx(100 * (1 - 35 / 1000), abs=1e-3)
    assert any("35 consecutive minutes" in b for b in r["breach_reasons"])
    assert r["target_met"] is False


def test_no_data_minutes_are_excluded_not_counted_as_downtime():
    add(list(range(0, 40)) + list(range(60, 100)))  # session stopped for 20 minutes
    r = check()
    assert r["no_data_minutes"] == 20 and r["measured_minutes"] == 80
    assert r["unavailable_minutes"] == 0 and r["availability_pct"] == 100.0


def test_gap_splits_outages():
    add(range(0, 10), req=100, err=100)
    add(range(20, 30), req=100, err=100)  # minutes 10-19 have no data
    r = check(0, 30)
    assert [o["minutes"] for o in r["outages"]] == [10, 10]


def test_no_data_at_all():
    r = check()
    assert r["measured_minutes"] == 0 and r["availability_pct"] is None
    assert r["target_met"] is None


def test_classify():
    assert sla_service.classify({"hosts": 0, "req": 0, "err": 0}) == "no healthy hosts"
    assert sla_service.classify({"hosts": 2, "req": 100, "err": 5}) is None  # exactly 5 %
    assert sla_service.classify({"hosts": 2, "req": 100, "err": 6}) is not None
    assert sla_service.classify({"hosts": 2, "req": 0, "err": 0}) is None


def test_endpoint_and_validation(client, admin, make_user, auth_header):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    with SessionLocal() as db:
        db.add_all(
            [
                AppMetric(
                    instance_id="i-1", worker=1, minute=now - timedelta(minutes=m), request_count=10
                )
                for m in range(1, 31)
            ]
        )
        db.commit()
    p = {"from": (now - timedelta(minutes=30)).isoformat(), "to": now.isoformat()}
    d = client.get(URL, params=p, headers=admin).json()
    assert (
        d["measured_minutes"] == 30 and d["availability_pct"] == 100.0 and d["target_met"] is True
    )
    assert client.get(URL, headers=admin).status_code == 200  # default window

    bad = {"from": now.isoformat(), "to": (now - timedelta(hours=1)).isoformat()}
    assert client.get(URL, params=bad, headers=admin).status_code == 422
    long = {"from": (now - timedelta(days=8)).isoformat(), "to": now.isoformat()}
    assert client.get(URL, params=long, headers=admin).status_code == 422

    make_user("c@x.com")
    assert client.get(URL, headers=auth_header("c@x.com")).status_code == 403
    assert client.get(URL).status_code == 401
