"""Searching indexers for movies / episodes and automatic grabbing of the best release.

Query planning is limit-aware: several wanted episodes of one season are covered by a single
season query instead of one query per episode, ID based queries are preferred and text
fallbacks are only issued when an ID query returned nothing.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from ..core import decision as dec
from ..core import settings as settings_mod
from ..core.parser import parse
from ..db import session_scope
from ..indexers import newznab, usage
from ..indexers.newznab import IndexerError, Release
from ..indexers.usage import LimitReached
from ..models import Episode, Indexer, Movie, Series, utcnow

log = logging.getLogger("search")
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="search")

# interactive search results, so the UI can grab by (indexer_id, guid)
_release_cache: dict[tuple[int, str], tuple[float, dict]] = {}


def cache_releases(decisions: Iterable[dec.Decision]) -> None:
    now = time.time()
    for k in [k for k, (t, _) in _release_cache.items() if now - t > 3600]:
        _release_cache.pop(k, None)
    for d in decisions:
        _release_cache[(d.release.indexer_id, d.release.guid)] = (now, d.to_dict())


def cached_release(indexer_id: int, guid: str) -> Optional[dict]:
    v = _release_cache.get((indexer_id, guid))
    return v[1] if v else None


def _tags_match(idx: Indexer, tags: list[int]) -> bool:
    return not idx.tags or bool(set(idx.tags) & set(tags or []))


def indexers_for(db: Session, media: str, mode: str, tags: list[int] | None = None) -> list[Indexer]:
    """media: movie|series|anime, mode: auto|interactive|rss"""
    flag = {"auto": "enable_auto_search", "interactive": "enable_interactive_search", "rss": "enable_rss"}[mode]
    out = []
    for idx in db.query(Indexer).filter(Indexer.enabled.is_(True)).order_by(Indexer.priority, Indexer.id).all():
        if not getattr(idx, flag):
            continue
        cats = idx.movie_categories if media == "movie" else (idx.anime_categories or idx.tv_categories) if media == "anime" else idx.tv_categories
        if not cats:
            continue
        if not _tags_match(idx, tags or []):
            continue
        out.append(idx)
    return out


def _cats(idx: Indexer, media: str) -> str:
    if media == "movie":
        cats = idx.movie_categories
    elif media == "anime":
        cats = list(dict.fromkeys((idx.anime_categories or []) + (idx.tv_categories or [])))
    else:
        cats = idx.tv_categories
    return ",".join(str(c) for c in cats)


def _run_queries(indexer_ids: list[int], plans: dict[int, list[list[dict]]], manual: bool,
                 kind: str = "query") -> tuple[list[Release], list[str]]:
    """Execute query plans per indexer in parallel. A plan is a list of alternatives: the next
    alternative is only tried when the previous returned no results."""

    def work(idx_id: int):
        found: list[Release] = []
        errors: list[str] = []
        with session_scope() as s:
            idx = s.get(Indexer, idx_id)
            for alternatives in plans.get(idx_id, []):
                for params in alternatives:
                    try:
                        res = newznab.search(s, idx, params, kind=kind, manual=manual)
                    except LimitReached as e:
                        errors.append(str(e))
                        return found, errors
                    except IndexerError as e:
                        errors.append(f"{idx.name}: {e}")
                        return found, errors
                    finally:
                        s.commit()  # release the SQLite write lock before the next (slow) HTTP request
                    found.extend(res)
                    if res:
                        break
        return found, errors

    releases: list[Release] = []
    errors: list[str] = []
    for fut in [_pool.submit(work, i) for i in indexer_ids]:
        try:
            r, e = fut.result(timeout=180)
            releases.extend(r)
            errors.extend(e)
        except Exception as e:  # pragma: no cover
            errors.append(str(e))
    # dedupe (same guid per indexer)
    seen, out = set(), []
    for r in releases:
        k = (r.indexer_id, r.guid)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out, errors


def _usable(db: Session, idxs: list[Indexer], manual: bool) -> tuple[list[Indexer], list[str]]:
    ok, skipped = [], []
    respect = settings_mod.get(db, "indexers").get("search_respect_limits", True)
    for idx in idxs:
        try:
            if respect or manual:
                usage.check(db, idx, "query", manual=manual)
            ok.append(idx)
        except LimitReached as e:
            skipped.append(str(e))
    return ok, skipped


# ===================================================================================== movies
def _movie_plan(idx: Indexer, movie: Movie) -> list[list[dict]]:
    cat = _cats(idx, "movie")
    alts: list[dict] = []
    if movie.imdb_id and newznab.supports(idx, "movie-search", "imdbid"):
        alts.append({"t": "movie", "imdbid": movie.imdb_id.replace("tt", ""), "cat": cat})
    elif movie.tmdb_id and newznab.supports(idx, "movie-search", "tmdbid"):
        alts.append({"t": "movie", "tmdbid": movie.tmdb_id, "cat": cat})
    q = f"{movie.title} {movie.year or ''}".strip()
    mode = "movie" if newznab.supports(idx, "movie-search", "q") else "search"
    alts.append({"t": mode, "q": q, "cat": cat})
    if movie.original_title and movie.original_title != movie.title:
        alts.append({"t": mode, "q": f"{movie.original_title} {movie.year or ''}".strip(), "cat": cat})
    return [alts]


def search_movie(db: Session, movie: Movie, manual: bool = False) -> dict:
    idxs, skipped = _usable(db, indexers_for(db, "movie", "interactive" if manual else "auto", movie.tags), manual)
    plans = {i.id: _movie_plan(i, movie) for i in idxs}
    releases, errors = _run_queries([i.id for i in idxs], plans, manual)
    db.expire_all()
    ctx = dec.Context(db, manual=manual)
    decisions = [dec.evaluate_movie(ctx, movie, r) for r in releases]
    ranked = dec.rank(decisions, approved_only=False)
    movie.last_search = utcnow()
    if manual:
        cache_releases(ranked)
    return {"decisions": ranked, "errors": errors + skipped, "indexers": len(idxs)}


def auto_search_movie(db: Session, movie: Movie) -> Optional[dict]:
    from . import delay
    from .grab import grab_decision

    res = search_movie(db, movie, manual=False)
    profile = delay.profile_for(db, movie.tags)
    for d in delay.prefer(res["decisions"], profile):
        if d.approved:
            if delay.hold(db, d, profile, series_profile_by_id(db, movie.quality_profile_id)):
                return None
            try:
                return grab_decision(db, d, manual=False)
            except Exception as e:
                log.warning("Grab fehlgeschlagen (%s): %s – nächster Kandidat", d.release.title, e)
    log.info("Keine passende Release für %s gefunden (%d geprüft)", movie.title, len(res["decisions"]))
    return None


# ===================================================================================== series
def _tv_plan(idx: Indexer, series: Series, episodes: list[Episode]) -> list[list[dict]]:
    media = "anime" if series.series_type == "anime" else "series"
    cat = _cats(idx, media)
    id_param: dict = {}
    for col, param in (("tvdb_id", "tvdbid"), ("tvmaze_id", "tvmazeid"), ("imdb_id", "imdbid")):
        val = getattr(series, col)
        if val and newznab.supports(idx, "tv-search", param):
            id_param = {param: str(val).replace("tt", "") if param == "imdbid" else val}
            break
    tv_q = newznab.supports(idx, "tv-search", "q") or not idx.capabilities
    title = series.title
    plans: list[list[dict]] = []
    by_season: dict[int, list[Episode]] = {}
    for e in episodes:
        by_season.setdefault(e.season, []).append(e)
    now = utcnow()
    for season, eps in sorted(by_season.items()):
        all_in_season = [e for e in series.episodes if e.season == season]
        season_aired = all(e.aired(now) for e in all_in_season)
        use_season_query = len(eps) >= 2 or (season_aired and len(eps) == len(all_in_season))
        if series.series_type == "daily":
            for e in eps:
                if not e.air_date:
                    continue
                y, m, d = e.air_date.split("-")
                alts = []
                if id_param:
                    alts.append({"t": "tvsearch", **id_param, "season": y, "ep": f"{m}/{d}", "cat": cat})
                alts.append({"t": "tvsearch" if tv_q else "search", "q": f"{title} {y} {m} {d}", "cat": cat})
                plans.append(alts)
            continue
        if series.series_type == "anime":
            for e in eps:
                alts = []
                if e.absolute_number:
                    alts.append({"t": "search", "q": f"{title} {e.absolute_number:02d}", "cat": cat})
                if id_param:
                    alts.append({"t": "tvsearch", **id_param, "season": e.season, "ep": e.number, "cat": cat})
                alts.append({"t": "search", "q": f"{title} S{e.season:02d}E{e.number:02d}", "cat": cat})
                plans.append(alts)
            continue
        if use_season_query:
            alts = []
            if id_param:
                alts.append({"t": "tvsearch", **id_param, "season": season, "cat": cat})
            alts.append({"t": "tvsearch" if tv_q else "search", "q": title, "season": season, "cat": cat}
                        if tv_q else {"t": "search", "q": f"{title} S{season:02d}", "cat": cat})
            plans.append(alts)
        else:
            for e in eps:
                alts = []
                if id_param:
                    alts.append({"t": "tvsearch", **id_param, "season": e.season, "ep": e.number, "cat": cat})
                alts.append({"t": "tvsearch", "q": title, "season": e.season, "ep": e.number, "cat": cat}
                            if tv_q else {"t": "search", "q": f"{title} S{e.season:02d}E{e.number:02d}", "cat": cat})
                plans.append(alts)
    return plans


def search_episodes(db: Session, series: Series, episodes: list[Episode], manual: bool = False) -> dict:
    media = "anime" if series.series_type == "anime" else "series"
    idxs, skipped = _usable(db, indexers_for(db, media, "interactive" if manual else "auto", series.tags), manual)
    plans = {i.id: _tv_plan(i, series, episodes) for i in idxs}
    releases, errors = _run_queries([i.id for i in idxs], plans, manual)
    db.expire_all()
    ctx = dec.Context(db, manual=manual)
    target = {e.id for e in episodes}
    decisions = [dec.evaluate_episodes(ctx, series, r, target_ids=target) for r in releases]
    ranked = dec.rank(decisions, approved_only=False)
    now = utcnow()
    for e in episodes:
        e.last_search = now
    if manual:
        cache_releases(ranked)
    return {"decisions": ranked, "errors": errors + skipped, "indexers": len(idxs)}


def auto_search_episodes(db: Session, series: Series, episodes: list[Episode]) -> list[dict]:
    """Grab best releases until all requested episodes are covered (season packs first if better)."""
    from . import delay
    from .grab import grab_decision

    res = search_episodes(db, series, episodes, manual=False)
    remaining = {e.id for e in episodes}
    grabbed = []
    profile = delay.profile_for(db, series.tags)
    for d in delay.prefer(res["decisions"], profile):
        if not d.approved or not remaining:
            continue
        ids = set(d.episode_ids)
        if not ids & remaining:
            continue
        if delay.hold(db, d, profile, series_profile(series)):
            remaining -= ids  # nothing worse for these episodes while the better one waits
            continue
        try:
            grabbed.append(grab_decision(db, d, manual=False))
            remaining -= ids
        except Exception as e:
            log.warning("Grab fehlgeschlagen (%s): %s", d.release.title, e)
    return grabbed


def wanted_episodes(series: Series, season: Optional[int] = None, include_cutoff: bool = False) -> list[Episode]:
    from ..core.decision import cutoff_met

    now = utcnow()
    out = []
    for e in series.episodes:
        if season is not None and e.season != season:
            continue
        if not e.monitored or not e.aired(now):
            continue
        if not e.file_id:
            out.append(e)
        elif include_cutoff and e.file and not cutoff_met(series_profile(series), e.file):
            out.append(e)
    return out


def series_profile_by_id(db: Session, pid: int):
    from ..models import QualityProfile

    return db.get(QualityProfile, pid)


def series_profile(series: Series):
    from sqlalchemy.orm import object_session
    from ..models import QualityProfile

    return object_session(series).get(QualityProfile, series.quality_profile_id)


def search_text(db: Session, query: str, media: str = "all") -> dict:
    """Free text search across all interactive indexers (no item mapping)."""
    medias = ["movie", "series"] if media == "all" else [media]
    cats: dict[int, list[str]] = {}
    for m in medias:
        for idx in indexers_for(db, m, "interactive"):
            cats.setdefault(idx.id, []).append(_cats(idx, m))
    plans = {i: [[{"t": "search", "q": query, "cat": ",".join(c)}]] for i, c in cats.items()}
    releases, errors = _run_queries(list(plans), plans, manual=True)
    out = []
    for r in releases:
        p = parse(r.title)
        out.append({"release": r.to_dict(), "parsed": p.to_dict()})
    return {"results": out, "errors": errors}
