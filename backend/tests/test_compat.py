"""Sonarr/Radarr compat layer as used by Prowlarr (indexer sync) and Jellyseerr."""
from fastapi.testclient import TestClient

from app import config
from app.main import app


def _indexer_body(cats, impl="Newznab", url="http://prowlarr:9696/7/"):
    return {"name": "TreasureMaps (Prowlarr)", "implementation": impl, "configContract": f"{impl}Settings",
            "enableRss": True, "enableAutomaticSearch": True, "enableInteractiveSearch": True, "priority": 25,
            "fields": [{"name": "baseUrl", "value": url}, {"name": "apiPath", "value": "/api"},
                       {"name": "apiKey", "value": "prowlarrkey"}, {"name": "categories", "value": cats}]}


def test_version_header_and_auth():
    with TestClient(app) as c:
        assert c.get("/sonarr/api/v3/system/status").status_code == 401
        r = c.get("/sonarr/api/v3/system/status", headers={"X-Api-Key": config.API_KEY})
        assert r.status_code == 200 and r.headers["X-Application-Version"].startswith("4.")
        r = c.get(f"/radarr/api/v3/system/status?apikey={config.API_KEY}")
        assert r.json()["appName"] == "Radarr" and r.headers["X-Application-Version"].startswith("5.")


def test_prowlarr_push_merges_indexer_for_both_apps():
    h = {"X-Api-Key": config.API_KEY}
    with TestClient(app) as c:
        a = c.post("/sonarr/api/v3/indexer", json=_indexer_body([5000, 5040]), headers=h).json()
        b = c.post("/radarr/api/v3/indexer", json=_indexer_body([2000, 2040]), headers=h).json()
        assert a["id"] == b["id"]
        idx = c.get(f"/api/v1/indexers/{a['id']}", headers=h).json()
        assert idx["tv_categories"] == [5000, 5040] and idx["movie_categories"] == [2000, 2040]
        # removing it from the sonarr side keeps the radarr part
        c.delete(f"/sonarr/api/v3/indexer/{a['id']}", headers=h)
        idx = c.get(f"/api/v1/indexers/{a['id']}", headers=h).json()
        assert idx["tv_categories"] == [] and idx["movie_categories"] == [2000, 2040]
        c.delete(f"/radarr/api/v3/indexer/{a['id']}", headers=h)
        assert c.get(f"/api/v1/indexers/{a['id']}", headers=h).status_code == 404


def test_language_profile_and_queue_shape():
    h = {"X-Api-Key": config.API_KEY}
    with TestClient(app) as c:
        assert c.get("/sonarr/api/v3/languageprofile", headers=h).json()[0]["id"] == 1
        q = c.get("/radarr/api/v3/queue?includeMovie=true&pageSize=50", headers=h).json()
        assert {"page", "pageSize", "totalRecords", "records"} <= q.keys()
