"""Multi-provider metadata: parallel search, ID cross-mapping, priority based merge and fallback."""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..core import settings as settings_mod
from ..core.parser import normalize_title
from .anilist import AniListProvider
from .base import Provider, ProviderError
from .omdb import OMDbProvider
from .tmdb import TMDBProvider
from .tvdb import TVDBProvider
from .tvmaze import TVmazeProvider

log = logging.getLogger("metadata")

PROVIDER_CLASSES: dict[str, type[Provider]] = {
    "tmdb": TMDBProvider, "tvdb": TVDBProvider, "tvmaze": TVmazeProvider, "omdb": OMDbProvider,
    "anilist": AniListProvider,
}
ID_KEYS = ("tvdb", "tmdb", "imdb", "tvmaze", "anilist")
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="meta")


class MetadataManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        enabled = cfg.get("enabled", {})
        self.providers: dict[str, Provider] = {}
        for name, cls in PROVIDER_CLASSES.items():
            if enabled.get(name, True):
                p = cls(cfg)
                if p.available():
                    self.providers[name] = p

    @classmethod
    def from_db(cls, db: Session) -> "MetadataManager":
        return cls(settings_mod.get(db, "metadata"))

    def status(self) -> list[dict]:
        out = []
        for name, cls in PROVIDER_CLASSES.items():
            p = cls(self.cfg)
            out.append({"name": name, "movies": cls.supports_movies, "series": cls.supports_series,
                        "needs_key": cls.needs_key, "available": p.available(),
                        "enabled": self.cfg.get("enabled", {}).get(name, True)})
        return out

    def _order(self, kind: str) -> list[Provider]:
        key = {"movie": "movie_providers", "series": "series_providers", "anime": "anime_providers"}[kind]
        names = list(self.cfg.get(key) or [])
        support = "supports_movies" if kind == "movie" else "supports_series"
        # providers not listed explicitly are appended as last-resort fallbacks
        for n, p in self.providers.items():
            if n not in names and getattr(p, support):
                names.append(n)
        return [self.providers[n] for n in names if n in self.providers and getattr(self.providers[n], support)]

    # ------------------------------------------------------------------------------- search
    @staticmethod
    def _direct_ids(term: str) -> Optional[dict]:
        m = re.match(r"^\s*(tvdb|tmdb|imdb|tvmaze|anilist)\s*:\s*(\S+)\s*$", term, re.I)
        if m:
            k, v = m.group(1).lower(), m.group(2)
            return {k: v if k == "imdb" else int(v)}
        if re.fullmatch(r"\s*tt\d{6,9}\s*", term):
            return {"imdb": term.strip()}
        return None

    def _parallel(self, fns: list) -> list:
        futures = [_pool.submit(fn) for fn in fns]
        out = []
        for f in futures:
            try:
                out.append(f.result(timeout=40))
            except Exception as e:  # provider failures must never break the whole search
                log.warning("metadata provider failed: %s", e)
                out.append(None)
        return out

    def search_movies(self, term: str) -> list[dict]:
        ids = self._direct_ids(term)
        if ids:
            m = self.get_movie(ids)
            return [{**m, "sources": m.get("metadata_sources") or [m["provider"]]}] if m else []
        year = None
        ym = re.search(r"\s\(?((?:19|20)\d{2})\)?\s*$", term)
        q = term
        if ym:
            year, q = int(ym.group(1)), term[: ym.start()].strip()
        providers = self._order("movie")
        results = self._parallel([lambda p=p: p.search_movies(q, year) for p in providers])
        return _merge_results([r or [] for r in results], q)

    def search_series(self, term: str) -> list[dict]:
        ids = self._direct_ids(term)
        if ids:
            s = self.get_series(ids, with_episodes=False)
            return [{**s, "sources": s.get("metadata_sources") or [s["provider"]]}] if s else []
        providers = self._order("series")
        for p in self._order("anime"):
            if p not in providers:
                providers.append(p)
        results = self._parallel([lambda p=p: p.search_series(term) for p in providers])
        return _merge_results([r or [] for r in results], term)

    # ------------------------------------------------------------------------------- fetch
    def get_movie(self, ids: dict, anime: bool = False) -> Optional[dict]:
        ids = {k: v for k, v in ids.items() if v}
        order = self._order("movie")
        if anime and "anilist" in self.providers and self.providers["anilist"] not in order:
            order.append(self.providers["anilist"])
        primary = None
        for p in order:
            try:
                primary = p.get_movie(ids)
            except ProviderError as e:
                log.warning("%s get_movie failed: %s", p.name, e)
                continue
            if primary:
                break
        if not primary:
            return None
        all_ids = {**ids, **{k: v for k, v in primary["ids"].items() if v}}
        secondaries = [p for p in order if p.name != primary["provider"]]
        extra = self._parallel([lambda p=p: p.get_movie(all_ids) for p in secondaries])
        merged = _merge_detail(primary, [e for e in extra if e])
        merged["metadata_sources"] = [primary["provider"]] + [e["provider"] for e in extra if e]
        return merged

    def get_series(self, ids: dict, with_episodes: bool = True, anime: bool = False,
                   preferred_source: str = "") -> Optional[dict]:
        ids = {k: v for k, v in ids.items() if v}
        order = self._order("anime" if anime else "series")
        if preferred_source in self.providers:
            order = [self.providers[preferred_source]] + [p for p in order if p.name != preferred_source]
        primary = None
        for p in order:
            try:
                primary = p.get_series(ids, with_episodes)
            except ProviderError as e:
                log.warning("%s get_series failed: %s", p.name, e)
                continue
            if primary and (not with_episodes or primary.get("episodes")):
                break
            if primary and with_episodes and not primary.get("episodes"):
                ids = {**ids, **{k: v for k, v in primary["ids"].items() if v}}
                primary = None
        if not primary:
            return None
        all_ids = {**ids, **{k: v for k, v in primary["ids"].items() if v}}
        secondaries = [p for p in order if p.name != primary["provider"]]
        want_eps = lambda p: with_episodes and (p.name == "tvmaze" or primary["provider"] == "tvmaze")
        extra = self._parallel([lambda p=p: p.get_series(all_ids, want_eps(p)) for p in secondaries])
        extra = [e for e in extra if e]
        merged = _merge_detail(primary, extra)
        merged["episode_source"] = primary["provider"]
        merged["metadata_sources"] = [primary["provider"]] + [e["provider"] for e in extra]
        if with_episodes:
            _enrich_episodes(merged, extra)
            _compute_utc(merged)
        return merged


