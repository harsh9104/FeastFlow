"""Order worker: `python -m worker.main`. Runs next to the API on every EC2 instance,
so when the Auto Scaling Group adds instances it also adds order-processing capacity.

Two threads:
  consumer: reads SQS (orders-prime before orders-standard) and confirms orders
  ticker:   moves orders along their timers, assigns partners, re-sends failed sends
"""

import logging
import signal
import threading

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.exc import SQLAlchemyError

from app.core import aws
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services import dispatch_service, notification_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("worker")

SWEEP_EVERY_TICKS = 10


class Consumer:
    def __init__(self, session_factory=SessionLocal, long_poll_seconds: int = 2):
        self.session_factory = session_factory
        self.long_poll_seconds = long_poll_seconds
        self.polls = 0

    def queue_order(self) -> list[str]:
        """Prime first for `prime_poll_weight` polls, then one poll reads standard
        first (4:1 by default), so standard orders still move during a Prime flood."""
        s = get_settings()
        self.polls += 1
        weight = max(1, s.prime_poll_weight)
        if self.polls % (weight + 1) == 0:
            return [s.sqs_standard_queue, s.sqs_prime_queue]
        return [s.sqs_prime_queue, s.sqs_standard_queue]

    def poll_once(self) -> int:
        """Process one batch from the first queue that has messages. Returns how many
        orders were confirmed."""
        for i, name in enumerate(self.queue_order()):
            url = aws.queue_url(name)
            # Quick check of the first queue; long-poll the second so an idle worker
            # isn't spinning (and paying for) empty receives.
            res = aws.sqs().receive_message(
                QueueUrl=url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=0 if i == 0 else self.long_poll_seconds,
            )
            messages = res.get("Messages", [])
            if messages:
                return self._process(url, messages)
        return 0

    def _process(self, url: str, messages: list[dict]) -> int:
        confirmed, done = 0, []
        notices = []
        for m in messages:
            order_id = dispatch_service.parse_message(m["Body"])
            if order_id is None:
                # Not deleted: after maxReceiveCount tries SQS moves it to the DLQ to inspect.
                log.error("malformed message %s: %r", m["MessageId"], m["Body"][:200])
                continue
            try:
                with self.session_factory() as db:
                    r = dispatch_service.confirm_order(db, order_id)
            except SQLAlchemyError:
                log.exception("DB error confirming order %s; SQS will redeliver", order_id)
                continue
            confirmed += r.count
            notices.extend(r.notices)
            done.append({"Id": m["MessageId"], "ReceiptHandle": m["ReceiptHandle"]})
        if done:
            aws.sqs().delete_message_batch(QueueUrl=url, Entries=done)
        notification_service.publish(notices)
        return confirmed


def run_consumer(stop: threading.Event) -> None:
    consumer = Consumer()
    while not stop.is_set():
        try:
            consumer.poll_once()
        except (BotoCoreError, ClientError):
            log.exception("SQS error; retrying in 5 s")
            stop.wait(5)


def run_ticker(stop: threading.Event) -> None:
    s = get_settings()
    ticks = 0
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                counts, notices = dispatch_service.tick(db)
                if ticks % SWEEP_EVERY_TICKS == 0:
                    dispatch_service.sweep_unqueued(db)
            notification_service.publish(notices)
            if any(counts.values()):
                log.info("tick %s", counts)
        except SQLAlchemyError:
            log.exception("DB error in ticker; retrying")
        ticks += 1
        stop.wait(s.worker_tick_seconds)


def main() -> None:
    stop = threading.Event()

    def shutdown(signum, _frame):
        # ASG scale-in or `docker stop` sends SIGTERM: finish the current batch, then exit.
        log.info("signal %s received, stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    threads = [
        threading.Thread(target=run_consumer, args=(stop,), name="consumer"),
        threading.Thread(target=run_ticker, args=(stop,), name="ticker"),
    ]
    for t in threads:
        t.start()
    log.info("worker started")
    for t in threads:
        t.join()
    log.info("worker stopped")


if __name__ == "__main__":
    main()
