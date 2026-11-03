"""Sonarr/Radarr v3 resource shapes (movie, series, episode, queue)."""
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
from .base import (_images, _quality, _languages, _slug)  # noqa: F401


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
        from .arrconfig import movie_file_resource

        res["movieFile"] = movie_file_resource(f, m)
        res["movieFileId"] = f.id
    return res


def _meta_to_movie(meta: dict) -> Movie:
    m = Movie(id=None, title=meta.get("title") or "", monitored=False, tags=[], minimum_availability="released",
              root_folder="", path="")
    library.apply_movie_meta(m, meta)
    return m



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
