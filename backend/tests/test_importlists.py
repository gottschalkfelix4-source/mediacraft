"""Import lists: JSON URL source, exclusions, library matching, Plex/Trakt parsing."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.db import session_scope
from app.models import ImportList, Movie, QualityProfile
from app.services import importlists

LIST = [{"title": "Listenfilm Eins", "tmdb_id": 991001, "imdb_id": "tt0991001"},
        {"title": "Listenfilm Zwei", "tmdbId": "991002"},
        {"title": "Ohne IDs"}]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps(LIST).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def list_server():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/list.json"
    srv.shutdown()


def test_json_list_sync_adds_new_skips_existing_and_excluded(tmp_root, list_server, monkeypatch):
    from app.services import library

    real_add = library.add_movie

    def fake_add(db, ids, pid, root, **kw):
        tmdb = int(ids["tmdb"])
        meta = {"provider": "tmdb", "ids": {"tmdb": tmdb, "imdb": ids.get("imdb")}, "title": f"Film {tmdb}", "year": 2020}
        return real_add(db, ids, pid, root, meta=meta, **kw)

    monkeypatch.setattr(library, "add_movie", fake_add)
    with session_scope() as db:
        pid = db.query(QualityProfile).first().id
        lst = ImportList(name="JSON", kind="json_url", media_type="movie", settings={"url": list_server},
                         quality_profile_id=pid, root_folder=str(tmp_root / "lists"), search_on_add=False)
        db.add(lst)
        db.flush()
        items = importlists.fetch(db, lst)
        assert [i["ids"].get("tmdb") for i in items] == [991001, 991002]

        importlists.add_exclusion(db, "movie", {"imdb": "tt0991001"}, "Listenfilm Eins")
        dry = importlists.sync_list(db, lst, dry_run=True)
        assert dry["excluded"] == 1 and len(dry["added"]) == 1

        res = importlists.sync_list(db, lst)
        assert res["added"] == ["Film 991002"]
        assert db.query(Movie).filter(Movie.tmdb_id == 991002).count() == 1
        again = importlists.sync_list(db, lst)
        assert again["added"] == [] and again["existing"] == 1
        assert lst.last_result["existing"] == 1


def test_trakt_and_plex_parsing(monkeypatch):
    rows = [{"movie": {"title": "A", "year": 2001, "ids": {"tmdb": 1, "imdb": "tt1"}}},
            {"title": "B", "year": 2002, "ids": {"tmdb": 2}}]
    assert [i["ids"]["tmdb"] for i in importlists._trakt_items(rows, "movie")] == [1, 2]

    class R:
        def json(self):
            return {"MediaContainer": {"totalSize": 2, "Metadata": [
                {"type": "movie", "title": "P", "year": 2003, "Guid": [{"id": "imdb://tt3"}, {"id": "tmdb://3"}]},
                {"type": "show", "title": "S", "Guid": [{"id": "tvdb://4"}]}]}}

    monkeypatch.setattr(importlists, "_http", lambda *a, **k: R())
    lst = ImportList(kind="plex_watchlist", media_type="movie", settings={"token": "x"})
    items = importlists._fetch_plex_watchlist(None, lst, lst.settings)
    assert items == [{"media_type": "movie", "ids": {"imdb": "tt3", "tmdb": 3}, "title": "P", "year": 2003}]


def test_import_list_api_validation():
    from fastapi.testclient import TestClient

    from app import config
    from app.main import app

    c = TestClient(app, headers={"X-Api-Key": config.API_KEY})
    assert any(s["kind"] == "trakt_watchlist" for s in c.get("/api/v1/importlists/schema").json())
    r = c.post("/api/v1/importlists", json={"name": "x", "kind": "tmdb_collection", "media_type": "series"})
    assert r.status_code == 400  # collections are movies only
    r = c.post("/api/v1/importlists", json={"name": "x", "kind": "nope"})
    assert r.status_code == 400
