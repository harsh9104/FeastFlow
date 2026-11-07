from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.db.session import SessionLocal
from app.models.order import MenuItem, Order, OrderStatusHistory

Q = "/api/v1/admin/orders"


@pytest.fixture
def setup(client, make_user, auth_header):
    with SessionLocal() as db:
        m = MenuItem(name="Naan", category="B", price=Decimal("2.50"))
        db.add(m)
        db.commit()
        item = m.id
    make_user("admin@x.com", role="ADMIN")
    make_user("admin2@x.com", role="ADMIN")
    make_user("free@x.com")
    make_user("prem@x.com", tier="PREMIUM")

    class S:
        pass

    s = S()
    s.item = item
    s.admin = auth_header("admin@x.com")
    s.admin2 = auth_header("admin2@x.com")
    s.free = auth_header("free@x.com")
    s.prem = auth_header("prem@x.com")

    def place(h, age_s=0):
        r = client.post(
            "/api/v1/orders", json={"items": [{"menu_item_id": item, "quantity": 1}]}, headers=h
        )
        oid = r.json()["id"]
        if age_s:  # backdate to make ordering deterministic
            with SessionLocal() as db:
                db.execute(
                    update(Order)
                    .where(Order.id == oid)
                    .values(created_at=datetime.now(UTC) - timedelta(seconds=age_s))
                )
                db.commit()
        return oid

    s.place = place
    return s


def test_premium_before_older_free(client, setup):
    free_old = setup.place(setup.free, age_s=600)
    free_new = setup.place(setup.free, age_s=300)
    prem = setup.place(setup.prem, age_s=10)

    q = client.get(f"{Q}/queue", headers=setup.admin).json()["items"]
    assert [o["id"] for o in q] == [prem, free_old, free_new]
    assert q[0]["customer"] == "Test"

    claimed = [client.post(f"{Q}/queue/next", headers=setup.admin).json() for _ in range(3)]
    assert [o["id"] for o in claimed] == [prem, free_old, free_new]
    assert all(o["status"] == "PREPARING" and o["version"] == 2 for o in claimed)
    assert client.post(f"{Q}/queue/next", headers=setup.admin).status_code == 204


def test_fifo_within_same_priority(client, setup):
    a = setup.place(setup.prem, age_s=100)
    b = setup.place(setup.prem, age_s=200)
    assert client.post(f"{Q}/queue/next", headers=setup.admin).json()["id"] == b
    assert client.post(f"{Q}/queue/next", headers=setup.admin).json()["id"] == a


def test_concurrent_claims_get_distinct_orders(client, setup):
    ids = {setup.place(setup.free, age_s=i + 1) for i in range(8)}
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda _: client.post(f"{Q}/queue/next", headers=setup.admin), range(8)))
    assert all(r.status_code == 200 for r in res)
    got = [r.json()["id"] for r in res]
    assert len(set(got)) == 8 and set(got) == ids


def test_transitions_and_conflicts(client, setup):
    oid = setup.place(setup.free)
    h = setup.admin
    # Cannot skip PENDING -> COMPLETED
    r = client.patch(f"{Q}/{oid}/status", json={"status": "COMPLETED", "version": 1}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_TRANSITION"

    # Stale version
    r = client.patch(f"{Q}/{oid}/status", json={"status": "PREPARING", "version": 7}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "STALE_VERSION"

    r = client.patch(f"{Q}/{oid}/status", json={"status": "PREPARING", "version": 1}, headers=h)
    assert r.status_code == 200 and r.json()["version"] == 2
    # Replaying the same request fails (already PREPARING)
    r = client.patch(f"{Q}/{oid}/status", json={"status": "PREPARING", "version": 1}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_TRANSITION"

    r = client.patch(f"{Q}/{oid}/status", json={"status": "COMPLETED", "version": 2}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "COMPLETED"
    # Completed is terminal, and cannot go back
    r = client.patch(f"{Q}/{oid}/status", json={"status": "PREPARING", "version": 3}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_TRANSITION"

    assert (
        client.patch(
            f"{Q}/9999/status", json={"status": "PREPARING", "version": 1}, headers=h
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"{Q}/{oid}/status", json={"status": "PENDING", "version": 1}, headers=h
        ).status_code
        == 422
    )

    hist = client.get(f"{Q}/{oid}/history", headers=h).json()
    assert [(x["from_status"], x["to_status"]) for x in hist] == [
        (None, "PENDING"),
        ("PENDING", "PREPARING"),
        ("PREPARING", "COMPLETED"),
    ]
    with SessionLocal() as db:
        o = db.scalar(select(Order).where(Order.id == oid))
        assert o.preparing_at and o.completed_at
        assert len(db.scalars(select(OrderStatusHistory)).all()) == 3
    # Customer sees the progress
    detail = client.get(f"/api/v1/orders/{oid}", headers=setup.free).json()
    assert detail["status"] == "COMPLETED" and len(detail["history"]) == 3


def test_access_control(client, setup):
    for method, path in [
        ("get", Q),
        ("get", f"{Q}/queue"),
        ("post", f"{Q}/queue/next"),
        ("get", f"{Q}/stats"),
        ("get", f"{Q}/1/history"),
    ]:
        assert getattr(client, method)(path, headers=setup.free).status_code == 403
        assert getattr(client, method)(path).status_code == 401


def test_admin_list_filters(client, setup):
    setup.place(setup.free)
    setup.place(setup.prem)
    h = setup.admin
    assert client.get(Q, headers=h).json()["total"] == 2
    assert client.get(f"{Q}?priority=1", headers=h).json()["total"] == 1
    assert client.get(f"{Q}?status=COMPLETED", headers=h).json()["total"] == 0
    future = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert client.get(f"{Q}?from={future}", headers=h).json()["total"] == 0
    assert client.get(f"{Q}?priority=5", headers=h).status_code == 422


def test_stats_show_premium_waits_less(client, setup):
    setup.place(setup.free, age_s=300)
    setup.place(setup.prem, age_s=20)
    assert client.get(f"{Q}/stats", headers=setup.admin).json()["avg_wait_premium_s"] is None
    # Premium is served first even though it is younger.
    client.post(f"{Q}/queue/next", headers=setup.admin)
    client.post(f"{Q}/queue/next", headers=setup.admin)
    s = client.get(f"{Q}/stats", headers=setup.admin).json()
    assert s["counts_by_status"] == {"PENDING": 0, "PREPARING": 2, "COMPLETED": 0}
    assert s["avg_wait_free_s"] >= 300
    assert 20 <= s["avg_wait_premium_s"] < 60
    assert s["avg_wait_premium_s"] < s["avg_wait_free_s"]
