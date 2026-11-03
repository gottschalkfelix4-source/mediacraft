"""Sonarr / Radarr v3 compatible API subset.

Lets existing stack components talk to MediaCraft as if it were Sonarr (``/sonarr``) and
Radarr (``/radarr``): Jellyseerr/Overseerr (requests), Prowlarr (indexer sync), Homepage
widgets, LunaSea/nzb360 style dashboards. Only the resources those tools actually use are
implemented; field names follow the upstream v3 schema.


Shared helpers, the two routers and the indexer (Prowlarr) mapping."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ... import config
from ...core import qualities
from ...models import (Indexer, QualityProfile, RootFolder,
                      Tag, iso, utcnow)
from ...services.commands import health_cache
from ..deps import require_api_key


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


# language ids shared by Sonarr and Radarr
LANG_IDS = {"unknown": 0, "english": 1, "french": 2, "spanish": 3, "german": 4, "italian": 5, "danish": 6, "dutch": 7,
            "japanese": 8, "icelandic": 9, "chinese": 10, "russian": 11, "polish": 12, "vietnamese": 13, "swedish": 14,
            "norwegian": 15, "finnish": 16, "turkish": 17, "portuguese": 18, "flemish": 19, "greek": 20, "korean": 21,
            "hungarian": 22, "hebrew": 23, "lithuanian": 24, "czech": 25, "hindi": 26, "arabic": 27}


def _languages(langs: list[str]) -> list[dict]:
    return [{"id": LANG_IDS.get(lang, 0), "name": lang.capitalize()} for lang in (langs or []) if lang != "multi"]


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
    from ...models import CustomFormat

    formats = db.query(CustomFormat).order_by(CustomFormat.id).all()
    out = []
    for p in db.query(QualityProfile).order_by(QualityProfile.id).all():
        items = [{"quality": _quality(it["quality"])["quality"], "items": [], "allowed": it.get("allowed", False)}
                 for it in p.items]
        scores = p.format_scores or {}
        format_items = [{"format": cf.id, "name": cf.name, "score": int(scores.get(str(cf.id), 0) or 0)} for cf in formats]
        out.append({"id": p.id, "name": p.name, "upgradeAllowed": p.upgrade_allowed,
                    "cutoff": qualities.get(p.cutoff).rank, "items": items, "minFormatScore": p.min_format_score,
                    "cutoffFormatScore": p.cutoff_format_score, "formatItems": format_items,
                    "minUpgradeFormatScore": 1,
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
