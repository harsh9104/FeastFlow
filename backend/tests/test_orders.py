from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.order import MenuItem, Order, OrderStatusHistory


@pytest.fixture
def menu():
    with SessionLocal() as db:
        a = MenuItem(name="Tikka", category="S", price=Decimal("8.50"))
        b = MenuItem(name="Naan", category="B", price=Decimal("2.50"))
        c = MenuItem(name="Gone", category="B", price=Decimal("1.00"), is_available=False)
        db.add_all([a, b, c])
        db.commit()
        return {"a": a.id, "b": b.id, "gone": c.id}


def place(client, h, items, **kw):
    return client.post("/api/v1/orders", json={"items": items, **kw.pop("body", {})}, headers=h)


def count(model):
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(model))


def test_menu_requires_auth_and_lists(client, make_user, auth_header, menu):
    assert client.get("/api/v1/menu").status_code == 401
    make_user("c@x.com")
    h = auth_header("c@x.com")
    r = client.get("/api/v1/menu", headers=h)
    assert r.status_code == 200
    assert {m["name"] for m in r.json()} == {"Tikka", "Naan", "Gone"}
    assert r.json()[0]["image_url"] is None  # no bucket configured locally
    assert client.get(f"/api/v1/menu/{menu['a']}", headers=h).json()["price"] == "8.50"
    assert client.get("/api/v1/menu/9999", headers=h).status_code == 404


def test_order_server_side_pricing_and_priority(client, make_user, auth_header, menu):
    make_user("p@x.com", tier="PREMIUM")
    h = auth_header("p@x.com")
    r = place(
        client,
        h,
        [
            {"menu_item_id": menu["a"], "quantity": 2},
            {"menu_item_id": menu["b"], "quantity": 1},
            {"menu_item_id": menu["a"], "quantity": 1},  # duplicate line is merged
        ],
    )
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["status"] == "PENDING"
    assert o["priority"] == 1 and o["tier_at_order"] == "PREMIUM"
    assert Decimal(o["total_amount"]) == Decimal("28.00")  # 3*8.50 + 2.50
    assert len(o["items"]) == 2
    assert {i["quantity"] for i in o["items"]} == {3, 1}

    detail = client.get(f"/api/v1/orders/{o['id']}", headers=h).json()
    assert [(x["from_status"], x["to_status"]) for x in detail["history"]] == [(None, "PENDING")]


def test_free_priority_and_snapshot(client, make_user, auth_header, menu):
    make_user("c@x.com")
    h = auth_header("c@x.com")
    first = place(client, h, [{"menu_item_id": menu["b"], "quantity": 1}]).json()
    assert first["priority"] == 0
    client.patch("/api/v1/users/me/subscription", json={"subscription_tier": "PREMIUM"}, headers=h)
    second = place(client, h, [{"menu_item_id": menu["b"], "quantity": 1}]).json()
    assert second["priority"] == 1
    # Earlier order keeps its snapshot.
    assert client.get(f"/api/v1/orders/{first['id']}", headers=h).json()["priority"] == 0


def test_client_cannot_set_price(client, make_user, auth_header, menu):
    make_user("c@x.com")
    h = auth_header("c@x.com")
    r = place(client, h, [{"menu_item_id": menu["a"], "quantity": 1, "unit_price": "0.01"}])
    assert r.status_code == 201
    assert r.json()["total_amount"] == "8.50"


def test_unavailable_item_rolls_back(client, make_user, auth_header, menu):
    make_user("c@x.com")
    h = auth_header("c@x.com")
    r = place(
        client,
        h,
        [{"menu_item_id": menu["a"], "quantity": 1}, {"menu_item_id": menu["gone"], "quantity": 1}],
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "ITEM_UNAVAILABLE"
    r = place(client, h, [{"menu_item_id": 99999, "quantity": 1}])
    assert r.status_code == 422
    assert count(Order) == 0 and count(OrderStatusHistory) == 0


def test_validation(client, make_user, auth_header, menu):
    make_user("c@x.com")
    h = auth_header("c@x.com")
    assert place(client, h, []).status_code == 422
    assert place(client, h, [{"menu_item_id": menu["a"], "quantity": 0}]).status_code == 422
    assert place(client, h, [{"menu_item_id": menu["a"], "quantity": 21}]).status_code == 422
    two = [{"menu_item_id": menu["a"], "quantity": 15}] * 2
    assert place(client, h, two).json()["error"]["code"] == "QUANTITY_EXCEEDED"
    assert (
        place(
            client, h, [{"menu_item_id": menu["a"], "quantity": 1}], body={"notes": "x" * 501}
        ).status_code
        == 422
    )


def test_roles(client, make_user, auth_header, menu):
    assert client.post("/api/v1/orders", json={}).status_code == 401
    make_user("admin@x.com", role="ADMIN")
    h = auth_header("admin@x.com")
    r = place(client, h, [{"menu_item_id": menu["a"], "quantity": 1}])
    assert r.status_code == 403


def test_my_orders_isolation_and_pagination(client, make_user, auth_header, menu):
    make_user("a@x.com")
    make_user("b@x.com")
    ha, hb = auth_header("a@x.com"), auth_header("b@x.com")
    ids = [
        place(client, ha, [{"menu_item_id": menu["b"], "quantity": 1}]).json()["id"]
        for _ in range(3)
    ]
    other = place(client, hb, [{"menu_item_id": menu["b"], "quantity": 1}]).json()["id"]

    r = client.get("/api/v1/orders?page_size=2", headers=ha).json()
    assert r["total"] == 3 and len(r["items"]) == 2
    assert r["items"][0]["id"] == ids[-1]  # newest first
    assert client.get("/api/v1/orders?status=COMPLETED", headers=ha).json()["total"] == 0
    assert client.get(f"/api/v1/orders/{other}", headers=ha).status_code == 404
    assert client.get("/api/v1/orders/99999", headers=ha).status_code == 404


def test_idempotency_key(client, make_user, auth_header, menu):
    make_user("c@x.com")
    h = {**auth_header("c@x.com"), "Idempotency-Key": "abc-123"}
    items = [{"menu_item_id": menu["a"], "quantity": 1}]
    r1 = place(client, h, items)
    r2 = place(client, h, items)
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    assert count(Order) == 1
