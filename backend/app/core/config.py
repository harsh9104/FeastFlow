from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"
    app_version: str = "dev"
    database_url: str = "postgresql+psycopg://feastflow:feastflow@localhost:5432/feastflow"
    db_pool_size: int = 5
    db_max_overflow: int = 5
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60
    log_level: str = "INFO"
    aws_region: str = "us-east-1"
    s3_bucket: str = ""
    admin_email: str = ""
    admin_password: str = ""
    locust_url: str = "http://localhost:8089"
    loadtest_target: str = (
        ""  # base URL Locust should hit, e.g. http://<alb-dns> (empty: Locust's own --host)
    )
    # Shared password of the seeded load-test accounts (lt-*@loadtest.feastflow.app).
    # Empty: dev/test use DEV_LOADTEST_PASSWORD, production seeds no accounts.
    loadtest_password: str = ""
    reports_dir: str = "./reports"  # used when S3_BUCKET is empty
    metrics_provider: str = "local"  # local | cloudwatch
    metrics_cache_ttl_s: int = 30
    asg_name: str = "feastflow-asg"
    alb_dimension: str = ""  # e.g. app/feastflow-alb/abc123
    tg_dimension: str = ""  # e.g. targetgroup/feastflow-tg/abc123
    tg_arn: str = ""
    db_instance_id: str = "feastflow-db"


# Published in loadtest/locustfile.py, so it is never used in production.
DEV_LOADTEST_PASSWORD = "loadtest-pass"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def loadtest_password(s: Settings) -> str | None:
    """Password for the seeded load-test accounts, or None to not seed them."""
    if s.loadtest_password:
        return s.loadtest_password
    return None if s.env == "production" else DEV_LOADTEST_PASSWORD
