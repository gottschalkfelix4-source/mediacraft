"""Disk scan, existing-library import, health checks and housekeeping."""
from __future__ import annotations

import logging
import os
import re
import shutil
import time
from datetime import timedelta

from sqlalchemy.orm import Session

from . import recycle
from ..core import customformats
from ..core import settings as settings_mod
from ..core.decision import map_episodes
from ..core.parser import parse, parse_path
from ..downloadclients.base import ClientError
from ..downloadclients.manager import get_client
from ..indexers import usage
from ..metadata.manager import MetadataManager
from ..models import (DownloadClient, Episode, Indexer, IndexerEvent, MediaFile, MetadataCache, Movie, QualityProfile,
                      QueueItem, RootFolder, Series, utcnow)
from .importer import probe_file, video_files

log = logging.getLogger("maintenance")


# ======================================================================================== disk scan
def scan_movie(db: Session, movie: Movie) -> dict:
    res = {"linked": 0, "unlinked": 0}
    if movie.file and not os.path.exists(movie.file.path):
        f = movie.file
        movie.file_id = None
        db.flush()
        db.delete(f)
        res["unlinked"] += 1
    if not movie.file_id and movie.path and os.path.isdir(movie.path):
        files = video_files(movie.path)
        if files:
            src = max(files, key=os.path.getsize)
            p = parse_path(src)
            size = os.path.getsize(src)
            score, _ = customformats.score_for(db, db.get(QualityProfile, movie.quality_profile_id), p, size)
            mf = MediaFile(media_type="movie", movie_id=movie.id, path=src, size=size, format_score=score,
                           quality=p.quality, proper=p.revision, languages=p.languages, release_group=p.release_group,
                           release_name=os.path.splitext(os.path.basename(src))[0], edition=p.edition,
                           media_info={"codec": p.codec, "hdr": p.hdr, "audio": p.audio})
            probe_file(mf, settings_mod.get(db, "media"))
            db.add(mf)
            db.flush()
            movie.file_id = mf.id
            res["linked"] += 1
    return res


def scan_series(db: Session, series: Series) -> dict:
    res = {"linked": 0, "unlinked": 0, "unmatched": []}
    files = {f.id: f for f in db.query(MediaFile).filter(MediaFile.series_id == series.id).all()}
    for fid, f in list(files.items()):
        if not os.path.exists(f.path):
            for e in series.episodes:
                if e.file_id == fid:
                    e.file_id = None
            db.flush()
            db.delete(f)
            files.pop(fid)
            res["unlinked"] += 1
    if not series.path or not os.path.isdir(series.path):
        return res
    known = {os.path.normcase(f.path) for f in files.values()}
    profile = db.get(QualityProfile, series.quality_profile_id)
    for path in video_files(series.path):
        if os.path.normcase(path) in known:
            continue
        p = parse_path(path)
        if not p.is_tv:
            # "Show/Season 1/01 - Title.mkv" style
            m = re.match(r"^(\d{1,3})\b", os.path.basename(path))
            sm = re.search(r"(?:season|staffel)\s*(\d+)", os.path.dirname(path), re.I)
            if m and sm:
                p.is_tv, p.seasons, p.episodes = True, [int(sm.group(1))], [int(m.group(1))]
        eps = [e for e in map_episodes(series, p) if not e.file_id] if p.is_tv else []
        if not eps:
            res["unmatched"].append(path)
            continue
        size = os.path.getsize(path)
        score, _ = customformats.score_for(db, profile, p, size)
        mf = MediaFile(media_type="episode", series_id=series.id, path=path, size=size, format_score=score,
                       quality=p.quality, proper=p.revision, languages=p.languages, release_group=p.release_group,
                       release_name=os.path.splitext(os.path.basename(path))[0],
                       media_info={"codec": p.codec, "hdr": p.hdr, "audio": p.audio})
        probe_file(mf, settings_mod.get(db, "media"))
        db.add(mf)
        db.flush()
        for e in eps:
            e.file_id = mf.id
        res["linked"] += 1
    return res


