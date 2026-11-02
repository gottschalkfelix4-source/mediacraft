"""Usenet clients: SABnzbd and NZBGet."""
from __future__ import annotations

import base64
import re
from typing import Optional

import httpx

from .base import AddRequest, BaseClient, ClientError, ClientItem


def _hms(v: str) -> Optional[int]:
    m = re.match(r"(?:(\d+):)?(\d+):(\d+):(\d+)$", v or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


class SABnzbd(BaseClient):
    protocol = "usenet"

    def _api(self, params: dict, files=None) -> dict:
        q = {**params, "apikey": self.cfg.api_key, "output": "json"}
        try:
            with self.http() as c:
                r = c.post(f"{self.base_url}/api", params=q, files=files) if files else c.get(f"{self.base_url}/api", params=q)
        except httpx.HTTPError as e:
            raise ClientError(f"SABnzbd nicht erreichbar: {e}") from e
        if r.status_code >= 400:
            raise ClientError(f"SABnzbd HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError:
            raise ClientError(f"SABnzbd: unerwartete Antwort {r.text[:100]}")
        if isinstance(data, dict) and data.get("status") is False:
            raise ClientError(f"SABnzbd: {data.get('error')}")
        return data

    def test(self) -> str:
        v = self._api({"mode": "version"}).get("version")
        self._api({"mode": "get_cats"})  # validates api key
        return f"SABnzbd {v}"

    def add(self, req: AddRequest) -> str:
        name = req.filename or f"{req.title}.nzb"
        params = {"mode": "addfile", "cat": req.category, "nzbname": req.title,
                  "priority": "-2" if self.cfg.add_paused else str(self.settings.get("priority", -100))}
        data = self._api(params, files={"name": (name, req.content, "application/x-nzb")})
        ids = data.get("nzo_ids") or []
        if not ids:
            raise ClientError("SABnzbd hat die NZB nicht angenommen")
        return ids[0]

    def items(self, categories: list[str]) -> list[ClientItem]:
        cats = {c.lower() for c in categories}
        out = []
        q = self._api({"mode": "queue", "limit": 500}).get("queue", {})
        for s in q.get("slots", []):
            if (s.get("cat") or "").lower() not in cats:
                continue
            mb, left = float(s.get("mb") or 0), float(s.get("mbleft") or 0)
            st = (s.get("status") or "").lower()
            status = {"paused": "paused", "queued": "queued", "grabbing": "queued", "propagating": "queued",
                      "fetching": "queued"}.get(st, "downloading")
            out.append(ClientItem(
                download_id=s["nzo_id"], title=s.get("filename", ""), category=s.get("cat"), status=status,
                size=int(mb * 1024 * 1024), size_left=int(left * 1024 * 1024),
                progress=float(s.get("percentage") or 0), eta_seconds=_hms(s.get("timeleft", "")),
            ))
        h = self._api({"mode": "history", "limit": 200}).get("history", {})
        for s in h.get("slots", []):
            if (s.get("category") or "").lower() not in cats:
                continue
            st = s.get("status", "")
            if st == "Completed":
                status = "completed"
            elif st == "Failed":
                status = "failed"
            else:  # Extracting, Verifying, Repairing, Moving, Running, Queued
                status = "downloading"
            out.append(ClientItem(
                download_id=s["nzo_id"], title=s.get("name", ""), category=s.get("category"), status=status,
                size=int(s.get("bytes") or 0), size_left=0, progress=100.0 if status == "completed" else 99.0,
                output_path=s.get("storage") or None, message=s.get("fail_message") or st,
                can_remove=status in ("completed", "failed"),
            ))
        return out

    def remove(self, download_id: str, delete_data: bool = True) -> None:
        # the job is either still queued or already in the history – SABnzbd answers status=false for the other one
        errors = []
        for where in ("queue", "history"):
            try:
                self._api({"mode": where, "name": "delete", "value": download_id, "del_files": int(delete_data)})
            except ClientError as e:
                errors.append(str(e))
        if len(errors) == 2:
            raise ClientError(errors[-1])


class NZBGet(BaseClient):
    protocol = "usenet"

    def _rpc(self, method: str, params: list | None = None):
        auth = (self.cfg.username, self.cfg.password) if self.cfg.username else None
        try:
            with self.http(auth=auth) as c:
                r = c.post(f"{self.base_url}/jsonrpc", json={"method": method, "params": params or [], "id": 1})
        except httpx.HTTPError as e:
            raise ClientError(f"NZBGet nicht erreichbar: {e}") from e
        if r.status_code == 401:
            raise ClientError("NZBGet: Authentifizierung fehlgeschlagen")
        data = r.json()
        if data.get("error"):
            raise ClientError(f"NZBGet: {data['error']}")
        return data.get("result")

    def test(self) -> str:
        return "NZBGet " + str(self._rpc("version"))

    def add(self, req: AddRequest) -> str:
        content = base64.b64encode(req.content or b"").decode()
        nzb_id = self._rpc("append", [req.filename or f"{req.title}.nzb", content, req.category,
                                      int(self.settings.get("priority", 0)), False, bool(self.cfg.add_paused),
                                      "", 0, "SCORE", []])
        if not nzb_id or int(nzb_id) <= 0:
            raise ClientError("NZBGet hat die NZB nicht angenommen")
        return str(nzb_id)

    def items(self, categories: list[str]) -> list[ClientItem]:
        cats = {c.lower() for c in categories}
        out = []
        for g in self._rpc("listgroups", [0]) or []:
            if (g.get("Category") or "").lower() not in cats:
                continue
            size = int(g.get("FileSizeMB", 0)) * 1024 * 1024
            left = int(g.get("RemainingSizeMB", 0)) * 1024 * 1024
            st = g.get("Status", "")
            status = "paused" if "PAUSED" in st else "queued" if st == "QUEUED" else "downloading"
            out.append(ClientItem(
                download_id=str(g["NZBID"]), title=g.get("NZBName", ""), category=g.get("Category"), status=status,
                size=size, size_left=left, progress=round(100 * (1 - left / size), 1) if size else 0,
                output_path=g.get("DestDir"),
            ))
        for h in self._rpc("history", [False]) or []:
            if (h.get("Category") or "").lower() not in cats or h.get("Kind", "NZB") != "NZB":
                continue
            st = h.get("Status", "")
            if st.startswith("SUCCESS") or st.startswith("WARNING/SCRIPT"):
                status = "completed"
            elif st.startswith("DELETED"):
                continue
            else:
                status = "failed"
            out.append(ClientItem(
                download_id=str(h["NZBID"]), title=h.get("Name", ""), category=h.get("Category"), status=status,
                size=int(h.get("FileSizeMB", 0)) * 1024 * 1024, progress=100.0,
                output_path=h.get("FinalDir") or h.get("DestDir"), message=st, can_remove=True,
            ))
        return out

    def remove(self, download_id: str, delete_data: bool = True) -> None:
        nid = int(download_id)
        self._rpc("editqueue", ["GroupFinalDelete" if delete_data else "GroupDelete", "", [nid]])
        self._rpc("editqueue", ["HistoryFinalDelete" if delete_data else "HistoryDelete", "", [nid]])
