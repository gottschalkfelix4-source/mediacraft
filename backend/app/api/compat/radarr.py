"""Radarr-only endpoints (movies, movie files, calendar, commands)."""
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
from .base import (_cmd_resource, _resolve_root, _paged)  # noqa: F401
from .resources import (movie_resource, _meta_to_movie)  # noqa: F401


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
        from .arrconfig import movie_file_resource

        q = db.query(Movie).filter(Movie.file_id.isnot(None))
        if movieId:
            q = q.filter(Movie.id == movieId)
        return [movie_file_resource(m.file, m) for m in q.all()]

    @router.get("/moviefile/{fid}")
    def movie_file(fid: int, db: Session = Depends(get_db)):
        from .arrconfig import movie_file_resource

        m = db.query(Movie).filter(Movie.file_id == fid).first()
        if not m or not m.file:
            raise HTTPException(404, "not found")
        return movie_file_resource(m.file, m)

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
        elif name == "RescanMovie" and (body.get("movieId") or body.get("movieIds")):
            mid = body.get("movieId") or (body.get("movieIds") or [None])[0]
            cmd = commands.enqueue("rescan_movie", {"movie_id": mid})
        elif name in ("DownloadedMoviesScan", "RescanMovie"):
            cmd = commands.enqueue("disk_scan_all")
        else:
            cmd = commands.enqueue("health_check")
        return _cmd_resource(cmd, name)


# ========================================================================================= sonarr
