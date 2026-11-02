"""Torrent clients: qBittorrent (WebUI API v2), Transmission (RPC), Deluge (Web JSON-RPC)."""
from __future__ import annotations

import base64
import threading
from typing import Optional

import httpx

from ..core.bencode import info_hash, magnet_hash
from .base import AddRequest, BaseClient, ClientError, ClientItem


def _hash_for(req: AddRequest) -> str:
    h = info_hash(req.content) if req.content else None
    if not h and req.magnet:
        h = magnet_hash(req.magnet)
    if not h:
        raise ClientError("Info-Hash konnte nicht ermittelt werden")
    return h.lower()


# ============================================================================== qBittorrent
_qbit_sessions: dict[int, httpx.Client] = {}
_qbit_lock = threading.Lock()

_QBIT_STATUS = {
    "error": "failed", "missingFiles": "failed", "uploading": "seeding", "pausedUP": "completed",
    "stoppedUP": "completed", "queuedUP": "seeding", "stalledUP": "seeding", "checkingUP": "seeding",
    "forcedUP": "seeding", "allocating": "downloading", "downloading": "downloading", "metaDL": "downloading",
    "forcedMetaDL": "downloading", "pausedDL": "paused", "stoppedDL": "paused", "queuedDL": "queued",
    "stalledDL": "warning", "checkingDL": "downloading", "forcedDL": "downloading",
    "checkingResumeData": "queued", "moving": "downloading",
}


