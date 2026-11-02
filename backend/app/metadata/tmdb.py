"""The Movie Database (TMDB) v3 – movies and TV. Accepts v3 API keys or v4 read access tokens."""
from __future__ import annotations

from typing import Optional

from .base import Provider, TMDB_LOCALE, parse_date, year_of

API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/"


class TMDBProvider(Provider):
    name = "tmdb"
    supports_movies = True
    supports_series = True
    needs_key = True
    min_interval = 0.05

    def available(self) -> bool:
        return bool(self.keys.get("tmdb"))

    def _get(self, path: str, params: dict | None = None, lang: str | None = None, **kw):
        key = self.keys.get("tmdb", "")
        params = dict(params or {})
        headers = {}
        if key.startswith("eyJ") or len(key) > 60:
            headers["Authorization"] = f"Bearer {key}"
        else:
            params["api_key"] = key
        if lang is not False:
            params["language"] = TMDB_LOCALE.get(lang or self.language, lang or self.language)
        return self.request_json("GET", API + path, params=params, headers=headers,
                                 cache_key_extra="", **kw)

    @staticmethod
    def _img(path: Optional[str], size: str = "w500") -> Optional[str]:
        return f"{IMG}{size}{path}" if path else None

    # ------------------------------------------------------------------------------- movies
    def search_movies(self, term: str, year: Optional[int] = None) -> list[dict]:
        params = {"query": term, "include_adult": "false"}
        if year:
            params["year"] = year
        data = self._get("/search/movie", params, ttl_hours=6) or {}
        out = []
        for m in (data.get("results") or [])[:20]:
            out.append({
                "provider": self.name, "ids": {"tmdb": m["id"]}, "title": m.get("title"),
                "original_title": m.get("original_title"), "year": year_of(m.get("release_date")),
                "overview": m.get("overview"), "images": {"poster": self._img(m.get("poster_path")),
                                                          "fanart": self._img(m.get("backdrop_path"), "w1280")},
                "ratings": {"tmdb": {"value": m.get("vote_average"), "votes": m.get("vote_count")}},
                "original_language": m.get("original_language"), "popularity": m.get("popularity", 0),
            })
        return out

    def _resolve_movie_id(self, ids: dict) -> Optional[int]:
        if ids.get("tmdb"):
            return int(ids["tmdb"])
        if ids.get("imdb"):
            data = self._get(f"/find/{ids['imdb']}", {"external_source": "imdb_id"}, lang=False) or {}
            res = data.get("movie_results") or []
            if res:
                return res[0]["id"]
        return None

    def get_movie(self, ids: dict) -> Optional[dict]:
        mid = self._resolve_movie_id(ids)
        if not mid:
            return None
        m = self._get(f"/movie/{mid}", {"append_to_response": "external_ids,release_dates,alternative_titles,translations"})
        if not m:
            return None
        overview = m.get("overview")
        title = m.get("title")
        if not overview or not title:
            for tr in (m.get("translations") or {}).get("translations", []):
                if tr.get("iso_639_1") == self.fallback_language:
                    overview = overview or tr["data"].get("overview")
                    title = title or tr["data"].get("title")
        dates = {3: None, 4: None, 5: None}
        cert = None
        for c in (m.get("release_dates") or {}).get("results", []):
            for rd in c.get("release_dates", []):
                t = rd.get("type")
                d = parse_date(rd.get("release_date"))
                if t in dates and d and (dates[t] is None or d < dates[t]):
                    dates[t] = d
                if c.get("iso_3166_1") == (self.language.upper() if self.language != "en" else "US") and rd.get("certification"):
                    cert = rd["certification"]
        if dates[3] is None:
            dates[3] = parse_date(m.get("release_date"))
        alt = [a["title"] for a in (m.get("alternative_titles") or {}).get("titles", [])]
        for tr in (m.get("translations") or {}).get("translations", []):
            if tr.get("data", {}).get("title"):
                alt.append(tr["data"]["title"])
        status = {"Released": "released", "In Production": "announced", "Post Production": "announced",
                  "Planned": "announced", "Rumored": "announced", "Canceled": "announced"}.get(m.get("status"), "announced")
        return {
            "provider": self.name,
            "ids": {"tmdb": m["id"], "imdb": m.get("imdb_id") or (m.get("external_ids") or {}).get("imdb_id")},
            "title": title, "original_title": m.get("original_title"),
            "alt_titles": sorted(set(a for a in alt if a and a != title)),
            "year": year_of(m.get("release_date")), "overview": overview, "runtime": m.get("runtime"),
            "status": status, "in_cinemas": dates[3], "digital_release": dates[4], "physical_release": dates[5],
            "genres": [g["name"] for g in m.get("genres", [])],
            "images": {"poster": self._img(m.get("poster_path")), "fanart": self._img(m.get("backdrop_path"), "w1280")},
            "ratings": {"tmdb": {"value": m.get("vote_average"), "votes": m.get("vote_count")}},
            "certification": cert,
            "studio": (m.get("production_companies") or [{}])[0].get("name") if m.get("production_companies") else None,
            "collection": (m.get("belongs_to_collection") or {}).get("name"),
            "original_language": m.get("original_language"),
        }

    # ------------------------------------------------------------------------------- series
    def search_series(self, term: str) -> list[dict]:
        data = self._get("/search/tv", {"query": term}, ttl_hours=6) or {}
        out = []
        for s in (data.get("results") or [])[:20]:
            out.append({
                "provider": self.name, "ids": {"tmdb": s["id"]}, "title": s.get("name"),
                "original_title": s.get("original_name"), "year": year_of(s.get("first_air_date")),
                "overview": s.get("overview"),
                "images": {"poster": self._img(s.get("poster_path")), "fanart": self._img(s.get("backdrop_path"), "w1280")},
                "ratings": {"tmdb": {"value": s.get("vote_average"), "votes": s.get("vote_count")}},
                "original_language": s.get("original_language"), "popularity": s.get("popularity", 0),
                "is_anime": 16 in (s.get("genre_ids") or []) and s.get("original_language") == "ja",
            })
        return out

    def _resolve_tv_id(self, ids: dict) -> Optional[int]:
        if ids.get("tmdb"):
            return int(ids["tmdb"])
        for key, src in (("tvdb", "tvdb_id"), ("imdb", "imdb_id")):
            if ids.get(key):
                data = self._get(f"/find/{ids[key]}", {"external_source": src}, lang=False) or {}
                res = data.get("tv_results") or []
                if res:
                    return res[0]["id"]
        return None

    def get_series(self, ids: dict, with_episodes: bool = True) -> Optional[dict]:
        tid = self._resolve_tv_id(ids)
        if not tid:
            return None
        s = self._get(f"/tv/{tid}", {"append_to_response": "external_ids,alternative_titles,content_ratings,translations"})
        if not s:
            return None
        ext = s.get("external_ids") or {}
        title, overview = s.get("name"), s.get("overview")
        if not overview:
            for tr in (s.get("translations") or {}).get("translations", []):
                if tr.get("iso_639_1") == self.fallback_language:
                    overview = tr["data"].get("overview")
        cert = None
        for c in (s.get("content_ratings") or {}).get("results", []):
            if c.get("iso_3166_1") in ("DE", "US"):
                cert = c.get("rating")
                if c.get("iso_3166_1") == self.language.upper():
                    break
        alt = [a["title"] for a in (s.get("alternative_titles") or {}).get("results", [])]
        status = {"Returning Series": "continuing", "Ended": "ended", "Canceled": "ended",
                  "In Production": "upcoming", "Planned": "upcoming"}.get(s.get("status"), "continuing")
        result = {
            "provider": self.name,
            "ids": {"tmdb": s["id"], "tvdb": ext.get("tvdb_id"), "imdb": ext.get("imdb_id")},
            "title": title, "original_title": s.get("original_name"),
            "alt_titles": sorted(set(a for a in alt if a and a != title)),
            "year": year_of(s.get("first_air_date")), "overview": overview,
            "runtime": (s.get("episode_run_time") or [None])[0], "status": status,
            "network": (s.get("networks") or [{}])[0].get("name") if s.get("networks") else None,
            "air_time": None, "genres": [g["name"] for g in s.get("genres", [])],
            "images": {"poster": self._img(s.get("poster_path")), "fanart": self._img(s.get("backdrop_path"), "w1280")},
            "ratings": {"tmdb": {"value": s.get("vote_average"), "votes": s.get("vote_count")}},
            "certification": cert, "original_language": s.get("original_language"),
            "is_anime": any(g.get("id") == 16 for g in s.get("genres", [])) and s.get("original_language") == "ja",
            "seasons": [{"number": se["season_number"], "images": {"poster": self._img(se.get("poster_path"))}}
                        for se in s.get("seasons", [])],
            "episodes": [],
        }
        if with_episodes:
            for se in s.get("seasons", []):
                data = self._get(f"/tv/{tid}/season/{se['season_number']}") or {}
                for ep in data.get("episodes", []):
                    result["episodes"].append({
                        "season": ep["season_number"], "number": ep["episode_number"], "absolute": None,
                        "title": ep.get("name"), "overview": ep.get("overview"),
                        "air_date": parse_date(ep.get("air_date")), "air_date_utc": None, "runtime": ep.get("runtime"),
                    })
        return result
