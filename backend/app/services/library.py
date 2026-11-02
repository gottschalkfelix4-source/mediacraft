"""Library management: add / refresh / delete movies and series, serialization."""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from ..core import naming
from ..core import settings as settings_mod
from ..core.events import publish
from ..metadata.manager import MetadataManager
from ..models import Episode, MediaFile, Movie, QualityProfile, Season, Series, iso, utcnow

log = logging.getLogger("library")


class LibraryError(Exception):
    pass


def _dt(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "")[:19])
    except ValueError:
        return None


def _sort_title(t: str) -> str:
    return naming.title_the(t or "").lower()


# ====================================================================================== movies
def apply_movie_meta(movie: Movie, meta: dict) -> None:
    ids = meta.get("ids") or {}
    movie.tmdb_id = ids.get("tmdb") or movie.tmdb_id
    movie.imdb_id = ids.get("imdb") or movie.imdb_id
    movie.anilist_id = ids.get("anilist") or movie.anilist_id
    movie.title = meta.get("title") or movie.title
    movie.original_title = meta.get("original_title")
    movie.sort_title = _sort_title(movie.title)
    movie.alt_titles = meta.get("alt_titles") or []
    movie.year = meta.get("year") or movie.year
    movie.overview = meta.get("overview")
    movie.runtime = meta.get("runtime") or movie.runtime
    movie.in_cinemas = _dt(meta.get("in_cinemas"))
    movie.digital_release = _dt(meta.get("digital_release"))
    movie.physical_release = _dt(meta.get("physical_release"))
    now = utcnow()
    released = [d for d in (movie.digital_release, movie.physical_release) if d and d <= now]
    if released or meta.get("status") == "released" and not (movie.in_cinemas and movie.in_cinemas > now - timedelta(days=90)):
        movie.status = "released"
    elif movie.in_cinemas and movie.in_cinemas <= now:
        movie.status = "in_cinemas"
    else:
        movie.status = "announced"
    movie.genres = meta.get("genres") or []
    movie.images = meta.get("images") or {}
    movie.ratings = meta.get("ratings") or {}
    movie.certification = meta.get("certification")
    movie.studio = meta.get("studio")
    movie.collection = meta.get("collection")
    movie.original_language = meta.get("original_language")
    movie.metadata_sources = meta.get("metadata_sources") or [meta.get("provider")]
    movie.last_refresh = utcnow()


def movie_folder(db: Session, movie: Movie) -> str:
    cfg = settings_mod.get(db, "media")
    return naming.render(cfg["movie_folder"], naming.movie_values(movie), cfg["colon_replacement"])


def add_movie(db: Session, ids: dict, quality_profile_id: int, root_folder: str, *, monitored: bool = True,
              minimum_availability: str = "released", tags: list[int] | None = None, path: str | None = None,
              meta: dict | None = None) -> Movie:
    if not db.get(QualityProfile, quality_profile_id):
        raise LibraryError("Qualitätsprofil existiert nicht")
    meta = meta or MetadataManager.from_db(db).get_movie(ids)
    if not meta:
        raise LibraryError("Film bei keinem Metadaten-Provider gefunden")
    mids = meta.get("ids") or {}
    for key, col in (("tmdb", Movie.tmdb_id), ("imdb", Movie.imdb_id), ("anilist", Movie.anilist_id)):
        if mids.get(key):
            existing = db.query(Movie).filter(col == mids[key]).first()
            if existing:
                raise LibraryError(f"'{existing.title}' ist bereits in der Bibliothek")
    movie = Movie(quality_profile_id=quality_profile_id, root_folder=root_folder, monitored=monitored,
                  minimum_availability=minimum_availability, tags=tags or [], title=meta.get("title") or "?", path="")
    apply_movie_meta(movie, meta)
    movie.path = path or os.path.join(root_folder, movie_folder(db, movie))
    db.add(movie)
    db.flush()
    log.info("Film hinzugefügt: %s (%s)", movie.title, movie.year)
    publish("movie.added", {"id": movie.id})
    return movie


def refresh_movie(db: Session, movie: Movie, mgr: MetadataManager | None = None) -> None:
    mgr = mgr or MetadataManager.from_db(db)
    meta = mgr.get_movie({"tmdb": movie.tmdb_id, "imdb": movie.imdb_id, "anilist": movie.anilist_id})
    if meta:
        apply_movie_meta(movie, meta)
        publish("movie.updated", {"id": movie.id})


