"""Login rate limiting: failed attempts per email and per client IP (app/services/login_limiter.py)."""

from types import SimpleNamespace

from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import engine
from app.services.login_limiter import client_ip

URL = "/api/v1/auth/login"


def attempt(client, email, password="wrong-password", ip=None):
    headers = {"X-Forwarded-For": ip} if ip else {}
    return client.post(URL, json={"email": email, "password": password}, headers=headers)


def test_email_locked_after_five_failures(client, make_user):
    make_user("a@x.com")
    make_user("b@x.com")
    for _ in range(5):
        assert attempt(client, "a@x.com").status_code == 401
    r = attempt(client, "A@x.com", "password123")  # even the right password, any casing
    assert r.status_code == 429
    body = r.json()["error"]
    assert body["code"] == "TOO_MANY_ATTEMPTS"
    assert "15 minutes" in body["message"]
    assert 890 <= int(r.headers["Retry-After"]) <= 900
    assert body["details"]["retry_after_s"] == int(r.headers["Retry-After"])
    assert attempt(client, "b@x.com", "password123").status_code == 200  # other accounts unaffected


def test_unknown_emails_are_limited_the_same_way(client):
    for _ in range(5):
        assert attempt(client, "ghost@x.com").status_code == 401
    assert attempt(client, "ghost@x.com").status_code == 429


def test_success_resets_the_email_counter(client, make_user):
    make_user("a@x.com")
    for _ in range(4):
        attempt(client, "a@x.com")
    assert attempt(client, "a@x.com", "password123").status_code == 200
    for _ in range(4):
        assert attempt(client, "a@x.com").status_code == 401


def test_ip_limit_across_many_emails(client, make_user, monkeypatch):
    monkeypatch.setattr(get_settings(), "login_max_failures_per_ip", 3)
    make_user("real@x.com")
    for i in range(3):
        assert attempt(client, f"guess{i}@x.com").status_code == 401
    assert attempt(client, "real@x.com", "password123").status_code == 429


def test_correct_logins_are_never_counted(client, make_user, monkeypatch):
    # Locust logs in many accounts from one IP; only failures count.
    monkeypatch.setattr(get_settings(), "login_max_failures_per_ip", 3)
    make_user("a@x.com")
    for _ in range(10):
        assert attempt(client, "a@x.com", "password123").status_code == 200


def test_lock_expires_with_the_window(client, make_user):
    make_user("a@x.com")
    for _ in range(5):
        attempt(client, "a@x.com")
    assert attempt(client, "a@x.com", "password123").status_code == 429
    with engine.begin() as c:
        c.execute(text("UPDATE login_failures SET created_at = created_at - interval '16 minutes'"))
    assert attempt(client, "a@x.com", "password123").status_code == 200


def test_forwarded_for_only_trusted_behind_alb(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "login_max_failures_per_ip", 2)
    # Not trusted (default): spoofed headers don't dodge the IP limit.
    attempt(client, "x1@x.com", ip="1.1.1.1")
    attempt(client, "x2@x.com", ip="2.2.2.2")
    assert attempt(client, "x3@x.com", ip="3.3.3.3").status_code == 429

    monkeypatch.setattr(s, "trust_forwarded_for", True)
    # Behind the ALB the real client is the LAST entry; a forged first entry is ignored.
    attempt(client, "y1@x.com", ip="9.9.9.9, 10.0.0.7")
    attempt(client, "y2@x.com", ip="8.8.8.8, 10.0.0.7")
    assert attempt(client, "y3@x.com", ip="7.7.7.7, 10.0.0.7").status_code == 429
    assert attempt(client, "y4@x.com", ip="10.0.0.8").status_code == 401


def test_client_ip_helper(monkeypatch):
    s = get_settings()
    req = SimpleNamespace(
        headers={"x-forwarded-for": "6.6.6.6, 203.0.113.9"}, client=SimpleNamespace(host="10.1.1.1")
    )
    assert client_ip(req) == "10.1.1.1"
    monkeypatch.setattr(s, "trust_forwarded_for", True)
    assert client_ip(req) == "203.0.113.9"
    req.headers = {}
    assert client_ip(req) == "10.1.1.1"
