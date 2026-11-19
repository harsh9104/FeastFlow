from decimal import Decimal
from unittest.mock import patch

from app.core.config import get_settings
from app.models.menu import MenuItem
from app.models.order import Order
from app.services.storage_service import seed_placeholder_images
from app.services.user_service import ensure_admin
from tests.conftest import auth, queued_messages, register

ADDRESS = "12 Lake View Road, Pune"


def order_body(*lines, address=ADDRESS):
    return {
        "items": [{"menu_item_id": i, "quantity": q} for i, q in lines],
        "delivery_address": address,
    }


def admin_token(client, db):
    ensure_admin(db)
    s = get_settings()
    return client.post(
        "/api/auth/login", json={"email": s.admin_email, "password": s.admin_password}
    ).json()["access_token"]


# ---- menu -------------------------------------------------------------------


def test_menu_is_public_and_has_presigned_image_urls(client, menu):
    assert [r["name"] for r in client.get("/api/restaurants").json()] == [
        "Spice Route",
        "Dosa Junction",
    ]
    items = client.get("/api/restaurants/1/menu").json()
    paneer = next(i for i in items if i["id"] == 1)
    assert "menu/1.svg" in paneer["image_url"] and "Signature" in paneer["image_url"]
    assert next(i for i in items if i["id"] == 2)["image_url"] is None
    assert client.get("/api/restaurants/99/menu").status_code == 404


def test_placeholder_images_uploaded_once(db, menu):
    items = db.query(MenuItem).all()
    assert seed_placeholder_images(items) == 1  # only item 1 has an image_key
    assert seed_placeholder_images(items) == 0  # already in S3


# ---- placing orders --------------------------------------------------------


def test_standard_order_goes_to_standard_queue(client, db, menu):
    token = register(client)["access_token"]
    res = client.post("/api/orders", json=order_body((1, 2), (2, 3)), headers=auth(token))
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["status"] == "PLACED" and body["is_prime"] is False
    assert Decimal(body["total_amount"]) == Decimal("650.00")  # 2*250 + 3*50
    assert [e["status"] for e in body["events"]] == ["PLACED"]

    s = get_settings()
    assert queued_messages(s.sqs_standard_queue)[0]["order_id"] == body["id"]
    assert queued_messages(s.sqs_prime_queue) == []
    assert db.get(Order, body["id"]).enqueued_at is not None


def test_prime_order_goes_to_prime_queue(client, menu):
    token = register(client)["access_token"]
    client.post("/api/prime/subscribe", headers=auth(token))
    body = client.post("/api/orders", json=order_body((4, 1)), headers=auth(token)).json()
    assert body["priority"] == 1 and body["is_prime"] is True
    msgs = queued_messages(get_settings().sqs_prime_queue)
    assert msgs == [{"order_id": body["id"], "priority": 1, "sent_at": msgs[0]["sent_at"]}]


def test_client_cannot_set_price_and_duplicate_lines_merge(client, menu):
    token = register(client)["access_token"]
    body = order_body((2, 1), (2, 2))
    body["items"][0]["unit_price"] = "0.01"  # ignored: extra field
    res = client.post("/api/orders", json=body, headers=auth(token)).json()
    assert res["items"] == [
        {"menu_item_id": 2, "name": "Naan", "quantity": 3, "unit_price": "50.00"}
    ]
    assert Decimal(res["total_amount"]) == Decimal("150.00")


def test_order_validation_errors(client, db, menu):
    token = register(client)["access_token"]
    cases = {
        "unknown": order_body((999, 1)),
        "unavailable": order_body((3, 1)),
        "two restaurants": order_body((1, 1), (4, 1)),
        "too many": order_body((1, get_settings().max_item_quantity + 1)),
        "zero qty": order_body((1, 0)),
        "empty": order_body(),
        "short address": order_body((1, 1), address="x"),
    }
    for name, body in cases.items():
        res = client.post("/api/orders", json=body, headers=auth(token))
        assert res.status_code == 422, f"{name}: {res.status_code} {res.text}"
    assert db.query(Order).count() == 0


