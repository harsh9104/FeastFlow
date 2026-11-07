import time

import jwt


def reg(client, email="a@x.com", tier="FREE", **kw):
    body = {"full_name": "A", "email": email, "password": "password123", "subscription_tier": tier}
    body.update(kw)
    return client.post("/api/v1/auth/register", json=body)


def test_register_and_login(client):
    r = reg(client, "A@X.com", "PREMIUM")
    assert r.status_code == 201
    assert r.json()["email"] == "a@x.com"
    assert r.json()["role"] == "CUSTOMER"
    assert r.json()["subscription_tier"] == "PREMIUM"
    assert "password" not in r.text

    r = client.post("/api/v1/auth/login", json={"email": "a@X.com", "password": "password123"})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert body["user"]["subscription_tier"] == "PREMIUM"


def test_register_duplicate_and_validation(client):
    assert reg(client).status_code == 201
    r = reg(client, "A@x.com")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "EMAIL_TAKEN"
    assert reg(client, "b@x.com", password="short").status_code == 422
    assert reg(client, "not-an-email").status_code == 422
    assert reg(client, "c@x.com", tier="GOLD").status_code == 422


def test_login_failures(client):
    reg(client)
    for body in (
        {"email": "a@x.com", "password": "wrong-password"},
        {"email": "nobody@x.com", "password": "password123"},
    ):
        r = client.post("/api/v1/auth/login", json=body)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_requires_valid_token(client, make_user, auth_header):
    assert client.get("/api/v1/users/me").status_code == 401
    bad = {"Authorization": "Bearer garbage"}
    assert client.get("/api/v1/users/me", headers=bad).status_code == 401
    expired = jwt.encode({"sub": "1", "exp": int(time.time()) - 10}, "test-secret", "HS256")
    r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401

    make_user("c@x.com")
    r = client.get("/api/v1/users/me", headers=auth_header("c@x.com"))
    assert r.status_code == 200
    assert r.json()["email"] == "c@x.com"


def test_customer_changes_own_tier(client, make_user, auth_header):
    make_user("c@x.com")
    h = auth_header("c@x.com")
    r = client.patch(
        "/api/v1/users/me/subscription", json={"subscription_tier": "PREMIUM"}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["subscription_tier"] == "PREMIUM"
    assert client.get("/api/v1/users/me", headers=h).json()["subscription_tier"] == "PREMIUM"


def test_admin_endpoints_forbidden_for_customer(client, make_user, auth_header):
    make_user("c@x.com")
    h = auth_header("c@x.com")
    assert client.get("/api/v1/admin/users", headers=h).status_code == 403
    r = client.patch(
        "/api/v1/admin/users/1/subscription", json={"subscription_tier": "PREMIUM"}, headers=h
    )
    assert r.status_code == 403
    assert client.get("/api/v1/admin/users").status_code == 401


def test_admin_lists_and_changes_tier(client, make_user, auth_header):
    make_user("admin@x.com", role="ADMIN")
    cid = make_user("c@x.com")
    make_user("p@x.com", tier="PREMIUM")
    h = auth_header("admin@x.com")

    r = client.get("/api/v1/admin/users", headers=h)
    assert r.json()["total"] == 3
    r = client.get("/api/v1/admin/users?tier=PREMIUM", headers=h)
    assert [u["email"] for u in r.json()["items"]] == ["p@x.com"]
    assert (
        client.get("/api/v1/admin/users?page_size=2&page=2", headers=h).json()["items"][0]["email"]
        == "p@x.com"
    )

    r = client.patch(
        f"/api/v1/admin/users/{cid}/subscription", json={"subscription_tier": "PREMIUM"}, headers=h
    )
    assert r.status_code == 200 and r.json()["subscription_tier"] == "PREMIUM"
    r = client.patch(
        "/api/v1/admin/users/9999/subscription", json={"subscription_tier": "FREE"}, headers=h
    )
    assert r.status_code == 404


def test_admin_cannot_use_customer_only_route(client, make_user, auth_header):
    make_user("admin@x.com", role="ADMIN")
    r = client.patch(
        "/api/v1/users/me/subscription",
        json={"subscription_tier": "PREMIUM"},
        headers=auth_header("admin@x.com"),
    )
    assert r.status_code == 403
