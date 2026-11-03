"""Running under a sub path (MEDIACRAFT_URL_BASE), e.g. behind a reverse proxy at /mediacraft."""
from fastapi.testclient import TestClient


def test_app_under_url_base(tmp_root, monkeypatch):
    from app import config
    from app.main import create_app

    static = tmp_root / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html><head><title>MC</title></head><body></body></html>", "utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", "utf-8")
    monkeypatch.setattr(config, "URL_BASE", "/mc")
    monkeypatch.setattr(config, "STATIC_DIR", static)
    c = TestClient(create_app(), headers={"X-Api-Key": config.API_KEY})

    for path in ("/mc/", "/mc/movies/12"):
        html = c.get(path).text
        assert '<base href="/mc/" />' in html and 'window.__MC_BASE__ = "/mc"' in html
    assert c.get("/mc/assets/app.js").text == "console.log(1)"
    assert c.get("/mc/api/v1/system/status").json()["url_base"] == "/mc"
    assert c.get("/mc/sonarr/api/v3/system/status").json()["appName"] == "Sonarr"
    assert c.get("/mc/ping").json() == {"status": "ok"}
    assert c.get("/mc/api/v1/nope").status_code == 404


def test_stats_endpoint():
    from app import config
    from app.main import app

    c = TestClient(app, headers={"X-Api-Key": config.API_KEY})
    s = c.get("/api/v1/stats?weeks=4").json()
    assert {"library", "qualities", "languages", "weeks", "indexers", "root_folders"} <= set(s)
    assert len(s["weeks"]) == 5
