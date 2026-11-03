"""Registration of all command handlers for the command queue / scheduler."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..core import settings as settings_mod
from ..core.scheduler import commands
from ..indexers import newznab, usage
from ..metadata.manager import MetadataManager
from ..models import Episode, Indexer, Movie, Series, utcnow
from . import backup, delay, importlists, library, maintenance, queue, rss, search
from .notifications import notify

log = logging.getLogger("commands")

health_cache: dict = {"issues": [], "checked": None}


def _movie_search(db: Session, movie_id: int):
    m = db.get(Movie, movie_id)
    return search.auto_search_movie(db, m) if m else None


def _movies_search(db: Session, movie_ids: list[int]):
    return [_movie_search(db, i) for i in movie_ids]


def _episode_search(db: Session, series_id: int, episode_ids: list[int]):
    s = db.get(Series, series_id)
    if not s:
        return None
    eps = [e for e in s.episodes if e.id in set(episode_ids)]
    return search.auto_search_episodes(db, s, eps)


def _season_search(db: Session, series_id: int, season: int):
    s = db.get(Series, series_id)
    eps = search.wanted_episodes(s, season=season, include_cutoff=True) if s else []
    return search.auto_search_episodes(db, s, eps) if eps else []


def _series_search(db: Session, series_id: int):
    s = db.get(Series, series_id)
    eps = search.wanted_episodes(s, include_cutoff=True) if s else []
    return search.auto_search_episodes(db, s, eps) if eps else []


def _refresh_movie(db: Session, movie_id: int):
    m = db.get(Movie, movie_id)
    if m:
        library.refresh_movie(db, m)
        maintenance.scan_movie(db, m)


def _refresh_series(db: Session, series_id: int):
    s = db.get(Series, series_id)
    if s:
        stats = library.refresh_series(db, s)
        maintenance.scan_series(db, s)
        return stats


def _refresh_all(db: Session):
    mgr = MetadataManager.from_db(db)
    n = 0
    for s in db.query(Series).all():
        if s.status == "ended" and s.last_refresh and (utcnow() - s.last_refresh).days < 7:
            continue
        try:
            library.refresh_series(db, s, mgr)
            db.commit()
            n += 1
        except Exception as e:
            log.warning("Refresh %s fehlgeschlagen: %s", s.title, e)
            db.rollback()
    for m in db.query(Movie).all():
        if m.status == "released" and m.has_file and m.last_refresh and (utcnow() - m.last_refresh).days < 7:
            continue
        try:
            library.refresh_movie(db, m, mgr)
            db.commit()
            n += 1
        except Exception as e:
            log.warning("Refresh %s fehlgeschlagen: %s", m.title, e)
            db.rollback()
    return {"refreshed": n}


def _poll_limits(db: Session):
    """Keep the live ``apilimits`` counters fresh for indexers that report them."""
    minutes = settings_mod.get(db, "indexers").get("limits_poll_minutes") or 0
    now, polled = utcnow(), []
    for idx in db.query(Indexer).filter(Indexer.enabled.is_(True), Indexer.sync_remote_limits.is_(True)).all():
        rl = idx.remote_limits or {}
        if rl.get("supported") is False or (idx.disabled_until and idx.disabled_until > now):
            continue
        last = rl.get("checked") or rl.get("seen")
        # normal searches / RSS deliver the counters too – only ask when they are getting stale
        if last and now - datetime.fromisoformat(last) < timedelta(minutes=minutes * 0.9):
            continue
        if not usage.can(db, idx, "query"):
            continue
        try:
            newznab.probe_limits(db, idx)
            db.commit()
            polled.append(idx.name)
        except Exception as e:
            db.rollback()
            log.warning("Live-Limits von %s nicht abrufbar: %s", idx.name, e)
    return {"polled": polled}


def _health(db: Session):
    issues = maintenance.health(db)
    old = {i["message"] for i in health_cache["issues"]}
    old_keys = {i.get("key") for i in health_cache["issues"]}
    for i in issues:
        if (i.get("key") or "").startswith("limit:"):
            if i["key"] not in old_keys:  # once per indexer/kind when it reaches 90 % and again at 100 %
                notify("limit", i["message"])
        elif i["message"] not in old and i["level"] == "error":
            notify("health", i["message"])
    health_cache["issues"] = issues
    health_cache["checked"] = utcnow().isoformat() + "Z"
    return {"issues": len(issues)}


def _rename_series(db: Session, series_id: int):
    s = db.get(Series, series_id)
    from .importer import rename_apply
    return rename_apply(db, series=s) if s else 0


def _rename_movie(db: Session, movie_id: int):
    m = db.get(Movie, movie_id)
    from .importer import rename_apply
    return rename_apply(db, movie=m) if m else 0


def _probe_files(db: Session, movie_id: int | None = None, series_id: int | None = None):
    return {"probed": maintenance.probe_missing(db, limit=100000, movie_id=movie_id, series_id=series_id, force=True)}


def _rescan_movie(db: Session, movie_id: int):
    m = db.get(Movie, movie_id)
    return maintenance.scan_movie(db, m) if m else None


def _rescan_series(db: Session, series_id: int):
    s = db.get(Series, series_id)
    if not s:
        return None
    res = maintenance.scan_series(db, s)
    return {k: (len(v) if isinstance(v, list) else v) for k, v in res.items()}


def register_all() -> None:
    commands.register("movie_search", _movie_search)
    commands.register("movies_search", _movies_search)
    commands.register("episode_search", _episode_search)
    commands.register("season_search", _season_search)
    commands.register("series_search", _series_search)
    commands.register("refresh_movie", _refresh_movie)
    commands.register("refresh_series", _refresh_series)
    commands.register("refresh_all", _refresh_all)
    commands.register("rename_movie", _rename_movie)
    commands.register("rename_series", _rename_series)
    commands.register("rss_sync", rss.rss_sync)
    commands.register("poll_limits", _poll_limits)
    commands.register("wanted_search", lambda db: rss.search_wanted(db))
    commands.register("cutoff_search", lambda db: rss.search_wanted(db, include_cutoff=True))
    commands.register("check_downloads", queue.check_downloads)
    commands.register("health_check", _health)
    commands.register("disk_scan_all", maintenance.scan_all)
    commands.register("housekeeping", maintenance.housekeeping)
    commands.register("backup", backup.scheduled_backup)
    commands.register("process_pending", delay.process_pending)
    commands.register("import_lists", importlists.sync_all)
    commands.register("probe_files", _probe_files)
    commands.register("rescan_movie", _rescan_movie)
    commands.register("rescan_series", _rescan_series)
