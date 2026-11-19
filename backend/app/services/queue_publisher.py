"""Send orders to SQS. SQS has no message priority, so Prime orders go to their own
queue (orders-prime) and the worker always empties that queue first."""

import json
import logging

from botocore.exceptions import BotoCoreError, ClientError

from app.core import aws
from app.core.config import get_settings
from app.core.time import utcnow

log = logging.getLogger(__name__)


def queue_name_for(priority: int) -> str:
    s = get_settings()
    return s.sqs_prime_queue if priority == 1 else s.sqs_standard_queue


def send_order(order_id: int, priority: int) -> bool:
    """True if SQS accepted the message. False is not fatal: the order is already
    saved with enqueued_at = NULL and the worker's sweeper re-sends it."""
    body = {"order_id": order_id, "priority": priority, "sent_at": utcnow().isoformat()}
    try:
        aws.sqs().send_message(
            QueueUrl=aws.queue_url(queue_name_for(priority)), MessageBody=json.dumps(body)
        )
        return True
    except (BotoCoreError, ClientError) as exc:
        log.error("SQS send failed for order %s: %s", order_id, exc)
        return False