def delete_movie(db: Session, movie: Movie, delete_files: bool = False) -> None:
    if delete_files and movie.path and os.path.isdir(movie.path):
        shutil.rmtree(movie.path, ignore_errors=True)
    if movie.file_id:
        f = db.get(MediaFile, movie.file_id)
        movie.file_id = None
        db.flush()
        if f:
            db.delete(f)
    db.query(MediaFile).filter(MediaFile.movie_id == movie.id).delete()
    db.delete(movie)
    publish("movie.deleted", {"id": movie.id})


def movie_to_dict(m: Movie) -> dict:
    return {
        "id": m.id, "type": "movie", "tmdb_id": m.tmdb_id, "imdb_id": m.imdb_id, "anilist_id": m.anilist_id,
        "title": m.title, "original_title": m.original_title, "sort_title": m.sort_title, "alt_titles": m.alt_titles,
        "year": m.year, "overview": m.overview, "runtime": m.runtime, "status": m.status,
        "in_cinemas": iso(m.in_cinemas), "digital_release": iso(m.digital_release),
        "physical_release": iso(m.physical_release), "genres": m.genres, "images": m.images, "ratings": m.ratings,
        "certification": m.certification, "studio": m.studio, "collection": m.collection,
        "original_language": m.original_language, "metadata_sources": m.metadata_sources, "monitored": m.monitored,
        "minimum_availability": m.minimum_availability, "quality_profile_id": m.quality_profile_id,
        "root_folder": m.root_folder, "path": m.path, "tags": m.tags, "added": iso(m.added),
        "last_refresh": iso(m.last_refresh), "has_file": m.has_file, "file": m.file.to_dict() if m.file else None,
    }


# ====================================================================================== series
MONITOR_OPTIONS = ["all", "future", "missing", "existing", "first_season", "latest_season", "pilot", "none"]


def series_folder(db: Session, series: Series) -> str:
    cfg = settings_mod.get(db, "media")
    return naming.render(cfg["series_folder"], naming.series_values(series), cfg["colon_replacement"])


def apply_series_meta(db: Session, series: Series, meta: dict, initial: bool = False) -> dict:
    """Update series fields and synchronise seasons/episodes. Returns change stats."""
    ids = meta.get("ids") or {}
    for k in ("tvdb", "tmdb", "tvmaze", "imdb", "anilist"):
        if ids.get(k):
            setattr(series, f"{k}_id", ids[k] if k == "imdb" else int(ids[k]))
    series.title = meta.get("title") or series.title
    series.original_title = meta.get("original_title")
    series.sort_title = _sort_title(series.title)
    series.alt_titles = meta.get("alt_titles") or []
    series.year = meta.get("year") or series.year
    series.overview = meta.get("overview")
    series.runtime = meta.get("runtime") or series.runtime
    series.status = meta.get("status") or series.status
    series.network = meta.get("network")
    series.air_time = meta.get("air_time")
    series.genres = meta.get("genres") or []
    series.images = meta.get("images") or {}
    series.ratings = meta.get("ratings") or {}
    series.certification = meta.get("certification")
    series.original_language = meta.get("original_language")
    series.episode_source = meta.get("episode_source") or series.episode_source
    series.metadata_sources = meta.get("metadata_sources") or []
    series.last_refresh = utcnow()
    stats = {"added": 0, "updated": 0, "removed": 0}
    if not meta.get("episodes"):
        return stats

    seasons = {s.number: s for s in series.seasons}
    meta_seasons = {s["number"]: s for s in meta.get("seasons") or []}
    for e in meta["episodes"]:
        meta_seasons.setdefault(e["season"], {"number": e["season"], "images": {}})
    for n, ms in meta_seasons.items():
        if n not in seasons:
            mon = series.monitor_new_seasons and n > 0 if not initial else n > 0
            s = Season(number=n, monitored=mon, images=ms.get("images") or {})
            series.seasons.append(s)
            seasons[n] = s
        elif ms.get("images", {}).get("poster"):
            seasons[n].images = ms["images"]

    existing = {(e.season, e.number): e for e in series.episodes}
    seen = set()
    for me in meta["episodes"]:
        key = (me["season"], me["number"])
        if key in seen:
            continue
        seen.add(key)
        ep = existing.get(key)
        utc = _dt(me.get("air_date_utc"))
        if ep is None:
            season = seasons.get(me["season"])
            ep = Episode(season=me["season"], number=me["number"],
                         monitored=bool(series.monitored and season and season.monitored))
            series.episodes.append(ep)
            stats["added"] += 1
        else:
            stats["updated"] += 1
        ep.absolute_number = me.get("absolute")
        ep.title = me.get("title") or ep.title
        ep.overview = me.get("overview") or ep.overview
        ep.air_date = me.get("air_date")
        ep.air_date_utc = utc
        ep.runtime = me.get("runtime")
    for key, ep in existing.items():
        if key not in seen and not ep.file_id:
            series.episodes.remove(ep)
            stats["removed"] += 1
    return stats


