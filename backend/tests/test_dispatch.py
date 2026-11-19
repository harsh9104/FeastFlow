import json
from datetime import timedelta

import pytest

from app.core import aws
from app.core.config import get_settings
from app.core.time import utcnow
from app.models.order import Order
from app.models.partner import DeliveryPartner
from app.models.user import User
from app.schemas.order import OrderIn
from app.services import dispatch_service as ds
from app.services import notification_service, order_service, user_service
from tests.conftest import TestingSession, auth, register
from worker.main import Consumer

S = get_settings


def make_user(db, email, prime=False) -> User:
    user = user_service.register(db, email.split("@")[0], email, "secret123")
    if prime:
        user_service.subscribe_prime(db, user)
    return user


def place(db, user, item=1) -> Order:
    body = OrderIn(items=[{"menu_item_id": item, "quantity": 1}], delivery_address="1 Main Road")
    order, _ = order_service.place_order(db, user, body, None)
    return order


def partners(db, n=1, status="AVAILABLE") -> list[DeliveryPartner]:
    ps = [DeliveryPartner(name=f"Rider {i}", phone=f"+9190000{i:05d}", status=status)
          for i in range(n)]
    db.add_all(ps)
    db.commit()
    return ps


def statuses(db, *orders) -> list[str]:
    db.expire_all()
    return [db.get(Order, o.id).status for o in orders]


def make_waiting(db, order, ready_at):
    """Fast-forward an order to 'food ready, waiting for a partner'."""
    ds.confirm_order(db, order.id)
    o = db.get(Order, order.id)
    o.status, o.ready_at, o.stage_due_at = "AWAITING_PARTNER", ready_at, None
    db.commit()


# ---- lifecycle ------------------------------------------------------------------


def test_full_lifecycle_with_timers(db, menu):
    s = S()
    rider = partners(db)[0]
    order = place(db, make_user(db, "asha@example.com"))
    t0 = utcnow()

    ds.confirm_order(db, order.id, t0)
    assert statuses(db, order) == ["CONFIRMED"]

    ds.tick(db, t0 + timedelta(seconds=s.confirm_seconds - 0.5))  # not due yet
    assert statuses(db, order) == ["CONFIRMED"]

    t1 = t0 + timedelta(seconds=s.confirm_seconds)
    ds.tick(db, t1)
    assert statuses(db, order) == ["PREPARING"]

    t2 = t1 + timedelta(seconds=s.prep_seconds)
    counts, notices = ds.tick(db, t2)
    # Ready and assigned in the same tick because a partner was free.
    assert counts["ready"] == 1 and counts["assigned"] == 1
    assert statuses(db, order) == ["OUT_FOR_DELIVERY"]
    db.refresh(rider)
    assert rider.status == "BUSY"
    assert notices[0].status == "OUT_FOR_DELIVERY" and notices[0].partner_name == "Rider 0"

    t3 = t2 + timedelta(seconds=s.delivery_seconds)
    ds.tick(db, t3)
    assert statuses(db, order) == ["DELIVERED"]
    db.refresh(rider)
    assert (rider.status, rider.deliveries_count) == ("AVAILABLE", 1)

    timeline = [e.status for e in order_service.get_order(db, order.id).events]
    assert timeline == ["PLACED", "CONFIRMED", "PREPARING", "AWAITING_PARTNER",
                        "OUT_FOR_DELIVERY", "DELIVERED"]


def test_confirm_is_idempotent_and_ignores_unknown_orders(db, menu):
    order = place(db, make_user(db, "asha@example.com"))
    assert ds.confirm_order(db, order.id).count == 1
    assert ds.confirm_order(db, order.id).count == 0  # SQS redelivery
    assert ds.confirm_order(db, 99999).count == 0
    events = order_service.get_order(db, order.id).events
    assert [e.status for e in events].count("CONFIRMED") == 1


def test_parse_message():
    assert ds.parse_message(json.dumps({"order_id": 7, "priority": 1})) == 7
    for bad in ("not json", "{}", json.dumps({"order_id": "x"}), "[]"):
        assert ds.parse_message(bad) is None


# ---- partner assignment ------------------------------------------------------


def test_prime_order_gets_the_partner_first(db, menu):
    partners(db, 1)
    now = utcnow()
    standard = place(db, make_user(db, "std@example.com"))
    prime = place(db, make_user(db, "vip@example.com", prime=True))
    make_waiting(db, standard, now - timedelta(seconds=30))  # waiting longer
    make_waiting(db, prime, now - timedelta(seconds=5))

    ds.assign_partners(db, now)
    assert statuses(db, prime, standard) == ["OUT_FOR_DELIVERY", "AWAITING_PARTNER"]


def test_long_waiting_standard_order_is_not_starved(db, menu):
    partners(db, 1)
    now = utcnow()
    standard = place(db, make_user(db, "std@example.com"))
    prime = place(db, make_user(db, "vip@example.com", prime=True))
    make_waiting(db, standard, now - timedelta(seconds=S().aging_seconds + 1))
    make_waiting(db, prime, now - timedelta(seconds=5))

    ds.assign_partners(db, now)
    assert statuses(db, standard, prime) == ["OUT_FOR_DELIVERY", "AWAITING_PARTNER"]


