"""Sonarr / Radarr v3 compatible API subset.

Lets existing stack components talk to MediaCraft as if it were Sonarr (``/sonarr``) and
Radarr (``/radarr``): Jellyseerr/Overseerr (requests), Prowlarr (indexer sync), Homepage
widgets, LunaSea/nzb360 style dashboards. Only the resources those tools actually use are
implemented; field names follow the upstream v3 schema.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import config
from ..core import qualities
from ..core.scheduler import commands
from ..db import get_db
from ..indexers import newznab
from ..metadata.manager import MetadataManager
from ..models import (DownloadClient, Episode, Indexer, MediaFile, Movie, QualityProfile, QueueItem, RootFolder,
                      Series, Tag, iso, utcnow)
from ..services import library, maintenance
from ..services.commands import health_cache
from .deps import require_api_key

sonarr_router = APIRouter(prefix="/sonarr/api/v3", dependencies=[Depends(require_api_key)], tags=["sonarr-compat"])
radarr_router = APIRouter(prefix="/radarr/api/v3", dependencies=[Depends(require_api_key)], tags=["radarr-compat"])

VERSIONS = {"sonarr": "4.0.11.2680", "radarr": "5.14.0.9383"}


# ========================================================================================= helpers
def _images(images: dict) -> list[dict]:
    out = []
    for k, cover in (("poster", "poster"), ("fanart", "fanart"), ("banner", "banner")):
        if (images or {}).get(k):
            out.append({"coverType": cover, "url": images[k], "remoteUrl": images[k]})
    return out


def _quality(name: str, proper: int = 0) -> dict:
    q = qualities.get(name)
    return {"quality": {"id": q.rank, "name": q.name, "source": q.source, "resolution": q.resolution},
            "revision": {"version": 1 + (proper or 0), "real": 0, "isRepack": False}}


def _languages(langs: list[str]) -> list[dict]:
    ids = {"english": 1, "french": 2, "spanish": 3, "german": 4, "italian": 5, "japanese": 8, "dutch": 7}
    return [{"id": ids.get(l, 0), "name": l.capitalize()} for l in (langs or []) if l != "multi"]


def _slug(title: str, suffix) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-") + (f"-{suffix}" if suffix else "")


def _cmd_resource(cmd: dict, name: str) -> dict:
    return {"id": cmd["id"], "name": name, "commandName": name, "status": cmd["status"], "queued": cmd["queued"],
            "started": cmd.get("started"), "ended": cmd.get("ended"), "trigger": "manual", "body": cmd["params"],
            "priority": "normal", "result": "unknown"}


def _status(flavor: str) -> dict:
    return {
        "appName": flavor.capitalize(), "instanceName": f"MediaCraft ({flavor.capitalize()})",
        "version": VERSIONS[flavor], "buildTime": "2026-01-01T00:00:00Z", "isDebug": False, "isProduction": True,
        "isAdmin": False, "isUserInteractive": False, "startupPath": "/app", "appData": str(config.CONFIG_DIR),
        "osName": "linux", "osVersion": "", "isNetCore": True, "isLinux": True, "isOsx": False, "isWindows": False,
        "isDocker": True, "mode": "console", "branch": "main", "authentication": "none", "sqliteVersion": "3",
        "urlBase": f"/{flavor}", "runtimeVersion": "", "runtimeName": "MediaCraft", "startTime": iso(utcnow()),
        "packageUpdateMechanism": "docker", "databaseType": "sqLite",
    }


def _root_folders(db: Session, kinds: tuple[str, ...]) -> list[dict]:
    out = []
    for rf in db.query(RootFolder).filter(RootFolder.media_type.in_(kinds)).all():
        try:
            import shutil
            free, total = shutil.disk_usage(rf.path).free, shutil.disk_usage(rf.path).total
            ok = True
        except OSError:
            free, total, ok = 0, 0, False
        out.append({"id": rf.id, "path": rf.path, "accessible": ok, "freeSpace": free, "totalSpace": total,
                    "unmappedFolders": []})
    return out


def _profiles(db: Session) -> list[dict]:
    out = []
    for p in db.query(QualityProfile).order_by(QualityProfile.id).all():
        items = [{"quality": _quality(it["quality"])["quality"], "items": [], "allowed": it.get("allowed", False)}
                 for it in p.items]
        out.append({"id": p.id, "name": p.name, "upgradeAllowed": p.upgrade_allowed,
                    "cutoff": qualities.get(p.cutoff).rank, "items": items, "minFormatScore": p.min_format_score,
                    "cutoffFormatScore": p.cutoff_format_score, "formatItems": [],
                    "language": {"id": 4, "name": "German"} if "german" in (p.languages or []) else {"id": 1, "name": "English"}})
    return out


def _tags(db: Session) -> list[dict]:
    return [t.to_dict() for t in db.query(Tag).all()]


def _create_tag(db: Session, body: dict) -> dict:
    label = (body.get("label") or "").strip().lower()
    t = db.query(Tag).filter(Tag.label == label).first()
    if not t:
        t = Tag(label=label)
        db.add(t)
        db.flush()
    return t.to_dict()


def _health(_flavor: str) -> list[dict]:
    return [{"source": i["source"], "type": i["level"], "message": i["message"], "wikiUrl": ""}
            for i in health_cache.get("issues", [])]


def _resolve_root(db: Session, path: str, media_type: str) -> str:
    path = (path or "").rstrip("/\\")
    if not path:
        rf = db.query(RootFolder).filter(RootFolder.media_type == media_type).first()
        if not rf:
            raise HTTPException(400, "Kein Root-Folder konfiguriert")
        return rf.path
    return path


def _queue_records(db: Session, flavor: str, include_detail: bool) -> list[dict]:
    names = {c.id: c.name for c in db.query(DownloadClient).all()}
    media = "movie" if flavor == "radarr" else "series"
    out = []
    for q in db.query(QueueItem).filter(QueueItem.media_type == media,
                                        QueueItem.status.notin_(("imported", "failed", "removed"))).all():
        eta = q.eta_seconds
        timeleft = f"{eta // 3600:02d}:{(eta % 3600) // 60:02d}:{eta % 60:02d}" if eta is not None else None
        state = {"grabbed": "downloading", "queued": "downloading", "downloading": "downloading",
                 "paused": "downloading", "completed": "importPending", "importing": "importing",
                 "import_blocked": "importBlocked", "warning": "downloading"}.get(q.status, "downloading")
        base = {
            "size": q.size, "title": q.title, "sizeleft": q.size_left, "timeleft": timeleft,
            "estimatedCompletionTime": iso(utcnow() + timedelta(seconds=eta)) if eta is not None else None,
            "status": "paused" if q.status == "paused" else ("completed" if q.status in ("completed", "importing", "import_blocked") else "downloading"),
            "trackedDownloadStatus": "warning" if q.status in ("import_blocked", "warning") else "ok",
            "trackedDownloadState": state,
            "statusMessages": [{"title": q.title, "messages": q.messages or []}] if q.messages else [],
            "downloadId": q.download_id.upper() if q.protocol == "torrent" else q.download_id,
            "protocol": q.protocol, "downloadClient": names.get(q.download_client_id), "indexer": q.indexer_name,
            "outputPath": q.output_path, "quality": _quality(q.quality), "languages": _languages(q.languages),
            "added": iso(q.added),
        }
        if flavor == "radarr":
            rec = {"id": q.id, "movieId": q.movie_id, **base}
            if include_detail and q.movie_id:
                m = db.get(Movie, q.movie_id)
                if m:
                    rec["movie"] = movie_resource(db, m)
            out.append(rec)
        else:
            for eid in q.episode_ids or [None]:
                rec = {"id": q.id * 1000 + (eid or 0) % 1000, "seriesId": q.series_id, "episodeId": eid, **base}
                if include_detail and eid:
                    e = db.get(Episode, eid)
                    if e:
                        rec["episode"] = episode_resource(e)
                        rec["seasonNumber"] = e.season
                out.append(rec)
    return out


def _paged(records: list, request: Request) -> dict:
    page = int(request.query_params.get("page", 1))
    size = int(request.query_params.get("pageSize", 10))
    return {"page": page, "pageSize": size, "sortKey": "timeleft", "sortDirection": "ascending",
            "totalRecords": len(records), "records": records[(page - 1) * size: page * size]}


# ========================================================================================= indexers
INDEXER_FIELDS = {
    "sonarr": ["baseUrl", "apiPath", "apiKey", "categories", "animeCategories", "animeStandardFormatSearch",
               "additionalParameters", "multiLanguages", "minimumSeeders", "seedCriteria.seedRatio",
               "seedCriteria.seedTime", "seedCriteria.seasonPackSeedTime", "rejectBlocklistedTorrentHashesWhileGrabbing"],
    "radarr": ["baseUrl", "apiPath", "apiKey", "categories", "additionalParameters", "multiLanguages", "removeYear",
               "minimumSeeders", "seedCriteria.seedRatio", "seedCriteria.seedTime", "requiredFlags",
               "rejectBlocklistedTorrentHashesWhileGrabbing"],
}


def _field_defaults(name: str):
    return {"apiPath": "/api", "categories": [], "animeCategories": [], "multiLanguages": [], "requiredFlags": [],
            "minimumSeeders": 1, "animeStandardFormatSearch": False, "removeYear": False,
            "rejectBlocklistedTorrentHashesWhileGrabbing": False}.get(name)


def _schema(flavor: str) -> list[dict]:
    out = []
    for impl, proto in (("Newznab", "usenet"), ("Torznab", "torrent")):
        fields = [f for f in INDEXER_FIELDS[flavor] if proto == "torrent" or not f.startswith(("seedCriteria", "minimumSeeders", "rejectBlock"))]
        out.append({"id": 0, "name": "", "implementation": impl, "implementationName": impl,
                    "configContract": f"{impl}Settings", "protocol": proto, "supportsRss": True, "supportsSearch": True,
                    "enableRss": True, "enableAutomaticSearch": True, "enableInteractiveSearch": True, "priority": 25,
                    "downloadClientId": 0, "tags": [], "presets": [],
                    "fields": [{"order": i, "name": f, "label": f, "value": _field_defaults(f), "type": "textbox",
                                "advanced": False} for i, f in enumerate(fields)]})
    return out


def indexer_resource(i: Indexer, flavor: str) -> dict:
    vals = {
        "baseUrl": i.url, "apiPath": i.api_path, "apiKey": i.api_key,
        "categories": i.tv_categories if flavor == "sonarr" else i.movie_categories,
        "animeCategories": i.anime_categories, "animeStandardFormatSearch": False,
        "additionalParameters": i.additional_params or None, "multiLanguages": [], "removeYear": False,
        "minimumSeeders": i.minimum_seeders, "seedCriteria.seedRatio": i.seed_ratio,
        "seedCriteria.seedTime": i.seed_time, "seedCriteria.seasonPackSeedTime": i.seed_time, "requiredFlags": [],
        "rejectBlocklistedTorrentHashesWhileGrabbing": False,
    }
    impl = "Torznab" if i.kind == "torznab" else "Newznab"
    fields = [f for f in INDEXER_FIELDS[flavor] if i.kind == "torznab" or not f.startswith(("seedCriteria", "minimumSeeders", "rejectBlock"))]
    return {"id": i.id, "name": i.name, "enableRss": i.enable_rss, "enableAutomaticSearch": i.enable_auto_search,
            "enableInteractiveSearch": i.enable_interactive_search, "supportsRss": True, "supportsSearch": True,
            "protocol": i.protocol, "priority": i.priority, "downloadClientId": i.download_client_id or 0,
            "implementation": impl, "implementationName": impl, "configContract": f"{impl}Settings",
            "tags": i.tags or [], "fields": [{"order": n, "name": f, "value": vals.get(f)} for n, f in enumerate(fields)]}


def _norm_url(u: str) -> str:
    return (u or "").rstrip("/").lower()


def _apply_indexer(db: Session, flavor: str, body: dict, existing: Optional[Indexer] = None) -> Indexer:
    f = {x.get("name"): x.get("value") for x in body.get("fields") or []}
    url, key = f.get("baseUrl") or "", f.get("apiKey") or ""
    i = existing
    if i is None:
        # merge with the same indexer pushed for the other app (shared usage limits!)
        for cand in db.query(Indexer).all():
            if _norm_url(cand.url) == _norm_url(url) and (cand.api_key or "") == key:
                i = cand
                break
    if i is None:
        i = Indexer(name=re.sub(r"\s*\(Prowlarr\)\s*$", "", body.get("name") or "Indexer") + " (Prowlarr)",
                    url=url, movie_categories=[], tv_categories=[], anime_categories=[])
        db.add(i)
    i.kind = "torznab" if (body.get("implementation") or "").lower() == "torznab" else "newznab"
    i.url, i.api_key = url, key
    i.api_path = f.get("apiPath") or "/api"
    cats = [int(c) for c in f.get("categories") or []]
    if flavor == "sonarr":
        i.tv_categories = cats
        i.anime_categories = [int(c) for c in f.get("animeCategories") or []]
    else:
        i.movie_categories = cats
    if f.get("additionalParameters"):
        i.additional_params = f["additionalParameters"]
    if f.get("minimumSeeders") is not None:
        i.minimum_seeders = int(f["minimumSeeders"])
    if f.get("seedCriteria.seedRatio") not in (None, ""):
        i.seed_ratio = float(f["seedCriteria.seedRatio"])
    if f.get("seedCriteria.seedTime") not in (None, ""):
        i.seed_time = int(f["seedCriteria.seedTime"])
    for src, dst in (("enableRss", "enable_rss"), ("enableAutomaticSearch", "enable_auto_search"),
                     ("enableInteractiveSearch", "enable_interactive_search"), ("priority", "priority")):
        if src in body:
            setattr(i, dst, body[src])
    i.enabled = True
    i.sync_source = {**(i.sync_source or {}), flavor: True}
    db.flush()
    return i


def _register_common(router: APIRouter, flavor: str) -> None:
    @router.get("/system/status")
    def system_status():
        return _status(flavor)

    @router.get("/health")
    def health():
        return _health(flavor)

    @router.get("/qualityprofile")
    def quality_profiles(db: Session = Depends(get_db)):
        return _profiles(db)

    @router.get("/qualityprofile/{pid}")
    def quality_profile(pid: int, db: Session = Depends(get_db)):
        return next((p for p in _profiles(db) if p["id"] == pid), None) or JSONResponse({}, 404)

    @router.get("/rootfolder")
    def root_folders(db: Session = Depends(get_db)):
        return _root_folders(db, ("movie",) if flavor == "radarr" else ("series", "anime"))

    @router.get("/tag")
    def tags(db: Session = Depends(get_db)):
        return _tags(db)

    @router.post("/tag")
    def create_tag(body: dict, db: Session = Depends(get_db)):
        return _create_tag(db, body)

    @router.get("/tag/detail")
    def tag_detail(db: Session = Depends(get_db)):
        return [{**t, "indexerIds": [], "delayProfileIds": [], "notificationIds": [], "restrictionIds": [],
                 "importListIds": []} for t in _tags(db)]

    @router.get("/diskspace")
    def diskspace(db: Session = Depends(get_db)):
        import shutil
        out = []
        for rf in db.query(RootFolder).all():
            try:
                u = shutil.disk_usage(rf.path)
                out.append({"path": rf.path, "label": os.path.basename(rf.path), "freeSpace": u.free, "totalSpace": u.total})
            except OSError:
                pass
        return out

    @router.get("/queue")
    def queue(request: Request, db: Session = Depends(get_db)):
        detail = request.query_params.get("includeMovie", request.query_params.get("includeEpisode", "false")).lower() == "true"
        return _paged(_queue_records(db, flavor, detail), request)

    @router.get("/queue/details")
    def queue_details(db: Session = Depends(get_db)):
        return _queue_records(db, flavor, True)

    @router.get("/queue/status")
    def queue_status(db: Session = Depends(get_db)):
        recs = _queue_records(db, flavor, False)
        warn = sum(1 for r in recs if r["trackedDownloadStatus"] == "warning")
        return {"totalCount": len(recs), "count": len(recs), "unknownCount": 0, "errors": False, "warnings": warn > 0,
                "unknownErrors": False, "unknownWarnings": False}

    @router.get("/command/{cid}")
    def command_status(cid: int):
        c = commands.get(cid)
        if not c:
            raise HTTPException(404, "not found")
        return _cmd_resource(c, c["name"])

    # ---- indexers (Prowlarr application sync)
    @router.get("/indexer")
    def indexers(db: Session = Depends(get_db)):
        key = "tv_categories" if flavor == "sonarr" else "movie_categories"
        return [indexer_resource(i, flavor) for i in db.query(Indexer).all()
                if getattr(i, key) or (i.sync_source or {}).get(flavor)]

    @router.get("/indexer/schema")
    def indexer_schema():
        return _schema(flavor)

    @router.get("/indexer/{iid}")
    def indexer(iid: int, db: Session = Depends(get_db)):
        i = db.get(Indexer, iid)
        if not i:
            raise HTTPException(404, "not found")
        return indexer_resource(i, flavor)

    @router.post("/indexer", status_code=201)
    def create_indexer(body: dict, db: Session = Depends(get_db)):
        return indexer_resource(_apply_indexer(db, flavor, body), flavor)

    @router.put("/indexer/{iid}", status_code=202)
    def update_indexer(iid: int, body: dict, db: Session = Depends(get_db)):
        i = db.get(Indexer, iid)
        if not i:
            raise HTTPException(404, "not found")
        return indexer_resource(_apply_indexer(db, flavor, body, i), flavor)

    @router.delete("/indexer/{iid}")
    def delete_indexer(iid: int, db: Session = Depends(get_db)):
        i = db.get(Indexer, iid)
        if not i:
            return {}
        if flavor == "sonarr":
            i.tv_categories, i.anime_categories = [], []
        else:
            i.movie_categories = []
        src = {**(i.sync_source or {})}
        src.pop(flavor, None)
        i.sync_source = src
        if not i.tv_categories and not i.movie_categories and not i.anime_categories:
            db.delete(i)
        return {}

    @router.post("/indexer/test")
    def test_indexer(body: dict, db: Session = Depends(get_db)):
        f = {x.get("name"): x.get("value") for x in body.get("fields") or []}
        tmp = Indexer(name="test", url=f.get("baseUrl") or "", api_path=f.get("apiPath") or "/api",
                      api_key=f.get("apiKey") or "", kind="torznab" if body.get("implementation") == "Torznab" else "newznab")
        db.add(tmp)
        db.flush()
        try:
            newznab.caps(db, tmp, manual=True)
        except Exception as e:
            return JSONResponse([{"propertyName": "BaseUrl", "errorMessage": f"Unable to connect to indexer: {e}",
                                  "severity": "error"}], status_code=400)
        finally:
            db.delete(tmp)
            db.flush()
        return {}

    @router.post("/indexer/testall")
    def test_all():
        return []

    @router.get("/downloadclient")
    def download_clients(db: Session = Depends(get_db)):
        return [{"id": c.id, "name": c.name, "enable": c.enabled, "protocol": c.protocol, "priority": c.priority,
                 "implementation": c.kind, "fields": [], "tags": []} for c in db.query(DownloadClient).all()]


# ========================================================================================= radarr
def movie_resource(db: Session, m: Movie, lookup_meta: dict | None = None) -> dict:
    f: MediaFile | None = m.file if m and m.id else None
    status = {"in_cinemas": "inCinemas"}.get(m.status, m.status) if m else "announced"
    res = {
        "id": m.id or 0, "title": m.title, "originalTitle": m.original_title or m.title,
        "originalLanguage": {"id": 0, "name": m.original_language or ""},
        "alternateTitles": [{"title": t, "sourceType": "tmdb"} for t in (m.alt_titles or [])[:20]],
        "sortTitle": m.sort_title or (m.title or "").lower(), "sizeOnDisk": f.size if f else 0, "status": status,
        "overview": m.overview, "inCinemas": iso(m.in_cinemas), "physicalRelease": iso(m.physical_release),
        "digitalRelease": iso(m.digital_release), "images": _images(m.images), "website": "", "year": m.year or 0,
        "hasFile": bool(f), "youTubeTrailerId": "", "studio": m.studio or "", "path": m.path,
        "qualityProfileId": m.quality_profile_id or 0, "monitored": bool(m.monitored),
        "minimumAvailability": {"in_cinemas": "inCinemas"}.get(m.minimum_availability, m.minimum_availability or "released"),
        "isAvailable": m.status == "released", "folderName": m.path, "runtime": m.runtime or 0,
        "cleanTitle": re.sub(r"[^a-z0-9]", "", (m.title or "").lower()), "imdbId": m.imdb_id, "tmdbId": m.tmdb_id or 0,
        "titleSlug": str(m.tmdb_id or _slug(m.title, m.year)), "rootFolderPath": m.root_folder,
        "certification": m.certification, "genres": m.genres or [], "tags": m.tags or [], "added": iso(m.added),
        "ratings": {k: {"votes": v.get("votes") or 0, "value": v.get("value") or 0, "type": "user"}
                    for k, v in (m.ratings or {}).items() if isinstance(v, dict)},
        "collection": {"title": m.collection} if m.collection else None, "popularity": 0,
        "statistics": {"movieFileCount": 1 if f else 0, "sizeOnDisk": f.size if f else 0, "releaseGroups": []},
    }
    if f:
        res["movieFile"] = {"id": f.id, "movieId": m.id, "relativePath": os.path.relpath(f.path, m.path) if m.path else f.path,
                            "path": f.path, "size": f.size, "dateAdded": iso(f.added), "quality": _quality(f.quality, f.proper),
                            "languages": _languages(f.languages), "releaseGroup": f.release_group, "edition": f.edition or "",
                            "mediaInfo": {"videoCodec": (f.media_info or {}).get("codec"),
                                          "videoDynamicRangeType": " ".join((f.media_info or {}).get("hdr") or [])}}
        res["movieFileId"] = f.id
    return res


def _meta_to_movie(meta: dict) -> Movie:
    m = Movie(id=None, title=meta.get("title") or "", monitored=False, tags=[], minimum_availability="released",
              root_folder="", path="")
    library.apply_movie_meta(m, meta)
    return m


def _register_radarr(router: APIRouter) -> None:
    @router.get("/movie")
    def movies(tmdbId: Optional[int] = None, imdbId: Optional[str] = None, db: Session = Depends(get_db)):
        q = db.query(Movie)
        if tmdbId:
            q = q.filter(Movie.tmdb_id == tmdbId)
        if imdbId:
            q = q.filter(Movie.imdb_id == imdbId)
        return [movie_resource(db, m) for m in q.all()]

    @router.get("/movie/lookup")
    def lookup(term: str, db: Session = Depends(get_db)):
        mgr = MetadataManager.from_db(db)
        out = []
        for meta in mgr.search_movies(term)[:20]:
            ids = meta.get("ids") or {}
            existing = None
            if ids.get("tmdb"):
                existing = db.query(Movie).filter(Movie.tmdb_id == ids["tmdb"]).first()
            if not existing and ids.get("imdb"):
                existing = db.query(Movie).filter(Movie.imdb_id == ids["imdb"]).first()
            if existing:
                out.append(movie_resource(db, existing))
            elif ids.get("tmdb") or ids.get("imdb"):
                r = movie_resource(db, _meta_to_movie(meta))
                r.pop("id", None)
                out.append(r)
        return out

    @router.get("/movie/lookup/tmdb")
    def lookup_tmdb(tmdbId: int, db: Session = Depends(get_db)):
        res = lookup(f"tmdb:{tmdbId}", db)
        if not res:
            raise HTTPException(404, "not found")
        return res[0]

    @router.get("/movie/lookup/imdb")
    def lookup_imdb(imdbId: str, db: Session = Depends(get_db)):
        res = lookup(f"imdb:{imdbId}", db)
        if not res:
            raise HTTPException(404, "not found")
        return res[0]

    @router.get("/movie/{mid}")
    def movie(mid: int, db: Session = Depends(get_db)):
        m = db.get(Movie, mid)
        if not m:
            raise HTTPException(404, "not found")
        return movie_resource(db, m)

    @router.post("/movie", status_code=201)
    def add(body: dict, db: Session = Depends(get_db)):
        ids = {"tmdb": body.get("tmdbId"), "imdb": body.get("imdbId")}
        existing = db.query(Movie).filter(Movie.tmdb_id == body.get("tmdbId")).first() if body.get("tmdbId") else None
        if existing:
            return JSONResponse([{"propertyName": "TmdbId", "errorMessage": "This movie has already been added",
                                  "errorCode": "MovieExistsValidator"}], status_code=400)
        avail = {"inCinemas": "in_cinemas", "preDB": "released", "tba": "announced"}.get(body.get("minimumAvailability"),
                                                                                       body.get("minimumAvailability") or "released")
        try:
            m = library.add_movie(db, ids, int(body.get("qualityProfileId") or 1),
                                  _resolve_root(db, body.get("rootFolderPath"), "movie"),
                                  monitored=body.get("monitored", True), minimum_availability=avail,
                                  tags=body.get("tags") or [], path=body.get("path") or None)
        except library.LibraryError as e:
            raise HTTPException(400, str(e))
        db.commit()
        maintenance.scan_movie(db, m)
        if (body.get("addOptions") or {}).get("searchForMovie") and m.monitored and not m.file_id:
            commands.enqueue("movie_search", {"movie_id": m.id})
        return movie_resource(db, m)

    def _update(db: Session, m: Movie, body: dict) -> dict:
        for src, dst in (("monitored", "monitored"), ("qualityProfileId", "quality_profile_id"), ("tags", "tags")):
            if src in body:
                setattr(m, dst, body[src])
        if body.get("minimumAvailability"):
            m.minimum_availability = {"inCinemas": "in_cinemas"}.get(body["minimumAvailability"], body["minimumAvailability"])
        if body.get("path"):
            m.path = body["path"]
        if (body.get("addOptions") or {}).get("searchForMovie") and m.monitored and not m.file_id:
            commands.enqueue("movie_search", {"movie_id": m.id})
        return movie_resource(db, m)

    @router.put("/movie/editor", status_code=202)
    def editor(body: dict, db: Session = Depends(get_db)):
        for m in db.query(Movie).filter(Movie.id.in_(body.get("movieIds") or [])).all():
            _update(db, m, body)
        return {}

    @router.put("/movie/{mid}", status_code=202)
    def update(mid: int, body: dict, db: Session = Depends(get_db)):
        m = db.get(Movie, mid)
        if not m:
            raise HTTPException(404, "not found")
        return _update(db, m, body)

    @router.put("/movie", status_code=202)
    def update_body(body: dict, db: Session = Depends(get_db)):
        m = db.get(Movie, int(body.get("id") or 0))
        if not m:
            raise HTTPException(404, "not found")
        return _update(db, m, body)

    @router.delete("/movie/{mid}")
    def delete(mid: int, deleteFiles: bool = False, db: Session = Depends(get_db)):
        m = db.get(Movie, mid)
        if m:
            library.delete_movie(db, m, deleteFiles)
        return {}

    @router.get("/moviefile")
    def movie_files(movieId: Optional[int] = None, db: Session = Depends(get_db)):
        q = db.query(Movie).filter(Movie.file_id.isnot(None))
        if movieId:
            q = q.filter(Movie.id == movieId)
        return [movie_resource(db, m)["movieFile"] for m in q.all()]

    @router.get("/calendar")
    def calendar(start: Optional[str] = None, end: Optional[str] = None, unmonitored: bool = False,
                 db: Session = Depends(get_db)):
        s = datetime.fromisoformat(start[:19]) if start else utcnow() - timedelta(days=1)
        e = datetime.fromisoformat(end[:19]) if end else utcnow() + timedelta(days=30)
        out = []
        for m in db.query(Movie).all():
            if not unmonitored and not m.monitored:
                continue
            if any(d and s <= d < e for d in (m.in_cinemas, m.digital_release, m.physical_release)):
                out.append(movie_resource(db, m))
        return out

    @router.get("/wanted/missing")
    def missing(request: Request, db: Session = Depends(get_db)):
        recs = [movie_resource(db, m) for m in db.query(Movie).filter(Movie.monitored.is_(True), Movie.file_id.is_(None)).all()]
        return _paged(recs, request)

    @router.post("/command", status_code=201)
    def command(body: dict):
        name = body.get("name", "")
        if name in ("MoviesSearch", "MovieSearch"):
            cmd = commands.enqueue("movies_search", {"movie_ids": body.get("movieIds") or [body.get("movieId")]})
        elif name in ("RefreshMovie",):
            ids = body.get("movieIds") or ([body["movieId"]] if body.get("movieId") else [])
            cmd = commands.enqueue("refresh_movie", {"movie_id": ids[0]}) if ids else commands.enqueue("refresh_all")
        elif name == "RssSync":
            cmd = commands.enqueue("rss_sync")
        elif name in ("MissingMoviesSearch", "CutOffUnmetMoviesSearch"):
            cmd = commands.enqueue("wanted_search" if name.startswith("Missing") else "cutoff_search")
        elif name in ("DownloadedMoviesScan", "RescanMovie"):
            cmd = commands.enqueue("disk_scan_all")
        else:
            cmd = commands.enqueue("health_check")
        return _cmd_resource(cmd, name)


# ========================================================================================= sonarr
def episode_resource(e: Episode) -> dict:
    return {"id": e.id, "seriesId": e.series_id, "tvdbId": 0, "episodeFileId": e.file_id or 0,
            "seasonNumber": e.season, "episodeNumber": e.number, "title": e.title, "airDate": e.air_date,
            "airDateUtc": iso(e.air_date_utc), "overview": e.overview, "hasFile": e.has_file, "monitored": e.monitored,
            "absoluteEpisodeNumber": e.absolute_number, "unverifiedSceneNumbering": False, "runtime": e.runtime or 0}


def series_resource(db: Session, s: Series, stats: dict | None = None) -> dict:
    stats = stats if stats is not None else (library.series_stats(db, [s.id]).get(s.id, {}) if s.id else {})
    per: dict[int, dict] = {}
    for e in s.episodes:
        p = per.setdefault(e.season, {"episodeFileCount": 0, "episodeCount": 0, "totalEpisodeCount": 0, "sizeOnDisk": 0})
        p["totalEpisodeCount"] += 1
        if e.monitored or e.file_id:
            p["episodeCount"] += 1
        if e.file_id:
            p["episodeFileCount"] += 1
    seasons = []
    for se in s.seasons:
        st = per.get(se.number, {"episodeFileCount": 0, "episodeCount": 0, "totalEpisodeCount": 0, "sizeOnDisk": 0})
        st["percentOfEpisodes"] = round(100.0 * st["episodeFileCount"] / st["episodeCount"], 1) if st["episodeCount"] else 0
        seasons.append({"seasonNumber": se.number, "monitored": se.monitored, "statistics": st})
    total = stats.get("episode_count", 0)
    files = stats.get("episode_file_count", 0)
    return {
        "id": s.id or 0, "title": s.title, "alternateTitles": [{"title": t, "seasonNumber": -1} for t in (s.alt_titles or [])[:20]],
        "sortTitle": s.sort_title or (s.title or "").lower(), "status": s.status, "ended": s.status == "ended",
        "overview": s.overview, "network": s.network, "airTime": s.air_time, "images": _images(s.images),
        "originalLanguage": {"id": 0, "name": s.original_language or ""}, "seasons": seasons, "year": s.year or 0,
        "path": s.path, "qualityProfileId": s.quality_profile_id or 0, "languageProfileId": 1,
        "seasonFolder": s.season_folder, "monitored": bool(s.monitored),
        "monitorNewItems": "all" if s.monitor_new_seasons else "none", "useSceneNumbering": False,
        "runtime": s.runtime or 0, "tvdbId": s.tvdb_id or 0, "tvRageId": 0, "tvMazeId": s.tvmaze_id or 0,
        "tmdbId": s.tmdb_id or 0, "firstAired": None, "seriesType": s.series_type or "standard",
        "cleanTitle": re.sub(r"[^a-z0-9]", "", (s.title or "").lower()), "imdbId": s.imdb_id,
        "titleSlug": _slug(s.title, s.tvdb_id or s.tmdb_id), "rootFolderPath": s.root_folder,
        "certification": s.certification, "genres": s.genres or [], "tags": s.tags or [], "added": iso(s.added),
        "ratings": {"votes": 0, "value": next((v.get("value") or 0 for v in (s.ratings or {}).values() if isinstance(v, dict)), 0)},
        "statistics": {"seasonCount": len([x for x in s.seasons if x.number > 0]), "episodeFileCount": files,
                       "episodeCount": stats.get("monitored_aired", total), "totalEpisodeCount": total,
                       "sizeOnDisk": stats.get("size_on_disk", 0),
                       "percentOfEpisodes": round(100.0 * stats.get("monitored_have", 0) / stats["monitored_aired"], 1)
                       if stats.get("monitored_aired") else 0},
    }


def _meta_to_series(meta: dict) -> Series:
    s = Series(id=None, title=meta.get("title") or "", monitored=False, tags=[], root_folder="", path="",
               series_type="anime" if meta.get("is_anime") else "standard", season_folder=True,
               monitor_new_seasons=True)
    library.apply_series_meta(None, s, meta)
    if not s.seasons:
        from ..models import Season
        for se in meta.get("seasons") or []:
            s.seasons.append(Season(number=se["number"], monitored=False))
    return s


def _apply_seasons(s: Series, seasons: list[dict]) -> None:
    flags = {int(x["seasonNumber"]): bool(x.get("monitored")) for x in seasons or [] if "seasonNumber" in x}
    for se in s.seasons:
        if se.number in flags:
            changed = se.monitored != flags[se.number]
            se.monitored = flags[se.number]
            if changed or se.monitored:
                for e in s.episodes:
                    if e.season == se.number:
                        e.monitored = se.monitored


def _register_sonarr(router: APIRouter) -> None:
    @router.get("/languageprofile")
    def language_profiles():
        return [{"id": 1, "name": "Deutsch / Englisch", "upgradeAllowed": True, "cutoff": {"id": 4, "name": "German"},
                 "languages": [{"language": {"id": 4, "name": "German"}, "allowed": True},
                               {"language": {"id": 1, "name": "English"}, "allowed": True}]}]

    @router.get("/series")
    def series_list(tvdbId: Optional[int] = None, db: Session = Depends(get_db)):
        q = db.query(Series)
        if tvdbId:
            q = q.filter(Series.tvdb_id == tvdbId)
        rows = q.all()
        stats = library.series_stats(db, [s.id for s in rows]) if rows else {}
        return [series_resource(db, s, stats.get(s.id, {})) for s in rows]

    @router.get("/series/lookup")
    def lookup(term: str, db: Session = Depends(get_db)):
        mgr = MetadataManager.from_db(db)
        m = re.match(r"^\s*tvdb:(\d+)\s*$", term)
        if m:
            existing = db.query(Series).filter(Series.tvdb_id == int(m.group(1))).first()
            if existing:
                return [series_resource(db, existing)]
        out = []
        for meta in mgr.search_series(term)[:20]:
            ids = meta.get("ids") or {}
            existing = None
            for key, col in (("tvdb", Series.tvdb_id), ("tmdb", Series.tmdb_id), ("tvmaze", Series.tvmaze_id)):
                if ids.get(key) and not existing:
                    existing = db.query(Series).filter(col == int(ids[key])).first()
            if existing:
                out.append(series_resource(db, existing))
                continue
            if not ids.get("tvdb") and m:
                ids["tvdb"] = int(m.group(1))
            full = meta if meta.get("seasons") else (mgr.get_series(ids, with_episodes=False) or meta)
            r = series_resource(db, _meta_to_series(full), {})
            r.pop("id", None)
            out.append(r)
        return out

    @router.get("/series/{sid}")
    def series(sid: int, db: Session = Depends(get_db)):
        s = db.get(Series, sid)
        if not s:
            raise HTTPException(404, "not found")
        return series_resource(db, s)

    @router.post("/series", status_code=201)
    def add(body: dict, db: Session = Depends(get_db)):
        if body.get("tvdbId") and db.query(Series).filter(Series.tvdb_id == body["tvdbId"]).first():
            return JSONResponse([{"propertyName": "TvdbId", "errorMessage": "This series has already been added",
                                  "errorCode": "SeriesExistsValidator"}], status_code=400)
        opts = body.get("addOptions") or {}
        monitor = {"all": "all", "future": "future", "missing": "missing", "existing": "existing",
                   "firstSeason": "first_season", "latestSeason": "latest_season", "pilot": "pilot",
                   "none": "none"}.get(opts.get("monitor") or "", "all")
        seasons = {int(x["seasonNumber"]): bool(x.get("monitored")) for x in body.get("seasons") or []
                   if "seasonNumber" in x} if not opts.get("monitor") else None
        try:
            s = library.add_series(db, {"tvdb": body.get("tvdbId"), "tmdb": body.get("tmdbId"),
                                        "tvmaze": body.get("tvMazeId"), "imdb": body.get("imdbId")},
                                   int(body.get("qualityProfileId") or 1),
                                   _resolve_root(db, body.get("rootFolderPath"), "series"),
                                   monitored=body.get("monitored", True), monitor=monitor,
                                   series_type=body.get("seriesType") or "standard",
                                   season_folder=body.get("seasonFolder", True), tags=body.get("tags") or [],
                                   path=body.get("path") or None, season_monitoring=seasons)
        except library.LibraryError as e:
            raise HTTPException(400, str(e))
        db.commit()
        maintenance.scan_series(db, s)
        if opts.get("searchForMissingEpisodes") and s.monitored:
            commands.enqueue("series_search", {"series_id": s.id})
        return series_resource(db, s)

    def _update(db: Session, s: Series, body: dict) -> dict:
        for src, dst in (("monitored", "monitored"), ("qualityProfileId", "quality_profile_id"), ("tags", "tags"),
                         ("seasonFolder", "season_folder"), ("seriesType", "series_type")):
            if src in body:
                setattr(s, dst, body[src])
        if body.get("path"):
            s.path = body["path"]
        if "seasons" in body:
            _apply_seasons(s, body["seasons"])
        if (body.get("addOptions") or {}).get("searchForMissingEpisodes"):
            commands.enqueue("series_search", {"series_id": s.id})
        db.flush()
        return series_resource(db, s)

    @router.put("/series/{sid}", status_code=202)
    def update(sid: int, body: dict, db: Session = Depends(get_db)):
        s = db.get(Series, sid)
        if not s:
            raise HTTPException(404, "not found")
        return _update(db, s, body)

    @router.put("/series", status_code=202)
    def update_body(body: dict, db: Session = Depends(get_db)):
        s = db.get(Series, int(body.get("id") or 0))
        if not s:
            raise HTTPException(404, "not found")
        return _update(db, s, body)

    @router.delete("/series/{sid}")
    def delete(sid: int, deleteFiles: bool = False, db: Session = Depends(get_db)):
        s = db.get(Series, sid)
        if s:
            library.delete_series(db, s, deleteFiles)
        return {}

    @router.get("/episode")
    def episodes(seriesId: Optional[int] = None, seasonNumber: Optional[int] = None, db: Session = Depends(get_db)):
        q = db.query(Episode)
        if seriesId:
            q = q.filter(Episode.series_id == seriesId)
        if seasonNumber is not None:
            q = q.filter(Episode.season == seasonNumber)
        return [episode_resource(e) for e in q.order_by(Episode.season, Episode.number).all()]

    @router.get("/episode/{eid}")
    def episode(eid: int, db: Session = Depends(get_db)):
        e = db.get(Episode, eid)
        if not e:
            raise HTTPException(404, "not found")
        return episode_resource(e)

    @router.put("/episode/monitor", status_code=202)
    def monitor(body: dict, db: Session = Depends(get_db)):
        for e in db.query(Episode).filter(Episode.id.in_(body.get("episodeIds") or [])).all():
            e.monitored = bool(body.get("monitored"))
        return []

    @router.get("/episodefile")
    def episode_files(seriesId: int, db: Session = Depends(get_db)):
        out = []
        for f in db.query(MediaFile).filter(MediaFile.series_id == seriesId).all():
            s = db.get(Series, seriesId)
            out.append({"id": f.id, "seriesId": seriesId, "seasonNumber": 0, "relativePath": os.path.relpath(f.path, s.path) if s else f.path,
                        "path": f.path, "size": f.size, "dateAdded": iso(f.added), "quality": _quality(f.quality, f.proper),
                        "languages": _languages(f.languages), "releaseGroup": f.release_group})
        return out

    @router.get("/calendar")
    def calendar(start: Optional[str] = None, end: Optional[str] = None, unmonitored: bool = False,
                 includeSeries: bool = False, db: Session = Depends(get_db)):
        s = datetime.fromisoformat(start[:19]) if start else utcnow() - timedelta(days=1)
        e = datetime.fromisoformat(end[:19]) if end else utcnow() + timedelta(days=7)
        q = db.query(Episode).filter(Episode.air_date_utc >= s, Episode.air_date_utc < e)
        if not unmonitored:
            q = q.filter(Episode.monitored.is_(True))
        out = []
        cache: dict[int, dict] = {}
        for ep in q.order_by(Episode.air_date_utc).all():
            r = episode_resource(ep)
            if includeSeries:
                if ep.series_id not in cache:
                    cache[ep.series_id] = series_resource(db, db.get(Series, ep.series_id))
                r["series"] = cache[ep.series_id]
            out.append(r)
        return out

    @router.get("/wanted/missing")
    def missing(request: Request, db: Session = Depends(get_db)):
        now = utcnow()
        eps = db.query(Episode).join(Series, Series.id == Episode.series_id).filter(
            Episode.monitored.is_(True), Series.monitored.is_(True), Episode.file_id.is_(None), Episode.season > 0,
            Episode.air_date_utc <= now).order_by(Episode.air_date_utc.desc()).all()
        recs = []
        include = request.query_params.get("includeSeries", "false").lower() == "true"
        for ep in eps:
            r = episode_resource(ep)
            if include:
                r["series"] = {"id": ep.series_id, "title": ep.series.title}
            recs.append(r)
        return _paged(recs, request)

    @router.post("/command", status_code=201)
    def command(body: dict, db: Session = Depends(get_db)):
        name = body.get("name", "")
        if name == "SeriesSearch":
            cmd = commands.enqueue("series_search", {"series_id": body.get("seriesId")})
        elif name == "SeasonSearch":
            cmd = commands.enqueue("season_search", {"series_id": body.get("seriesId"), "season": body.get("seasonNumber")})
        elif name == "EpisodeSearch":
            ids = body.get("episodeIds") or []
            sid = db.query(Episode.series_id).filter(Episode.id.in_(ids)).first() if ids else None
            cmd = commands.enqueue("episode_search", {"series_id": sid[0] if sid else 0, "episode_ids": ids})
        elif name == "RefreshSeries":
            cmd = commands.enqueue("refresh_series", {"series_id": body["seriesId"]}) if body.get("seriesId") \
                else commands.enqueue("refresh_all")
        elif name == "RssSync":
            cmd = commands.enqueue("rss_sync")
        elif name in ("MissingEpisodeSearch", "CutoffUnmetEpisodeSearch"):
            cmd = commands.enqueue("wanted_search" if name.startswith("Missing") else "cutoff_search")
        elif name in ("RescanSeries", "DownloadedEpisodesScan"):
            cmd = commands.enqueue("disk_scan_all")
        else:
            cmd = commands.enqueue("health_check")
        return _cmd_resource(cmd, name)


_register_common(sonarr_router, "sonarr")
_register_common(radarr_router, "radarr")
_register_radarr(radarr_router)
_register_sonarr(sonarr_router)
