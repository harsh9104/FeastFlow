from app.core import aws
from app.core.config import get_settings
from app.models.menu import MenuItem
from app.services import storage_service, user_service
from tests.conftest import auth, register

NEW_DISH = {
    "restaurant_id": 1,
    "name": "Malai Kofta",
    "description": "Paneer dumplings in a cashew cream gravy",
    "category": "Main Course",
    "is_veg": True,
    "price": "279.00",
    "is_bestseller": True,
}


def admin(client, db):
    user_service.ensure_admin(db)
    s = get_settings()
    return auth(client.post(
        "/api/auth/login", json={"email": s.admin_email, "password": s.admin_password}
    ).json()["access_token"])


def test_admin_adds_dish_and_customers_see_it(client, db, menu):
    res = client.post("/api/admin/menu-items", json=NEW_DISH, headers=admin(client, db))
    assert res.status_code == 201, res.text
    dish = res.json()
    assert dish["name"] == "Malai Kofta" and dish["is_bestseller"] is True
    assert dish["image_url"] and ".svg" in dish["image_url"]  # placeholder picture right away

    item = db.get(MenuItem, dish["id"])
    obj = aws.s3().get_object(Bucket=get_settings().s3_bucket, Key=item.image_key)
    assert obj["ContentType"] == "image/svg+xml"

    menu_names = [i["name"] for i in client.get("/api/restaurants/1/menu").json()]
    assert "Malai Kofta" in menu_names

    # ...and it can be ordered at the server-side price.
    token = register(client)["access_token"]
    order = client.post(
        "/api/orders",
        json={"items": [{"menu_item_id": dish["id"], "quantity": 2}],
              "delivery_address": "5 Park Street"},
        headers=auth(token),
    ).json()
    assert order["total_amount"] == "558.00"


def test_add_dish_validation(client, db, menu):
    h = admin(client, db)
    dup = {**NEW_DISH, "name": "paneer"}  # menu fixture already has "Paneer" in restaurant 1
    assert client.post("/api/admin/menu-items", json=dup, headers=h).status_code == 409
    other = {**NEW_DISH, "name": "Paneer", "restaurant_id": 2}  # same name elsewhere is fine
    assert client.post("/api/admin/menu-items", json=other, headers=h).status_code == 201
    missing = {**NEW_DISH, "restaurant_id": 99}
    assert client.post("/api/admin/menu-items", json=missing, headers=h).status_code == 404
    for bad in ({"price": "0"}, {"price": "-5"}, {"name": "x"}, {"category": ""}):
        res = client.post("/api/admin/menu-items", json={**NEW_DISH, **bad}, headers=h)
        assert res.status_code == 422, bad

    customer = auth(register(client)["access_token"])
    assert client.post("/api/admin/menu-items", json=NEW_DISH, headers=customer).status_code == 403


def test_admin_edits_dish(client, db, menu):
    h = admin(client, db)
    res = client.patch(
        "/api/admin/menu-items/2",
        json={"name": "Garlic Naan", "description": "With butter", "price": "65",
              "is_bestseller": True, "is_veg": True},
        headers=h,
    )
    assert res.status_code == 200, res.text
    assert (res.json()["name"], res.json()["price"], res.json()["is_bestseller"]) == (
        "Garlic Naan", "65.00", True,
    )
    # Description can be cleared; renaming onto another dish's name is refused.
    assert client.patch("/api/admin/menu-items/2", json={"description": None},
                        headers=h).json()["description"] is None
    assert client.patch("/api/admin/menu-items/2", json={"name": "PANEER"},
                        headers=h).status_code == 409
    assert client.patch("/api/admin/menu-items/999", json={"price": "10"},
                        headers=h).status_code == 404


def test_placeholder_art_matches_the_dish():
    assert storage_service.dish_emoji("Chicken Biryani") == "🍛"
    assert storage_service.dish_emoji("Margherita Pizza") == "🍕"
    assert storage_service.dish_emoji("Mystery Special") == "🍽️"
    svg = storage_service.placeholder_svg("Veg Burger", 3).decode()
    assert svg.startswith("<svg") and "🍔" in svg


def test_restaurants_include_display_details(client, menu):
    r = client.get("/api/restaurants").json()[0]
    assert {"rating", "delivery_minutes", "cost_for_two", "offer"} <= r.keys()