def test_orders_wait_until_a_partner_frees_up(db, menu):
    s = S()
    partners(db, 1)
    now = utcnow()
    a = place(db, make_user(db, "a@example.com"))
    b = place(db, make_user(db, "b@example.com"))
    make_waiting(db, a, now - timedelta(seconds=10))
    make_waiting(db, b, now - timedelta(seconds=5))

    ds.tick(db, now)
    assert statuses(db, a, b) == ["OUT_FOR_DELIVERY", "AWAITING_PARTNER"]

    # When a's delivery finishes, the same tick hands the partner to b.
    ds.tick(db, now + timedelta(seconds=s.delivery_seconds))
    assert statuses(db, a, b) == ["DELIVERED", "OUT_FOR_DELIVERY"]


def test_offline_partners_are_never_assigned(db, menu):
    partners(db, 2, status="OFFLINE")
    order = place(db, make_user(db, "a@example.com"))
    make_waiting(db, order, utcnow())
    assert ds.assign_partners(db).count == 0
    assert statuses(db, order) == ["AWAITING_PARTNER"]


def test_work_is_spread_across_partners(db, menu):
    ps = partners(db, 2)
    ps[0].deliveries_count = 5
    db.commit()
    order = place(db, make_user(db, "a@example.com"))
    make_waiting(db, order, utcnow())
    ds.assign_partners(db)
    db.expire_all()
    assert db.get(Order, order.id).partner_id == ps[1].id  # fewer deliveries so far


# ---- sweeper ------------------------------------------------------------------


def test_sweeper_resends_orders_whose_sqs_send_failed(db, menu):
    order = place(db, make_user(db, "a@example.com"))
    aws.sqs().purge_queue(QueueUrl=aws.queue_url(S().sqs_standard_queue))
    o = db.get(Order, order.id)
    o.enqueued_at = None
    db.commit()

    assert ds.sweep_unqueued(db, utcnow()) == 0  # too recent: the API may still be sending
    later = utcnow() + timedelta(seconds=S().sweeper_after_seconds + 1)
    assert ds.sweep_unqueued(db, later) == 1
    db.expire_all()
    assert db.get(Order, order.id).enqueued_at is not None
    assert ds.sweep_unqueued(db, later) == 0


# ---- SQS consumer -----------------------------------------------------------------


def test_consumer_reads_prime_queue_first(db, menu):
    standard = place(db, make_user(db, "std@example.com"))
    prime = place(db, make_user(db, "vip@example.com", prime=True))
    consumer = Consumer(session_factory=TestingSession, long_poll_seconds=0)

    assert consumer.poll_once() == 1
    assert statuses(db, prime, standard) == ["CONFIRMED", "PLACED"]
    assert consumer.poll_once() == 1
    assert statuses(db, standard) == ["CONFIRMED"]
    assert consumer.poll_once() == 0  # both queues empty; messages were deleted


def test_consumer_reads_standard_first_every_fifth_poll():
    s = S()
    consumer = Consumer(long_poll_seconds=0)
    orders = [consumer.queue_order()[0] for _ in range(10)]
    assert orders.count(s.sqs_standard_queue) == 2
    assert orders[4] == s.sqs_standard_queue and orders[9] == s.sqs_standard_queue


def test_consumer_leaves_malformed_messages_for_the_dlq(db):
    url = aws.queue_url(S().sqs_prime_queue)
    aws.sqs().send_message(QueueUrl=url, MessageBody="garbage")
    Consumer(session_factory=TestingSession, long_poll_seconds=0).poll_once()
    attrs = aws.sqs().get_queue_attributes(
        QueueUrl=url, AttributeNames=["ApproximateNumberOfMessagesNotVisible"]
    )["Attributes"]
    assert attrs["ApproximateNumberOfMessagesNotVisible"] == "1"  # not deleted


# ---- SNS ------------------------------------------------------------------------


def _inbox_for(user_id: int) -> str:
    """An SQS queue subscribed with the same filter policy a customer's email gets."""
    url = aws.sqs().create_queue(QueueName=f"inbox-{user_id}")["QueueUrl"]
    arn = aws.sqs().get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])[
        "Attributes"]["QueueArn"]
    aws.sns().subscribe(
        TopicArn=aws.topic_arn(), Protocol="sqs", Endpoint=arn,
        Attributes={"FilterPolicy": json.dumps({"user_id": [str(user_id)]}),
                    "RawMessageDelivery": "true"},
    )
    return url


def test_customers_only_receive_their_own_notifications():
    inbox = _inbox_for(1)
    sent = notification_service.publish([
        notification_service.Notice(10, 1, "CONFIRMED"),
        notification_service.Notice(11, 2, "CONFIRMED"),  # someone else
        notification_service.Notice(12, 1, "PREPARING"),  # not a notifying status
        notification_service.Notice(13, 1, "DELIVERED", is_synthetic=True),  # festival sim
    ])
    assert sent == 2
    msgs = aws.sqs().receive_message(QueueUrl=inbox, MaxNumberOfMessages=10)["Messages"]
    assert [m["Body"] for m in msgs] == [
        "Your order #10 is confirmed and the restaurant has started on it."
    ]


