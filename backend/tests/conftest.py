"""Tests run on in-memory SQLite by default (fast, no Docker needed).
Set TEST_DATABASE_URL to a MySQL URL to run them against real MySQL; P3's
concurrency tests (SKIP LOCKED) will require that."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app

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
