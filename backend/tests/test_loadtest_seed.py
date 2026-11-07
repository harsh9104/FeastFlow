"""Migration 0006: who gets the 100 load-test accounts, and with which password."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.core.config import DEV_LOADTEST_PASSWORD, get_settings, loadtest_password
from app.db.session import engine
from app.models.user import User

MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "0006_seed_loadtest_users.py"


@pytest.fixture
def run_seed(monkeypatch):
    spec = importlib.util.spec_from_file_location("seed_0006", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def _run():
        with engine.begin() as conn:
            monkeypatch.setattr(mod, "op", SimpleNamespace(get_bind=lambda: conn))
            mod.upgrade()
        with engine.connect() as conn:
            return conn.scalar(
                select(func.count()).select_from(User).where(User.email.like("lt-%"))
            )

    return _run


def test_password_rules(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "loadtest_password", "")
    assert loadtest_password(s) == DEV_LOADTEST_PASSWORD  # dev/test default
    monkeypatch.setattr(s, "env", "production")
    assert loadtest_password(s) is None  # production never uses the public password
    monkeypatch.setattr(s, "loadtest_password", "r" * 32)
    assert loadtest_password(s) == "r" * 32


def test_production_without_password_seeds_nothing(monkeypatch, run_seed):
    s = get_settings()
    monkeypatch.setattr(s, "env", "production")
    monkeypatch.setattr(s, "loadtest_password", "")
    assert run_seed() == 0


def test_production_seeds_with_configured_password(monkeypatch, run_seed, client):
    s = get_settings()
    monkeypatch.setattr(s, "env", "production")
    monkeypatch.setattr(s, "loadtest_password", "a-random-secret-0123456789")
    assert run_seed() == 100
    login = {"email": "lt-prem-01@loadtest.feastflow.app"}
    ok = client.post("/api/v1/auth/login", json={**login, "password": "a-random-secret-0123456789"})
    assert ok.status_code == 200
    bad = client.post("/api/v1/auth/login", json={**login, "password": DEV_LOADTEST_PASSWORD})
    assert bad.status_code == 401
