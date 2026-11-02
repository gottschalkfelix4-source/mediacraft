"""Configuration resources: profiles, formats, root folders, tags, indexers (+usage), clients, notifications."""
from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core import qualities
from ...db import get_db
from ...downloadclients.base import ClientError
from ...downloadclients.manager import CLIENT_CLASSES, CLIENT_DEFAULTS, get_client
from ...indexers import newznab, usage
from ...metadata.manager import MetadataManager
from ...models import (CustomFormat, DownloadClient, Indexer, IndexerEvent, Movie, Notification, QualityProfile,
                       RemotePathMapping, RootFolder, Series, Tag, iso, utcnow)
from ...services import notifications as notif
from ..deps import apply, get_or_404, require_auth

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])


# ===================================================================================== qualities
@router.get("/qualities")
def list_qualities():
    return [{"name": q.name, "source": q.source, "resolution": q.resolution, "rank": q.rank,
             "min_mb_min": q.min_mb_min, "max_mb_min": q.max_mb_min} for q in qualities.QUALITIES.values()]


PROFILE_FIELDS = ("name", "items", "cutoff", "upgrade_allowed", "languages", "language_mode", "format_scores",
                  "min_format_score", "cutoff_format_score", "required_terms", "ignored_terms")


@router.get("/qualityprofiles")
def list_profiles(db: Session = Depends(get_db)):
    return [p.to_dict() for p in db.query(QualityProfile).order_by(QualityProfile.id).all()]


@router.post("/qualityprofiles")
def create_profile(body: dict, db: Session = Depends(get_db)):
    p = apply(QualityProfile(items=qualities.default_profile_items([])), body, PROFILE_FIELDS)
    db.add(p)
    db.flush()
    return p.to_dict()


@router.put("/qualityprofiles/{pid}")
def update_profile(pid: int, body: dict, db: Session = Depends(get_db)):
    p = apply(get_or_404(db, QualityProfile, pid), body, PROFILE_FIELDS)
    db.flush()
    return p.to_dict()


@router.delete("/qualityprofiles/{pid}")
def delete_profile(pid: int, db: Session = Depends(get_db)):
    p = get_or_404(db, QualityProfile, pid)
    if db.query(Movie).filter(Movie.quality_profile_id == pid).count() or \
            db.query(Series).filter(Series.quality_profile_id == pid).count():
        raise HTTPException(400, "Profil wird noch verwendet")
    db.delete(p)
    return {"ok": True}


@router.get("/customformats")
def list_formats(db: Session = Depends(get_db)):
    return [f.to_dict() for f in db.query(CustomFormat).order_by(CustomFormat.name).all()]


@router.post("/customformats")
def create_format(body: dict, db: Session = Depends(get_db)):
    f = apply(CustomFormat(), body, ("name", "conditions"))
    db.add(f)
    db.flush()
    return f.to_dict()


@router.put("/customformats/{fid}")
def update_format(fid: int, body: dict, db: Session = Depends(get_db)):
    f = apply(get_or_404(db, CustomFormat, fid), body, ("name", "conditions"))
    db.flush()
    return f.to_dict()


@router.delete("/customformats/{fid}")
def delete_format(fid: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, CustomFormat, fid))
    for p in db.query(QualityProfile).all():
        if str(fid) in (p.format_scores or {}):
            p.format_scores = {k: v for k, v in p.format_scores.items() if k != str(fid)}
    return {"ok": True}


@router.post("/customformats/test")
def test_format(body: dict, db: Session = Depends(get_db)):
    """Parse a release title and show which formats match (+ score per profile)."""
    from ...core import customformats
    from ...core.parser import parse

    p = parse(body.get("title", ""))
    formats = [f.to_dict() for f in db.query(CustomFormat).all()]
    matched = [f["name"] for f in formats if customformats.matches(f, p, int(body.get("size", 0)))]
    profiles = [{"id": pr.id, "name": pr.name,
                 "score": customformats.evaluate(formats, pr.format_scores or {}, p, int(body.get("size", 0)))[0],
                 "quality_allowed": qualities.profile_rank(pr.items, p.quality) >= 0}
                for pr in db.query(QualityProfile).all()]
    return {"parsed": p.to_dict(), "formats": matched, "profiles": profiles}


# ===================================================================================== root folders / tags
def _rf_dict(rf: RootFolder) -> dict:
    d = rf.to_dict()
    try:
        u = shutil.disk_usage(rf.path)
        d.update(free_space=u.free, total_space=u.total, accessible=True)
    except OSError:
        d.update(free_space=None, total_space=None, accessible=False)
    return d


