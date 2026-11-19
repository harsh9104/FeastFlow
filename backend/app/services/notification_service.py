"""Customer notifications through one SNS topic.

Each customer's email is subscribed with a filter policy {"user_id": ["<id>"]}, and
every message carries a user_id attribute, so a customer only gets their own updates.
AWS emails a confirmation link first; nothing is delivered until they click it."""

import json
import logging
from dataclasses import dataclass

from botocore.exceptions import BotoCoreError, ClientError

from app.core import aws
from app.core.config import get_settings

log = logging.getLogger(__name__)

# Only these steps send a message, so customers aren't spammed with every status.
NOTIFY_STATUSES = {
    "CONFIRMED": "Your order #{id} is confirmed and the restaurant has started on it.",
    "OUT_FOR_DELIVERY": "Your order #{id} is on the way with {partner}.",
    "DELIVERED": "Your order #{id} has been delivered. Enjoy your meal!",
}


@dataclass(frozen=True)
class Notice:
    order_id: int
    user_id: int
    status: str
    is_synthetic: bool = False
    partner_name: str | None = None


def publish(notices: list[Notice]) -> int:
    """Publish after the DB commit. Failures are logged, never raised: a missed email
    must not undo or retry an order step. Returns how many were sent."""
    sent = 0
    for n in notices:
        template = NOTIFY_STATUSES.get(n.status)
        if template is None or n.is_synthetic:  # festival test orders stay silent
            continue
        text = template.format(id=n.order_id, partner=n.partner_name or "your delivery partner")
        try:
            aws.sns().publish(
                TopicArn=aws.topic_arn(),
                Subject=f"FeastFlow order #{n.order_id}: {n.status.replace('_', ' ').title()}",
                Message=text,
                MessageAttributes={
                    "user_id": {"DataType": "String", "StringValue": str(n.user_id)},
                    "status": {"DataType": "String", "StringValue": n.status},
                },
            )
            sent += 1
        except (BotoCoreError, ClientError) as exc:
            log.warning("SNS publish failed for order %s: %s", n.order_id, exc)
    return sent


def subscribe_email(user_id: int, email: str) -> bool:
    if not get_settings().sns_email_subscriptions:
        return False
    try:
        aws.sns().subscribe(
            TopicArn=aws.topic_arn(),
            Protocol="email",
            Endpoint=email,
            Attributes={"FilterPolicy": json.dumps({"user_id": [str(user_id)]})},
        )
        return True
    except (BotoCoreError, ClientError) as exc:
        log.warning("SNS subscribe failed for user %s: %s", user_id, exc)
        return False
