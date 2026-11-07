import os

# Must be set before the app is imported. Cheap bcrypt is not configurable, so tests stay modest.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://feastflow:feastflow@localhost:5432/feastflow_test",
)
os.environ["JWT_SECRET"] = "test-secret"
import tempfile  # noqa: E402

os.environ["REPORTS_DIR"] = tempfile.mkdtemp(prefix="ff-reports-")
os.environ["S3_BUCKET"] = ""
os.environ["ENV"] = "test"
os.environ["METRICS_CACHE_TTL_S"] = "0"
os.environ["ADMIN_EMAIL"] = ""
os.environ["ADMIN_PASSWORD"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import models  # noqa: E402, F401
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with engine.begin() as c:
        c.execute(
            text(
                "TRUNCATE users, menu_items, load_test_runs, app_metrics, reports RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def make_user():
    def _make(email, role="CUSTOMER", tier="FREE", password="password123"):
        with SessionLocal() as db:
            u = User(
                email=email,
                full_name="Test",
                password_hash=hash_password(password, rounds=4),
                role=role,
                subscription_tier=tier,
            )
            db.add(u)
            db.commit()
            return u.id

    return _make


@pytest.fixture
def auth_header(client):
    def _login(email, password="password123"):
        r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _login
