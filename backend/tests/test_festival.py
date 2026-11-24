from datetime import timedelta
from unittest.mock import patch

import httpx
import pytest

from app.core.config import get_settings
from app.core.time import utcnow
from app.models.festival import FestivalRun
from app.models.order import Order
from app.models.user import User
from app.services import festival_service, notification_service, user_service
from tests.conftest import TestingSession, auth, queued_messages, register


def admin(client, db):
    user_service.ensure_admin(db)
    s = get_settings()
    token = client.post(
        "/api/auth/login", json={"email": s.admin_email, "password": s.admin_password}
    ).json()["access_token"]
    return auth(token)


@pytest.fixture
def test_users(db):
    user_service.ensure_test_users(db)


@pytest.fixture
def run_inline(monkeypatch):
    """Run festival generation synchronously instead of in a background thread."""
    monkeypatch.setattr(
        festival_service,
        "start_in_background",
        lambda run_id: festival_service.execute(run_id, TestingSession, sleep=lambda s: None),
    )


# ---- seeded load-test customers -----------------------------------------------


def test_test_users_seeded_once_with_prime_share(db, test_users):
    users = db.query(User).filter(User.is_test_user.is_(True)).all()
    assert len(users) == 10 and sum(u.is_prime for u in users) == 3
    assert user_service.ensure_test_users(db) == 0  # idempotent