def test_closed_restaurant_rejected(client, db, menu):
    from app.models.menu import Restaurant

    db.get(Restaurant, 1).is_open = False
    db.commit()
    token = register(client)["access_token"]
    res = client.post("/api/orders", json=order_body((1, 1)), headers=auth(token))
    assert res.status_code == 422 and "closed" in res.json()["detail"]


def test_idempotency_key_prevents_duplicates(client, db, menu):
    token = register(client)["access_token"]
    headers = {**auth(token), "Idempotency-Key": "cart-abc-1"}
    first = client.post("/api/orders", json=order_body((1, 1)), headers=headers)
    retry = client.post("/api/orders", json=order_body((1, 1)), headers=headers)
    assert first.status_code == 202 and retry.status_code == 200
    assert first.json()["id"] == retry.json()["id"]
    assert db.query(Order).count() == 1
    assert len(queued_messages(get_settings().sqs_standard_queue)) == 1


def test_sqs_outage_still_saves_order_for_sweeper(client, db, menu):
    token = register(client)["access_token"]
    with patch("app.services.queue_publisher.aws.queue_url", side_effect=_boto_error()):
        res = client.post("/api/orders", json=order_body((1, 1)), headers=auth(token))
    assert res.status_code == 202
    order = db.get(Order, res.json()["id"])
    assert order.status == "PLACED" and order.enqueued_at is None


def _boto_error():
    from botocore.exceptions import EndpointConnectionError

    return EndpointConnectionError(endpoint_url="http://sqs")


def test_auth_rules_for_orders(client, db, menu):
    assert client.post("/api/orders", json=order_body((1, 1))).status_code == 401
    admin = admin_token(client, db)
    assert (
        client.post("/api/orders", json=order_body((1, 1)), headers=auth(admin)).status_code
        == 403
    )


# ---- reading orders --------------------------------------------------------


def test_my_orders_newest_first_and_private(client, db, menu):
    asha = register(client, email="asha@example.com")["access_token"]
    ravi = register(client, email="ravi@example.com")["access_token"]
    first = client.post("/api/orders", json=order_body((1, 1)), headers=auth(asha)).json()
    second = client.post("/api/orders", json=order_body((2, 1)), headers=auth(asha)).json()

    mine = client.get("/api/orders", headers=auth(asha)).json()
    assert mine["total"] == 2
    assert [o["id"] for o in mine["items"]] == [second["id"], first["id"]]
    assert client.get("/api/orders", headers=auth(ravi)).json()["total"] == 0

    assert client.get(f"/api/orders/{first['id']}", headers=auth(asha)).status_code == 200
    assert client.get(f"/api/orders/{first['id']}", headers=auth(ravi)).status_code == 404
    admin = admin_token(client, db)
    assert client.get(f"/api/orders/{first['id']}", headers=auth(admin)).status_code == 200


# ---- admin menu management -------------------------------------------------

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_admin_can_upload_image_and_toggle_availability(client, db, menu):
    admin = admin_token(client, db)
    res = client.post(
        "/api/admin/menu-items/2/image",
        files={"file": ("naan.png", PNG, "image/png")},
        headers=auth(admin),
    )
    assert res.status_code == 200, res.text
    assert "menu/2-" in res.json()["image_url"]

    res = client.patch(
        "/api/admin/menu-items/2", json={"is_available": False}, headers=auth(admin)
    )
    assert res.json()["is_available"] is False


def test_image_upload_rejects_bad_files(client, db, menu):
    admin = admin_token(client, db)
    url = "/api/admin/menu-items/2/image"
    gif = client.post(url, files={"file": ("a.gif", b"GIF89a", "image/gif")}, headers=auth(admin))
    assert gif.status_code == 415
    fake = client.post(url, files={"file": ("a.png", b"MZ\x90", "image/png")}, headers=auth(admin))
    assert fake.status_code == 415
    customer = register(client)["access_token"]
    res = client.post(url, files={"file": ("a.png", PNG, "image/png")}, headers=auth(customer))
    assert res.status_code == 403
