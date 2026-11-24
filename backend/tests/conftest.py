"""Tests run on in-memory SQLite by default (fast, no Docker needed).
Set TEST_DATABASE_URL to a MySQL URL to run them against real MySQL; P3's
concurrency tests (SKIP LOCKED) will require that."""

import os

# Never let tests touch real AWS or LocalStack: moto intercepts these fake credentials.
os.environ.update(
    AWS_ACCESS_KEY_ID="testing",
    AWS_SECRET_ACCESS_KEY="testing",
    AWS_SESSION_TOKEN="testing",
    AWS_DEFAULT_REGION="us-east-1",
    AWS_ENDPOINT_URL="",
    S3_PUBLIC_ENDPOINT_URL="",
    TIMER_JITTER="0",  # deterministic worker timers
    BCRYPT_ROUNDS="4",  # minimum cost: keeps the suite fast, production stays at 12
    # Pin settings a developer's shell might also define, so tests behave like CI.
    ADMIN_EMAIL="admin@feastflow.app",
    ADMIN_PASSWORD="Admin@12345",
    JWT_SECRET="test-secret",
    SNS_EMAIL_SUBSCRIPTIONS="true",
    LOADTEST_USERS="10",
    LOADTEST_PRIME_PERCENT="30",
    LOADTEST_PASSWORD="",
    LOCUST_URL="",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from moto import mock_aws  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402, F401
from app.core import aws  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.menu import MenuItem, Restaurant  # noqa: E402


@pytest.fixture(autouse=True)
def fake_aws():
    """Fresh in-memory SQS queues and S3 bucket for every test."""
    get_settings.cache_clear()
    with mock_aws():
        aws.reset_clients()
        s = get_settings()
        for name in (s.sqs_prime_queue, s.sqs_standard_queue):
            aws.sqs().create_queue(QueueName=name)
        aws.s3().create_bucket(Bucket=s.s3_bucket)
        aws.topic_arn()  # creates the SNS topic
        yield
    aws.reset_clients()


_url = os.getenv("TEST_DATABASE_URL", "sqlite://")
_kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
engine = create_engine(_url, **(_kwargs if _url.startswith("sqlite") else {}))
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def register(client, email="asha@example.com", password="secret123", name="Asha"):
    res = client.post(
        "/api/auth/register", json={"name": name, "email": email, "password": password}
    )
    assert res.status_code == 201, res.text
    return res.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def menu(db):
    """Two restaurants: 1 has items 1-3 (item 3 unavailable), 2 has item 4."""
    db.add_all(
        [
            Restaurant(id=1, name="Spice Route", area="MG Road", cuisine="North Indian"),
            Restaurant(id=2, name="Dosa Junction", area="Koramangala", cuisine="South Indian"),
            MenuItem(
                id=1,
                restaurant_id=1,
                name="Paneer",
                category="Main",
                price=250,
                image_key="menu/1.svg",
            ),
            MenuItem(id=2, restaurant_id=1, name="Naan", category="Breads", price=50),
            MenuItem(
                id=3,
                restaurant_id=1,
                name="Kulfi",
                category="Desserts",
                price=90,
                is_available=False,
            ),
            MenuItem(id=4, restaurant_id=2, name="Dosa", category="Dosa", price=130),
        ]
    )
    db.commit()


def queued_messages(queue_name: str) -> list[dict]:
    import json

    res = aws.sqs().receive_message(
        QueueUrl=aws.queue_url(queue_name), MaxNumberOfMessages=10, WaitTimeSeconds=0
    )
    return [json.loads(m["Body"]) for m in res.get("Messages", [])]