def test_test_users_locked_unless_password_set(client, db, monkeypatch):
    email = user_service.loadtest_email(1)
    user_service.ensure_test_users(db)
    res = client.post("/api/auth/login", json={"email": email, "password": "anything"})
    assert res.status_code == 401

    monkeypatch.setenv("LOADTEST_PASSWORD", "festival-pass-1")
    get_settings.cache_clear()
    user_service.ensure_test_users(db)
    res = client.post("/api/auth/login", json={"email": email, "password": "festival-pass-1"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    # Their Prime/standard split is fixed so reports stay comparable.
    assert client.post("/api/prime/cancel", headers=auth(token)).status_code == 403

    monkeypatch.setenv("LOADTEST_PASSWORD", "")
    get_settings.cache_clear()
    user_service.ensure_test_users(db)  # unsetting the password locks them again
    res = client.post("/api/auth/login", json={"email": email, "password": "festival-pass-1"})
    assert res.status_code == 401


def test_test_users_hidden_from_customer_list(client, db, test_users):
    h = admin(client, db)
    register(client, email="real@example.com")
    assert client.get("/api/admin/users", headers=h).json()["total"] == 2  # admin + real
    shown = client.get("/api/admin/users?include_test_users=true", headers=h).json()
    assert shown["total"] == 12


def test_test_user_orders_are_synthetic_and_silent(client, db, menu, test_users, monkeypatch):
    monkeypatch.setenv("LOADTEST_PASSWORD", "festival-pass-1")
    get_settings.cache_clear()
    user_service.ensure_test_users(db)
    token = client.post(
        "/api/auth/login",
        json={"email": user_service.loadtest_email(5), "password": "festival-pass-1"},
    ).json()["access_token"]
    body = {"items": [{"menu_item_id": 1, "quantity": 1}], "delivery_address": "1 Test Road"}
    order_id = client.post("/api/orders", json=body, headers=auth(token)).json()["id"]
    order = db.get(Order, order_id)
    assert order.is_synthetic is True
    notice = notification_service.Notice(order.id, order.user_id, "CONFIRMED", order.is_synthetic)
    assert notification_service.publish([notice]) == 0


# ---- festival simulator ------------------------------------------------------------


def test_festival_run_creates_orders_with_exact_prime_share(
    client, db, menu, test_users, run_inline
):
    h = admin(client, db)
    res = client.post(
        "/api/admin/festival/runs",
        json={"orders": 40, "duration_seconds": 0, "prime_percent": 25},
        headers=h,
    )
    assert res.status_code == 202, res.text
    db.expire_all()
    run = db.get(FestivalRun, res.json()["id"])
    assert (run.status, run.created_orders, run.prime_orders, run.failed_orders) == (
        "COMPLETED",
        40,
        10,
        0,
    )
    orders = db.query(Order).all()
    assert len(orders) == 40 and all(o.is_synthetic for o in orders)
    assert sum(o.priority for o in orders) == 10
    # Every order went through checkout into SQS.
    assert all(o.enqueued_at is not None for o in orders)
    s = get_settings()
    assert all(m["priority"] == 1 for m in queued_messages(s.sqs_prime_queue))
    assert all(m["priority"] == 0 for m in queued_messages(s.sqs_standard_queue))

    listed = client.get("/api/admin/festival/runs", headers=h).json()
    assert listed[0]["id"] == run.id and listed[0]["status"] == "COMPLETED"


def test_festival_paces_orders_over_the_duration(db, menu, test_users, monkeypatch):
    user_service.ensure_admin(db)
    admin_user = db.query(User).filter_by(role="ADMIN").one()
    run = festival_service.create_run(db, admin_user, orders=10, duration=20, prime_percent=50)

    clock = [1000.0]  # fake monotonic clock that only moves when the generator sleeps
    monkeypatch.setattr(festival_service.time, "monotonic", lambda: clock[0])
    sleeps = []

    def fake_sleep(s):
        sleeps.append(s)
        clock[0] += s

    festival_service.execute(run.id, TestingSession, sleep=fake_sleep)
    # 10 orders over 20 s: one every 2 s.
    assert sleeps == [pytest.approx(2.0)] * 10


def test_only_one_run_at_a_time_and_cancel(client, db, menu, test_users):
    h = admin(client, db)
    with patch.object(festival_service, "start_in_background"):  # leave it RUNNING
        first = client.post(
            "/api/admin/festival/runs",
            json={"orders": 100, "duration_seconds": 60, "prime_percent": 30},
            headers=h,
        )
        second = client.post(
            "/api/admin/festival/runs",
            json={"orders": 10, "duration_seconds": 0, "prime_percent": 30},
            headers=h,
        )
    assert first.status_code == 202 and second.status_code == 409

    run_id = first.json()["id"]
    res = client.post(f"/api/admin/festival/runs/{run_id}/cancel", headers=h)
    assert res.json()["status"] == "CANCELLED"
    # The generator notices the cancel at its first check and creates nothing.
    festival_service.execute(run_id, TestingSession, sleep=lambda s: None)
    db.expire_all()
    assert db.get(FestivalRun, run_id).status == "CANCELLED"
    assert db.query(Order).count() == 0


def test_run_on_dead_instance_is_reported_failed(client, db, menu, test_users):
    h = admin(client, db)
    with patch.object(festival_service, "start_in_background"):
        run_id = client.post(
            "/api/admin/festival/runs",
            json={"orders": 100, "duration_seconds": 60, "prime_percent": 30},
            headers=h,
        ).json()["id"]
    run = db.get(FestivalRun, run_id)
    run.heartbeat_at = utcnow() - timedelta(minutes=5)
    db.commit()
    listed = client.get("/api/admin/festival/runs", headers=h).json()
    assert listed[0]["status"] == "FAILED" and "stopped responding" in listed[0]["error"]


def test_festival_validation(client, db, menu):
    h = admin(client, db)
    too_many = {
        "orders": get_settings().festival_max_orders + 1,
        "duration_seconds": 0,
        "prime_percent": 10,
    }
    assert client.post("/api/admin/festival/runs", json=too_many, headers=h).status_code == 422
    bad_pct = {"orders": 5, "duration_seconds": 0, "prime_percent": 101}
    assert client.post("/api/admin/festival/runs", json=bad_pct, headers=h).status_code == 422
    # No test users seeded yet:
    ok = {"orders": 5, "duration_seconds": 0, "prime_percent": 10}
    res = client.post("/api/admin/festival/runs", json=ok, headers=h)
    assert res.status_code == 409 and "Load-test customers" in res.json()["detail"]
    customer = auth(register(client, email="c@example.com")["access_token"])
    assert client.post("/api/admin/festival/runs", json=ok, headers=customer).status_code == 403


# ---- Locust control ---------------------------------------------------------------

LOCUST_STATS = {
    "state": "running",
    "user_count": 300,
    "total_rps": 142.37,
    "total_fail_per_sec": 0.5,
    "fail_ratio": 0.0035,
    "stats": [
        {"name": "Aggregated", "num_requests": 9000, "num_failures": 31, "avg_response_time": 85.4}
    ],
    "current_response_time_percentiles": {
        "response_time_percentile_0.5": 60,
        "response_time_percentile_0.95": 240,
    },
    "errors": [],
}


def test_loadtest_not_configured(client, db):
    assert client.get("/api/admin/loadtest", headers=admin(client, db)).status_code == 503


def test_loadtest_proxy(client, db, monkeypatch):
    monkeypatch.setenv("LOCUST_URL", "http://locust:8089/")
    get_settings.cache_clear()
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs.get("data")))
        return httpx.Response(200, json=LOCUST_STATS, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake_request)
    h = admin(client, db)
    res = client.post("/api/admin/loadtest/start", json={"profile": "festival"}, headers=h)
    assert res.status_code == 200
    body = res.json()
    assert (body["users"], body["rps"], body["p95_ms"], body["failures"]) == (300, 142.4, 240, 31)
    assert calls[0][0:2] == ("POST", "http://locust:8089/swarm")
    assert calls[0][2]["profile"] == "festival"
    assert "host" not in calls[0][2]  # no LOADTEST_TARGET: Locust keeps its own --host

    client.post("/api/admin/loadtest/stop", headers=h)
    assert ("GET", "http://locust:8089/stop", None) in calls
    bad = client.post("/api/admin/loadtest/start", json={"profile": "huge"}, headers=h)
    assert bad.status_code == 422


def test_loadtest_sends_target(client, db, monkeypatch):
    monkeypatch.setenv("LOCUST_URL", "http://locust:8089")
    monkeypatch.setenv("LOADTEST_TARGET", "http://feastflow-alb.example.com/")
    get_settings.cache_clear()
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append(kwargs.get("data"))
        return httpx.Response(200, json=LOCUST_STATS, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", fake_request)
    res = client.post(
        "/api/admin/loadtest/start", json={"profile": "normal"}, headers=admin(client, db)
    )
    assert res.status_code == 200
    assert calls[0]["host"] == "http://feastflow-alb.example.com"


def test_loadtest_unreachable(client, db, monkeypatch):
    monkeypatch.setenv("LOCUST_URL", "http://locust:8089")
    get_settings.cache_clear()

    def boom(method, url, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "request", boom)
    assert client.get("/api/admin/loadtest", headers=admin(client, db)).status_code == 502