@router.get("/rootfolders")
def list_rootfolders(db: Session = Depends(get_db)):
    return [_rf_dict(r) for r in db.query(RootFolder).all()]


@router.post("/rootfolders")
def add_rootfolder(body: dict, db: Session = Depends(get_db)):
    path = (body.get("path") or "").rstrip("/\\") or "/"
    if not os.path.isdir(path):
        raise HTTPException(400, f"Ordner existiert nicht: {path}")
    if db.query(RootFolder).filter(RootFolder.path == path).first():
        raise HTTPException(400, "Root-Folder existiert bereits")
    rf = RootFolder(path=path, media_type=body.get("media_type", "movie"))
    db.add(rf)
    db.flush()
    return _rf_dict(rf)


@router.delete("/rootfolders/{rid}")
def delete_rootfolder(rid: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, RootFolder, rid))
    return {"ok": True}


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)):
    return [t.to_dict() for t in db.query(Tag).order_by(Tag.label).all()]


@router.post("/tags")
def create_tag(body: dict, db: Session = Depends(get_db)):
    label = (body.get("label") or "").strip().lower()
    t = db.query(Tag).filter(Tag.label == label).first() or Tag(label=label)
    db.add(t)
    db.flush()
    return t.to_dict()


@router.delete("/tags/{tid}")
def delete_tag(tid: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Tag, tid))
    return {"ok": True}


# ===================================================================================== indexers
INDEXER_FIELDS = (
    "name", "kind", "url", "api_path", "api_key", "movie_categories", "tv_categories", "anime_categories",
    "additional_params", "enabled", "enable_rss", "enable_auto_search", "enable_interactive_search", "priority",
    "minimum_seeders", "seed_ratio", "seed_time", "download_client_id", "tags", "query_limit", "grab_limit",
    "limit_window_hours", "limit_mode", "limit_reset_hour", "grab_reserve", "query_reserve", "min_request_interval",
    "sync_remote_limits",
)

LIMIT_PRESETS = [
    {"name": "Unbegrenzt", "query_limit": 0, "grab_limit": 0, "limit_window_hours": 24, "limit_mode": "rolling"},
    {"name": "TreasureMaps-Stil: 400 Grabs / 24 h rollierend", "query_limit": 0, "grab_limit": 400,
     "limit_window_hours": 24, "limit_mode": "rolling"},
    {"name": "Free-Account: 100 API / 5 Grabs täglich (Reset 00:00 UTC)", "query_limit": 100, "grab_limit": 5,
     "limit_window_hours": 24, "limit_mode": "fixed", "limit_reset_hour": 0},
    {"name": "VIP: 5000 API / 1000 Grabs / 24 h rollierend", "query_limit": 5000, "grab_limit": 1000,
     "limit_window_hours": 24, "limit_mode": "rolling"},
]


def indexer_to_dict(db: Session, i: Indexer, with_usage: bool = True) -> dict:
    d = {f: getattr(i, f) for f in INDEXER_FIELDS}
    d.update(id=i.id, protocol=i.protocol, capabilities=i.capabilities, disabled_until=iso(i.disabled_until),
             failure_count=i.failure_count, last_error=i.last_error, remote_limits=i.remote_limits,
             sync_source=i.sync_source)
    if with_usage:
        d["usage"] = {"query": usage.state(db, i, "query").to_dict(), "grab": usage.state(db, i, "grab").to_dict()}
    return d


@router.get("/indexers")
def list_indexers(db: Session = Depends(get_db)):
    return [indexer_to_dict(db, i) for i in db.query(Indexer).order_by(Indexer.priority, Indexer.id).all()]


@router.get("/indexers/presets")
def indexer_presets():
    return {"limits": LIMIT_PRESETS,
            "categories": {"movie": [2000, 2010, 2020, 2030, 2040, 2045, 2050, 2060],
                           "tv": [5000, 5010, 5020, 5030, 5040, 5045, 5050], "anime": [5070]}}


@router.post("/indexers")
def create_indexer(body: dict, db: Session = Depends(get_db)):
    i = apply(Indexer(), body, INDEXER_FIELDS)
    if not i.movie_categories and not i.tv_categories:
        i.movie_categories, i.tv_categories = [2000], [5000]
    db.add(i)
    db.flush()
    return indexer_to_dict(db, i)


@router.get("/indexers/{iid}")
def get_indexer(iid: int, db: Session = Depends(get_db)):
    return indexer_to_dict(db, get_or_404(db, Indexer, iid))


