"""Notification targets: Sonarr/Radarr webhook format, Apprise API, secret masking."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.models import Notification
from app.services import notifications

RECEIVED: list = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        RECEIVED.append((self.path, json.loads(body or b"{}")))
        self.send_response(200)
        self.end_headers()


@pytest.fixture(scope="module")
def receiver():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_webhook_radarr_format_and_apprise(receiver, tmp_root):
    from app.db import session_scope
    from app.models import QualityProfile
    from app.services import library

    with session_scope() as db:
        pid = db.query(QualityProfile).first().id
        m = library.add_movie(db, {"tmdb": 992001}, pid, str(tmp_root),
                              meta={"provider": "tmdb", "ids": {"tmdb": 992001, "imdb": "tt992001"}, "title": "Webhookfilm", "year": 2021})
        mid = m.id
    RECEIVED.clear()
    hook = Notification(name="w", kind="webhook", settings={"url": receiver + "/hook", "format": "radarr"})
    notifications._send(hook, "grab", "x", {"movie_id": mid, "release_title": "Webhookfilm.2021.1080p", "quality": "WEBDL-1080p",
                                            "download_id": "abc", "download_client": "SAB"})
    path, body = RECEIVED[-1]
    assert body["eventType"] == "Grab" and body["movie"]["tmdbId"] == 992001
    assert body["release"]["releaseTitle"] == "Webhookfilm.2021.1080p" and body["downloadId"] == "abc"

    notifications._send(Notification(name="t", kind="webhook", settings={"url": receiver + "/hook", "format": "sonarr"}),
                        "test", "Test", {})
    assert RECEIVED[-1][1]["eventType"] == "Test"

    apprise = Notification(name="a", kind="apprise", settings={"url": receiver + "/notify/mykey", "tag": "media"})
    notifications._send(apprise, "failure", "kaputt", {})
    path, body = RECEIVED[-1]
    assert path == "/notify/mykey" and body["type"] == "failure" and body["tag"] == "media"

    # media servers ignore grabs
    before = len(RECEIVED)
    notifications._send(Notification(name="j", kind="jellyfin", settings={"url": receiver, "api_key": "k"}), "grab", "x", {})
    assert len(RECEIVED) == before


def test_notification_secrets_are_masked():
    from fastapi.testclient import TestClient

    from app import config
    from app.main import app

    c = TestClient(app, headers={"X-Api-Key": config.API_KEY})
    n = c.post("/api/v1/notifications", json={"name": "po", "kind": "pushover", "on_grab": True,
                                              "settings": {"user_key": "uuu", "app_token": "ttt"}}).json()
    assert n["settings"]["app_token"] == "********"
    n["settings"]["priority"] = "1"
    c.put(f"/api/v1/notifications/{n['id']}", json=n)
    from app.db import session_scope

    with session_scope() as db:
        assert db.get(Notification, n["id"]).settings["app_token"] == "ttt"
    c.delete(f"/api/v1/notifications/{n['id']}")
