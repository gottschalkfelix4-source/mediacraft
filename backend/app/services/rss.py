"""RSS sync (one query per indexer covering movies + TV) and limit-aware wanted searches."""
from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from ..core import decision as dec
from ..core import settings as settings_mod
from ..core.parser import parse, title_variants, normalize_title
from ..db import session_scope
from ..indexers import newznab, usage
from ..indexers.newznab import IndexerError
from ..indexers.usage import LimitReached
from ..models import Indexer, Movie, Series, utcnow
from . import delay
from . import search as search_svc
from .grab import grab_decision

log = logging.getLogger("rss")


def _lookup(db: Session):
    series_idx: dict[str, list[Series]] = {}
    for s in db.query(Series).filter(Series.monitored.is_(True)).all():
        names = set()
        for t in [s.title, s.original_title, *(s.alt_titles or [])]:
            if t:
                names |= title_variants(t)
                if s.year:
                    names.add(normalize_title(f"{t} {s.year}"))
        for n in names:
            series_idx.setdefault(n, []).append(s)
    movie_idx: dict[str, list[Movie]] = {}
    for m in db.query(Movie).filter(Movie.monitored.is_(True)).all():
        for t in [m.title, m.original_title, *(m.alt_titles or [])]:
            if t:
                for n in title_variants(t):
                    movie_idx.setdefault(n, []).append(m)
    by_tvdb = {s.tvdb_id: s for lst in series_idx.values() for s in lst if s.tvdb_id}
    by_imdb = {m.imdb_id: m for lst in movie_idx.values() for m in lst if m.imdb_id}
    by_tmdb = {m.tmdb_id: m for lst in movie_idx.values() for m in lst if m.tmdb_id}
    return series_idx, movie_idx, by_tvdb, by_imdb, by_tmdb


def rss_sync(db: Session) -> dict:
    cfg = settings_mod.get(db, "indexers")
    stats = {"indexers": 0, "releases": 0, "grabbed": 0, "skipped": [], "errors": []}
    idx_ids = []
    for idx in db.query(Indexer).filter(Indexer.enabled.is_(True), Indexer.enable_rss.is_(True)).all():
        if cfg.get("rss_respect_limits", True) and not usage.can(db, idx, "query"):
            stats["skipped"].append(idx.name)
            continue
        idx_ids.append(idx.id)

    releases = []
    for idx_id in idx_ids:
        with session_scope() as s:
            idx = s.get(Indexer, idx_id)
            cats = sorted(set((idx.movie_categories or []) + (idx.tv_categories or []) + (idx.anime_categories or [])))
            if not cats:
                continue
            try:
                res = newznab.search(s, idx, {"t": "search", "cat": ",".join(map(str, cats))}, kind="rss")
                stats["indexers"] += 1
                releases.extend(res)
            except (LimitReached, IndexerError) as e:
                stats["errors"].append(f"{idx.name}: {e}")
    stats["releases"] = len(releases)
    if not releases:
        return stats

    db.expire_all()
    series_idx, movie_idx, by_tvdb, by_imdb, by_tmdb = _lookup(db)
    ctx = dec.Context(db)
    movie_cands: dict[int, list[dec.Decision]] = {}
    ep_decisions: list[dec.Decision] = []
    for r in releases:
        p = parse(r.title)
        if p.is_tv:
            cands = [by_tvdb[r.tvdb_id]] if r.tvdb_id in by_tvdb else series_idx.get(p.clean_title, []) + \
                series_idx.get(p.clean_title + str(p.year or ""), [])
            for s in dict.fromkeys(cands):
                d = dec.evaluate_episodes(ctx, s, r, p)
                if d.approved:
                    ep_decisions.append(d)
        else:
            cands = []
            if r.imdb_id in by_imdb:
                cands = [by_imdb[r.imdb_id]]
            elif r.tmdb_id in by_tmdb:
                cands = [by_tmdb[r.tmdb_id]]
            else:
                cands = movie_idx.get(p.clean_title, [])
            for m in dict.fromkeys(cands):
                d = dec.evaluate_movie(ctx, m, r, p)
                if d.approved:
                    movie_cands.setdefault(m.id, []).append(d)

    stats["held"] = 0
    for mid, cands in movie_cands.items():
        m = db.get(Movie, mid)
        profile = delay.profile_for(db, m.tags)
        d = delay.prefer(cands, profile)[0]
        if delay.hold(db, d, profile, ctx.profiles[m.quality_profile_id]):
            stats["held"] += 1
            continue
        try:
            grab_decision(db, d)
            stats["grabbed"] += 1
        except Exception as e:
            stats["errors"].append(f"{d.release.title}: {e}")
    covered: set[int] = set()
    by_series: dict[int, list[dec.Decision]] = {}
    for d in ep_decisions:
        by_series.setdefault(d.series_id, []).append(d)
    ranked_eps: list[tuple[dec.Decision, object, Series]] = []
    for sid, cands in by_series.items():
        s = db.get(Series, sid)
        profile = delay.profile_for(db, s.tags)
        ranked_eps += [(d, profile, s) for d in delay.prefer(cands, profile)]
    for d, profile, s in ranked_eps:
        if set(d.episode_ids) & covered:
            continue
        if delay.hold(db, d, profile, ctx.profiles[s.quality_profile_id]):
            covered |= set(d.episode_ids)
            stats["held"] += 1
            continue
        try:
            grab_decision(db, d)
            covered |= set(d.episode_ids)
            stats["grabbed"] += 1
        except Exception as e:
            stats["errors"].append(f"{d.release.title}: {e}")
    log.info("RSS-Sync: %d Releases von %d Indexern, %d gegrabbt", stats["releases"], stats["indexers"], stats["grabbed"])
    return stats


