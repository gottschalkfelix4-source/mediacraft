"""Download tracking and completed/failed download handling."""
from __future__ import annotations

import logging
import threading
from datetime import timedelta

from sqlalchemy.orm import Session

from ..core import settings as settings_mod
from ..core.events import live_state, publish
from ..downloadclients.base import ClientError
from ..downloadclients.manager import get_client, map_path
from ..models import Blocklist, DownloadClient, History, Movie, QueueItem, Series, iso, utcnow
from .importer import import_progress, process_download
from .notifications import notify

log = logging.getLogger("queue")

ACTIVE = ("grabbed", "queued", "downloading", "completed", "importing")  # worth live progress polling
TRACKED = ("grabbed", "queued", "downloading", "paused", "warning", "completed", "importing", "import_blocked", "seeding")


_check_lock = threading.Lock()  # one check_downloads at a time (scheduler + "Downloads prüfen" button)
_import_guard = threading.Lock()
_importing: set[int] = set()  # queue id being imported right now – never more than one (see _import)


def import_running(qid: int) -> bool:
    return qid in _importing


def check_downloads(db: Session) -> dict:
    if not _check_lock.acquire(blocking=False):
        return {"skipped": "läuft bereits"}
    try:
        return _check_downloads(db)
    finally:
        _check_lock.release()


def _check_downloads(db: Session) -> dict:
    cfg = settings_mod.get(db, "downloads")
    stats = {"checked": 0, "imported": 0, "failed": 0, "errors": []}
    clients = db.query(DownloadClient).filter(DownloadClient.enabled.is_(True)).all()
    for c in clients:
        items = db.query(QueueItem).filter(QueueItem.download_client_id == c.id,
                                           QueueItem.status.in_(TRACKED + ("imported",))).all()
        if not items:
            continue
        try:
            client_items = {ci.download_id.lower(): ci for ci in get_client(c).items([c.movie_category, c.tv_category])}
        except ClientError as e:
            stats["errors"].append(f"{c.name}: {e}")
            log.warning("Downloadclient %s: %s", c.name, e)
            continue
        for q in items:
            if q.id in _importing:  # e.g. "Import wiederholen" is copying it right now
                continue
            stats["checked"] += 1
            ci = client_items.get(q.download_id.lower())
            if ci is None:
                if q.status == "imported" or utcnow() - q.added > timedelta(minutes=15):
                    if q.status != "imported":
                        q.messages = (q.messages or []) + ["Download wurde im Client entfernt"]
                        q.status = "removed"
                    else:
                        db.delete(q)
                continue
            if q.status == "imported":
                # torrents keep seeding; remove once seed goals are reached (if configured)
                if c.remove_completed and ci.can_remove:
                    _safe_remove(c, q, delete_data=True)
                    db.delete(q)
                continue
            prev_progress = q.progress or 0.0
            q.size = ci.size or q.size
            q.size_left = ci.size_left
            q.progress = ci.progress
            q.eta_seconds = ci.eta_seconds
            q.client_status = ci.message or ci.status
            q.output_path = ci.output_path
            q.updated = utcnow()
            if ci.status == "failed":
                handle_failed(db, q, ci.message or "Download im Client fehlgeschlagen", c)
                stats["failed"] += 1
                continue
            if ci.status in ("completed", "seeding") and ci.progress >= 99.9 or (ci.status == "completed" and q.protocol == "usenet"):
                if not ci.output_path:
                    # finished, but the client hasn't reported the final folder yet (SABnzbd right after
                    # post-processing) – importing now would fail with "path not found"; just ask again next time
                    q.status = "downloading"
                    continue
                if q.status == "import_blocked" or not cfg.get("completed_handling", True):
                    q.status = "import_blocked" if q.status == "import_blocked" else "completed"
                    continue
                if _import(db, q, c):
                    stats["imported"] += 1
                    if c.remove_completed and (q.protocol == "usenet" or ci.can_remove):
                        _safe_remove(c, q, delete_data=True)
                        db.delete(q)
                continue
            if _stalled(q, ci.status, ci.progress, prev_progress, float(cfg.get("stalled_timeout_hours") or 0)):
                hours = float(cfg.get("stalled_timeout_hours") or 0)
                handle_failed(db, q, f"Download hängt seit über {hours:g} h ohne Fortschritt", c)
                stats["failed"] += 1
                continue
            q.status = {"downloading": "downloading", "queued": "queued", "paused": "paused",
                        "warning": "warning"}.get(ci.status, "downloading")
    live_state["active_downloads"] = db.query(QueueItem.id).filter(QueueItem.status.in_(ACTIVE)).first() is not None
    if stats["checked"]:
        publish("queue.updated", {})
    return stats


def _stalled(q: QueueItem, status: str, progress: float, prev_progress: float, timeout_hours: float) -> bool:
    """Track how long a download made no progress; True once that exceeds the configured timeout."""
    if status in ("paused", "queued") or progress > prev_progress + 0.001:
        q.stalled_since = None  # waiting on purpose, or moving again
        return False
    if q.stalled_since is None:
        q.stalled_since = utcnow()
        return False
    return timeout_hours > 0 and utcnow() - q.stalled_since >= timedelta(hours=timeout_hours)


def _safe_remove(c: DownloadClient, q: QueueItem, delete_data: bool) -> None:
    try:
        get_client(c).remove(q.download_id, delete_data=delete_data)
    except ClientError as e:
        log.warning("Entfernen aus %s fehlgeschlagen: %s", c.name, e)


