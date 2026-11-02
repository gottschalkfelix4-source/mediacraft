"""Download client interface."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import httpx

from ..models import DownloadClient


class ClientError(Exception):
    pass


@dataclass
class ClientItem:
    download_id: str
    title: str
    category: Optional[str]
    status: str  # queued | downloading | paused | completed | failed | warning | seeding
    size: int = 0
    size_left: int = 0
    progress: float = 0.0  # 0..100
    eta_seconds: Optional[int] = None
    output_path: Optional[str] = None
    message: Optional[str] = None
    ratio: Optional[float] = None
    can_remove: bool = False  # seed goals reached / usenet finished

    def to_dict(self):
        return asdict(self)


@dataclass
class AddRequest:
    title: str
    category: str
    content: Optional[bytes] = None  # .torrent / .nzb
    magnet: Optional[str] = None
    url: Optional[str] = None
    seed_ratio: Optional[float] = None
    seed_time: Optional[int] = None  # minutes
    filename: Optional[str] = None


class BaseClient:
    protocol = "torrent"

    def __init__(self, cfg: DownloadClient):
        self.cfg = cfg
        self.settings = cfg.settings or {}

    @property
    def base_url(self) -> str:
        scheme = "https" if self.cfg.use_ssl else "http"
        base = (self.cfg.url_base or "").strip("/")
        return f"{scheme}://{self.cfg.host}:{self.cfg.port}" + (f"/{base}" if base else "")

    def http(self, **kw) -> httpx.Client:
        return httpx.Client(timeout=kw.pop("timeout", 30), verify=False, follow_redirects=True, **kw)

    # interface ---------------------------------------------------------------------------
    def test(self) -> str:
        raise NotImplementedError

    def add(self, req: AddRequest) -> str:
        raise NotImplementedError

    def items(self, categories: list[str]) -> list[ClientItem]:
        raise NotImplementedError

    def remove(self, download_id: str, delete_data: bool = True) -> None:
        raise NotImplementedError
