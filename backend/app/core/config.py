from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str = "mysql+pymysql://feastflow:feastflow@localhost:3306/feastflow"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 120
    # bcrypt work factor: 12 (~0.25 s per hash) in production; tests use 4.
    bcrypt_rounds: int = 12
    # Must pass email validation: reserved domains such as .local are rejected.
    admin_email: str = "admin@feastflow.app"
    admin_password: str = "Admin@12345"
    prime_plan_days: int = 30

    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None  # LocalStack only; None on AWS
    sqs_prime_queue: str = "orders-prime"
    sqs_standard_queue: str = "orders-standard"
    sns_topic_name: str = "order-notifications"
    s3_bucket: str = "feastflow-assets"
    # Locally the API reaches LocalStack as http://localstack:4566, but the browser
    # needs http://localhost:4566, so presigned image URLs are signed for this host.
    s3_public_endpoint_url: str | None = None
    image_url_ttl_seconds: int = 3600
    seed_images: bool = False  # upload placeholder food images for items missing one

    # ---- festival-day load testing ----
    # Seeded test customers (no email subscriptions, orders flagged synthetic).
    loadtest_users: int = 200
    loadtest_prime_percent: int = 30
    loadtest_email_domain: str = "loadtest.feastflow.app"
    # Only when set can anyone log in as a test customer (Locust needs this).
    # Unset = the accounts exist for the festival simulator but can't be logged into.
    loadtest_password: str | None = None
    festival_max_orders: int = 5000
    # Locust web API on the load-generator EC2, e.g. http://10.0.1.23:8089
    locust_url: str | None = None

    # Built React app (copied in by the Dockerfile). Missing = API only.
    static_dir: str = "static"

    max_order_lines: int = 20
    max_item_quantity: int = 20

    # Customers get order emails through one SNS topic with a per-user filter policy.
    sns_email_subscriptions: bool = True

    # ---- worker / simulated kitchen and delivery (seconds) ----
    confirm_seconds: float = 2  # CONFIRMED -> PREPARING
    prep_seconds: float = 20  # PREPARING -> food ready, needs a partner
    delivery_seconds: float = 40  # OUT_FOR_DELIVERY -> DELIVERED, partner free again
    timer_jitter: float = 0.25  # +/- 25% so orders don't all move in lockstep
    # A standard order waiting longer than this is treated like Prime, so a flood of
    # Prime orders on a festival day can't starve ordinary customers forever.
    aging_seconds: float = 120
    # Worker reads Prime first N times, then standard first once (same anti-starvation idea).
    prime_poll_weight: int = 4
    worker_tick_seconds: float = 1
    worker_batch_size: int = 50
    # Orders whose SQS send failed (enqueued_at NULL) are re-sent after this long.
    sweeper_after_seconds: float = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
