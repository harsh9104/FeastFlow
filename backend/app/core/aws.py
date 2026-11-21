"""boto3 clients. On AWS they authenticate through the EC2 instance profile (LabRole);
locally AWS_ENDPOINT_URL points them at LocalStack."""

from functools import lru_cache

import boto3
from botocore.config import Config

from app.core.config import get_settings

_RETRIES = Config(retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=2)


def client(service: str, endpoint_url: str | None = None):
    s = get_settings()
    return boto3.client(
        service,
        region_name=s.aws_region,
        endpoint_url=endpoint_url or s.aws_endpoint_url or None,
        config=_RETRIES,
    )


@lru_cache
def sqs():
    return client("sqs")


@lru_cache
def s3():
    return client("s3")


@lru_cache
def s3_presigner():
    s = get_settings()
    return client("s3", endpoint_url=s.s3_public_endpoint_url)


@lru_cache
def sns():
    return client("sns")


@lru_cache
def topic_arn() -> str:
    # create_topic is idempotent: it returns the existing topic's ARN.
    return sns().create_topic(Name=get_settings().sns_topic_name)["TopicArn"]


@lru_cache
def queue_url(name: str) -> str:
    return sqs().get_queue_url(QueueName=name)["QueueUrl"]


@lru_cache
def service(name: str):
    """Any other client (autoscaling, cloudwatch, rds, ec2, elbv2, budgets, sts), cached."""
    return client(name)


def reset_clients() -> None:
    """Tests call this so each test gets clients bound to a fresh moto mock."""
    for fn in (sqs, s3, s3_presigner, sns, topic_arn, queue_url, service):
        fn.cache_clear()
