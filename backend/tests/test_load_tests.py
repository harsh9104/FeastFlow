from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.db.session import SessionLocal
from app.models.load_test import LoadTestRun
from app.services import load_test_service as svc

L = "/api/v1/admin/load-tests"


class FakeLocust:
    def __init__(self):
        self.calls = []
        self.down = False
        self.requests = 120
        self.failures = 3

    def __call__(self, path, method="GET", data=None):
        self.calls.append((method, path, data))
        if self.down:
            raise ConnectionError("locust down")
        if path == "/stats/requests":
            return {
                "state": "running",
                "user_count": 25,
                "total_rps": 9.5,
                "fail_ratio": 0.025,
                "stats": [
                    {
                        "name": "GET /menu",
                        "method": "GET",
                        "num_requests": 100,
                        "num_failures": 0,
                        "avg_response_time": 12.34,
                        "response_time_percentile_0.95": 30,
                    },
                    {
                        "name": "Aggregated",
                        "num_requests": self.requests,
                        "num_failures": self.failures,
                        "avg_response_time": 20.0,
                        "median_response_time": 15,
                        "response_time_percentile_0.95": 80,
                    },
                ],
            }
        return {"success": True}


@pytest.fixture
def fake(monkeypatch):
    f = FakeLocust()
    monkeypatch.setattr(svc, "_locust", f)
    return f


@pytest.fixture
def admin(make_user, auth_header):
    make_user("admin@x.com", role="ADMIN")
    return auth_header("admin@x.com")


def backdate(run_id, seconds):
    with SessionLocal() as db:
        db.execute(
            update(LoadTestRun)
            .where(LoadTestRun.id == run_id)
            .values(started_at=datetime.now(UTC) - timedelta(seconds=seconds))
        )
        db.commit()


def test_requires_admin(client, make_user, auth_header, fake):
    make_user("c@x.com")
    h = auth_header("c@x.com")
    assert client.get(f"{L}/scenarios", headers=h).status_code == 403
    assert client.post(L, json={"scenario": "NORMAL"}, headers=h).status_code == 403
    assert client.get(L).status_code == 401


def test_scenarios(client, admin):
    s = {x["name"]: x for x in client.get(f"{L}/scenarios", headers=admin).json()}
    assert s["NORMAL"]["users"] == 25 and s["FESTIVAL"]["users"] == 250
    assert s["FESTIVAL"]["duration_s"] == 900


def test_start_sends_swarm_and_blocks_second_run(client, admin, fake):
    r = client.post(L, json={"scenario": "FESTIVAL"}, headers=admin)
    assert r.status_code == 202 and r.json()["status"] == "RUNNING"
    method, path, data = next(c for c in fake.calls if c[1] == "/swarm")
    assert method == "POST"
    assert data["user_count"] == 250 and data["spawn_rate"] == 10
    assert data["user_classes"] == "FestivalUser" and data["run_time"] == "900s"

    r2 = client.post(L, json={"scenario": "NORMAL"}, headers=admin)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "LOAD_TEST_ALREADY_RUNNING"


def test_locust_unreachable_marks_failed_and_frees_slot(client, admin, fake):
    fake.down = True
    r = client.post(L, json={"scenario": "NORMAL"}, headers=admin)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "LOAD_GENERATOR_UNAVAILABLE"
    run = client.get(L, headers=admin).json()["items"][0]
    assert run["status"] == "FAILED"
    fake.down = False
    assert client.post(L, json={"scenario": "NORMAL"}, headers=admin).status_code == 202


def test_override_validation(client, admin, fake):
    assert client.post(L, json={"scenario": "X"}, headers=admin).status_code == 422
    assert client.post(L, json={"scenario": "NORMAL", "users": 0}, headers=admin).status_code == 422
    assert (
        client.post(L, json={"scenario": "NORMAL", "duration_s": 5}, headers=admin).status_code
        == 422
    )
    r = client.post(L, json={"scenario": "NORMAL", "users": 5, "duration_s": 30}, headers=admin)
    assert r.status_code == 202
    run = client.get(f"{L}/{r.json()['run_id']}", headers=admin).json()["run"]
    assert run["target_users"] == 5 and run["duration_seconds"] == 30


