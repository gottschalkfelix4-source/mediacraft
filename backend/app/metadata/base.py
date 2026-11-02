"""Shared plumbing for metadata providers: HTTP with DB cache, throttling, normalized result shapes.

Normalized movie dict::
    {provider, ids:{tmdb,imdb,anilist}, title, original_title, alt_titles[], year, overview, runtime,
     status, in_cinemas, digital_release, physical_release, genres[], images{poster,fanart},
     ratings{src:{value,votes}}, certification, studio, collection, original_language}

Normalized series dict::
    {provider, ids:{tvdb,tmdb,imdb,tvmaze,anilist}, title, original_title, alt_titles[], year, overview,
     runtime, status, network, air_time, genres[], images{}, ratings{}, certification, original_language,
     is_anime, seasons:[{number, images}], episodes:[{season, number, absolute, title, overview,
     air_date, air_date_utc, runtime}]}
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from ..db import session_scope
from ..models import MetadataCache, utcnow

log = logging.getLogger("metadata")

USER_AGENT = "MediaCraft/1.0 (+https://github.com/mediacraft)"


class ProviderError(Exception):
    pass


class Provider:
    name = "base"
    supports_movies = False
    supports_series = False
    needs_key = False
    min_interval = 0.0  # seconds between requests

    def __init__(self, settings: dict):
        self.settings = settings
        self.keys = settings.get("keys", {})
        self.language = settings.get("language", "en")
        self.fallback_language = settings.get("fallback_language", "en")
        self.cache_hours = float(settings.get("cache_hours", 24))
        self._lock = threading.Lock()
        self._last = 0.0

    # -- availability ------------------------------------------------------------------------
    def available(self) -> bool:
        return True

    # -- interface (override) ----------------------------------------------------------------
    def search_movies(self, term: str, year: Optional[int] = None) -> list[dict]:
        return []

    def search_series(self, term: str) -> list[dict]:
        return []

    def get_movie(self, ids: dict) -> Optional[dict]:
        return None

    def get_series(self, ids: dict, with_episodes: bool = True) -> Optional[dict]:
        return None

    # -- http ----------------------------------------------------------------------------------
    def _throttle(self):
        if self.min_interval <= 0:
            return
        with self._lock:
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def request_json(self, method: str, url: str, *, params: dict | None = None, headers: dict | None = None,
                     json_body: Any = None, cache: bool = True, ttl_hours: float | None = None,
                     cache_key_extra: str = "") -> Any:
        ttl = self.cache_hours if ttl_hours is None else ttl_hours
        key = None
        if cache and ttl > 0:
            raw = json.dumps([self.name, method, url, params or {}, json_body, cache_key_extra], sort_keys=True,
                             default=str)
            key = f"{self.name}:{hashlib.sha1(raw.encode()).hexdigest()}"
            with session_scope() as s:
                row = s.get(MetadataCache, key)
                if row and row.created > utcnow() - timedelta(hours=ttl):
                    return row.value
        self._throttle()
        h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        h.update(headers or {})
        for attempt in range(3):
            try:
                r = httpx.request(method, url, params=params, headers=h, json=json_body, timeout=20,
                                  follow_redirects=True)
            except httpx.HTTPError as e:
                if attempt == 2:
                    raise ProviderError(f"{self.name}: {e}") from e
                time.sleep(1 + attempt)
                continue
            if r.status_code == 429:
                time.sleep(float(r.headers.get("Retry-After", 2 + attempt * 2)))
                continue
            if r.status_code == 404:
                data = None
                break
            if r.status_code >= 400:
                raise ProviderError(f"{self.name}: HTTP {r.status_code} {r.text[:200]}")
            data = r.json()
            break
        else:
            raise ProviderError(f"{self.name}: rate limited")
        if key is not None and data is not None:
            with session_scope() as s:
                row = s.get(MetadataCache, key)
                if row:
                    row.value, row.created = data, utcnow()
                else:
                    s.add(MetadataCache(key=key, value=data))
        return data


def parse_date(value: Optional[str]) -> Optional[str]:
    """Return YYYY-MM-DD or None."""
    if not value:
        return None
    v = str(value)[:10]
    try:
        datetime.strptime(v, "%Y-%m-%d")
        return v
    except ValueError:
        return None


def year_of(value: Optional[str]) -> Optional[int]:
    d = parse_date(value)
    return int(d[:4]) if d else None


def strip_html(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    import re
    import html

    t = re.sub(r"<br\s*/?>", "\n", text)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t).strip()


LANG3 = {"de": "deu", "en": "eng", "fr": "fra", "es": "spa", "it": "ita", "ja": "jpn", "nl": "nld", "pl": "pol",
         "pt": "por", "ru": "rus", "sv": "swe", "da": "dan", "no": "nor", "fi": "fin", "tr": "tur", "ko": "kor",
         "zh": "zho", "cs": "ces", "hu": "hun"}
TMDB_LOCALE = {"de": "de-DE", "en": "en-US", "fr": "fr-FR", "es": "es-ES", "it": "it-IT", "ja": "ja-JP",
               "nl": "nl-NL", "pl": "pl-PL", "pt": "pt-BR", "ru": "ru-RU"}