def test_register_subscribes_email_with_filter_policy(client):
    user = register(client, email="asha@example.com")["user"]
    subs = aws.sns().list_subscriptions_by_topic(TopicArn=aws.topic_arn())["Subscriptions"]
    email_sub = next(s for s in subs if s["Endpoint"] == "asha@example.com")
    attrs = aws.sns().get_subscription_attributes(SubscriptionArn=email_sub["SubscriptionArn"])
    assert json.loads(attrs["Attributes"]["FilterPolicy"]) == {"user_id": [str(user["id"])]}


# ---- admin dispatch API ----------------------------------------------------------------


def admin_headers(client, db):
    user_service.ensure_admin(db)
    s = S()
    token = client.post(
        "/api/auth/login", json={"email": s.admin_email, "password": s.admin_password}
    ).json()["access_token"]
    return auth(token)


def test_order_board_lists_active_orders_prime_first(client, db, menu):
    h = admin_headers(client, db)
    standard = place(db, make_user(db, "std@example.com"))
    prime = place(db, make_user(db, "vip@example.com", prime=True))
    board = client.get("/api/admin/orders", headers=h).json()
    assert [o["id"] for o in board["items"]] == [prime.id, standard.id]
    assert board["items"][0]["customer_name"] == "vip"
    assert client.get("/api/admin/orders?status=DELIVERED", headers=h).json()["total"] == 0
    assert client.get("/api/admin/orders?status=NOPE", headers=h).status_code == 422


def test_partner_management(client, db, menu):
    h = admin_headers(client, db)
    res = client.post("/api/admin/partners", json={"name": "New Rider", "phone": "+919876543210"},
                      headers=h)
    assert res.status_code == 201 and res.json()["status"] == "AVAILABLE"
    pid = res.json()["id"]
    dup = client.post("/api/admin/partners", json={"name": "Dup Rider", "phone": "+919876543210"},
                      headers=h)
    assert dup.status_code == 409

    off = client.patch(f"/api/admin/partners/{pid}", json={"status": "OFFLINE"}, headers=h)
    assert off.json()["status"] == "OFFLINE"
    bad = client.patch(f"/api/admin/partners/{pid}", json={"status": "BUSY"}, headers=h)
    assert bad.status_code == 422  # only the worker sets BUSY

    # A partner on a delivery can't be taken off shift.
    client.patch(f"/api/admin/partners/{pid}", json={"status": "AVAILABLE"}, headers=h)
    order = place(db, make_user(db, "a@example.com"))
    make_waiting(db, order, utcnow())
    ds.assign_partners(db)
    listed = {p["id"]: p for p in client.get("/api/admin/partners", headers=h).json()}
    assert listed[pid]["status"] == "BUSY" and listed[pid]["current_order_id"] == order.id
    busy = client.patch(f"/api/admin/partners/{pid}", json={"status": "OFFLINE"}, headers=h)
    assert busy.status_code == 409

    customer = register(client, email="c@example.com")["access_token"]
    assert client.get("/api/admin/partners", headers=auth(customer)).status_code == 403


def test_dispatch_stats(client, db, menu):
    h = admin_headers(client, db)
    partners(db, 3)
    place(db, make_user(db, "std@example.com"))
    place(db, make_user(db, "vip@example.com", prime=True))
    stats = client.get("/api/admin/dispatch/stats", headers=h).json()
    assert stats["queues"]["prime"]["waiting"] == 1
    assert stats["queues"]["standard"]["waiting"] == 1
    assert stats["orders_by_status"]["PLACED"] == 2
    assert stats["partners"] == {"AVAILABLE": 3, "BUSY": 0, "OFFLINE": 0}
    assert stats["prime"]["orders"] == 1 and stats["standard"]["orders"] == 1


# ---- real MySQL only: concurrent workers ---------------------------------------------


@pytest.mark.skipif(
    not TestingSession.kw["bind"].url.drivername.startswith("mysql"),
    reason="needs TEST_DATABASE_URL pointing at MySQL (SQLite has no SKIP LOCKED)",
)
def test_concurrent_workers_never_double_assign(db, menu):
    from concurrent.futures import ThreadPoolExecutor

    partners(db, 5)
    now = utcnow()
    for i in range(30):
        order = place(db, make_user(db, f"u{i}@example.com", prime=i % 3 == 0))
        make_waiting(db, order, now)

    def worker(_):
        total = 0
        for _ in range(10):
            with TestingSession() as s:
                total += ds.assign_partners(s, now).count
        return total

    with ThreadPoolExecutor(4) as pool:
        assigned = sum(pool.map(worker, range(4)))

    db.expire_all()
    active = db.query(Order).filter(Order.status == "OUT_FOR_DELIVERY").all()
    assert assigned == len(active) == 5  # exactly one order per partner
    assert len({o.partner_id for o in active}) == 5
