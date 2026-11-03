"""Background scheduler (interval tasks) and command queue (user-triggered jobs)."""
from __future__ import annotations

import itertools
import logging
import queue
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from ..db import session_scope
from ..models import TaskState, utcnow
from . import settings as settings_mod
from .events import publish, live_state

log = logging.getLogger("scheduler")


# ================================================================================== commands
class CommandQueue:
    def __init__(self, workers: int = 2):
        self.handlers: dict[str, Callable] = {}
        self._q: queue.Queue = queue.Queue()
        self._ids = itertools.count(1)
        self.history: deque = deque(maxlen=200)
        self._workers = workers
        self._started = False
        self._lock = threading.Lock()

    def register(self, name: str, fn: Callable) -> None:
        self.handlers[name] = fn

    def enqueue(self, name: str, params: Optional[dict] = None) -> dict:
        if name not in self.handlers:
            raise KeyError(f"Unbekannter Befehl: {name}")
        cmd = {"id": next(self._ids), "name": name, "params": params or {}, "status": "queued",
               "queued": datetime.now(timezone.utc).isoformat(), "started": None, "ended": None,
               "result": None, "error": None}
        # de-duplicate identical queued commands
        with self._lock:
            for c in self.history:
                if c["status"] == "queued" and c["name"] == name and c["params"] == cmd["params"]:
                    return c
            self.history.appendleft(cmd)
        self._q.put(cmd)
        publish("command.queued", {"id": cmd["id"], "name": name})
        return cmd

    def get(self, cid: int) -> Optional[dict]:
        return next((c for c in self.history if c["id"] == cid), None)

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        for i in range(self._workers):
            threading.Thread(target=self._run, daemon=True, name=f"cmd-{i}").start()

    def run_sync(self, name: str, params: Optional[dict] = None):
        with session_scope() as db:
            return self.handlers[name](db, **(params or {}))

    def _run(self) -> None:
        while True:
            cmd = self._q.get()
            cmd["status"] = "running"
            cmd["started"] = datetime.now(timezone.utc).isoformat()
            publish("command.started", {"id": cmd["id"], "name": cmd["name"]})
            try:
                with session_scope() as db:
                    cmd["result"] = self.handlers[cmd["name"]](db, **cmd["params"])
                cmd["status"] = "completed"
            except Exception as e:
                cmd["status"] = "failed"
                cmd["error"] = str(e)
                log.error("Befehl %s fehlgeschlagen: %s\n%s", cmd["name"], e, traceback.format_exc())
            cmd["ended"] = datetime.now(timezone.utc).isoformat()
            publish("command.finished", {"id": cmd["id"], "name": cmd["name"], "status": cmd["status"],
                                         "error": cmd["error"]})


commands = CommandQueue(workers=3)


# ================================================================================== tasks
class Task:
    def __init__(self, name: str, label: str, interval: Callable[[dict], float], command: str):
        self.name, self.label, self.interval_fn, self.command = name, label, interval, command


def _cfg(section: str, key: str, factor: float = 1.0, default: float = 0.0) -> Callable[[dict], float]:
    return lambda all_cfg: float(all_cfg.get(section, {}).get(key, default) or 0) * factor


LIVE_DOWNLOAD_INTERVAL = 4  # seconds while something downloads (the loop ticks every 5 s, so this gives ~5 s updates)


def _download_interval(all_cfg: dict) -> float:
    base = _cfg("downloads", "check_interval_seconds", 1)(all_cfg)
    if base > 0 and live_state["active_downloads"]:
        return min(base, LIVE_DOWNLOAD_INTERVAL)
    return base


TASKS = [
    Task("check_downloads", "Downloads prüfen", _download_interval, "check_downloads"),
    Task("process_pending", "Zurückgestellte Releases", lambda c: 120, "process_pending"),
    Task("rss_sync", "RSS-Sync", _cfg("indexers", "rss_interval_minutes", 60), "rss_sync"),
    Task("poll_limits", "Indexer-Limits abfragen", _cfg("indexers", "limits_poll_minutes", 60, 15), "poll_limits"),
    Task("refresh_metadata", "Metadaten aktualisieren", _cfg("metadata", "refresh_interval_hours", 3600), "refresh_all"),
    Task("wanted_search", "Fehlende suchen", _cfg("wanted", "auto_search_interval_hours", 3600), "wanted_search"),
    Task("health_check", "Health-Check", lambda c: 300, "health_check"),
    Task("disk_scan", "Festplatten-Scan", lambda c: 6 * 3600, "disk_scan_all"),
    Task("housekeeping", "Aufräumen", lambda c: 24 * 3600, "housekeeping"),
    Task("import_lists", "Import-Listen", _cfg("importlists", "sync_interval_hours", 3600), "import_lists"),
    Task("backup", "Backup", _cfg("backup", "interval_days", 86400), "backup"),
]


TASK_SECTIONS = ("downloads", "indexers", "metadata", "wanted", "backup", "importlists")


class Scheduler:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.running: set[str] = set()

    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> list[dict]:
        with session_scope() as db:
            cfg = {s: settings_mod.get(db, s) for s in TASK_SECTIONS}
            states = {t.name: t for t in db.query(TaskState).all()}
            out = []
            for t in TASKS:
                st = states.get(t.name)
                interval = t.interval_fn(cfg)
                last = st.last_run if st else None
                out.append({
                    "name": t.name, "label": t.label, "interval_seconds": interval, "enabled": interval > 0,
                    "last_run": last.isoformat() + "Z" if last else None,
                    "next_run": (last + timedelta(seconds=interval)).isoformat() + "Z" if last and interval > 0 else None,
                    "last_duration_ms": st.last_duration_ms if st else 0, "last_error": st.last_error if st else None,
                    "running": t.name in self.running,
                })
            return out

    def run_now(self, name: str) -> dict:
        task = next(t for t in TASKS if t.name == name)
        return self._dispatch(task)

    def _dispatch(self, task: Task) -> dict:
        def wrapped(db, **_):
            self.running.add(task.name)
            t0 = time.monotonic()
            err = None
            result = None
            try:
                result = commands.handlers[task.command](db)
                db.commit()
            except Exception as e:
                err = str(e)
                db.rollback()
            finally:
                self.running.discard(task.name)
            # record the run in the same session (a second session would wait on our own write lock)
            st = db.get(TaskState, task.name) or TaskState(name=task.name)
            st.last_run = utcnow()
            st.last_duration_ms = int((time.monotonic() - t0) * 1000)
            st.last_error = err
            db.merge(st)
            db.commit()
            if err:
                raise RuntimeError(err)
            return result

        cmd_name = f"task:{task.name}"
        commands.register(cmd_name, wrapped)
        return commands.enqueue(cmd_name)

    def _loop(self) -> None:
        time.sleep(5)
        while not self._stop.is_set():
            try:
                with session_scope() as db:
                    cfg = {s: settings_mod.get(db, s) for s in TASK_SECTIONS}
                    states = {t.name: t.last_run for t in db.query(TaskState).all()}
                now = utcnow()
                for t in TASKS:
                    interval = t.interval_fn(cfg)
                    if interval <= 0 or t.name in self.running:
                        continue
                    last = states.get(t.name)
                    if last is None or (now - last).total_seconds() >= interval:
                        if not any(c["name"] == f"task:{t.name}" and c["status"] in ("queued", "running")
                                   for c in commands.history):
                            self._dispatch(t)
            except Exception:
                log.exception("Scheduler-Fehler")
            self._stop.wait(5)


scheduler = Scheduler()
