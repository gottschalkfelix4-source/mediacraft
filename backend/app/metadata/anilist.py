"""AniList GraphQL – keyless anime metadata (series and movies, absolute episode numbering)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .base import Provider, strip_html

API = "https://graphql.anilist.co"

_FIELDS = """
id idMal format episodes duration status season seasonYear countryOfOrigin genres averageScore popularity
title { romaji english native } synonyms description(asHtml: false)
startDate { year month day } coverImage { extraLarge large } bannerImage
studios(isMain: true) { nodes { name } }
"""

_SEARCH = "query ($q: String, $type: MediaType) { Page(perPage: 15) { media(search: $q, type: $type, sort: SEARCH_MATCH) { %s } } }" % _FIELDS
_DETAIL = "query ($id: Int) { Media(id: $id, type: ANIME) { %s airingSchedule(perPage: 50) { nodes { episode airingAt } } } }" % _FIELDS


def _date(d: dict | None) -> Optional[str]:
    if not d or not d.get("year"):
        return None
    return f"{d['year']:04d}-{(d.get('month') or 1):02d}-{(d.get('day') or 1):02d}"


class AniListProvider(Provider):
    name = "anilist"
    supports_movies = True
    supports_series = True
    min_interval = 0.7  # 90 req/min

    def _gql(self, query: str, variables: dict, **kw):
        data = self.request_json("POST", API, json_body={"query": query, "variables": variables}, **kw) or {}
        return data.get("data") or {}

    def _base(self, m: dict) -> dict:
        t = m.get("title") or {}
        title = t.get("english") or t.get("romaji")
        return {
            "provider": self.name, "ids": {"anilist": m["id"]}, "title": title,
            "original_title": t.get("native") or t.get("romaji"),
            "alt_titles": sorted({x for x in [t.get("romaji"), t.get("english"), t.get("native"), *(m.get("synonyms") or [])]
                                  if x and x != title}),
            "year": (m.get("startDate") or {}).get("year") or m.get("seasonYear"),
            "overview": strip_html(m.get("description")), "runtime": m.get("duration"),
            "genres": m.get("genres") or [],
            "images": {"poster": (m.get("coverImage") or {}).get("extraLarge"), "fanart": m.get("bannerImage")},
            "ratings": {"anilist": {"value": (m.get("averageScore") or 0) / 10 or None, "votes": m.get("popularity")}},
            "original_language": "ja" if m.get("countryOfOrigin") == "JP" else None,
            "is_anime": True, "format": m.get("format"),
            "studio": ((m.get("studios") or {}).get("nodes") or [{}])[0].get("name") if (m.get("studios") or {}).get("nodes") else None,
        }

    def search_movies(self, term: str, year: Optional[int] = None) -> list[dict]:
        data = self._gql(_SEARCH, {"q": term, "type": "ANIME"}, ttl_hours=6)
        return [self._base(m) for m in (data.get("Page") or {}).get("media", []) if m.get("format") == "MOVIE"]

    def search_series(self, term: str) -> list[dict]:
        data = self._gql(_SEARCH, {"q": term, "type": "ANIME"}, ttl_hours=6)
        return [self._base(m) for m in (data.get("Page") or {}).get("media", [])
                if m.get("format") in ("TV", "TV_SHORT", "ONA", "OVA")]

    def _get(self, ids: dict) -> Optional[dict]:
        if not ids.get("anilist"):
            return None
        return (self._gql(_DETAIL, {"id": int(ids["anilist"])}) or {}).get("Media")

    def get_movie(self, ids: dict) -> Optional[dict]:
        m = self._get(ids)
        if not m:
            return None
        r = self._base(m)
        r["in_cinemas"] = _date(m.get("startDate"))
        r["status"] = "released" if m.get("status") == "FINISHED" else "announced"
        return r

    def get_series(self, ids: dict, with_episodes: bool = True) -> Optional[dict]:
        m = self._get(ids)
        if not m:
            return None
        r = self._base(m)
        r["status"] = {"FINISHED": "ended", "RELEASING": "continuing", "NOT_YET_RELEASED": "upcoming"}.get(m.get("status"), "continuing")
        sched = {n["episode"]: n["airingAt"] for n in ((m.get("airingSchedule") or {}).get("nodes") or [])}
        count = m.get("episodes") or (max(sched) if sched else 0)
        r["seasons"] = [{"number": 1, "images": {}}]
        r["episodes"] = []
        if with_episodes:
            for n in range(1, count + 1):
                ts = sched.get(n)
                utc = datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None) if ts else None
                r["episodes"].append({
                    "season": 1, "number": n, "absolute": n, "title": f"Episode {n}", "overview": None,
                    "air_date": utc.strftime("%Y-%m-%d") if utc else (_date(m.get("startDate")) if n == 1 else None),
                    "air_date_utc": utc.isoformat() if utc else None, "runtime": m.get("duration"),
                })
        return r
