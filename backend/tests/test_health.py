from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_liveness_reports_instance():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.headers["X-Served-By"] == res.json()["instance"]
