"""Library resources: movies, series, episodes, lookup, releases, calendar, wanted, imports, activity."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...core import decision as dec
from ...core.parser import parse
from ...core.scheduler import commands
from ...db import get_db
from ...indexers.newznab import Release
from ...metadata.manager import MetadataManager
from ...models import (Blocklist, DownloadClient, Episode, History, MediaFile, Movie, QualityProfile, QueueItem,
                       RootFolder, Series, iso, utcnow)
from ...services import importer, library, maintenance
from ...services import queue as queue_svc
from ...services import search as search_svc
from ...services.grab import GrabError, grab
from ..deps import apply, get_or_404, require_auth

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])


# ========================================================================================= lookup
def _mark_existing(db: Session, results: list[dict], kind: str) -> list[dict]:
    for r in results:
        ids = r.get("ids") or {}
        q = None
        if kind == "movie":
            conds = [c for c in (Movie.tmdb_id == ids.get("tmdb") if ids.get("tmdb") else None,
                                 Movie.imdb_id == ids.get("imdb") if ids.get("imdb") else None,
                                 Movie.anilist_id == ids.get("anilist") if ids.get("anilist") else None)
                     if c is not None]
            q = db.query(Movie).filter(or_(*conds)).first() if conds else None
        else:
            conds = [c for c in (Series.tvdb_id == ids.get("tvdb") if ids.get("tvdb") else None,
                                 Series.tmdb_id == ids.get("tmdb") if ids.get("tmdb") else None,
                                 Series.tvmaze_id == ids.get("tvmaze") if ids.get("tvmaze") else None,
                                 Series.anilist_id == ids.get("anilist") if ids.get("anilist") else None)
                     if c is not None]
            q = db.query(Series).filter(or_(*conds)).first() if conds else None
        r["existing_id"] = q.id if q else None
        r.pop("episodes", None)
    return results


@router.get("/lookup/movie")
def lookup_movie(term: str, db: Session = Depends(get_db)):
    return _mark_existing(db, MetadataManager.from_db(db).search_movies(term), "movie")


@router.get("/lookup/series")
def lookup_series(term: str, db: Session = Depends(get_db)):
    return _mark_existing(db, MetadataManager.from_db(db).search_series(term), "series")


# ========================================================================================= movies
MOVIE_EDIT = ("monitored", "minimum_availability", "quality_profile_id", "tags", "path", "root_folder")


@router.get("/movies")
def list_movies(db: Session = Depends(get_db)):
    return [library.movie_to_dict(m) for m in db.query(Movie).order_by(Movie.sort_title).all()]


@router.post("/movies")
def add_movie(body: dict, db: Session = Depends(get_db)):
    try:
        m = library.add_movie(db, body.get("ids") or {}, int(body["quality_profile_id"]), body["root_folder"],
                              monitored=body.get("monitored", True),
                              minimum_availability=body.get("minimum_availability", "released"),
                              tags=body.get("tags") or [], path=body.get("path"))
    except library.LibraryError as e:
        raise HTTPException(400, str(e))
    db.commit()
    maintenance.scan_movie(db, m)
    if body.get("search", False) and m.monitored and not m.file_id:
        commands.enqueue("movie_search", {"movie_id": m.id})
    return library.movie_to_dict(m)


@router.get("/movies/{mid}")
def get_movie(mid: int, db: Session = Depends(get_db)):
    return library.movie_to_dict(get_or_404(db, Movie, mid))


@router.put("/movies/{mid}")
def update_movie(mid: int, body: dict, db: Session = Depends(get_db)):
    m = get_or_404(db, Movie, mid)
    old_path = m.path
    apply(m, body, MOVIE_EDIT)
    if body.get("move_files") and old_path != m.path and os.path.isdir(old_path):
        os.makedirs(os.path.dirname(m.path), exist_ok=True)
        os.replace(old_path, m.path) if not os.path.exists(m.path) else None
        if m.file and m.file.path.startswith(old_path):
            m.file.path = m.path + m.file.path[len(old_path):]
    return library.movie_to_dict(m)


@router.put("/movies")
def bulk_update_movies(body: dict, db: Session = Depends(get_db)):
    ids = body.get("ids") or []
    for m in db.query(Movie).filter(Movie.id.in_(ids)).all():
        apply(m, body.get("changes") or {}, ("monitored", "minimum_availability", "quality_profile_id", "tags"))
    return {"updated": len(ids)}


@router.delete("/movies/{mid}")
def delete_movie(mid: int, delete_files: bool = False, db: Session = Depends(get_db)):
    library.delete_movie(db, get_or_404(db, Movie, mid), delete_files)
    return {"ok": True}


@router.delete("/movies/{mid}/file")
def delete_movie_file(mid: int, db: Session = Depends(get_db)):
    m = get_or_404(db, Movie, mid)
    f = m.file
    if f:
        m.file_id = None
        db.flush()
        try:
            os.remove(f.path)
        except OSError:
            pass
        db.delete(f)
        db.add(History(event="deleted", media_type="movie", movie_id=m.id, source_title=os.path.basename(f.path),
                       quality=f.quality))
    return library.movie_to_dict(m)


@router.get("/movies/{mid}/releases")
def movie_releases(mid: int, db: Session = Depends(get_db)):
    m = get_or_404(db, Movie, mid)
    res = search_svc.search_movie(db, m, manual=True)
    return {"releases": [d.to_dict() for d in res["decisions"]], "errors": res["errors"], "indexers": res["indexers"]}


@router.get("/movies/{mid}/history")
def movie_history(mid: int, db: Session = Depends(get_db)):
    return [_history_dict(h) for h in db.query(History).filter(History.movie_id == mid).order_by(History.date.desc()).limit(100)]


@router.get("/movies/{mid}/rename")
def movie_rename_preview(mid: int, db: Session = Depends(get_db)):
    return importer.rename_preview(db, movie=get_or_404(db, Movie, mid))


# ========================================================================================= series
SERIES_EDIT = ("monitored", "monitor_new_seasons", "quality_profile_id", "series_type", "season_folder", "tags", "path",
               "root_folder", "episode_source")


@router.get("/series")
def list_series(db: Session = Depends(get_db)):
    stats = library.series_stats(db)
    return [library.series_to_dict(s, stats.get(s.id), with_seasons=False)
            for s in db.query(Series).order_by(Series.sort_title).all()]


@router.post("/series")
def add_series(body: dict, db: Session = Depends(get_db)):
    try:
        s = library.add_series(db, body.get("ids") or {}, int(body["quality_profile_id"]), body["root_folder"],
                               monitored=body.get("monitored", True), monitor=body.get("monitor", "all"),
                               series_type=body.get("series_type", "standard"),
                               season_folder=body.get("season_folder", True), tags=body.get("tags") or [],
                               path=body.get("path"), episode_source=body.get("episode_source", ""),
                               season_monitoring={int(k): v for k, v in (body.get("season_monitoring") or {}).items()})
    except library.LibraryError as e:
        raise HTTPException(400, str(e))
    db.commit()
    maintenance.scan_series(db, s)
    if body.get("search", False) and s.monitored:
        commands.enqueue("series_search", {"series_id": s.id})
    return library.series_to_dict(s, library.series_stats(db, [s.id]).get(s.id))


@router.get("/series/{sid}")
def get_series(sid: int, db: Session = Depends(get_db)):
    s = get_or_404(db, Series, sid)
    return library.series_to_dict(s, library.series_stats(db, [sid]).get(sid))


@router.put("/series/{sid}")
def update_series(sid: int, body: dict, db: Session = Depends(get_db)):
    s = get_or_404(db, Series, sid)
    apply(s, body, SERIES_EDIT)
    if "monitored" in body and body["monitored"] is False:
        pass  # episodes keep their own flags, like Sonarr
    return library.series_to_dict(s, library.series_stats(db, [sid]).get(sid))


@router.put("/series/{sid}/seasons/{season}")
def update_season(sid: int, season: int, body: dict, db: Session = Depends(get_db)):
    s = get_or_404(db, Series, sid)
    mon = bool(body.get("monitored"))
    for se in s.seasons:
        if se.number == season:
            se.monitored = mon
    for e in s.episodes:
        if e.season == season:
            e.monitored = mon
    return library.series_to_dict(s, library.series_stats(db, [sid]).get(sid))


@router.post("/series/{sid}/monitoring")
def series_monitoring(sid: int, body: dict, db: Session = Depends(get_db)):
    s = get_or_404(db, Series, sid)
    library.apply_monitoring(s, body.get("monitor", "all"))
    return library.series_to_dict(s)


@router.delete("/series/{sid}")
def delete_series(sid: int, delete_files: bool = False, db: Session = Depends(get_db)):
    library.delete_series(db, get_or_404(db, Series, sid), delete_files)
    return {"ok": True}


@router.get("/series/{sid}/episodes")
def series_episodes(sid: int, db: Session = Depends(get_db)):
    s = get_or_404(db, Series, sid)
    return [library.episode_to_dict(e) for e in s.episodes]


@router.put("/episodes/monitor")
def monitor_episodes(body: dict, db: Session = Depends(get_db)):
    for e in db.query(Episode).filter(Episode.id.in_(body.get("ids") or [])).all():
        e.monitored = bool(body.get("monitored"))
    return {"ok": True}


@router.delete("/episodefiles/{fid}")
def delete_episode_file(fid: int, db: Session = Depends(get_db)):
    f = get_or_404(db, MediaFile, fid)
    eps = db.query(Episode).filter(Episode.file_id == fid).all()
    for e in eps:
        e.file_id = None
    db.flush()
    try:
        os.remove(f.path)
    except OSError:
        pass
    db.add(History(event="deleted", media_type="series", series_id=f.series_id, episode_ids=[e.id for e in eps],
                   source_title=os.path.basename(f.path), quality=f.quality))
    db.delete(f)
    return {"ok": True}


@router.get("/series/{sid}/releases")
def series_releases(sid: int, season: Optional[int] = None, episode_id: Optional[int] = None,
                    db: Session = Depends(get_db)):
    s = get_or_404(db, Series, sid)
    if episode_id:
        eps = [e for e in s.episodes if e.id == episode_id]
    elif season is not None:
        eps = [e for e in s.episodes if e.season == season]
    else:
        raise HTTPException(400, "season oder episode_id angeben")
    if not eps:
        raise HTTPException(404, "Keine Episoden")
    res = search_svc.search_episodes(db, s, eps, manual=True)
    return {"releases": [d.to_dict() for d in res["decisions"]], "errors": res["errors"], "indexers": res["indexers"]}


@router.get("/series/{sid}/history")
def series_history(sid: int, db: Session = Depends(get_db)):
    return [_history_dict(h) for h in db.query(History).filter(History.series_id == sid).order_by(History.date.desc()).limit(200)]


@router.get("/series/{sid}/rename")
def series_rename_preview(sid: int, db: Session = Depends(get_db)):
    return importer.rename_preview(db, series=get_or_404(db, Series, sid))


# ========================================================================================= releases
@router.post("/releases/grab")
def grab_release(body: dict, db: Session = Depends(get_db)):
    """Grab a release from an interactive search (by indexer_id + guid). ``force`` ignores rejections."""
    cached = search_svc.cached_release(int(body["indexer_id"]), body["guid"])
    if not cached:
        raise HTTPException(404, "Release nicht mehr im Cache – bitte erneut suchen")
    if not cached["approved"] and not body.get("force"):
        raise HTTPException(400, "Release wurde abgelehnt: " + "; ".join(cached["rejections"]))
    r = Release(**cached["release"])
    try:
        return grab(db, r, quality=cached["quality"], languages=cached["parsed"]["languages"],
                    format_score=cached["format_score"], movie_id=cached["movie_id"], series_id=cached["series_id"],
                    episode_ids=cached["episode_ids"], manual=True, revision=cached["parsed"]["revision"])
    except GrabError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # limit reached etc.
        raise HTTPException(400, str(e))


@router.get("/releases/search")
def free_search(q: str, media: str = "all", db: Session = Depends(get_db)):
    return search_svc.search_text(db, q, media)


@router.get("/parse")
def parse_title(title: str, db: Session = Depends(get_db)):
    p = parse(title)
    return {"parsed": p.to_dict()}


# ========================================================================================= calendar / wanted
@router.get("/calendar")
def calendar(start: str, end: str, unmonitored: bool = False, db: Session = Depends(get_db)):
    s, e = datetime.fromisoformat(start[:19]), datetime.fromisoformat(end[:19])
    out = []
    q = db.query(Episode, Series).join(Series, Series.id == Episode.series_id).filter(
        Episode.air_date_utc >= s, Episode.air_date_utc < e)
    if not unmonitored:
        q = q.filter(Episode.monitored.is_(True))
    for ep, se in q.all():
        out.append({"type": "episode", "id": ep.id, "series_id": se.id, "title": se.title, "season": ep.season,
                    "number": ep.number, "absolute_number": ep.absolute_number, "episode_title": ep.title,
                    "date": iso(ep.air_date_utc), "has_file": ep.has_file, "monitored": ep.monitored,
                    "network": se.network, "poster": (se.images or {}).get("poster")})
    mq = db.query(Movie)
    if not unmonitored:
        mq = mq.filter(Movie.monitored.is_(True))
    for m in mq.all():
        for kind, d in (("cinema", m.in_cinemas), ("digital", m.digital_release), ("physical", m.physical_release)):
            if d and s <= d < e:
                out.append({"type": "movie", "id": m.id, "title": m.title, "year": m.year, "release_type": kind,
                            "date": iso(d), "has_file": m.has_file, "monitored": m.monitored,
                            "poster": (m.images or {}).get("poster")})
    out.sort(key=lambda x: x["date"] or "")
    return out


@router.get("/wanted/missing")
def wanted_missing(db: Session = Depends(get_db)):
    now = utcnow()
    movies = [library.movie_to_dict(m) for m in db.query(Movie).filter(Movie.monitored.is_(True), Movie.file_id.is_(None)).all()
              if dec.movie_available(m, now)]
    eps = db.query(Episode, Series).join(Series, Series.id == Episode.series_id).filter(
        Episode.monitored.is_(True), Series.monitored.is_(True), Episode.file_id.is_(None), Episode.season > 0,
        Episode.air_date_utc <= now).order_by(Episode.air_date_utc.desc()).limit(1000).all()
    return {"movies": movies, "episodes": [{**library.episode_to_dict(e, False), "series_title": s.title,
                                            "series_poster": (s.images or {}).get("poster")} for e, s in eps]}


@router.get("/wanted/cutoff")
def wanted_cutoff(db: Session = Depends(get_db)):
    profiles = {p.id: p for p in db.query(QualityProfile).all()}
    movies = [library.movie_to_dict(m) for m in db.query(Movie).filter(Movie.monitored.is_(True), Movie.file_id.isnot(None)).all()
              if not dec.cutoff_met(profiles[m.quality_profile_id], m.file)]
    out_eps = []
    for e, s in db.query(Episode, Series).join(Series, Series.id == Episode.series_id).filter(
            Episode.monitored.is_(True), Episode.file_id.isnot(None)).all():
        if not dec.cutoff_met(profiles[s.quality_profile_id], e.file):
            out_eps.append({**library.episode_to_dict(e), "series_title": s.title})
    return {"movies": movies, "episodes": out_eps[:1000]}


# ========================================================================================= imports
@router.get("/libraryimport")
def library_import_list(root_folder_id: int, db: Session = Depends(get_db)):
    rf = get_or_404(db, RootFolder, root_folder_id)
    return maintenance.unmapped_folders(db, rf)


@router.post("/libraryimport/lookup")
def library_import_lookup(body: dict, db: Session = Depends(get_db)):
    res = maintenance.lookup_folder(db, body)
    return _mark_existing(db, res, "movie" if body.get("media_type") == "movie" else "series")


@router.get("/manualimport")
def manual_import_scan(path: str, db: Session = Depends(get_db)):
    if not os.path.exists(path):
        raise HTTPException(404, "Pfad existiert nicht")
    return importer.scan_for_manual_import(db, path)


@router.post("/manualimport")
def manual_import_run(body: dict, db: Session = Depends(get_db)):
    return importer.manual_import(db, body.get("items") or [], body.get("mode", "copy"))


# ========================================================================================= activity
@router.get("/queue")
def get_queue(include_imported: bool = False, db: Session = Depends(get_db)):
    names = {c.id: c.name for c in db.query(DownloadClient).all()}
    q = db.query(QueueItem)
    if not include_imported:
        q = q.filter(QueueItem.status.notin_(("imported",)))
    return [queue_svc.queue_to_dict(db, i, names) for i in q.order_by(QueueItem.added.desc()).all()]


@router.delete("/queue/{qid}")
def remove_queue(qid: int, remove_from_client: bool = True, blocklist: bool = False, search_again: bool = False,
                 db: Session = Depends(get_db)):
    queue_svc.remove_item(db, get_or_404(db, QueueItem, qid), remove_from_client, blocklist, search_again)
    return {"ok": True}


@router.post("/queue/{qid}/import")
def retry_queue_import(qid: int, db: Session = Depends(get_db)):
    q = get_or_404(db, QueueItem, qid)
    ok = queue_svc.retry_import(db, q)
    return {"ok": ok, "messages": q.messages}


def _history_dict(h: History) -> dict:
    return {"id": h.id, "event": h.event, "date": iso(h.date), "media_type": h.media_type, "movie_id": h.movie_id,
            "series_id": h.series_id, "episode_ids": h.episode_ids, "source_title": h.source_title,
            "quality": h.quality, "indexer": h.indexer, "download_client": h.download_client,
            "download_id": h.download_id, "data": h.data}


@router.get("/history")
def history(page: int = 1, page_size: int = 50, event: str = "", db: Session = Depends(get_db)):
    q = db.query(History)
    if event:
        q = q.filter(History.event == event)
    total = q.count()
    rows = q.order_by(History.date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    titles_m = {m.id: m.title for m in db.query(Movie.id, Movie.title).all()}
    titles_s = {s.id: s.title for s in db.query(Series.id, Series.title).all()}
    out = []
    for h in rows:
        d = _history_dict(h)
        d["title"] = titles_m.get(h.movie_id) if h.movie_id else titles_s.get(h.series_id)
        out.append(d)
    return {"total": total, "page": page, "page_size": page_size, "records": out}


@router.post("/history/{hid}/failed")
def mark_failed(hid: int, db: Session = Depends(get_db)):
    """Mark a grab/import as failed: blocklist the release and search again."""
    h = get_or_404(db, History, hid)
    db.add(Blocklist(media_type=h.media_type, movie_id=h.movie_id, series_id=h.series_id, episode_ids=h.episode_ids,
                     source_title=h.source_title, guid=(h.data or {}).get("guid"),
                     info_hash=(h.data or {}).get("info_hash"), indexer=h.indexer, reason="Manuell als fehlgeschlagen markiert"))
    if h.movie_id:
        commands.enqueue("movie_search", {"movie_id": h.movie_id})
    elif h.series_id and h.episode_ids:
        commands.enqueue("episode_search", {"series_id": h.series_id, "episode_ids": h.episode_ids})
    return {"ok": True}


@router.get("/blocklist")
def blocklist(db: Session = Depends(get_db)):
    return [{"id": b.id, "date": iso(b.date), "media_type": b.media_type, "movie_id": b.movie_id,
             "series_id": b.series_id, "source_title": b.source_title, "indexer": b.indexer, "protocol": b.protocol,
             "reason": b.reason} for b in db.query(Blocklist).order_by(Blocklist.date.desc()).limit(500)]


@router.delete("/blocklist/{bid}")
def delete_blocklist(bid: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Blocklist, bid))
    return {"ok": True}


@router.delete("/blocklist")
def clear_blocklist(db: Session = Depends(get_db)):
    return {"deleted": db.query(Blocklist).delete()}


# ========================================================================================= dashboard
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    now = utcnow()
    from sqlalchemy import func

    movie_total = db.query(Movie).count()
    movie_files = db.query(Movie).filter(Movie.file_id.isnot(None)).count()
    stats = library.series_stats(db)
    size = db.query(func.sum(MediaFile.size)).scalar() or 0
    upcoming = calendar((now - timedelta(hours=12)).isoformat(), (now + timedelta(days=7)).isoformat(), db=db)[:20]
    recent = db.query(History).filter(History.event.in_(("imported", "upgraded"))).order_by(History.date.desc()).limit(10).all()
    return {
        "movies": {"total": movie_total, "with_file": movie_files, "missing": movie_total - movie_files},
        "series": {"total": db.query(Series).count(),
                   "episodes": sum(s["episode_count"] for s in stats.values()),
                   "episode_files": sum(s["episode_file_count"] for s in stats.values()),
                   "missing": sum(s["monitored_aired"] - s["monitored_have"] for s in stats.values())},
        "size_on_disk": int(size),
        "queue": db.query(QueueItem).filter(QueueItem.status.notin_(("imported", "failed", "removed"))).count(),
        "upcoming": upcoming,
        "recent": [_history_dict(h) for h in recent],
    }


@router.get("/feed/calendar.ics", response_class=PlainTextResponse)
def ical(db: Session = Depends(get_db)):
    now = utcnow()
    items = calendar((now - timedelta(days=14)).isoformat(), (now + timedelta(days=60)).isoformat(), db=db)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MediaCraft//DE"]
    for it in items:
        d = it["date"][:19].replace("-", "").replace(":", "")
        title = (f"{it['title']} - S{it['season']:02d}E{it['number']:02d} - {it.get('episode_title') or ''}"
                 if it["type"] == "episode" else f"{it['title']} ({it['release_type']})")
        lines += ["BEGIN:VEVENT", f"UID:mediacraft-{it['type']}-{it['id']}-{it.get('release_type', '')}",
                  f"DTSTAMP:{now:%Y%m%dT%H%M%SZ}", f"DTSTART:{d}Z", f"SUMMARY:{title}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return PlainTextResponse("\r\n".join(lines), media_type="text/calendar")