def scan_all(db: Session) -> dict:
    total = {"movies": 0, "series": 0, "linked": 0, "unlinked": 0}
    for m in db.query(Movie).all():
        r = scan_movie(db, m)
        total["movies"] += 1
        total["linked"] += r["linked"]
        total["unlinked"] += r["unlinked"]
    for s in db.query(Series).all():
        r = scan_series(db, s)
        total["series"] += 1
        total["linked"] += r["linked"]
        total["unlinked"] += r["unlinked"]
    db.commit()
    total["probed"] = probe_missing(db)
    return total


def probe_missing(db: Session, limit: int = 300, movie_id: int | None = None, series_id: int | None = None,
                  force: bool = False) -> int:
    """Read stream info for library files that don't have it yet (bounded per run – probing is slow on NAS)."""
    from ..core import mediainfo

    cfg = settings_mod.get(db, "media")
    if not cfg.get("probe_files", True) or not mediainfo.tool():
        return 0
    q = db.query(MediaFile)
    if movie_id:
        q = q.filter(MediaFile.movie_id == movie_id)
    if series_id:
        q = q.filter(MediaFile.series_id == series_id)
    done = 0
    for mf in q.all():
        if done >= limit:
            break
        if not force and (mf.media_info or {}).get("probed"):
            continue
        if probe_file(mf, cfg):
            done += 1
            if done % 20 == 0:
                db.commit()  # don't hold the write lock for a whole library
        else:
            mf.media_info = {**(mf.media_info or {}), "probed": True}  # unreadable: don't retry every scan
    db.commit()
    return done


# ======================================================================================== library import
_ID_PATTERNS = {
    "tmdb": re.compile(r"[\[{(]tmdb(?:id)?[-=](\d+)[\]})]", re.I),
    "tvdb": re.compile(r"[\[{(]tvdb(?:id)?[-=](\d+)[\]})]", re.I),
    "imdb": re.compile(r"[\[{(]imdb(?:id)?[-=](tt\d+)[\]})]", re.I),
}


def unmapped_folders(db: Session, root: RootFolder) -> list[dict]:
    if not os.path.isdir(root.path):
        return []
    used = {os.path.normcase(os.path.normpath(p)) for (p,) in db.query(Movie.path).all()} | \
           {os.path.normcase(os.path.normpath(p)) for (p,) in db.query(Series.path).all()}
    out = []
    for entry in sorted(os.scandir(root.path), key=lambda e: e.name.lower()):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name.lower() in ("@eadir", "lost+found", "$recycle.bin"):
            continue
        if os.path.normcase(os.path.normpath(entry.path)) in used:
            continue
        ids = {k: (m.group(1) if k == "imdb" else int(m.group(1))) for k, pat in _ID_PATTERNS.items()
               if (m := pat.search(entry.name))}
        clean = re.sub(r"[\[{(](?:tmdb|tvdb|imdb)(?:id)?[-=][^\]})]+[\]})]", "", entry.name).strip()
        ym = re.search(r"\((\d{4})\)\s*$", clean)
        year = int(ym.group(1)) if ym else None
        title = clean[: ym.start()].strip() if ym else parse(clean).title or clean
        out.append({"folder": entry.name, "path": entry.path, "title": title, "year": year, "ids": ids,
                    "media_type": root.media_type})
    return out


def lookup_folder(db: Session, item: dict) -> list[dict]:
    mgr = MetadataManager.from_db(db)
    ids = item.get("ids") or {}
    if item.get("media_type") == "movie":
        if ids:
            m = mgr.get_movie(ids)
            return [m] if m else []
        return mgr.search_movies(f"{item['title']} {item.get('year') or ''}".strip())[:5]
    if ids:
        s = mgr.get_series(ids, with_episodes=False)
        return [s] if s else []
    return mgr.search_series(item["title"])[:5]


