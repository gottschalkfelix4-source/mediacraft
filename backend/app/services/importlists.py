"""Import lists: add movies/series from TMDB, Trakt, IMDb, Plex watchlists or a JSON URL automatically.

Every list source returns plain items ``{"media_type", "ids", "title", "year"}``; syncing skips what is
already in the library or on the exclusion list and adds the rest with the list's profile/root folder.
"""
from __future__ import annotations

import logging
import re
from typing import Callable

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core import settings as settings_mod
from ..metadata.manager import MetadataManager
from ..metadata.tmdb import TMDBProvider
from ..models import ImportList, ImportListExclusion, Movie, Series, utcnow
from . import library, maintenance

log = logging.getLogger("importlists")
UA = "MediaCraft/1.0 (+https://github.com/gottschalkfelix4-source/mediacraft)"


class ListError(Exception):
    pass


# ---------------------------------------------------------------------------------- schema
# kind -> (label, media types, fields [(key, label, help)])
KINDS: dict[str, dict] = {
    "tmdb_list": {"label": "TMDB-Liste", "media": ("movie", "series"),
                  "fields": [("list_id", "Listen-ID", "Zahl aus themoviedb.org/list/<ID>")]},
    "tmdb_collection": {"label": "TMDB-Sammlung", "media": ("movie",),
                        "fields": [("collection_id", "Sammlungs-ID", "Zahl aus themoviedb.org/collection/<ID>")]},
    "tmdb_chart": {"label": "TMDB-Charts", "media": ("movie", "series"),
                   "fields": [("chart", "Chart", "popular, top_rated, trending, upcoming, now_playing (Filme) bzw. on_the_air (Serien)"),
                              ("pages", "Seiten", "je 20 Einträge")]},
    "trakt_watchlist": {"label": "Trakt-Watchlist", "media": ("movie", "series"),
                        "fields": [("client_id", "Trakt Client-ID", "trakt.tv/oauth/applications → neue App"),
                                   ("username", "Benutzername", "Watchlist muss öffentlich sein")]},
    "trakt_list": {"label": "Trakt-Liste", "media": ("movie", "series"),
                   "fields": [("client_id", "Trakt Client-ID", "trakt.tv/oauth/applications → neue App"),
                              ("username", "Benutzername", ""), ("list_slug", "Listen-Slug", "aus trakt.tv/users/<name>/lists/<slug>")]},
    "trakt_chart": {"label": "Trakt-Charts", "media": ("movie", "series"),
                    "fields": [("client_id", "Trakt Client-ID", ""), ("chart", "Chart", "trending, popular, anticipated"),
                               ("limit", "Anzahl", "")]},
    "imdb_list": {"label": "IMDb-Liste", "media": ("movie", "series"),
                  "fields": [("list_id", "Listen-ID", "ls… (öffentliche Liste) oder ur… (öffentliche Watchlist)")]},
    "plex_watchlist": {"label": "Plex-Watchlist", "media": ("movie", "series"),
                       "fields": [("token", "Plex-Token", "X-Plex-Token des Kontos")]},
    "json_url": {"label": "JSON-URL", "media": ("movie", "series"),
                 "fields": [("url", "URL", "JSON-Array mit tmdb_id / imdb_id / tvdb_id (z. B. StevenLu-Format)")]},
}


def schema() -> list[dict]:
    return [{"kind": k, "label": v["label"], "media": list(v["media"]),
             "fields": [{"key": f, "label": l, "help": h} for f, l, h in v["fields"]]} for k, v in KINDS.items()]


def _item(media: str, ids: dict, title: str | None = None, year: int | None = None) -> dict:
    return {"media_type": media, "ids": {k: v for k, v in ids.items() if v}, "title": title or "", "year": year}