def test_live_stats_while_running(client, admin, fake):
    rid = client.post(L, json={"scenario": "NORMAL"}, headers=admin).json()["run_id"]
    d = client.get(f"{L}/{rid}", headers=admin).json()
    assert d["run"]["status"] == "RUNNING"
    live = d["live_stats"]
    assert live["users"] == 25 and live["rps"] == 9.5
    assert live["p95_response_ms"] == 80
    assert live["endpoints"][0]["name"] == "GET /menu"


def test_lazy_finalization_after_duration(client, admin, fake):
    rid = client.post(L, json={"scenario": "NORMAL", "duration_s": 60}, headers=admin).json()[
        "run_id"
    ]
    client.get(f"{L}/{rid}", headers=admin)  # records peak rps 9.5
    backdate(rid, 120)
    d = client.get(f"{L}/{rid}", headers=admin).json()
    run = d["run"]
    assert run["status"] == "COMPLETED" and d["live_stats"] is None
    assert run["total_requests"] == 120 and run["failed_requests"] == 3
    assert run["avg_response_ms"] == 20.0 and run["p95_response_ms"] == 80
    assert run["peak_rps"] == 9.5
    assert run["ended_at"] is not None
    assert ("GET", "/stop", None) in fake.calls
    # Slot is free again, and finalization is idempotent.
    assert client.get(f"{L}/{rid}", headers=admin).json()["run"]["status"] == "COMPLETED"
    assert client.post(L, json={"scenario": "NORMAL"}, headers=admin).status_code == 202


def test_stop(client, admin, fake):
    rid = client.post(L, json={"scenario": "NORMAL"}, headers=admin).json()["run_id"]
    r = client.post(f"{L}/{rid}/stop", headers=admin)
    assert r.status_code == 200 and r.json()["run"]["status"] == "STOPPED"
    assert r.json()["run"]["total_requests"] == 120
    assert client.post(f"{L}/{rid}/stop", headers=admin).json()["error"]["code"] == "NOT_RUNNING"
    assert client.post(f"{L}/9999/stop", headers=admin).status_code == 404
    assert client.get(f"{L}/9999", headers=admin).status_code == 404


def test_history_pagination(client, admin, fake):
    for _ in range(3):
        rid = client.post(L, json={"scenario": "NORMAL"}, headers=admin).json()["run_id"]
        client.post(f"{L}/{rid}/stop", headers=admin)
    d = client.get(f"{L}?page_size=2", headers=admin).json()
    assert d["total"] == 3 and len(d["items"]) == 2
    assert d["items"][0]["id"] > d["items"][1]["id"]


def test_unreachable_at_finalization_marks_failed(client, admin, fake):
    rid = client.post(L, json={"scenario": "NORMAL", "duration_s": 60}, headers=admin).json()[
        "run_id"
    ]
    backdate(rid, 120)
    fake.down = True
    assert client.get(f"{L}/{rid}", headers=admin).json()["run"]["status"] == "FAILED"


def test_stale_running_run_does_not_block_a_new_start(client, admin, fake):
    rid = client.post(L, json={"scenario": "NORMAL", "duration_s": 60}, headers=admin).json()[
        "run_id"
    ]
    backdate(rid, 300)  # time is up but nobody polled it
    r = client.post(L, json={"scenario": "FESTIVAL"}, headers=admin)
    assert r.status_code == 202
    old = client.get(f"{L}/{rid}", headers=admin).json()["run"]
    assert old["status"] == "COMPLETED"


def test_live_run_still_blocks_a_new_start(client, admin, fake):
    client.post(L, json={"scenario": "NORMAL", "duration_s": 600}, headers=admin)
    assert client.post(L, json={"scenario": "NORMAL"}, headers=admin).status_code == 409


def test_swarm_sends_target_host_when_configured(client, admin, fake, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "loadtest_target", "http://my-alb.example")
    client.post(L, json={"scenario": "NORMAL"}, headers=admin)
    data = next(c[2] for c in fake.calls if c[1] == "/swarm")
    assert data["host"] == "http://my-alb.example"


def test_swarm_omits_host_locally(client, admin, fake):
    client.post(L, json={"scenario": "NORMAL"}, headers=admin)
    data = next(c[2] for c in fake.calls if c[1] == "/swarm")
    assert "host" not in data
