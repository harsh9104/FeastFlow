from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str = "mysql+pymysql://feastflow:feastflow@localhost:3306/feastflow"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 120
    admin_email: str = "admin@feastflow.local"
    admin_password: str = "Admin@12345"
    prime_plan_days: int = 30

    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None  # LocalStack only; None on AWS
    sqs_prime_queue: str = "orders-prime"
    sqs_standard_queue: str = "orders-standard"
    sns_topic_name: str = "order-notifications"
    s3_bucket: str = "feastflow-assets"


@lru_cache
def get_settings() -> Settings:
    return Settings()