# ------------------------------------------------------------------------------------- merge helpers
def _ids_overlap(a: dict, b: dict) -> bool:
    return any(a.get(k) and b.get(k) and str(a[k]) == str(b[k]) for k in ID_KEYS)


def _fill(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if k in ("provider",):
            continue
        if k == "ids":
            for ik, iv in v.items():
                if iv and not dst["ids"].get(ik):
                    dst["ids"][ik] = iv
        elif k == "images":
            dst.setdefault("images", {})
            for ik, iv in (v or {}).items():
                if iv and not dst["images"].get(ik):
                    dst["images"][ik] = iv
        elif k == "ratings":
            dst.setdefault("ratings", {})
            for ik, iv in (v or {}).items():
                if iv and iv.get("value") and ik not in dst["ratings"]:
                    dst["ratings"][ik] = iv
        elif k == "alt_titles":
            dst["alt_titles"] = sorted(set(dst.get("alt_titles") or []) | set(v or []) | (
                {src["title"]} if src.get("title") and src.get("title") != dst.get("title") else set()))
        elif k in ("episodes", "seasons"):
            continue
        elif k == "is_anime":
            dst[k] = bool(dst.get(k)) or bool(v)
        elif dst.get(k) in (None, "", []) and v not in (None, "", []):
            dst[k] = v


def _merge_results(groups: list[list[dict]], term: str) -> list[dict]:
    merged: list[dict] = []
    for results in groups:
        for r in results:
            r = {**r, "ids": dict(r.get("ids") or {}), "sources": [r["provider"]]}
            target = next((m for m in merged if _ids_overlap(m["ids"], r["ids"])), None)
            if target is None and not any(r["ids"].get(k) for k in ("tvdb", "tmdb", "imdb")):
                # id-less (e.g. anilist only): merge on exact normalized title + year
                target = next((m for m in merged if normalize_title(m.get("title") or "") == normalize_title(r.get("title") or "")
                               and m.get("year") == r.get("year")), None)
            if target:
                _fill(target, r)
                target["sources"].append(r["provider"])
            else:
                merged.append(r)
    nt = normalize_title(term)

    def rank(m: dict):
        titles = [m.get("title") or "", m.get("original_title") or ""] + list(m.get("alt_titles") or [])
        exact = any(normalize_title(t) == nt for t in titles)
        return (not exact, -len(m["sources"]), -(m.get("popularity") or 0))

    merged.sort(key=rank)
    return merged


def _merge_detail(primary: dict, extras: list[dict]) -> dict:
    out = {**primary, "ids": dict(primary.get("ids") or {}), "images": dict(primary.get("images") or {}),
           "ratings": dict(primary.get("ratings") or {})}
    for e in extras:
        _fill(out, e)
    return out


def _enrich_episodes(merged: dict, extras: list[dict]) -> None:
    for e in extras:
        idx = {(x["season"], x["number"]): x for x in e.get("episodes") or []}
        if not idx:
            continue
        for ep in merged["episodes"]:
            other = idx.get((ep["season"], ep["number"]))
            if not other:
                continue
            for k in ("title", "overview", "air_date", "air_date_utc", "runtime"):
                if not ep.get(k) and other.get(k):
                    ep[k] = other[k]
            # TVmaze airstamps are exact; prefer them when the date matches
            if other.get("air_date_utc") and other.get("air_date") == ep.get("air_date"):
                ep["air_date_utc"] = other["air_date_utc"]


def _compute_utc(merged: dict) -> None:
    """Approximate UTC airing time for providers that only deliver a date (assume US prime time)."""
    air_time = merged.get("air_time") or "20:00"
    try:
        hh, mm = (int(x) for x in air_time.split(":")[:2])
    except ValueError:
        hh, mm = 20, 0
    for ep in merged.get("episodes") or []:
        if ep.get("air_date_utc") or not ep.get("air_date"):
            continue
        d = datetime.strptime(ep["air_date"], "%Y-%m-%d") + timedelta(hours=hh, minutes=mm)
        if merged.get("original_language") not in ("ja", "jpn"):
            d += timedelta(hours=5)
        else:
            d -= timedelta(hours=9)
        ep["air_date_utc"] = d.isoformat()
