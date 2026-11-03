"""Download client adapters against mocked HTTP APIs (qBittorrent WebUI v2, SABnzbd)."""
from urllib.parse import parse_qs

import httpx
import pytest

from app.downloadclients import base
from app.downloadclients.base import AddRequest, ClientError
from app.downloadclients.torrent import QBittorrent, _qbit_sessions
from app.downloadclients.usenet import SABnzbd
from app.models import DownloadClient

TORRENT = b"d8:announce3:url4:infod6:lengthi1e4:name4:test12:piece lengthi1e6:pieces20:aaaaaaaaaaaaaaaaaaaaee"


def _mock(monkeypatch, handler):
    monkeypatch.setattr(base.BaseClient, "http", lambda self, **kw: httpx.Client(
        transport=httpx.MockTransport(handler), headers=kw.get("headers"), follow_redirects=True))


def test_qbittorrent_login_add_and_items(monkeypatch):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        calls.append(path)
        if path.endswith("/auth/login"):
            body = parse_qs(req.content.decode())
            ok = body.get("password") == ["secret"]
            return httpx.Response(200 if ok else 403, text="Ok." if ok else "Fails.")
        if path.endswith("/app/version"):
            return httpx.Response(200, text="v5.0.0")
        if path.endswith("/torrents/createCategory"):
            return httpx.Response(409)
        if path.endswith("/torrents/add"):
            return httpx.Response(200, text="Ok.")
        if path.endswith("/torrents/info"):
            cat = req.url.params.get("category")
            rows = [
                {"hash": "ABC", "name": "Film", "state": "stalledDL", "progress": 0.4, "size": 100, "amount_left": 60,
                 "eta": 8640000, "content_path": "/dl/Film"},
                {"hash": "DEF", "name": "Fertig", "state": "pausedUP", "progress": 1.0, "size": 100, "amount_left": 0,
                 "eta": 0, "save_path": "/dl", "ratio": 2.0},
            ] if cat == "movies" else []
            return httpx.Response(200, json=rows)
        return httpx.Response(404)

    _mock(monkeypatch, handler)
    _qbit_sessions.clear()
    cfg = DownloadClient(id=901, name="qb", kind="qbittorrent", host="qb", port=8080, username="u", password="secret",
                         add_paused=False, settings={})
    c = QBittorrent(cfg)
    assert c.test() == "qBittorrent v5.0.0"
    h = c.add(AddRequest(title="Film", category="movies", content=TORRENT, seed_ratio=1.5))
    assert len(h) == 40
    items = {i.download_id: i for i in c.items(["movies"])}
    assert items["abc"].status == "warning" and items["abc"].progress == 40.0 and items["abc"].eta_seconds is None
    assert items["def"].status == "completed" and items["def"].can_remove
    _qbit_sessions.clear()
    cfg.password = "wrong"
    with pytest.raises(ClientError):
        QBittorrent(cfg).test()
    _qbit_sessions.clear()


def test_sabnzbd_queue_history_and_errors(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        mode = req.url.params.get("mode")
        if req.url.params.get("apikey") != "key":
            return httpx.Response(200, json={"status": False, "error": "API Key Incorrect"})
        if mode == "version":
            return httpx.Response(200, json={"version": "4.4.0"})
        if mode == "get_cats":
            return httpx.Response(200, json={"categories": ["tv"]})
        if mode == "addfile":
            return httpx.Response(200, json={"status": True, "nzo_ids": ["SABnzbd_nzo_1"]})
        if mode == "queue":
            return httpx.Response(200, json={"queue": {"slots": [
                {"nzo_id": "q1", "filename": "Show.S01E01", "cat": "tv", "mb": "1000", "mbleft": "250",
                 "percentage": "75", "status": "Downloading", "timeleft": "0:01:40"}]}})
        if mode == "history":
            return httpx.Response(200, json={"history": {"slots": [
                {"nzo_id": "h1", "name": "Show.S01E02", "category": "tv", "status": "Completed", "bytes": 5,
                 "storage": "/dl/tv/Show.S01E02"},
                {"nzo_id": "h2", "name": "Show.S01E03", "category": "tv", "status": "Failed", "bytes": 5,
                 "fail_message": "Repair failed"}]}})
        return httpx.Response(404)

    _mock(monkeypatch, handler)
    cfg = DownloadClient(id=902, name="sab", kind="sabnzbd", host="sab", port=8080, api_key="key", add_paused=False,
                         settings={})
    c = SABnzbd(cfg)
    assert c.test() == "SABnzbd 4.4.0"
    assert c.add(AddRequest(title="Show.S01E01", category="tv", content=b"<nzb/>")) == "SABnzbd_nzo_1"
    items = {i.download_id: i for i in c.items(["tv"])}
    assert items["q1"].progress == 75.0 and items["q1"].eta_seconds == 100
    assert items["h1"].status == "completed" and items["h1"].output_path == "/dl/tv/Show.S01E02"
    assert items["h2"].status == "failed"
    cfg.api_key = "bad"
    with pytest.raises(ClientError):
        SABnzbd(cfg).test()
