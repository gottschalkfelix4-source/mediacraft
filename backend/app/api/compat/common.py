"""Endpoints both flavors share (status, profiles, root folders, tags, queue, indexers, …)."""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ... import config
from ...core import qualities
from ...core.scheduler import commands
from ...db import get_db
from ...indexers import newznab
from ...metadata.manager import MetadataManager
from ...models import (DownloadClient, Episode, Indexer, MediaFile, Movie, QualityProfile, QueueItem, RootFolder,
                      Series, Tag, iso, utcnow)
from ...services import library, maintenance
from ...services.commands import health_cache
from ..deps import require_api_key
from .base import (_cmd_resource, _status, _root_folders, _profiles, _tags, _create_tag, _health, _paged, _schema, indexer_resource, _apply_indexer)  # noqa: F401
from .resources import (_queue_records)  # noqa: F401


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