def _http(url: str, *, params: dict | None = None, headers: dict | None = None) -> httpx.Response:
    try:
        r = httpx.get(url, params=params, headers={"User-Agent": UA, **(headers or {})}, timeout=30,
                      follow_redirects=True)
    except httpx.HTTPError as e:
        raise ListError(f"Nicht erreichbar: {e}") from e
    if r.status_code in (401, 403):
        raise ListError(f"Zugriff verweigert (HTTP {r.status_code}) – Key/Token oder Freigabe prüfen")
    if r.status_code == 404:
        raise ListError("Liste nicht gefunden (HTTP 404)")
    if r.status_code >= 400:
        raise ListError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r


# ---------------------------------------------------------------------------------- sources
def _tmdb(db: Session) -> TMDBProvider:
    p = TMDBProvider(settings_mod.get(db, "metadata"))
    if not p.available():
        raise ListError("Für TMDB-Listen wird ein TMDB-API-Key benötigt (Einstellungen → Metadaten)")
    return p


def _fetch_tmdb_list(db, lst, s):
    return _tmdb(db).list_items(str(s.get("list_id", "")).strip())


def _fetch_tmdb_collection(db, lst, s):
    c = _tmdb(db).collection(int(s.get("collection_id") or 0))
    if not c:
        raise ListError("Sammlung nicht gefunden")
    return c["parts"]


def _fetch_tmdb_chart(db, lst, s):
    chart = (s.get("chart") or "popular").strip()
    if chart not in TMDBProvider.CHARTS[lst.media_type]:
        raise ListError(f"Unbekannter Chart '{chart}'")
    return _tmdb(db).chart(lst.media_type, chart, int(s.get("pages") or 1))


def _trakt_get(s: dict, path: str, params: dict | None = None) -> list:
    if not s.get("client_id"):
        raise ListError("Trakt Client-ID fehlt")
    r = _http(f"https://api.trakt.tv{path}", params=params,
              headers={"trakt-api-version": "2", "trakt-api-key": s["client_id"].strip(), "Content-Type": "application/json"})
    return r.json()


def _trakt_items(rows: list, media: str) -> list[dict]:
    key = "movie" if media == "movie" else "show"
    out = []
    for row in rows or []:
        obj = row.get(key) or (row if "ids" in row else None)
        if not obj:
            continue
        ids = obj.get("ids") or {}
        out.append(_item(media, {"tmdb": ids.get("tmdb"), "imdb": ids.get("imdb"), "tvdb": ids.get("tvdb")},
                         obj.get("title"), obj.get("year")))
    return out


def _trakt_kind(media: str) -> str:
    return "movies" if media == "movie" else "shows"


def _fetch_trakt_watchlist(db, lst, s):
    user = (s.get("username") or "").strip()
    return _trakt_items(_trakt_get(s, f"/users/{user}/watchlist/{_trakt_kind(lst.media_type)}"), lst.media_type)


def _fetch_trakt_list(db, lst, s):
    user, slug = (s.get("username") or "").strip(), (s.get("list_slug") or "").strip()
    return _trakt_items(_trakt_get(s, f"/users/{user}/lists/{slug}/items/{_trakt_kind(lst.media_type)}"), lst.media_type)


def _fetch_trakt_chart(db, lst, s):
    chart = (s.get("chart") or "trending").strip()
    if chart not in ("trending", "popular", "anticipated"):
        raise ListError(f"Unbekannter Chart '{chart}'")
    rows = _trakt_get(s, f"/{_trakt_kind(lst.media_type)}/{chart}", {"limit": int(s.get("limit") or 20)})
    return _trakt_items(rows, lst.media_type)


def _fetch_imdb_list(db, lst, s):
    lid = (s.get("list_id") or "").strip()
    if re.fullmatch(r"ls\d+", lid):
        url = f"https://www.imdb.com/list/{lid}/"
    elif re.fullmatch(r"ur\d+", lid):
        url = f"https://www.imdb.com/user/{lid}/watchlist/"
    else:
        raise ListError("Listen-ID muss mit ls oder ur beginnen")
    html = _http(url, headers={"Accept-Language": "en-US,en;q=0.8", "Accept": "text/html"}).text
    ids = list(dict.fromkeys(re.findall(r"/title/(tt\d{7,9})", html)))
    if not ids:
        raise ListError("Keine Titel gefunden – ist die Liste öffentlich?")
    return [_item(lst.media_type, {"imdb": tt}) for tt in ids]