def apply_monitoring(series: Series, option: str) -> None:
    now = utcnow()
    eps = list(series.episodes)
    regular = [e for e in eps if e.season > 0]
    seasons = sorted({e.season for e in regular})
    for e in eps:
        if option == "all":
            e.monitored = e.season > 0
        elif option == "future":
            e.monitored = e.season > 0 and not e.aired(now)
        elif option == "missing":
            e.monitored = e.season > 0 and not e.file_id
        elif option == "existing":
            e.monitored = bool(e.file_id)
        elif option == "first_season":
            e.monitored = bool(seasons) and e.season == seasons[0]
        elif option == "latest_season":
            e.monitored = bool(seasons) and e.season == seasons[-1]
        elif option == "pilot":
            e.monitored = e.season == (seasons[0] if seasons else 1) and e.number == 1
        elif option == "none":
            e.monitored = False
    for s in series.seasons:
        s.monitored = any(e.monitored for e in eps if e.season == s.number)
    if option in ("future", "all", "latest_season"):
        series.monitor_new_seasons = True
    elif option == "none":
        series.monitor_new_seasons = False


def add_series(db: Session, ids: dict, quality_profile_id: int, root_folder: str, *, monitored: bool = True,
               monitor: str = "all", series_type: str = "standard", season_folder: bool = True,
               tags: list[int] | None = None, path: str | None = None, episode_source: str = "",
               season_monitoring: dict[int, bool] | None = None) -> Series:
    if not db.get(QualityProfile, quality_profile_id):
        raise LibraryError("Qualitätsprofil existiert nicht")
    mgr = MetadataManager.from_db(db)
    meta = mgr.get_series(ids, with_episodes=True, anime=series_type == "anime", preferred_source=episode_source)
    if not meta:
        raise LibraryError("Serie bei keinem Metadaten-Provider gefunden")
    mids = meta.get("ids") or {}
    for key, col in (("tvdb", Series.tvdb_id), ("tmdb", Series.tmdb_id), ("tvmaze", Series.tvmaze_id),
                     ("anilist", Series.anilist_id)):
        if mids.get(key):
            ex = db.query(Series).filter(col == int(mids[key])).first()
            if ex:
                raise LibraryError(f"'{ex.title}' ist bereits in der Bibliothek")
    if series_type == "standard" and meta.get("is_anime"):
        series_type = "anime"
    series = Series(quality_profile_id=quality_profile_id, root_folder=root_folder, monitored=monitored,
                    series_type=series_type, season_folder=season_folder, tags=tags or [],
                    title=meta.get("title") or "?", path="")
    apply_series_meta(db, series, meta, initial=True)
    series.path = path or os.path.join(root_folder, series_folder(db, series))
    apply_monitoring(series, monitor)
    if season_monitoring:
        for s in series.seasons:
            if s.number in season_monitoring:
                s.monitored = bool(season_monitoring[s.number])
                for e in series.episodes:
                    if e.season == s.number:
                        e.monitored = s.monitored
    db.add(series)
    db.flush()
    log.info("Serie hinzugefügt: %s (%s) – %d Episoden via %s", series.title, series.year, len(series.episodes),
             series.episode_source)
    publish("series.added", {"id": series.id})
    return series


def refresh_series(db: Session, series: Series, mgr: MetadataManager | None = None) -> dict:
    mgr = mgr or MetadataManager.from_db(db)
    meta = mgr.get_series({"tvdb": series.tvdb_id, "tmdb": series.tmdb_id, "tvmaze": series.tvmaze_id,
                           "imdb": series.imdb_id, "anilist": series.anilist_id},
                          with_episodes=True, anime=series.series_type == "anime",
                          preferred_source=series.episode_source)
    if not meta:
        return {}
    stats = apply_series_meta(db, series, meta)
    publish("series.updated", {"id": series.id})
    return stats


