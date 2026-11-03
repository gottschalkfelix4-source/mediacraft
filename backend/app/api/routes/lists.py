"""Import lists, exclusions and movie collections."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...core import settings as settings_mod
from ...db import get_db
from ...metadata.tmdb import TMDBProvider
from ...models import ImportList, ImportListExclusion, Movie, QualityProfile, iso
from ...services import importlists, library, maintenance
from ..deps import apply, get_or_404, require_auth

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])

LIST_FIELDS = ("name", "kind", "enabled", "media_type", "settings", "quality_profile_id", "root_folder", "monitored",
               "monitor", "minimum_availability", "series_type", "search_on_add", "tags")
SECRET_KEYS = ("token",)
MASK = "********"


def list_to_dict(lst: ImportList) -> dict:
    d = {f: getattr(lst, f) for f in LIST_FIELDS}
    d["settings"] = {k: (MASK if k in SECRET_KEYS and v else v) for k, v in (lst.settings or {}).items()}
    d.update(id=lst.id, last_sync=iso(lst.last_sync), last_error=lst.last_error, last_result=lst.last_result or {})
    return d


def _validate(db: Session, body: dict, saved: ImportList | None = None) -> dict:
    body = dict(body)
    settings = dict(body.get("settings") or {})
    for k in SECRET_KEYS:
        if settings.get(k) == MASK:
            settings[k] = (saved.settings or {}).get(k, "") if saved else ""
    body["settings"] = settings
    kind = body.get("kind") or (saved.kind if saved else None)
    if kind not in importlists.KINDS:
        raise HTTPException(400, "Unbekannter Listentyp")
    media = body.get("media_type") or (saved.media_type if saved else "movie")
    if media not in importlists.KINDS[kind]["media"]:
        raise HTTPException(400, "Dieser Listentyp unterstützt den Medientyp nicht")
    pid = body.get("quality_profile_id") or (saved.quality_profile_id if saved else None)
    if not pid or not db.get(QualityProfile, int(pid)):
        raise HTTPException(400, "Qualitätsprofil fehlt")
    if not (body.get("root_folder") or (saved.root_folder if saved else None)):
        raise HTTPException(400, "Root-Folder fehlt")
    return body


@router.get("/importlists/schema")
def lists_schema():
    return importlists.schema()


@router.get("/importlists")
def get_lists(db: Session = Depends(get_db)):
    return [list_to_dict(lst) for lst in db.query(ImportList).order_by(ImportList.name).all()]


@router.post("/importlists")
def create_list(body: dict, db: Session = Depends(get_db)):
    lst = apply(ImportList(), _validate(db, body), LIST_FIELDS)
    db.add(lst)
    db.flush()
    return list_to_dict(lst)


@router.put("/importlists/{lid}")
def update_list(lid: int, body: dict, db: Session = Depends(get_db)):
    lst = get_or_404(db, ImportList, lid)
    apply(lst, _validate(db, body, lst), LIST_FIELDS)
    return list_to_dict(lst)


@router.delete("/importlists/{lid}")
def delete_list(lid: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, ImportList, lid))
    return {"ok": True}


@router.post("/importlists/test")
def test_list(body: dict, db: Session = Depends(get_db)):
    """Fetch the list without adding anything: how many entries, which would be new."""
    saved = db.get(ImportList, body["id"]) if body.get("id") else None
    data = _validate(db, body, saved)
    lst = apply(ImportList(), data, LIST_FIELDS)
    try:
        res = importlists.sync_list(db, lst, dry_run=True)
    except importlists.ListError as e:
        raise HTTPException(400, str(e))
    finally:
        db.expunge(lst) if lst in db else None
    return {"items": res["items"], "new": res["added"][:50], "new_count": len(res["added"]),
            "existing": res["existing"], "excluded": res["excluded"]}


@router.post("/importlists/{lid}/sync")
def sync_list(lid: int, db: Session = Depends(get_db)):
    lst = get_or_404(db, ImportList, lid)
    try:
        return importlists.sync_list(db, lst)
    except importlists.ListError as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------------------------ exclusions
@router.get("/exclusions")
def get_exclusions(db: Session = Depends(get_db)):
    return [e.to_dict() for e in db.query(ImportListExclusion).order_by(ImportListExclusion.title).all()]


@router.post("/exclusions")
def create_exclusion(body: dict, db: Session = Depends(get_db)):
    ids = {k: body.get(f"{k}_id") for k in ("tmdb", "tvdb", "imdb")}
    if not any(ids.values()):
        raise HTTPException(400, "Mindestens eine ID angeben")
    return importlists.add_exclusion(db, body.get("media_type", "movie"), ids, body.get("title", ""),
                                     body.get("year")).to_dict()


@router.delete("/exclusions/{eid}")
def delete_exclusion(eid: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, ImportListExclusion, eid))
    return {"ok": True}


# ------------------------------------------------------------------------------------ collections
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="collections")


def _tmdb(db: Session) -> TMDBProvider:
    p = TMDBProvider(settings_mod.get(db, "metadata"))
    if not p.available():
        raise HTTPException(400, "Sammlungen brauchen einen TMDB-API-Key (Einstellungen → Metadaten)")
    return p


def _collection_dict(db: Session, c: dict, movies: list[Movie]) -> dict:
    by_tmdb = {m.tmdb_id: m for m in movies if m.tmdb_id}
    lib_by_tmdb = {m.tmdb_id: m for m in db.query(Movie).filter(
        Movie.tmdb_id.in_([p["ids"]["tmdb"] for p in c["parts"]])).all()}
    by_tmdb.update(lib_by_tmdb)
    watched = db.query(ImportList).filter(ImportList.kind == "tmdb_collection").all()
    watch = next((lst for lst in watched if str((lst.settings or {}).get("collection_id")) == str(c["id"])), None)
    parts = []
    for p in c["parts"]:
        m = by_tmdb.get(p["ids"]["tmdb"])
        excluded = importlists.is_excluded(db, "movie", p["ids"])
        parts.append({**p, "movie_id": m.id if m else None, "has_file": bool(m and m.file_id),
                      "monitored": bool(m and m.monitored), "excluded": excluded})
    return {"id": c["id"], "name": c["name"], "overview": c.get("overview"), "images": c.get("images") or {},
            "parts": parts, "in_library": sum(1 for p in parts if p["movie_id"]),
            "missing": sum(1 for p in parts if not p["movie_id"] and not p["excluded"]),
            "watch_list_id": watch.id if watch else None}


@router.get("/collections")
def get_collections(db: Session = Depends(get_db)):
    movies = db.query(Movie).filter(Movie.collection_tmdb_id.isnot(None)).all()
    groups: dict[int, list[Movie]] = {}
    for m in movies:
        groups.setdefault(m.collection_tmdb_id, []).append(m)
    if not groups:
        return []
    tmdb = _tmdb(db)
    fetched = list(_pool.map(lambda cid: (cid, tmdb.collection(cid)), groups))
    out = []
    for cid, c in fetched:
        if c:
            out.append(_collection_dict(db, c, groups[cid]))
    out.sort(key=lambda c: c["name"] or "")
    return out


@router.post("/collections/{cid}/add")
def add_collection_movies(cid: int, body: dict, db: Session = Depends(get_db)):
    """Add movies of a collection: ``tmdb_ids`` (default: all missing, not excluded)."""
    from ...core.scheduler import commands

    c = _tmdb(db).collection(cid)
    if not c:
        raise HTTPException(404, "Sammlung nicht gefunden")
    wanted = set(body.get("tmdb_ids") or [])
    pid, root = body.get("quality_profile_id"), body.get("root_folder")
    if not pid or not root:
        raise HTTPException(400, "Qualitätsprofil und Root-Folder angeben")
    added, failed = [], []
    for p in c["parts"]:
        ids = p["ids"]
        if wanted and ids["tmdb"] not in wanted:
            continue
        if importlists.in_library(db, "movie", ids) or (not wanted and importlists.is_excluded(db, "movie", ids)):
            continue
        try:
            m = library.add_movie(db, ids, int(pid), root, monitored=body.get("monitored", True),
                                  minimum_availability=body.get("minimum_availability", "released"),
                                  tags=body.get("tags") or [])
            db.commit()
            maintenance.scan_movie(db, m)
            if body.get("search") and m.monitored and not m.file_id:
                commands.enqueue("movie_search", {"movie_id": m.id})
            added.append(m.title)
        except library.LibraryError as e:
            db.rollback()
            failed.append(f"{p['title']}: {e}")
    return {"added": added, "failed": failed}
