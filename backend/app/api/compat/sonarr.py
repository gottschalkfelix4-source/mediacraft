"""Sonarr-only endpoints (series, episodes, episode files, calendar, commands)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ...core.scheduler import commands
from ...db import get_db
from ...metadata.manager import MetadataManager
from ...models import (Episode, MediaFile, Series, utcnow)
from ...services import library, maintenance
from .base import (_cmd_resource, _resolve_root, _paged)
from .resources import (episode_resource, series_resource, _meta_to_series, _apply_seasons)


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
    def episodes(seriesId: Optional[int] = None, seasonNumber: Optional[int] = None, episodeIds: Optional[str] = None,
                 includeEpisodeFile: bool = False, db: Session = Depends(get_db)):
        from .arrconfig import episode_file_resource

        q = db.query(Episode)
        if seriesId:
            q = q.filter(Episode.series_id == seriesId)
        if seasonNumber is not None:
            q = q.filter(Episode.season == seasonNumber)
        if episodeIds:
            q = q.filter(Episode.id.in_([int(x) for x in episodeIds.split(",") if x.strip().isdigit()]))
        out = []
        for e in q.order_by(Episode.season, Episode.number).all():
            r = episode_resource(e)
            if includeEpisodeFile and e.file:
                r["episodeFile"] = episode_file_resource(db, e.file)
            out.append(r)
        return out

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
    def episode_files(seriesId: Optional[int] = None, episodeFileIds: Optional[str] = None,
                      db: Session = Depends(get_db)):
        from .arrconfig import episode_file_resource

        q = db.query(MediaFile).filter(MediaFile.media_type == "episode")
        if seriesId:
            q = q.filter(MediaFile.series_id == seriesId)
        if episodeFileIds:
            q = q.filter(MediaFile.id.in_([int(x) for x in episodeFileIds.split(",") if x.strip().isdigit()]))
        elif not seriesId:
            raise HTTPException(400, "seriesId oder episodeFileIds angeben")
        series = db.get(Series, seriesId) if seriesId else None
        return [episode_file_resource(db, f, series) for f in q.all()]

    @router.get("/episodefile/{fid}")
    def episode_file(fid: int, db: Session = Depends(get_db)):
        from .arrconfig import episode_file_resource

        f = db.get(MediaFile, fid)
        if not f or f.media_type != "episode":
            raise HTTPException(404, "not found")
        return episode_file_resource(db, f)

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
        elif name == "RescanSeries" and body.get("seriesId"):
            cmd = commands.enqueue("rescan_series", {"series_id": body["seriesId"]})
        elif name in ("RescanSeries", "DownloadedEpisodesScan"):
            cmd = commands.enqueue("disk_scan_all")
        else:
            cmd = commands.enqueue("health_check")
        return _cmd_resource(cmd, name)
