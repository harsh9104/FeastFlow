"""Festival-day simulator: fire N orders over M seconds from the seeded test customers,
X% of them Prime. Orders go through the normal checkout path (DB + SQS), so the worker,
queues and dashboard behave exactly as they would for real customers."""

import logging
import random
import threading
import time
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.instance import instance_id
from app.core.time import utcnow
from app.db.session import SessionLocal
from app.models.festival import FestivalRun
from app.models.menu import MenuItem, Restaurant
from app.models.user import User
from app.schemas.order import OrderIn
from app.services import order_service

log = logging.getLogger(__name__)

STALE_AFTER = timedelta(seconds=30)  # no heartbeat for this long = instance died
CHECK_EVERY = 20  # orders between cancel checks / progress saves
ADDRESSES = ["MG Road", "Koramangala 5th Block", "Indiranagar 100ft Rd", "HSR Sector 2",
             "Whitefield Main Rd", "Jayanagar 4th Block", "Electronic City Ph 1"]


def _expire_stale(db: Session) -> None:
    for run in db.scalars(select(FestivalRun).where(FestivalRun.status == "RUNNING")):
        if run.heartbeat_at < utcnow() - STALE_AFTER:
            run.status, run.finished_at = "FAILED", run.heartbeat_at
            run.error = f"Instance {run.instance_id} stopped responding"
    db.commit()


def list_runs(db: Session, limit: int = 10) -> list[FestivalRun]:
    _expire_stale(db)
    return list(db.scalars(select(FestivalRun).order_by(FestivalRun.id.desc()).limit(limit)))


def _test_users(db: Session) -> tuple[list[User], list[User]]:
    users = list(db.scalars(select(User).where(User.is_test_user.is_(True))))
    return [u for u in users if u.is_prime], [u for u in users if not u.is_prime]


def create_run(
    db: Session, admin: User, orders: int, duration: int, prime_percent: int
) -> FestivalRun:
    _expire_stale(db)
    if db.scalar(select(FestivalRun.id).where(FestivalRun.status == "RUNNING")):
        raise HTTPException(status.HTTP_409_CONFLICT, "A festival run is already in progress")
    prime, standard = _test_users(db)
    if (prime_percent > 0 and not prime) or (prime_percent < 100 and not standard):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Load-test customers are missing. They are created at startup by `python -m app.seed`.",
        )
    run = FestivalRun(
        requested_orders=orders,
        prime_percent=prime_percent,
        duration_seconds=duration,
        instance_id=instance_id(),
        created_by=admin.id,
        heartbeat_at=utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def cancel_run(db: Session, run_id: int) -> FestivalRun:
    run = db.get(FestivalRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    if run.status == "RUNNING":
        # The generator, on whatever instance it runs, sees this at its next check.
        run.status, run.finished_at = "CANCELLED", utcnow()
        db.commit()
    return run


def _random_order(menus: dict[int, list[MenuItem]]) -> OrderIn:
    rid = random.choice(list(menus))
    picks = random.sample(menus[rid], k=min(len(menus[rid]), random.randint(1, 3)))
    return OrderIn(
        items=[{"menu_item_id": m.id, "quantity": random.randint(1, 2)} for m in picks],
        delivery_address=f"{random.randint(1, 400)} {random.choice(ADDRESSES)}, Bengaluru",
    )


def execute(run_id: int, session_factory=SessionLocal, sleep=time.sleep) -> None:
    """Generate the run's orders, pacing them evenly over its duration. Runs in a
    background thread of the API instance that accepted the request."""
    with session_factory() as db:
        run = db.get(FestivalRun, run_id)
        try:
            _generate(db, run, sleep)
        except Exception as exc:  # noqa: BLE001 - record any failure on the run
            log.exception("festival run %s failed", run_id)
            db.rollback()
            run = db.get(FestivalRun, run_id)
            run.status, run.finished_at, run.error = "FAILED", utcnow(), str(exc)[:255]
            db.commit()


def _generate(db: Session, run: FestivalRun, sleep) -> None:
    prime_users, standard_users = _test_users(db)
    menus: dict[int, list[MenuItem]] = {}
    for item in db.scalars(
        select(MenuItem)
        .join(Restaurant)
        .where(MenuItem.is_available.is_(True), Restaurant.is_open.is_(True))
    ):
        menus.setdefault(item.restaurant_id, []).append(item)
    if not menus:
        raise RuntimeError("No open restaurant has available items")

    # Exact Prime share, in random order.
    n = run.requested_orders
    n_prime = round(n * run.prime_percent / 100)
    plan = [True] * n_prime + [False] * (n - n_prime)
    random.shuffle(plan)

    interval = run.duration_seconds / n if n else 0
    start = time.monotonic()
    created = prime_created = failed = 0
    run_id = run.id

    for i, is_prime in enumerate(plan):
        if i % CHECK_EVERY == 0:
            db.refresh(run)
            if run.status != "RUNNING":
                log.info("festival run %s stopped (%s) after %d orders", run_id, run.status, i)
                break
            run.created_orders, run.prime_orders, run.failed_orders = created, prime_created, failed
            run.heartbeat_at = utcnow()
            db.commit()

        user = random.choice(prime_users if is_prime else standard_users)
        try:
            order_service.place_order(db, user, _random_order(menus), None, synthetic=True)
            created += 1
            prime_created += is_prime
        except HTTPException as exc:  # e.g. a dish was marked sold out mid-run
            db.rollback()
            failed += 1
            log.warning("festival order rejected: %s", exc.detail)

        delay = start + (i + 1) * interval - time.monotonic()
        if delay > 0:
            sleep(delay)

    db.refresh(run)
    run.created_orders, run.prime_orders, run.failed_orders = created, prime_created, failed
    run.heartbeat_at = utcnow()
    if run.status == "RUNNING":
        run.status, run.finished_at = "COMPLETED", utcnow()
    db.commit()
    log.info(
        "festival run %s: %d orders (%d Prime), %d rejected", run_id, created, prime_created, failed
    )


def start_in_background(run_id: int) -> None:
    threading.Thread(target=execute, args=(run_id,), name=f"festival-{run_id}", daemon=True).start()


def max_orders() -> int:
    return get_settings().festival_max_orders
