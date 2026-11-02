"""OMDb – IMDb based data; mainly used for ratings (IMDb, Rotten Tomatoes, Metacritic) and fallback search."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from .base import Provider

API = "https://www.omdbapi.com/"


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


class OMDbProvider(Provider):
    name = "omdb"
    supports_movies = True
    supports_series = True
    needs_key = True
    min_interval = 0.1

    def available(self) -> bool:
        return bool(self.keys.get("omdb"))

    def _q(self, params: dict, **kw):
        data = self.request_json("GET", API, params={"apikey": self.keys.get("omdb"), **params}, **kw)
        if not data or data.get("Response") == "False":
            return None
        return data

    def _search(self, term: str, kind: str, year: Optional[int] = None) -> list[dict]:
        params = {"s": term, "type": kind}
        if year:
            params["y"] = year
        data = self._q(params, ttl_hours=6) or {}
        out = []
        for m in data.get("Search", [])[:10]:
            y = re.match(r"\d{4}", m.get("Year", ""))
            out.append({"provider": self.name, "ids": {"imdb": m.get("imdbID")}, "title": m.get("Title"),
                        "original_title": m.get("Title"), "year": int(y.group()) if y else None,
                        "images": {"poster": m.get("Poster") if m.get("Poster", "N/A") != "N/A" else None}})
        return out

    def search_movies(self, term: str, year: Optional[int] = None) -> list[dict]:
        return self._search(term, "movie", year)

    def search_series(self, term: str) -> list[dict]:
        return self._search(term, "series")

    def _detail(self, imdb: str) -> Optional[dict]:
        d = self._q({"i": imdb, "plot": "full"})
        if not d:
            return None
        ratings = {}
        if d.get("imdbRating") not in (None, "N/A"):
            ratings["imdb"] = {"value": _num(d["imdbRating"]), "votes": _num(d.get("imdbVotes"))}
        for r in d.get("Ratings", []):
            if r.get("Source") == "Rotten Tomatoes":
                ratings["rottenTomatoes"] = {"value": _num(r["Value"].rstrip("%")), "votes": None}
            elif r.get("Source") == "Metacritic":
                ratings["metacritic"] = {"value": _num(r["Value"].split("/")[0]), "votes": None}
        released = None
        try:
            released = datetime.strptime(d.get("Released", ""), "%d %b %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
        runtime = re.match(r"(\d+)", d.get("Runtime", ""))
        y = re.match(r"\d{4}", d.get("Year", ""))
        return {
            "provider": self.name, "ids": {"imdb": d.get("imdbID")}, "title": d.get("Title"),
            "original_title": d.get("Title"), "alt_titles": [], "year": int(y.group()) if y else None,
            "overview": d.get("Plot") if d.get("Plot") != "N/A" else None,
            "runtime": int(runtime.group(1)) if runtime else None, "genres": [g.strip() for g in d.get("Genre", "").split(",") if g.strip() and g != "N/A"],
            "images": {"poster": d.get("Poster") if d.get("Poster", "N/A") != "N/A" else None},
            "ratings": ratings, "certification": d.get("Rated") if d.get("Rated") != "N/A" else None,
            "in_cinemas": released, "status": "released" if released else None,
        }

    def get_movie(self, ids: dict) -> Optional[dict]:
        return self._detail(ids["imdb"]) if ids.get("imdb") else None

    def get_series(self, ids: dict, with_episodes: bool = True) -> Optional[dict]:
        d = self._detail(ids["imdb"]) if ids.get("imdb") else None
        if d:
            d.update({"seasons": [], "episodes": []})  # OMDb is enrichment-only for series
        return d
