def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "X-Served-By" in r.headers
    assert "X-Request-ID" in r.headers


def test_error_envelope(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["request_id"]


def test_production_refuses_weak_jwt_secret(monkeypatch):
    import pytest

    from app.core.config import get_settings
    from app.main import create_app

    s = get_settings()
    monkeypatch.setattr(s, "env", "production")
    for weak in ("change-me", "", "short-secret"):
        monkeypatch.setattr(s, "jwt_secret", weak)
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            create_app()
    monkeypatch.setattr(s, "jwt_secret", "x" * 64)
    create_app()  # a strong secret starts fine


def test_production_refuses_weak_loadtest_password(monkeypatch):
    import pytest

    from app.core.config import get_settings
    from app.main import create_app

    s = get_settings()
    monkeypatch.setattr(s, "env", "production")
    monkeypatch.setattr(s, "jwt_secret", "x" * 64)
    monkeypatch.setattr(s, "loadtest_password", "loadtest-pass")
    with pytest.raises(RuntimeError, match="LOADTEST_PASSWORD"):
        create_app()
    monkeypatch.setattr(s, "loadtest_password", "")
    create_app()  # empty: no load-test accounts, starts fine
