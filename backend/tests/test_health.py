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