@router.put("/indexers/{iid}")
def update_indexer(iid: int, body: dict, db: Session = Depends(get_db)):
    i = apply(get_or_404(db, Indexer, iid), body, INDEXER_FIELDS)
    db.flush()
    return indexer_to_dict(db, i)


@router.delete("/indexers/{iid}")
def delete_indexer(iid: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Indexer, iid))
    return {"ok": True}


@router.post("/indexers/test")
def test_indexer(body: dict, db: Session = Depends(get_db)):
    """Test unsaved settings (or a saved indexer when ``id`` is given) by fetching caps."""
    i = db.get(Indexer, body["id"]) if body.get("id") else None
    if i is None:
        i = apply(Indexer(id=None, name=body.get("name") or "Test"), body, INDEXER_FIELDS)
        i.limit_window_hours = i.limit_window_hours or 24
        db.add(i)
        db.flush()
        temp = True
    else:
        temp = False
    try:
        caps = newznab.caps(db, i, manual=True)
        return {"ok": True, "capabilities": caps}
    except Exception as e:
        raise HTTPException(400, f"Test fehlgeschlagen: {e}")
    finally:
        if temp:
            db.delete(i)
            db.flush()


@router.post("/indexers/{iid}/caps")
def refresh_caps(iid: int, db: Session = Depends(get_db)):
    i = get_or_404(db, Indexer, iid)
    try:
        return newznab.caps(db, i, manual=True)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/indexers/{iid}/limits")
def refresh_limits(iid: int, db: Session = Depends(get_db)):
    """Ask the indexer for its live counters right now (one API call, no grab)."""
    i = get_or_404(db, Indexer, iid)
    try:
        newznab.probe_limits(db, i, manual=True)
    except Exception as e:
        raise HTTPException(400, str(e))
    return indexer_to_dict(db, i)


@router.post("/indexers/{iid}/unpause")
def unpause(iid: int, db: Session = Depends(get_db)):
    i = get_or_404(db, Indexer, iid)
    i.disabled_until, i.failure_count, i.last_error = None, 0, None
    return indexer_to_dict(db, i)


@router.get("/indexers/{iid}/usage")
def indexer_usage(iid: int, hours: int = 48, db: Session = Depends(get_db)):
    i = get_or_404(db, Indexer, iid)
    events = db.query(IndexerEvent).filter(IndexerEvent.indexer_id == iid).order_by(IndexerEvent.timestamp.desc()).limit(200).all()
    return {
        "indexer": indexer_to_dict(db, i),
        "histogram": usage.histogram(db, i, min(max(hours, 1), 24 * 14)),
        "forecast": {"query": usage.forecast(db, i, "query"), "grab": usage.forecast(db, i, "grab")},
        "events": [{"id": e.id, "kind": e.kind, "timestamp": iso(e.timestamp), "success": e.success, "manual": e.manual,
                    "elapsed_ms": e.elapsed_ms, "results": e.results, "detail": e.detail} for e in events],
    }


@router.get("/indexers-usage")
def all_usage(db: Session = Depends(get_db)):
    """Compact overview for the dashboard."""
    out = []
    now = utcnow()
    for i in db.query(Indexer).order_by(Indexer.priority, Indexer.id).all():
        out.append({"id": i.id, "name": i.name, "enabled": i.enabled, "protocol": i.protocol,
                    "paused_until": iso(i.disabled_until) if i.disabled_until and i.disabled_until > now else None,
                    "last_error": i.last_error, "limit_mode": i.limit_mode, "window_hours": i.limit_window_hours,
                    "query": usage.state(db, i, "query", now).to_dict(), "grab": usage.state(db, i, "grab", now).to_dict()})
    return out


@router.delete("/indexers/{iid}/usage")
def reset_usage(iid: int, db: Session = Depends(get_db)):
    get_or_404(db, Indexer, iid)
    n = db.query(IndexerEvent).filter(IndexerEvent.indexer_id == iid).delete()
    return {"deleted": n}


# ===================================================================================== download clients
CLIENT_FIELDS = ("name", "kind", "enabled", "priority", "host", "port", "use_ssl", "url_base", "username", "password",
                 "api_key", "movie_category", "tv_category", "remove_completed", "remove_failed", "add_paused",
                 "settings", "tags")


MASK = "********"


def client_to_dict(c: DownloadClient) -> dict:
    d = {f: getattr(c, f) for f in CLIENT_FIELDS}
    d.update(id=c.id, protocol=c.protocol)
    for secret in ("password", "api_key"):
        if d[secret]:
            d[secret] = MASK  # never send stored secrets back to the browser
    return d


