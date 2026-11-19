from datetime import timedelta

import jwt

from app.core.config import get_settings
from app.core.time import utcnow
from app.models.user import User
from app.services.user_service import ensure_admin
from tests.conftest import auth, register


def test_register_returns_token_and_customer(client):
    body = register(client, email="Asha@Example.com")
    assert body["user"]["email"] == "asha@example.com"  # stored lower-case
    assert body["user"]["role"] == "CUSTOMER"
    assert body["user"]["is_prime"] is False
    me = client.get("/api/users/me", headers=auth(body["access_token"]))
    assert me.status_code == 200 and me.json()["id"] == body["user"]["id"]


def test_duplicate_email_rejected_case_insensitive(client):
    register(client, email="asha@example.com")
    res = client.post(
        "/api/auth/register",
        json={"name": "Other", "email": "ASHA@example.com", "password": "secret123"},
    )
    assert res.status_code == 409


def test_short_password_rejected(client):
    res = client.post(
        "/api/auth/register", json={"name": "Asha", "email": "a@example.com", "password": "short"}
    )
    assert res.status_code == 422


def test_login_ok_and_wrong_password(client):
    register(client)
    ok = client.post("/api/auth/login", json={"email": "asha@example.com", "password": "secret123"})
    assert ok.status_code == 200
    bad = client.post("/api/auth/login", json={"email": "asha@example.com", "password": "nope1234"})
    assert bad.status_code == 401
    unknown = client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": "secret123"}
    )
    assert unknown.status_code == 401


def test_me_requires_valid_token(client):
    assert client.get("/api/users/me").status_code == 401
    assert client.get("/api/users/me", headers=auth("garbage")).status_code == 401
    expired = jwt.encode(
        {"sub": "1", "exp": utcnow() - timedelta(minutes=1)}, get_settings().jwt_secret, "HS256"
    )
    assert client.get("/api/users/me", headers=auth(expired)).status_code == 401


def test_admin_endpoint_forbidden_for_customer(client):
    token = register(client)["access_token"]
    assert client.get("/api/admin/users", headers=auth(token)).status_code == 403


def test_seeded_admin_can_list_users(client, db):
    assert ensure_admin(db) is True
    assert ensure_admin(db) is False  # idempotent
    s = get_settings()
    login = client.post(
        "/api/auth/login", json={"email": s.admin_email, "password": s.admin_password}
    )
    assert login.status_code == 200 and login.json()["user"]["role"] == "ADMIN"
    register(client)
    res = client.get("/api/admin/users", headers=auth(login.json()["access_token"]))
    assert res.status_code == 200 and res.json()["total"] == 2


def test_prime_subscribe_cancel_and_expiry(client, db):
    body = register(client)
    token = body["access_token"]

    sub = client.post("/api/prime/subscribe", headers=auth(token))
    assert sub.status_code == 200
    assert sub.json()["user"]["is_prime"] is True
    first_expiry = db.get(User, body["user"]["id"]).prime_expires_at

    # Renewing early stacks another 30 days on top.
    client.post("/api/prime/subscribe", headers=auth(token))
    db.expire_all()
    second_expiry = db.get(User, body["user"]["id"]).prime_expires_at
    assert second_expiry - first_expiry == timedelta(days=get_settings().prime_plan_days)

    cancel = client.post("/api/prime/cancel", headers=auth(token))
    assert cancel.json()["user"]["is_prime"] is False


def test_prime_lapses_when_expiry_passes(client, db):
    body = register(client)
    user = db.get(User, body["user"]["id"])
    user.prime_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    # Even with an old token that said prime=True, the server reads the DB.
    me = client.get("/api/users/me", headers=auth(body["access_token"]))
    assert me.json()["is_prime"] is False


def test_admin_prime_filter(client, db):
    ensure_admin(db)
    t1 = register(client, email="p@example.com")["access_token"]
    register(client, email="f@example.com")
    client.post("/api/prime/subscribe", headers=auth(t1))
    s = get_settings()
    admin = client.post(
        "/api/auth/login", json={"email": s.admin_email, "password": s.admin_password}
    ).json()["access_token"]
    res = client.get("/api/admin/users?prime_only=true", headers=auth(admin))
    assert [u["email"] for u in res.json()["items"]] == ["p@example.com"]
