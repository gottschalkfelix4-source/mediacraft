"""TVmaze – free, keyless series metadata with exact UTC air stamps and localized AKAs."""
from __future__ import annotations

from typing import Optional

from .base import Provider, parse_date, strip_html, year_of

API = "https://api.tvmaze.com"

_COUNTRY_FOR_LANG = {"de": {"DE", "AT", "CH"}, "fr": {"FR"}, "es": {"ES"}, "it": {"IT"}, "nl": {"NL"}}


class TVmazeProvider(Provider):
    name = "tvmaze"
    supports_series = True
    min_interval = 0.55  # 20 calls / 10s limit

    def _show_to_result(self, s: dict) -> dict:
        ext = s.get("externals") or {}
        return {
            "provider": self.name,
            "ids": {"tvmaze": s["id"], "tvdb": ext.get("thetvdb"), "imdb": ext.get("imdb")},
            "title": s.get("name"), "original_title": s.get("name"),
            "year": year_of(s.get("premiered")), "overview": strip_html(s.get("summary")),
            "images": {"poster": (s.get("image") or {}).get("original") or (s.get("image") or {}).get("medium")},
            "network": ((s.get("network") or s.get("webChannel")) or {}).get("name"),
            "status": {"Running": "continuing", "Ended": "ended", "To Be Determined": "continuing",
                       "In Development": "upcoming"}.get(s.get("status"), "continuing"),
            "runtime": s.get("averageRuntime") or s.get("runtime"),
            "genres": s.get("genres") or [],
            "ratings": {"tvmaze": {"value": (s.get("rating") or {}).get("average"), "votes": None}},
            "original_language": (s.get("language") or "")[:2].lower() or None,
            "air_time": (s.get("schedule") or {}).get("time") or None,
            "is_anime": "Anime" in (s.get("genres") or []),
        }

    def search_series(self, term: str) -> list[dict]:
        data = self.request_json("GET", f"{API}/search/shows", params={"q": term}, ttl_hours=6) or []
        return [self._show_to_result(d["show"]) for d in data[:20]]

    def _resolve(self, ids: dict) -> Optional[int]:
        if ids.get("tvmaze"):
            return int(ids["tvmaze"])
        for key, param in (("tvdb", "thetvdb"), ("imdb", "imdb")):
            if ids.get(key):
                s = self.request_json("GET", f"{API}/lookup/shows", params={param: ids[key]})
                if s and s.get("id"):
                    return s["id"]
        return None

    def get_series(self, ids: dict, with_episodes: bool = True) -> Optional[dict]:
        tid = self._resolve(ids)
        if not tid:
            return None
        s = self.request_json("GET", f"{API}/shows/{tid}", params={"embed[]": ["akas", "seasons"]})
        if not s:
            return None
        result = self._show_to_result(s)
        emb = s.get("_embedded") or {}
        akas = emb.get("akas") or []
        countries = _COUNTRY_FOR_LANG.get(self.language, set())
        local = next((a["name"] for a in akas if (a.get("country") or {}).get("code") in countries), None)
        if local:
            result["title"] = local
        result["alt_titles"] = sorted({a["name"] for a in akas if a.get("name")} - {result["title"]})
        result["seasons"] = [{"number": se["number"], "images": {"poster": (se.get("image") or {}).get("original")}}
                             for se in emb.get("seasons") or []]
        result["episodes"] = []
        if with_episodes:
            eps = self.request_json("GET", f"{API}/shows/{tid}/episodes", params={"specials": 1}) or []
            special_no = 0
            for e in eps:
                season, number = e.get("season"), e.get("number")
                if e.get("type") != "regular" or number is None:
                    special_no += 1
                    season, number = 0, special_no
                stamp = e.get("airstamp")
                result["episodes"].append({
                    "season": season, "number": number, "absolute": None, "title": e.get("name"),
                    "overview": strip_html(e.get("summary")), "air_date": parse_date(e.get("airdate")),
                    "air_date_utc": stamp[:19] if stamp else None, "runtime": e.get("runtime"),
                })
        return result
