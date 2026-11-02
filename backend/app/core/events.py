"""In-process event bus (for the UI live stream) and an in-memory log ring buffer."""
from __future__ import annotations

import json
import logging
import queue
import threading
from collections import deque
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from ..config import LOG_DIR

_subscribers: list[queue.Queue] = []
_sub_lock = threading.Lock()


# set while downloads are running so the scheduler polls the download clients more often (live progress)
live_state = {"active_downloads": False}


def publish(kind: str, data: dict | None = None) -> None:
    msg = json.dumps({"type": kind, "data": data or {}, "ts": datetime.now(timezone.utc).isoformat()}, default=str)
    with _sub_lock:
        subs = list(_subscribers)
    for q in subs:
        try:
            q.put_nowait(msg)
        except queue.Full:
            pass


def subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=500)
    with _sub_lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _sub_lock:
        if q in _subscribers:
            _subscribers.remove(q)


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 2000):
        super().__init__()
        self.records: deque = deque(maxlen=capacity)
        self._id = 0

    def emit(self, record: logging.LogRecord) -> None:
        self._id += 1
        self.records.append({
            "id": self._id, "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname, "logger": record.name, "message": self.format(record),
        })


ring = RingBufferHandler()


def setup_logging(level: str = "INFO") -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    fileh = RotatingFileHandler(LOG_DIR / "mediacraft.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fileh.setFormatter(fmt)
    ring.setFormatter(logging.Formatter("%(message)s"))
    for h in (console, fileh, ring):
        root.addHandler(h)
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
