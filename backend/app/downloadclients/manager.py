"""Client factory, blackhole implementation and remote path mapping."""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from sqlalchemy.orm import Session

from ..models import DownloadClient, RemotePathMapping
from .base import AddRequest, BaseClient, ClientError, ClientItem
from .torrent import Deluge, QBittorrent, Transmission
from .usenet import NZBGet, SABnzbd


class Blackhole(BaseClient):
    """Drops .torrent/.nzb files into a watch folder; finished downloads appear in a completed folder."""

    @property
    def protocol(self):  # type: ignore[override]
        return self.cfg.protocol

    def test(self) -> str:
        for key in ("watch_folder", "completed_folder"):
            p = self.settings.get(key)
            if not p or not os.path.isdir(p):
                raise ClientError(f"Ordner '{key}' existiert nicht: {p}")
        return "Blackhole OK"

    @staticmethod
    def _id(title: str) -> str:
        return "bh-" + hashlib.sha1(title.encode()).hexdigest()[:16]

    def add(self, req: AddRequest) -> str:
        ext = ".torrent" if self.cfg.kind == "blackhole_torrent" else ".nzb"
        safe = re.sub(r'[\\/:*?"<>|]', "", req.title)
        target = Path(self.settings.get("watch_folder", "")) / f"{safe}{ext}"
        if req.magnet and not req.content:
            target = target.with_suffix(".magnet")
            target.write_text(req.magnet, "utf-8")
        else:
            target.write_bytes(req.content or b"")
        return self._id(safe)

    def items(self, categories: list[str]) -> list[ClientItem]:
        root = Path(self.settings.get("completed_folder", ""))
        if not root.is_dir():
            return []
        out = []
        for entry in root.iterdir():
            name = entry.stem if entry.is_file() else entry.name
            size = entry.stat().st_size if entry.is_file() else sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
            out.append(ClientItem(download_id=self._id(name), title=name, category=None, status="completed",
                                  size=size, progress=100.0, output_path=str(entry), can_remove=False))
        return out

    def remove(self, download_id: str, delete_data: bool = True) -> None:
        return None


CLIENT_CLASSES: dict[str, type[BaseClient]] = {
    "qbittorrent": QBittorrent, "transmission": Transmission, "deluge": Deluge,
    "sabnzbd": SABnzbd, "nzbget": NZBGet, "blackhole_torrent": Blackhole, "blackhole_usenet": Blackhole,
}

CLIENT_DEFAULTS = {
    "qbittorrent": {"port": 8080}, "transmission": {"port": 9091}, "deluge": {"port": 8112},
    "sabnzbd": {"port": 8080}, "nzbget": {"port": 6789}, "blackhole_torrent": {"port": 0}, "blackhole_usenet": {"port": 0},
}


def get_client(cfg: DownloadClient) -> BaseClient:
    cls = CLIENT_CLASSES.get(cfg.kind)
    if not cls:
        raise ClientError(f"Unbekannter Client-Typ {cfg.kind}")
    return cls(cfg)


def pick_client(db: Session, protocol: str, preferred_id: int | None = None) -> DownloadClient | None:
    q = [c for c in db.query(DownloadClient).filter(DownloadClient.enabled.is_(True)).all() if c.protocol == protocol]
    if preferred_id:
        for c in q:
            if c.id == preferred_id:
                return c
    q.sort(key=lambda c: (c.priority, c.id))
    return q[0] if q else None


def map_path(db: Session, client: DownloadClient, remote: str | None) -> str | None:
    """Translate a path reported by the client into a path visible to MediaCraft."""
    if not remote:
        return remote
    for m in db.query(RemotePathMapping).all():
        if m.host.lower() not in (client.host.lower(), "*", ""):
            continue
        rp = m.remote_path.rstrip("/\\")
        norm = remote.replace("\\", "/")
        if norm == rp.replace("\\", "/") or norm.startswith(rp.replace("\\", "/") + "/"):
            rest = norm[len(rp.replace("\\", "/")):].lstrip("/")
            return os.path.join(m.local_path, *rest.split("/")) if rest else m.local_path
    return remote
