from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.spa import mount_spa


def make_client(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("nope")
    app = FastAPI()

    @app.get("/api/real")
    def real():
        return {"ok": True}

    assert mount_spa(app, tmp_path)
    return TestClient(app)


def test_deep_links_get_index_html(tmp_path):
    c = make_client(tmp_path)
    for path in ("/", "/orders/12", "/admin/partners"):
        res = c.get(path)
        assert res.status_code == 200 and "root" in res.text
        assert res.headers["cache-control"] == "no-cache"


def test_assets_and_api_are_not_swallowed(tmp_path):
    c = make_client(tmp_path)
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/api/real").json() == {"ok": True}
    unknown = c.get("/api/does-not-exist")
    assert unknown.status_code == 404 and unknown.json() == {"detail": "Not found"}


def test_cannot_escape_static_dir(tmp_path):
    c = make_client(tmp_path)
    res = c.get("/..%2Fsecret.txt")
    assert "nope" not in res.text


def test_no_build_means_api_only(tmp_path):
    assert mount_spa(FastAPI(), tmp_path) is False
