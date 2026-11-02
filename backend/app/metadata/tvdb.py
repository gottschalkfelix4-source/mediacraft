"""TheTVDB API v4 – series (episode numbering incl. absolute/anime order)."""
from __future__ import annotations

import threading
import time
from typing import Optional

import httpx

from .base import LANG3, Provider, ProviderError, USER_AGENT, parse_date, year_of

API = "https://api4.thetvdb.com/v4"

_token_lock = threading.Lock()
_token: dict = {"key": None, "token": None, "expires": 0.0}


class TVDBProvider(Provider):
    name = "tvdb"
    supports_series = True
    needs_key = True
    min_interval = 0.05

    def available(self) -> bool:
        return bool(self.keys.get("tvdb"))

    def _token(self) -> str:
        key = self.keys.get("tvdb")
        with _token_lock:
            if _token["token"] and _token["key"] == key and _token["expires"] > time.time():
                return _token["token"]
            body = {"apikey": key}
            if self.keys.get("tvdb_pin"):
                body["pin"] = self.keys["tvdb_pin"]
            r = httpx.post(f"{API}/login", json=body, headers={"User-Agent": USER_AGENT}, timeout=20)
            if r.status_code != 200:
                raise ProviderError(f"tvdb login failed: HTTP {r.status_code} {r.text[:200]}")
            _token.update(key=key, token=r.json()["data"]["token"], expires=time.time() + 25 * 86400)
            return _token["token"]

    def _get(self, path: str, params: dict | None = None, **kw):
        data = self.request_json("GET", API + path, params=params,
                                 headers={"Authorization": f"Bearer {self._token()}"}, **kw)
        return (data or {}).get("data") if isinstance(data, dict) else None

    @property
    def _lang3(self) -> str:
        return LANG3.get(self.language, "eng")

    def search_series(self, term: str) -> list[dict]:
        data = self._get("/search", {"query": term, "type": "series", "limit": 20}, ttl_hours=6) or []
        out = []
        for s in data:
            tr = s.get("translations") or {}
            ov = s.get("overviews") or {}
            ids = {"tvdb": int(s.get("tvdb_id") or s.get("id", "0").replace("series-", "") or 0)}
            for rid in s.get("remote_ids") or []:
                src = (rid.get("sourceName") or "").lower()
                if "imdb" in src:
                    ids["imdb"] = rid.get("id")
                elif "themoviedb" in src or "tmdb" in src:
                    try:
                        ids["tmdb"] = int(rid.get("id"))
                    except (TypeError, ValueError):
                        pass
            out.append({
                "provider": self.name, "ids": ids,
                "title": tr.get(self._lang3) or s.get("name"), "original_title": s.get("name"),
                "year": int(s["year"]) if str(s.get("year") or "").isdigit() else None,
                "overview": ov.get(self._lang3) or ov.get("eng") or s.get("overview"),
                "images": {"poster": s.get("image_url") or s.get("thumbnail")},
                "network": s.get("network"), "status": (s.get("status") or "").lower() or None,
                "original_language": s.get("primary_language"),
                "alt_titles": s.get("aliases") or [],
            })
        return out

    def _resolve(self, ids: dict) -> Optional[int]:
        if ids.get("tvdb"):
            return int(ids["tvdb"])
        for key in ("imdb", "tmdb"):
            if ids.get(key):
                data = self._get(f"/search/remoteid/{ids[key]}") or []
                for d in data:
                    s = d.get("series")
                    if s and s.get("id"):
                        return int(s["id"])
        return None

    def _episodes(self, sid: int, season_type: str, lang: Optional[str]) -> list[dict]:
        out, page = [], 0
        while page < 50:
            path = f"/series/{sid}/episodes/{season_type}" + (f"/{lang}" if lang else "")
            data = self._get(path, {"page": page})
            if not data:
                break
            eps = data.get("episodes") or []
            out.extend(eps)
            if len(eps) < 500:
                break
            page += 1
        return out

    def get_series(self, ids: dict, with_episodes: bool = True) -> Optional[dict]:
        sid = self._resolve(ids)
        if not sid:
            return None
        s = self._get(f"/series/{sid}/extended", {"meta": "translations", "short": "true"})
        if not s:
            return None
        tr = s.get("translations") or {}
        title = next((t["name"] for t in tr.get("nameTranslations") or [] if t.get("language") == self._lang3), None)
        overview = next((t["overview"] for t in tr.get("overviewTranslations") or [] if t.get("language") == self._lang3), None)
        if not overview:
            overview = next((t["overview"] for t in tr.get("overviewTranslations") or []
                             if t.get("language") == LANG3.get(self.fallback_language, "eng")), s.get("overview"))
        out_ids = {"tvdb": s["id"]}
        for rid in s.get("remoteIds") or []:
            src = (rid.get("sourceName") or "").lower()
            if "imdb" in src:
                out_ids["imdb"] = rid.get("id")
            elif "themoviedb" in src:
                try:
                    out_ids["tmdb"] = int(rid["id"])
                except (TypeError, ValueError):
                    pass
            elif "tv maze" in src or "tvmaze" in src:
                try:
                    out_ids["tvmaze"] = int(rid["id"])
                except (TypeError, ValueError):
                    pass
        status = (s.get("status") or {}).get("name", "").lower()
        status = {"continuing": "continuing", "ended": "ended", "upcoming": "upcoming"}.get(status, "continuing")
        genres = [g.get("name") for g in s.get("genres") or []]
        poster = s.get("image")
        fanart = next((a.get("image") for a in s.get("artworks") or [] if a.get("type") == 3), None)
        result = {
            "provider": self.name, "ids": out_ids,
            "title": title or s.get("name"), "original_title": s.get("name"),
            "alt_titles": sorted({a.get("name") for a in s.get("aliases") or [] if a.get("name")}
                                 | {t["name"] for t in tr.get("nameTranslations") or [] if t.get("name")}),
            "year": int(s["year"]) if str(s.get("year") or "").isdigit() else year_of(s.get("firstAired")),
            "overview": overview, "runtime": s.get("averageRuntime"), "status": status,
            "network": (s.get("originalNetwork") or {}).get("name") or (s.get("latestNetwork") or {}).get("name"),
            "air_time": s.get("airsTime"), "genres": genres,
            "images": {"poster": poster, "fanart": fanart}, "ratings": {},
            "certification": None, "original_language": s.get("originalLanguage"),
            "is_anime": "Anime" in genres or ("Animation" in genres and s.get("originalLanguage") == "jpn"),
            "seasons": [], "episodes": [],
        }
        seasons = set()
        if with_episodes:
            base = self._episodes(sid, "default", None)
            localized = {e["id"]: e for e in self._episodes(sid, "default", self._lang3)} if self._lang3 != "eng" else {}
            for e in base:
                loc = localized.get(e["id"], {})
                seasons.add(e.get("seasonNumber") or 0)
                result["episodes"].append({
                    "season": e.get("seasonNumber") or 0, "number": e.get("number") or 0,
                    "absolute": e.get("absoluteNumber") or None,
                    "title": loc.get("name") or e.get("name"), "overview": loc.get("overview") or e.get("overview"),
                    "air_date": parse_date(e.get("aired")), "air_date_utc": None, "runtime": e.get("runtime"),
                })
        result["seasons"] = [{"number": n, "images": {}} for n in sorted(seasons)]
        return result
