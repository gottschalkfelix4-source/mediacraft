"""Typed-ish access to persisted settings with defaults (deep-merged)."""
from __future__ import annotations

import copy
import threading
from typing import Any

from sqlalchemy.orm import Session

DEFAULTS: dict[str, dict] = {
    "metadata": {
        "language": "de",
        "fallback_language": "en",
        "movie_providers": ["tmdb", "omdb", "anilist"],
        "series_providers": ["tvdb", "tmdb", "tvmaze"],
        "anime_providers": ["tvdb", "anilist", "tmdb", "tvmaze"],
        "enabled": {"tmdb": True, "tvdb": True, "tvmaze": True, "omdb": True, "anilist": True},
        "keys": {"tmdb": "", "tvdb": "", "tvdb_pin": "", "omdb": ""},
        "cache_hours": 24,
        "refresh_interval_hours": 12,
    },
    "media": {
        "rename": True,
        "movie_folder": "{Movie Title} ({Release Year})",
        "movie_file": "{Movie Title} ({Release Year}) {Edition Tags} [{Quality Full}]{-Release Group}",
        "series_folder": "{Series Title} ({Series Year})",
        "season_folder": "Season {season:00}",
        "specials_folder": "Specials",
        "episode_file": "{Series Title} - S{season:00}E{episode:00} - {Episode Title} [{Quality Full}]{-Release Group}",
        "daily_file": "{Series Title} - {Air-Date} - {Episode Title} [{Quality Full}]{-Release Group}",
        "anime_file": "{Series Title} - S{season:00}E{episode:00} - {absolute:000} - {Episode Title} [{Quality Full}]{-Release Group}",
        "multi_episode_style": "extend",  # extend: S01E01-E02 | duplicate: S01E01E02
        "colon_replacement": " - ",
        "use_hardlinks": True,
        "recycle_bin": "",
        "recycle_bin_days": 7,
        "delete_empty_folders": True,
        "import_extra_files": True,
        "extra_extensions": "srt,ass,ssa,sub,idx,sup,nfo",
        "sample_max_mb": 150,
        "min_free_space_mb": 200,
        "file_chmod": "",
        "upgrade_propers": True,
    },
    "downloads": {
        "completed_handling": True,
        "redownload_failed": True,
        "check_interval_seconds": 60,
        "stalled_timeout_hours": 0,
    },
    "indexers": {
        "rss_interval_minutes": 15,
        "limits_poll_minutes": 15,  # refresh live apilimits counters (0 = only from normal queries)
        "minimum_age_minutes": 0,
        "retention_days": 0,
        "maximum_size_mb": 0,
        "rss_respect_limits": True,
        "search_respect_limits": True,
        "backoff_minutes": [5, 15, 30, 60, 180, 360],
    },
    "wanted": {
        "auto_search_interval_hours": 0,  # 0 = disabled
        "batch_size": 10,
        "search_on_add": True,
        "cutoff_unmet_search": False,
        "min_hours_between_item_searches": 24,
    },
    "backup": {
        "interval_days": 7,  # 0 = no scheduled backups
        "retention_days": 28,  # scheduled/migration backups older than this are removed
    },
    "ui": {
        "language": "de",
        "first_day_of_week": 1,
        "date_format": "DD.MM.YYYY",
        "time_format": "HH:mm",
    },
    "auth": {
        "method": "none",  # none | forms
        "local_bypass": False,  # forms: no login needed from private/loopback addresses (not via proxy)
        "username": "",
        "password_hash": "",
        "secret": "",
    },
}

_lock = threading.Lock()
_cache: dict[str, dict] = {}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def get(db: Session, section: str) -> dict:
    from ..models import Setting

    with _lock:
        if section in _cache:
            return copy.deepcopy(_cache[section])
    row = db.get(Setting, section)
    value = _merge(DEFAULTS.get(section, {}), row.value if row else {})
    with _lock:
        _cache[section] = value
    return copy.deepcopy(value)


def update(db: Session, section: str, patch: dict[str, Any]) -> dict:
    from ..models import Setting

    current = get(db, section)
    new = _merge(current, patch)
    row = db.get(Setting, section)
    if row:
        row.value = new
    else:
        db.add(Setting(key=section, value=new))
    db.flush()
    with _lock:
        _cache[section] = new
    return copy.deepcopy(new)


def invalidate() -> None:
    with _lock:
        _cache.clear()