def _fetch_plex_watchlist(db, lst, s):
    token = (s.get("token") or "").strip()
    if not token:
        raise ListError("Plex-Token fehlt")
    out, start = [], 0
    want = "movie" if lst.media_type == "movie" else "show"
    while start < 2000:
        r = _http("https://discover.provider.plex.tv/library/sections/watchlist/all",
                  params={"includeGuids": 1, "X-Plex-Container-Start": start, "X-Plex-Container-Size": 100},
                  headers={"X-Plex-Token": token, "Accept": "application/json"})
        mc = (r.json() or {}).get("MediaContainer") or {}
        rows = mc.get("Metadata") or []
        for m in rows:
            if m.get("type") != want:
                continue
            ids = {}
            for g in m.get("Guid") or []:
                scheme, _, val = (g.get("id") or "").partition("://")
                if scheme in ("imdb", "tmdb", "tvdb") and val:
                    ids[scheme] = val if scheme == "imdb" else int(val)
            if ids:
                out.append(_item(lst.media_type, ids, m.get("title"), m.get("year")))
        start += len(rows)
        if not rows or start >= int(mc.get("totalSize") or 0):
            break
    return out


def _fetch_json_url(db, lst, s):
    url = (s.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ListError("Ungültige URL")
    try:
        data = _http(url).json()
    except ValueError as e:
        raise ListError("Antwort ist kein JSON") from e
    if isinstance(data, dict):
        data = data.get("items") or data.get("results") or []
    out = []
    for row in data or []:
        if not isinstance(row, dict):
            continue
        def get(*keys, row=row):
            return next((row[k] for k in keys if row.get(k)), None)

        ids = {"tmdb": get("tmdb_id", "tmdbId", "tmdb"), "imdb": get("imdb_id", "imdbId", "imdb"),
               "tvdb": get("tvdb_id", "tvdbId", "tvdb")}
        for k in ("tmdb", "tvdb"):
            try:
                ids[k] = int(ids[k]) if ids[k] else None
            except (TypeError, ValueError):
                ids[k] = None
        if any(ids.values()):
            out.append(_item(lst.media_type, ids, get("title", "name"), get("year")))
    return out


FETCHERS: dict[str, Callable] = {
    "tmdb_list": _fetch_tmdb_list, "tmdb_collection": _fetch_tmdb_collection, "tmdb_chart": _fetch_tmdb_chart,
    "trakt_watchlist": _fetch_trakt_watchlist, "trakt_list": _fetch_trakt_list, "trakt_chart": _fetch_trakt_chart,
    "imdb_list": _fetch_imdb_list, "plex_watchlist": _fetch_plex_watchlist, "json_url": _fetch_json_url,
}


def fetch(db: Session, lst: ImportList) -> list[dict]:
    fn = FETCHERS.get(lst.kind)
    if not fn:
        raise ListError(f"Unbekannter Listentyp {lst.kind}")
    try:
        items = fn(db, lst, lst.settings or {})
    except ListError:
        raise
    except Exception as e:  # provider errors, bad JSON, …
        raise ListError(str(e)) from e
    return [i for i in items if i["media_type"] == lst.media_type and i["ids"]]


# ---------------------------------------------------------------------------------- matching
def _ids_filter(model, ids: dict):
    conds = []
    if ids.get("tmdb"):
        conds.append(model.tmdb_id == int(ids["tmdb"]))
    if ids.get("imdb"):
        conds.append(model.imdb_id == ids["imdb"])
    if ids.get("tvdb") and hasattr(model, "tvdb_id"):
        conds.append(model.tvdb_id == int(ids["tvdb"]))
    return or_(*conds) if conds else None


def in_library(db: Session, media: str, ids: dict) -> bool:
    model = Movie if media == "movie" else Series
    cond = _ids_filter(model, ids)
    return cond is not None and db.query(model.id).filter(cond).first() is not None


def is_excluded(db: Session, media: str, ids: dict) -> bool:
    cond = _ids_filter(ImportListExclusion, ids)
    return cond is not None and db.query(ImportListExclusion.id).filter(
        ImportListExclusion.media_type == media, cond).first() is not None


def add_exclusion(db: Session, media: str, ids: dict, title: str = "", year: int | None = None) -> ImportListExclusion:
    if is_excluded(db, media, ids):
        return db.query(ImportListExclusion).filter(ImportListExclusion.media_type == media,
                                                    _ids_filter(ImportListExclusion, ids)).first()
    ex = ImportListExclusion(media_type=media, tmdb_id=ids.get("tmdb"), tvdb_id=ids.get("tvdb"),
                             imdb_id=ids.get("imdb"), title=title, year=year)
    db.add(ex)
    db.flush()
    return ex


# ---------------------------------------------------------------------------------- sync
def _add(db: Session, lst: ImportList, item: dict, mgr: MetadataManager):
    from ..core.scheduler import commands

    if lst.media_type == "movie":
        m = library.add_movie(db, item["ids"], lst.quality_profile_id, lst.root_folder, monitored=lst.monitored,
                              minimum_availability=lst.minimum_availability, tags=list(lst.tags or []))
        db.commit()
        maintenance.scan_movie(db, m)
        if lst.search_on_add and m.monitored and not m.file_id:
            commands.enqueue("movie_search", {"movie_id": m.id})
        return m
    s = library.add_series(db, item["ids"], lst.quality_profile_id, lst.root_folder, monitored=lst.monitored,
                           monitor=lst.monitor or "all", series_type=lst.series_type or "standard",
                           tags=list(lst.tags or []))
    db.commit()
    maintenance.scan_series(db, s)
    if lst.search_on_add and s.monitored:
        commands.enqueue("series_search", {"series_id": s.id})
    return s


def sync_list(db: Session, lst: ImportList, dry_run: bool = False) -> dict:
    res = {"items": 0, "added": [], "existing": 0, "excluded": 0, "failed": []}
    try:
        items = fetch(db, lst)
    except ListError as e:
        lst.last_error, lst.last_sync = str(e), utcnow()
        db.commit()
        raise
    res["items"] = len(items)
    mgr = MetadataManager.from_db(db)
    for it in items:
        if is_excluded(db, lst.media_type, it["ids"]):
            res["excluded"] += 1
            continue
        if in_library(db, lst.media_type, it["ids"]):
            res["existing"] += 1
            continue
        if dry_run:
            res["added"].append(it["title"] or str(it["ids"]))
            continue
        try:
            obj = _add(db, lst, it, mgr)
            res["added"].append(obj.title)
        except library.LibraryError as e:
            db.rollback()
            if "bereits in der Bibliothek" in str(e):
                res["existing"] += 1
            else:
                res["failed"].append(f"{it['title'] or it['ids']}: {e}")
        except Exception as e:
            db.rollback()
            res["failed"].append(f"{it['title'] or it['ids']}: {e}")
    if not dry_run:
        lst.last_sync, lst.last_error = utcnow(), None
        lst.last_result = {k: (len(v) if isinstance(v, list) else v) for k, v in res.items()}
        db.commit()
        if res["added"]:
            log.info("Import-Liste %s: %d hinzugefügt (%s)", lst.name, len(res["added"]), ", ".join(res["added"][:10]))
    return res


def sync_all(db: Session) -> dict:
    out = {}
    for lst in db.query(ImportList).filter(ImportList.enabled.is_(True)).all():
        try:
            r = sync_list(db, lst)
            out[lst.name] = {"added": len(r["added"]), "failed": len(r["failed"])}
        except ListError as e:
            log.warning("Import-Liste %s: %s", lst.name, e)
            out[lst.name] = {"error": str(e)}
    return out