# ======================================================================================== health
def health(db: Session) -> list[dict]:
    issues: list[dict] = []
    for rf in db.query(RootFolder).all():
        if not os.path.isdir(rf.path):
            issues.append({"level": "error", "source": "rootfolder", "message": f"Root-Folder fehlt: {rf.path}"})
        elif not os.access(rf.path, os.W_OK):
            issues.append({"level": "error", "source": "rootfolder", "message": f"Root-Folder nicht beschreibbar: {rf.path}"})
        else:
            try:
                free = shutil.disk_usage(rf.path).free
                if free < 10 * 1024 ** 3:
                    issues.append({"level": "warning", "source": "disk",
                                   "message": f"Wenig Speicher auf {rf.path}: {free / 1024 ** 3:.1f} GB frei"})
            except OSError:
                pass
    if not db.query(RootFolder).count():
        issues.append({"level": "warning", "source": "rootfolder", "message": "Kein Root-Folder konfiguriert"})
    for c in db.query(DownloadClient).filter(DownloadClient.enabled.is_(True)).all():
        try:
            get_client(c).test()
        except (ClientError, Exception) as e:
            issues.append({"level": "error", "source": "downloadclient", "message": f"{c.name}: {e}"})
    if not db.query(DownloadClient).filter(DownloadClient.enabled.is_(True)).count():
        issues.append({"level": "warning", "source": "downloadclient", "message": "Kein Downloadclient aktiv"})
    now = utcnow()
    idxs = db.query(Indexer).filter(Indexer.enabled.is_(True)).all()
    if not idxs:
        issues.append({"level": "warning", "source": "indexer", "message": "Kein Indexer aktiv"})
    for i in idxs:
        if i.disabled_until and i.disabled_until > now:
            issues.append({"level": "warning", "source": "indexer",
                           "message": f"{i.name} pausiert bis {i.disabled_until:%d.%m. %H:%M} UTC: {i.last_error or ''}"})
        for kind in ("query", "grab"):
            st = usage.state(db, i, kind, now)
            if st.limit and st.percent >= 90:
                issues.append({"level": "warning" if st.percent < 100 else "error", "source": "indexer",
                               "key": f"limit:{i.id}:{kind}:{'full' if st.percent >= 100 else 'high'}",
                               "message": f"{i.name}: {kind}-Kontingent {st.used}/{st.limit} ({st.percent:.0f} %)"
                                          + (f", frei ab {st.next_slot[:16].replace('T', ' ')} UTC" if st.next_slot else "")})
    meta = MetadataManager.from_db(db)
    if not any(p.supports_movies and n in ("tmdb", "omdb") for n, p in meta.providers.items()):
        issues.append({"level": "warning", "source": "metadata",
                       "message": "Kein Film-Metadatenprovider mit Key (TMDB empfohlen) – Filmsuche eingeschränkt"})
    if settings_mod.get(db, "auth").get("method", "none") == "none":
        issues.append({"level": "warning", "source": "security",
                       "message": "Keine Anmeldung aktiv – jeder im Netz kann MediaCraft bedienen "
                                  "(Einstellungen → Allgemein / Sicherheit)"})
    blocked = db.query(QueueItem).filter(QueueItem.status == "import_blocked").count()
    if blocked:
        issues.append({"level": "warning", "source": "queue", "message": f"{blocked} Download(s) mit blockiertem Import"})
    return issues


# ======================================================================================== housekeeping
def housekeeping(db: Session) -> dict:
    now = utcnow()
    max_window = max([i.limit_window_hours or 24 for i in db.query(Indexer).all()] + [24])
    keep = max(timedelta(days=30), timedelta(hours=max_window * 2))
    ev = db.query(IndexerEvent).filter(IndexerEvent.timestamp < now - keep).delete()
    mc = db.query(MetadataCache).filter(MetadataCache.created < now - timedelta(days=7)).delete()
    qi = db.query(QueueItem).filter(QueueItem.status.in_(("failed", "removed")),
                                    QueueItem.updated < now - timedelta(days=7)).delete()
    from ..models import CommandRecord
    from .delay import drop_stale

    pending = drop_stale(db)
    keep_ids = [r[0] for r in db.query(CommandRecord.id).order_by(CommandRecord.id.desc()).limit(1000).all()]
    if keep_ids:
        db.query(CommandRecord).filter(CommandRecord.id < min(keep_ids)).delete()
    cfg = settings_mod.get(db, "media")
    days = int(cfg.get("recycle_bin_days") or 0)
    removed = recycle.empty(cfg, older_than_days=days) if days else 0
    return {"indexer_events": ev, "metadata_cache": mc, "queue": qi, "recycle_bin": removed, "pending": pending}