def _client_body(body: dict, saved: DownloadClient | None) -> dict:
    body = dict(body)
    for secret in ("password", "api_key"):
        if body.get(secret) == MASK:
            if saved:
                body[secret] = getattr(saved, secret)
            else:
                body.pop(secret)
    return body


@router.get("/downloadclients")
def list_clients(db: Session = Depends(get_db)):
    return [client_to_dict(c) for c in db.query(DownloadClient).order_by(DownloadClient.priority, DownloadClient.id).all()]


@router.get("/downloadclients/schema")
def client_schema():
    return [{"kind": k, "protocol": "torrent" if k in ("qbittorrent", "transmission", "deluge", "blackhole_torrent") else "usenet",
             **CLIENT_DEFAULTS.get(k, {})} for k in CLIENT_CLASSES]


@router.post("/downloadclients")
def create_client(body: dict, db: Session = Depends(get_db)):
    c = apply(DownloadClient(), body, CLIENT_FIELDS)
    db.add(c)
    db.flush()
    return client_to_dict(c)


@router.put("/downloadclients/{cid}")
def update_client(cid: int, body: dict, db: Session = Depends(get_db)):
    saved = get_or_404(db, DownloadClient, cid)
    c = apply(saved, _client_body(body, saved), CLIENT_FIELDS)
    db.flush()
    return client_to_dict(c)


@router.delete("/downloadclients/{cid}")
def delete_client(cid: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, DownloadClient, cid))
    return {"ok": True}


@router.post("/downloadclients/test")
def test_client(body: dict, db: Session = Depends(get_db)):
    saved = db.get(DownloadClient, body["id"]) if body.get("id") else None
    c = apply(DownloadClient(id=body.get("id")), _client_body(body, saved), CLIENT_FIELDS)
    c.settings = c.settings or {}
    try:
        return {"ok": True, "message": get_client(c).test()}
    except (ClientError, Exception) as e:
        raise HTTPException(400, f"Test fehlgeschlagen: {e}")


@router.get("/remotepathmappings")
def list_mappings(db: Session = Depends(get_db)):
    return [m.to_dict() for m in db.query(RemotePathMapping).all()]


def _trim(body: dict) -> dict:
    return {k: v.strip() if isinstance(v, str) else v for k, v in body.items()}


@router.post("/remotepathmappings")
def create_mapping(body: dict, db: Session = Depends(get_db)):
    m = apply(RemotePathMapping(), _trim(body), ("host", "remote_path", "local_path"))
    db.add(m)
    db.flush()
    return m.to_dict()


@router.put("/remotepathmappings/{mid}")
def update_mapping(mid: int, body: dict, db: Session = Depends(get_db)):
    m = apply(get_or_404(db, RemotePathMapping, mid), _trim(body), ("host", "remote_path", "local_path"))
    return m.to_dict()


@router.delete("/remotepathmappings/{mid}")
def delete_mapping(mid: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, RemotePathMapping, mid))
    return {"ok": True}


# ===================================================================================== notifications
NOTIF_FIELDS = ("name", "kind", "enabled", "on_grab", "on_import", "on_upgrade", "on_failure", "on_health", "settings")


def notif_to_dict(n: Notification) -> dict:
    return {"id": n.id, **{f: getattr(n, f) for f in NOTIF_FIELDS}}


@router.get("/notifications")
def list_notifications(db: Session = Depends(get_db)):
    return [notif_to_dict(n) for n in db.query(Notification).all()]


@router.get("/notifications/schema")
def notification_schema():
    return [{"kind": k, "fields": v} for k, v in notif.KINDS.items()]


@router.post("/notifications")
def create_notification(body: dict, db: Session = Depends(get_db)):
    n = apply(Notification(), body, NOTIF_FIELDS)
    db.add(n)
    db.flush()
    return notif_to_dict(n)


@router.put("/notifications/{nid}")
def update_notification(nid: int, body: dict, db: Session = Depends(get_db)):
    n = apply(get_or_404(db, Notification, nid), body, NOTIF_FIELDS)
    return notif_to_dict(n)


@router.delete("/notifications/{nid}")
def delete_notification(nid: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Notification, nid))
    return {"ok": True}


@router.post("/notifications/test")
def test_notification(body: dict):
    n = apply(Notification(), body, NOTIF_FIELDS)
    try:
        notif.test(n)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(400, f"Test fehlgeschlagen: {e}")


# ===================================================================================== metadata
@router.get("/metadata/providers")
def providers(db: Session = Depends(get_db)):
    return MetadataManager.from_db(db).status()
