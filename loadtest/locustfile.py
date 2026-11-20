"""FeastFlow load test: simulated customers on a normal day or a festival day.

Each simulated user logs in as one of the seeded load-test customers (30% Prime),
browses menus, places orders and polls their order status like the real UI does.
The traffic goes through the ALB, so CPU rises on the app instances and the Auto
Scaling Group adds instances during the festival profile.

Run locally (UI on :8089):   locust -f locustfile.py --host http://localhost:8000
Headless festival run:
    locust -f locustfile.py --host http://<alb-dns> --headless --profile festival
The admin dashboard starts/stops runs through Locust's web API (POST /swarm, GET /stop).
"""

import random
import uuid

from locust import HttpUser, LoadTestShape, between, events, task
from locust.exception import StopUser

# (stage ends at second, users, spawn rate per second)
PROFILES = {
    # A quiet weekday: steady light traffic for 10 minutes.
    "normal": [(60, 10, 2), (600, 20, 2)],
    # Festival evening, 20 minutes. Long enough for the ASG to react: the CPU alarm
    # needs a few minutes above target, and new instances take ~3 min to boot.
    "festival": [
        (120, 50, 5),  # early evening
        (300, 300, 10),  # orders pour in
        (540, 300, 10),  # sustained rush
        (660, 450, 25),  # peak spike (dinner time)
        (840, 300, 25),  # still busy
        (1200, 30, 10),  # quiet again: watch the ASG scale back in
    ],
}


@events.init_command_line_parser.add_listener
def _add_arguments(parser):
    parser.add_argument(
        "--profile",
        choices=list(PROFILES),
        default="normal",
        include_in_web_ui=True,
        help="Traffic shape: normal day or festival day",
    )
    parser.add_argument("--test-users", type=int, env_var="LOADTEST_USERS", default=200,
                        help="How many seeded load-test customers exist")
    parser.add_argument("--email-domain", env_var="LOADTEST_EMAIL_DOMAIN",
                        default="loadtest.feastflow.app")
    parser.add_argument("--test-password", env_var="LOADTEST_PASSWORD", default="",
                        is_secret=True, help="LOADTEST_PASSWORD configured on the app")


class Customer(HttpUser):
    wait_time = between(1, 4)

    def on_start(self):
        opts = self.environment.parsed_options
        if not opts.test_password:
            raise StopUser("LOADTEST_PASSWORD is not set")
        email = f"customer{random.randint(1, opts.test_users):04d}@{opts.email_domain}"
        with self.client.post(
            "/api/auth/login",
            json={"email": email, "password": opts.test_password},
            name="/api/auth/login",
            catch_response=True,
        ) as res:
            if res.status_code != 200:
                res.failure(f"login failed ({res.status_code}); check LOADTEST_PASSWORD")
                raise StopUser()
        self.client.headers["Authorization"] = f"Bearer {res.json()['access_token']}"
        self.restaurants = [r["id"] for r in self.client.get("/api/restaurants").json()
                            if r["is_open"]]
        self.menus: dict[int, list[dict]] = {}
        self.my_orders: list[int] = []

    def _menu(self, rid: int) -> list[dict]:
        items = self.client.get(f"/api/restaurants/{rid}/menu",
                                name="/api/restaurants/[id]/menu").json()
        self.menus[rid] = [i for i in items if i["is_available"]]
        return self.menus[rid]

    @task(5)
    def browse(self):
        self.client.get("/api/restaurants")
        if self.restaurants:
            self._menu(random.choice(self.restaurants))

    @task(3)
    def place_order(self):
        if not self.restaurants:
            return
        rid = random.choice(self.restaurants)
        menu = self.menus.get(rid) or self._menu(rid)
        if not menu:
            return
        picks = random.sample(menu, k=min(len(menu), random.randint(1, 3)))
        res = self.client.post(
            "/api/orders",
            json={
                "items": [{"menu_item_id": i["id"], "quantity": random.randint(1, 2)}
                          for i in picks],
                "delivery_address": f"{random.randint(1, 400)} Festival Street, Bengaluru",
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        if res.status_code == 202:
            self.my_orders = (self.my_orders + [res.json()["id"]])[-5:]

    @task(4)
    def track_order(self):
        # The order page polls every 3 s; this is a large share of real traffic.
        if self.my_orders:
            self.client.get(f"/api/orders/{random.choice(self.my_orders)}",
                            name="/api/orders/[id]")

    @task(1)
    def order_history(self):
        self.client.get("/api/orders")


class ProfileShape(LoadTestShape):
    """Drives the user count from the chosen profile; stops when the profile ends."""

    def tick(self):
        profile = self.runner.environment.parsed_options.profile
        elapsed = self.get_run_time()
        for ends_at, users, rate in PROFILES[profile]:
            if elapsed < ends_at:
                return users, rate
        return None