class QBittorrent(BaseClient):
    def _session(self, fresh: bool = False) -> httpx.Client:
        with _qbit_lock:
            c = _qbit_sessions.get(self.cfg.id)
            if c is None or fresh:
                c = self.http(headers={"Referer": self.base_url})
                r = c.post(f"{self.base_url}/api/v2/auth/login",
                           data={"username": self.cfg.username, "password": self.cfg.password})
                if r.status_code == 403:
                    raise ClientError("qBittorrent: IP gesperrt (zu viele Fehlversuche)")
                if r.status_code != 200 or r.text.strip() not in ("Ok.", ""):
                    raise ClientError(f"qBittorrent Login fehlgeschlagen: {r.status_code} {r.text[:100]}")
                if self.cfg.id is not None:
                    _qbit_sessions[self.cfg.id] = c
            return c

    def _call(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            r = self._session().request(method, f"{self.base_url}/api/v2/{path}", **kw)
            if r.status_code == 403:
                r = self._session(fresh=True).request(method, f"{self.base_url}/api/v2/{path}", **kw)
        except httpx.HTTPError as e:
            raise ClientError(f"qBittorrent nicht erreichbar: {e}") from e
        if r.status_code >= 400 and r.status_code != 409:
            raise ClientError(f"qBittorrent {path}: HTTP {r.status_code} {r.text[:200]}")
        return r

    def test(self) -> str:
        return "qBittorrent " + self._call("GET", "app/version").text

    def add(self, req: AddRequest) -> str:
        h = _hash_for(req)
        self._call("POST", "torrents/createCategory", data={"category": req.category, "savePath": ""})
        data = {"category": req.category, "paused": str(self.cfg.add_paused).lower(),
                "stopped": str(self.cfg.add_paused).lower()}
        if req.seed_ratio is not None:
            data["ratioLimit"] = str(req.seed_ratio)
        if req.seed_time is not None:
            data["seedingTimeLimit"] = str(req.seed_time)
        if self.settings.get("sequential"):
            data["sequentialDownload"] = "true"
        if req.content:
            files = {"torrents": (req.filename or f"{h}.torrent", req.content, "application/x-bittorrent")}
            r = self._call("POST", "torrents/add", data=data, files=files)
        else:
            r = self._call("POST", "torrents/add", data={**data, "urls": req.magnet})
        if "Fails" in r.text:
            raise ClientError("qBittorrent hat den Torrent abgelehnt")
        return h

    def items(self, categories: list[str]) -> list[ClientItem]:
        out = []
        for cat in set(categories):
            for t in self._call("GET", "torrents/info", params={"category": cat}).json():
                status = _QBIT_STATUS.get(t.get("state"), "downloading")
                if t.get("progress", 0) >= 1 and status not in ("failed",):
                    status = "completed" if status in ("paused", "completed") else "seeding"
                done_seeding = t.get("state") in ("pausedUP", "stoppedUP")
                out.append(ClientItem(
                    download_id=t["hash"].lower(), title=t.get("name", ""), category=cat, status=status,
                    size=t.get("size") or t.get("total_size") or 0, size_left=t.get("amount_left", 0),
                    progress=round(t.get("progress", 0) * 100, 1),
                    eta_seconds=t.get("eta") if t.get("eta", 8640000) < 8640000 else None,
                    output_path=t.get("content_path") or t.get("save_path"), ratio=t.get("ratio"),
                    message=t.get("state"), can_remove=done_seeding,
                ))
        return out

    def remove(self, download_id: str, delete_data: bool = True) -> None:
        self._call("POST", "torrents/delete", data={"hashes": download_id, "deleteFiles": str(delete_data).lower()})


# ============================================================================== Transmission
_TR_STATUS = {0: "paused", 1: "queued", 2: "downloading", 3: "queued", 4: "downloading", 5: "seeding", 6: "seeding"}


class Transmission(BaseClient):
    _sid: dict[int, str] = {}

    def _rpc(self, method: str, arguments: dict | None = None) -> dict:
        url = f"{self.base_url.rstrip('/')}" + ("" if (self.cfg.url_base or "").strip("/") else "/transmission") + "/rpc"
        auth = (self.cfg.username, self.cfg.password) if self.cfg.username else None
        body = {"method": method, "arguments": arguments or {}}
        with self.http(auth=auth) as c:
            for _ in range(2):
                try:
                    r = c.post(url, json=body, headers={"X-Transmission-Session-Id": self._sid.get(self.cfg.id or 0, "")})
                except httpx.HTTPError as e:
                    raise ClientError(f"Transmission nicht erreichbar: {e}") from e
                if r.status_code == 409:
                    self._sid[self.cfg.id or 0] = r.headers.get("X-Transmission-Session-Id", "")
                    continue
                break
        if r.status_code == 401:
            raise ClientError("Transmission: Authentifizierung fehlgeschlagen")
        if r.status_code >= 400:
            raise ClientError(f"Transmission HTTP {r.status_code}")
        data = r.json()
        if data.get("result") != "success":
            raise ClientError(f"Transmission: {data.get('result')}")
        return data.get("arguments", {})

    def test(self) -> str:
        return "Transmission " + str(self._rpc("session-get", {"fields": ["version"]}).get("version"))

    def add(self, req: AddRequest) -> str:
        h = _hash_for(req)
        args: dict = {"paused": self.cfg.add_paused, "labels": [req.category]}
        if self.settings.get("directory"):
            args["download-dir"] = self.settings["directory"].rstrip("/") + "/" + req.category
        if req.content:
            args["metainfo"] = base64.b64encode(req.content).decode()
        else:
            args["filename"] = req.magnet
        res = self._rpc("torrent-add", args)
        t = res.get("torrent-added") or res.get("torrent-duplicate") or {}
        h = (t.get("hashString") or h).lower()
        if req.seed_ratio is not None:
            self._rpc("torrent-set", {"ids": [h], "seedRatioLimit": req.seed_ratio, "seedRatioMode": 1})
        return h

    def items(self, categories: list[str]) -> list[ClientItem]:
        fields = ["hashString", "name", "totalSize", "leftUntilDone", "percentDone", "eta", "status", "downloadDir",
                  "errorString", "error", "isFinished", "uploadRatio", "labels"]
        res = self._rpc("torrent-get", {"fields": fields})
        cats = set(categories)
        directory = (self.settings.get("directory") or "").rstrip("/")
        out = []
        for t in res.get("torrents", []):
            labels = set(t.get("labels") or [])
            in_cat = labels & cats or (directory and any(t["downloadDir"].rstrip("/") == f"{directory}/{c}" for c in cats))
            if not in_cat:
                continue
            status = _TR_STATUS.get(t["status"], "downloading")
            if t.get("error"):
                status = "warning" if t["error"] in (1, 2) else "failed"
            if t["percentDone"] >= 1 and status in ("paused", "seeding"):
                status = "completed" if t["status"] == 0 else "seeding"
            out.append(ClientItem(
                download_id=t["hashString"].lower(), title=t["name"], category=next(iter(labels & cats), None),
                status=status, size=t["totalSize"], size_left=t["leftUntilDone"],
                progress=round(t["percentDone"] * 100, 1), eta_seconds=t["eta"] if t["eta"] >= 0 else None,
                output_path=f"{t['downloadDir'].rstrip('/')}/{t['name']}", ratio=t.get("uploadRatio"),
                message=t.get("errorString") or None, can_remove=bool(t.get("isFinished")),
            ))
        return out

    def remove(self, download_id: str, delete_data: bool = True) -> None:
        self._rpc("torrent-remove", {"ids": [download_id], "delete-local-data": delete_data})


# ============================================================================== Deluge
_DELUGE_STATUS = {"Downloading": "downloading", "Seeding": "seeding", "Paused": "paused", "Error": "failed",
                  "Queued": "queued", "Checking": "downloading", "Moving": "downloading", "Allocating": "downloading"}


class Deluge(BaseClient):
    _cookies: dict[int, httpx.Cookies] = {}

    def _call(self, method: str, params: list, _retry: bool = True):
        url = f"{self.base_url}/json"
        try:
            with self.http(cookies=self._cookies.get(self.cfg.id or 0)) as c:
                r = c.post(url, json={"method": method, "params": params, "id": 1})
                if c.cookies:
                    self._cookies[self.cfg.id or 0] = c.cookies
        except httpx.HTTPError as e:
            raise ClientError(f"Deluge nicht erreichbar: {e}") from e
        data = r.json()
        err = data.get("error")
        if err:
            if err.get("code") == 1 and _retry:  # not authenticated
                self._login()
                return self._call(method, params, False)
            raise ClientError(f"Deluge: {err.get('message')}")
        return data.get("result")

    def _login(self) -> None:
        with self.http() as c:
            r = c.post(f"{self.base_url}/json", json={"method": "auth.login", "params": [self.cfg.password], "id": 1})
            if not r.json().get("result"):
                raise ClientError("Deluge: Passwort falsch")
            self._cookies[self.cfg.id or 0] = c.cookies
        if not self._call("web.connected", [], False):
            hosts = self._call("web.get_hosts", [], False) or []
            if hosts:
                self._call("web.connect", [hosts[0][0]], False)

    def test(self) -> str:
        self._login()
        return "Deluge " + str(self._call("daemon.info", []))

    def _ensure_label(self, label: str) -> bool:
        try:
            labels = self._call("label.get_labels", [])
        except ClientError:
            return False
        if label not in (labels or []):
            self._call("label.add", [label])
        return True

    def add(self, req: AddRequest) -> str:
        opts: dict = {"add_paused": self.cfg.add_paused}
        if req.seed_ratio is not None:
            opts.update(stop_at_ratio=True, stop_ratio=req.seed_ratio)
        if req.content:
            h = self._call("core.add_torrent_file", [req.filename or "release.torrent",
                                                     base64.b64encode(req.content).decode(), opts])
        else:
            h = self._call("core.add_torrent_magnet", [req.magnet, opts])
        h = (h or _hash_for(req)).lower()
        if self._ensure_label(req.category.lower()):
            self._call("label.set_torrent", [h, req.category.lower()])
        return h

    def items(self, categories: list[str]) -> list[ClientItem]:
        fields = ["name", "total_size", "total_done", "progress", "eta", "state", "save_path", "ratio",
                  "is_finished", "message", "label"]
        res = self._call("web.update_ui", [fields, {}]) or {}
        cats = {c.lower() for c in categories}
        out = []
        for h, t in (res.get("torrents") or {}).items():
            if (t.get("label") or "").lower() not in cats:
                continue
            status = _DELUGE_STATUS.get(t.get("state"), "downloading")
            if t.get("is_finished") and status == "paused":
                status = "completed"
            out.append(ClientItem(
                download_id=h.lower(), title=t["name"], category=t.get("label"), status=status,
                size=t.get("total_size", 0), size_left=max(t.get("total_size", 0) - t.get("total_done", 0), 0),
                progress=round(t.get("progress", 0), 1), eta_seconds=t.get("eta") or None,
                output_path=f"{t['save_path'].rstrip('/')}/{t['name']}", ratio=t.get("ratio"),
                message=t.get("message"), can_remove=bool(t.get("is_finished")) and status == "completed",
            ))
        return out

    def remove(self, download_id: str, delete_data: bool = True) -> None:
        self._call("core.remove_torrent", [download_id, delete_data])