def _import(db: Session, q: QueueItem, c: DownloadClient) -> bool:
    with _import_guard:
        # only ever one import at a time: parallel copies to the same disk/share only slow each other down
        # and compete for the database; the next check_downloads picks up whatever had to wait
        if _importing:
            return False
        _importing.add(q.id)
    try:
        db.flush()  # keep the client data just set (output path, ...) – refresh would drop it
        db.refresh(q)  # another run may have finished it meanwhile
        if q.status == "imported":
            return True
        return _do_import(db, q, c)
    finally:
        with _import_guard:
            _importing.discard(q.id)


def _do_import(db: Session, q: QueueItem, c: DownloadClient) -> bool:
    q.status = "importing"
    # commit + announce now, so the UI can show "importing" while files are copied/moved
    db.commit()
    publish("queue.updated", {"id": q.id})
    path = map_path(db, c, q.output_path)
    mode = "move" if q.protocol == "usenet" else "copy"
    try:
        ok, messages = process_download(db, q, path, mode)
    except Exception as e:  # never let one broken import stop the queue
        log.exception("Import von %s fehlgeschlagen", q.title)
        db.rollback()  # files imported so far are already committed one by one
        ok, messages = False, [f"Unerwarteter Fehler: {e}"]
    q.messages = messages
    if ok:
        q.status = "imported"
        q.finished = utcnow()
        log.info("Download importiert: %s", q.title)
    else:
        q.status = "import_blocked"
        log.warning("Import blockiert für %s: %s", q.title, "; ".join(messages))
    return ok


def schedule_import(db: Session, q: QueueItem) -> None:
    """'Import wiederholen': hand the item to the regular import queue (one import at a time)."""
    q.status = "completed"
    q.messages = ["Import eingeplant – startet, sobald kein anderer Import läuft"]
    db.commit()
    live_state["active_downloads"] = True
    publish("queue.updated", {"id": q.id})
    from ..core.scheduler import commands

    commands.enqueue("check_downloads")


def handle_failed(db: Session, q: QueueItem, reason: str, c: DownloadClient | None = None, blocklist: bool = True,
                  search_again: bool | None = None) -> None:
    cfg = settings_mod.get(db, "downloads")
    q.status = "failed"
    q.messages = (q.messages or []) + [reason]
    q.finished = utcnow()
    if blocklist:
        hist = db.query(History).filter(History.download_id == q.download_id, History.event == "grabbed").first()
        db.add(Blocklist(media_type=q.media_type, movie_id=q.movie_id, series_id=q.series_id,
                         episode_ids=q.episode_ids, source_title=q.title, guid=q.guid,
                         info_hash=q.download_id if q.protocol == "torrent" else None,
                         indexer=q.indexer_name, protocol=q.protocol, reason=reason[:500]))
    db.add(History(event="failed", media_type=q.media_type, movie_id=q.movie_id, series_id=q.series_id,
                   episode_ids=q.episode_ids, source_title=q.title, quality=q.quality, indexer=q.indexer_name,
                   download_id=q.download_id, data={"reason": reason}))
    db.flush()
    notify("failure", f"{q.title}: {reason}")
    if c and c.remove_failed:
        _safe_remove(c, q, delete_data=True)
    if search_again if search_again is not None else cfg.get("redownload_failed", True):
        from ..core.scheduler import commands

        if q.movie_id:
            commands.enqueue("movie_search", {"movie_id": q.movie_id})
        elif q.series_id and q.episode_ids:
            commands.enqueue("episode_search", {"series_id": q.series_id, "episode_ids": q.episode_ids})
    log.warning("Download fehlgeschlagen: %s (%s)", q.title, reason)


def remove_item(db: Session, q: QueueItem, remove_from_client: bool, blocklist: bool, search_again: bool = False) -> None:
    c = db.get(DownloadClient, q.download_client_id)
    if blocklist:
        handle_failed(db, q, "Manuell entfernt", c if remove_from_client else None, blocklist=True,
                      search_again=search_again)
    elif remove_from_client and c:
        _safe_remove(c, q, delete_data=True)
    db.delete(q)


def queue_to_dict(db: Session, q: QueueItem, names: dict | None = None) -> dict:
    target = None
    if q.movie_id:
        m = db.get(Movie, q.movie_id)
        target = {"type": "movie", "id": q.movie_id, "title": m.title if m else "?", "year": m.year if m else None}
    elif q.series_id:
        s = db.get(Series, q.series_id)
        target = {"type": "series", "id": q.series_id, "title": s.title if s else "?"}
    return {
        "id": q.id, "title": q.title, "status": q.status, "client_status": q.client_status, "protocol": q.protocol,
        "download_id": q.download_id, "download_client_id": q.download_client_id,
        "download_client": (names or {}).get(q.download_client_id), "indexer": q.indexer_name,
        "quality": q.quality, "languages": q.languages, "format_score": q.format_score, "size": q.size,
        "size_left": q.size_left, "progress": q.progress, "eta_seconds": q.eta_seconds, "output_path": q.output_path,
        "messages": q.messages, "media_type": q.media_type, "movie_id": q.movie_id, "series_id": q.series_id,
        "episode_ids": q.episode_ids, "target": target, "added": iso(q.added), "updated": iso(q.updated),
        "manual": q.manual, "import_progress": _import_pct(q.id), "stalled_since": iso(q.stalled_since),
    }


def _import_pct(qid: int) -> float | None:
    p = import_progress.get(qid)
    return round(100.0 * p["done"] / p["total"], 1) if p else None
