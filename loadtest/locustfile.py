"""FeastFlow load scenarios (doc 13). Run by the Locust web UI/API; the backend picks a user class.

NormalUser   = normal day  (2-5 s think time, order weight 3)
FestivalUser = festival day (1-3 s think time, order weight 4)

Each simulated user logs in ONCE from a seeded pool (~70 % FREE / 30 % PREMIUM) so bcrypt does not
dominate the CPU measurement. Accounts are created by Alembic migration 0006.
"""

import os
import random

from locust import HttpUser, between
from locust.exception import StopUser

# Must match the app's LOADTEST_PASSWORD (infra sets a random one on AWS; local runs use the dev default).
PASSWORD = os.environ.get("LOADTEST_PASSWORD") or "loadtest-pass"
FREE_ACCOUNTS = 70
PREMIUM_ACCOUNTS = 30
DOMAIN = "loadtest.feastflow.app"


def pick_account() -> str:
    if random.random() < 0.7:
        return f"lt-free-{random.randint(1, FREE_ACCOUNTS):02d}@{DOMAIN}"
    return f"lt-prem-{random.randint(1, PREMIUM_ACCOUNTS):02d}@{DOMAIN}"


class Shopper(HttpUser):
    abstract = True

    def on_start(self):
        self.order_ids: list[int] = []
        r = self.client.post(
            "/api/v1/auth/login",
            json={"email": pick_account(), "password": PASSWORD},
            name="POST /auth/login",
        )
        if r.status_code != 200:
            raise StopUser()
        self.client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        menu = self.client.get("/api/v1/menu", name="GET /menu").json()
        self.menu_ids = [m["id"] for m in menu if m["is_available"]]
        if not self.menu_ids:
            raise StopUser()

    def browse(self):
        self.client.get("/api/v1/menu", name="GET /menu")

    def place_order(self):
        picks = random.sample(self.menu_ids, k=min(len(self.menu_ids), random.randint(1, 4)))
        r = self.client.post(
            "/api/v1/orders",
            json={"items": [{"menu_item_id": i, "quantity": random.randint(1, 3)} for i in picks]},
            name="POST /orders",
        )
        if r.status_code == 201:
            self.order_ids = (self.order_ids + [r.json()["id"]])[-20:]

    def my_orders(self):
        self.client.get("/api/v1/orders?page_size=10", name="GET /orders")

    def one_order(self):
        if self.order_ids:
            self.client.get(f"/api/v1/orders/{random.choice(self.order_ids)}", name="GET /orders/{id}")


class NormalUser(Shopper):
    wait_time = between(2, 5)
    tasks = {Shopper.browse: 5, Shopper.place_order: 3, Shopper.my_orders: 2, Shopper.one_order: 1}


class FestivalUser(Shopper):
    wait_time = between(1, 3)
    tasks = {Shopper.browse: 5, Shopper.place_order: 4, Shopper.my_orders: 2, Shopper.one_order: 1}