def _any_query_budget(db: Session) -> bool:
    return any(usage.can(db, i, "query") for i in db.query(Indexer).filter(Indexer.enabled.is_(True),
                                                                           Indexer.enable_auto_search.is_(True)).all())


def search_wanted(db: Session, include_cutoff: bool | None = None) -> dict:
    """Search a batch of missing items, oldest search first, stopping when indexer budgets are used up."""
    cfg = settings_mod.get(db, "wanted")
    include_cutoff = cfg.get("cutoff_unmet_search", False) if include_cutoff is None else include_cutoff
    batch = int(cfg.get("batch_size", 10))
    min_gap = timedelta(hours=float(cfg.get("min_hours_between_item_searches", 24)))
    now = utcnow()
    done = {"movies": 0, "series": 0, "grabbed": 0, "stopped_by_limits": False}

    movies = [m for m in db.query(Movie).filter(Movie.monitored.is_(True)).all()
              if (not m.file_id or include_cutoff and m.file and not dec.cutoff_met(
                  ctx_profile(db, m.quality_profile_id), m.file))
              and dec.movie_available(m, now) and (not m.last_search or now - m.last_search > min_gap)]
    movies.sort(key=lambda m: m.last_search or m.added)
    candidates: list[tuple] = [("movie", m) for m in movies]

    for s in db.query(Series).filter(Series.monitored.is_(True)).all():
        eps = [e for e in search_svc.wanted_episodes(s, include_cutoff=include_cutoff)
               if not e.last_search or now - e.last_search > min_gap]
        if eps:
            candidates.append(("series", (s, eps)))
    candidates.sort(key=lambda c: (c[1].last_search or c[1].added) if c[0] == "movie"
                    else min((e.last_search or c[1][0].added) for e in c[1][1]))

    for kind, item in candidates[:batch]:
        if not _any_query_budget(db):
            done["stopped_by_limits"] = True
            break
        if kind == "movie":
            if search_svc.auto_search_movie(db, item):
                done["grabbed"] += 1
            done["movies"] += 1
        else:
            s, eps = item
            done["grabbed"] += len(search_svc.auto_search_episodes(db, s, eps))
            done["series"] += 1
        db.commit()
    return done


def ctx_profile(db: Session, pid: int):
    from ..models import QualityProfile

    return db.get(QualityProfile, pid)