def delete_series(db: Session, series: Series, delete_files: bool = False) -> None:
    if delete_files and series.path and os.path.isdir(series.path):
        shutil.rmtree(series.path, ignore_errors=True)
    for e in series.episodes:
        e.file_id = None
    db.flush()
    db.query(MediaFile).filter(MediaFile.series_id == series.id).delete()
    db.delete(series)
    publish("series.deleted", {"id": series.id})


def series_stats(db: Session, series_ids: list[int] | None = None) -> dict[int, dict]:
    now = utcnow()
    aired = and_(Episode.monitored.is_(True), Episode.air_date_utc <= now)
    q = db.query(Episode.series_id, func.count(Episode.id), func.count(Episode.file_id),
                 func.sum(case((aired, 1), else_=0)),
                 func.sum(case((and_(aired, Episode.file_id.isnot(None)), 1), else_=0)),
                 func.min(case((Episode.air_date_utc > now, Episode.air_date_utc), else_=None)),
                 func.max(case((Episode.air_date_utc <= now, Episode.air_date_utc), else_=None))) \
        .filter(Episode.season > 0).group_by(Episode.series_id)
    if series_ids:
        q = q.filter(Episode.series_id.in_(series_ids))
    sizes = dict(db.query(MediaFile.series_id, func.sum(MediaFile.size)).filter(MediaFile.series_id.isnot(None))
                 .group_by(MediaFile.series_id).all())
    out = {}
    for sid, total, files, mon_aired, mon_have, nxt, prev in q.all():
        out[sid] = {"episode_count": total, "episode_file_count": files, "monitored_aired": mon_aired or 0,
                    "monitored_have": mon_have or 0, "next_airing": _isos(nxt), "previous_airing": _isos(prev),
                    "size_on_disk": int(sizes.get(sid) or 0)}
    return out


def _isos(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        return v.replace(" ", "T")[:19] + "Z"
    return iso(v)


def series_to_dict(s: Series, stats: dict | None = None, with_seasons: bool = True) -> dict:
    d = {
        "id": s.id, "type": "series", "tvdb_id": s.tvdb_id, "tmdb_id": s.tmdb_id, "tvmaze_id": s.tvmaze_id,
        "imdb_id": s.imdb_id, "anilist_id": s.anilist_id, "title": s.title, "original_title": s.original_title,
        "sort_title": s.sort_title, "alt_titles": s.alt_titles, "year": s.year, "overview": s.overview,
        "runtime": s.runtime, "status": s.status, "network": s.network, "air_time": s.air_time, "genres": s.genres,
        "images": s.images, "ratings": s.ratings, "certification": s.certification,
        "original_language": s.original_language, "series_type": s.series_type, "episode_source": s.episode_source,
        "metadata_sources": s.metadata_sources, "monitored": s.monitored, "monitor_new_seasons": s.monitor_new_seasons,
        "season_folder": s.season_folder, "quality_profile_id": s.quality_profile_id, "root_folder": s.root_folder,
        "path": s.path, "tags": s.tags, "added": iso(s.added), "last_refresh": iso(s.last_refresh),
        "stats": stats or {},
    }
    if with_seasons:
        per = {}
        for e in s.episodes:
            p = per.setdefault(e.season, {"total": 0, "files": 0, "aired": 0, "monitored": 0})
            p["total"] += 1
            p["files"] += 1 if e.file_id else 0
            p["aired"] += 1 if e.aired() else 0
            p["monitored"] += 1 if e.monitored else 0
        d["seasons"] = [{"number": se.number, "monitored": se.monitored, "images": se.images,
                         "stats": per.get(se.number, {"total": 0, "files": 0, "aired": 0, "monitored": 0})}
                        for se in s.seasons]
    return d


def episode_to_dict(e: Episode, with_file: bool = True) -> dict:
    return {
        "id": e.id, "series_id": e.series_id, "season": e.season, "number": e.number,
        "absolute_number": e.absolute_number, "title": e.title, "overview": e.overview, "air_date": e.air_date,
        "air_date_utc": iso(e.air_date_utc), "runtime": e.runtime, "monitored": e.monitored, "has_file": e.has_file,
        "file_id": e.file_id, "file": e.file.to_dict() if with_file and e.file else None,
    }
