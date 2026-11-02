"""Newznab / Torznab client with usage accounting and error-code aware back-off."""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlencode

import httpx
from defusedxml import ElementTree as ET
from sqlalchemy.orm import Session

from ..core import settings as settings_mod
from ..models import Indexer, utcnow
from . import usage

log = logging.getLogger("indexer")
UA = "MediaCraft/1.0"


class IndexerError(Exception):
    pass


@dataclass
class Release:
    guid: str
    title: str
    indexer_id: int
    indexer: str
    protocol: str
    download_url: str
    info_url: Optional[str] = None
    size: int = 0
    publish_date: Optional[str] = None
    age_hours: float = 0.0
    seeders: Optional[int] = None
    leechers: Optional[int] = None
    grabs: Optional[int] = None
    info_hash: Optional[str] = None
    magnet: Optional[str] = None
    categories: list[int] = field(default_factory=list)
    imdb_id: Optional[str] = None
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    tvmaze_id: Optional[int] = None
    flags: list[str] = field(default_factory=list)
    indexer_priority: int = 25

    def to_dict(self):
        return asdict(self)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _int(v) -> Optional[int]:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _base_url(idx: Indexer) -> str:
    url = idx.url.rstrip("/")
    path = idx.api_path or "/api"
    if url.endswith(path.rstrip("/")):
        return url
    return url + "/" + path.strip("/")


def _extra_params(idx: Indexer) -> dict:
    out = {}
    for part in re.split(r"[&\n]", idx.additional_params or ""):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def probe_limits(db: Session, idx: Indexer, manual: bool = False) -> dict:
    """Fetch the live ``apilimits`` counters with the smallest possible query (1 result, no grab).

    Costs one API call, never a grab. Indexers that don't report limits are remembered as such.
    """
    before = (idx.remote_limits or {}).get("seen")
    search(db, idx, {"t": "search", "limit": 1}, kind="limits", manual=manual)
    if (idx.remote_limits or {}).get("seen") == before:
        usage.mark_remote_missing(idx)
    return idx.remote_limits or {}


def _check_error(root, idx: Indexer) -> None:
    if _local(root.tag) == "error":
        code = _int(root.get("code")) or 0
        desc = root.get("description") or "unknown error"
        raise IndexerError(f"[{code}] {desc}", ) from None


def _error_code(msg: str) -> int:
    m = re.match(r"\[(\d+)\]", msg)
    return int(m.group(1)) if m else 0


def _request(db: Session, idx: Indexer, params: dict, kind: str, manual: bool) -> tuple[bytes, int]:
    """Perform one API call with limit check, interval, accounting and failure handling."""
    usage.check(db, idx, "query", manual=manual)
    usage.wait_interval(idx)
    q = {**_extra_params(idx), **params}
    if idx.api_key:
        q["apikey"] = idx.api_key
    url = _base_url(idx)
    t0 = time.monotonic()
    try:
        r = httpx.get(url, params=q, headers={"User-Agent": UA}, timeout=60, follow_redirects=True)
    except httpx.HTTPError as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        usage.record(db, idx, kind, success=False, manual=manual, elapsed_ms=elapsed, detail=str(e))
        usage.pause(db, idx, f"Verbindungsfehler: {e}", backoff=settings_mod.get(db, "indexers")["backoff_minutes"])
        raise IndexerError(str(e)) from e
    elapsed = int((time.monotonic() - t0) * 1000)
    if r.status_code == 429:
        retry = r.headers.get("Retry-After")
        until = utcnow() + timedelta(seconds=int(retry)) if retry and retry.isdigit() else None
        usage.record(db, idx, kind, success=False, manual=manual, elapsed_ms=elapsed, detail="HTTP 429")
        usage.pause(db, idx, "HTTP 429 – Rate limit", until=until or usage.next_slot(db, idx, "query", usage.effective_limit(idx, "query") or 1))
        raise IndexerError("HTTP 429 rate limited")
    if r.status_code >= 400:
        usage.record(db, idx, kind, success=False, manual=manual, elapsed_ms=elapsed, detail=f"HTTP {r.status_code}")
        if r.status_code in (401, 403):
            usage.pause(db, idx, f"HTTP {r.status_code} – API-Key ungültig?", until=utcnow() + timedelta(hours=6))
        else:
            usage.pause(db, idx, f"HTTP {r.status_code}", backoff=settings_mod.get(db, "indexers")["backoff_minutes"])
        raise IndexerError(f"HTTP {r.status_code}")
    return r.content, elapsed


def _handle_api_error(db: Session, idx: Indexer, msg: str, kind: str, manual: bool, elapsed: int) -> None:
    code = _error_code(msg)
    usage.record(db, idx, kind, success=False, manual=manual, elapsed_ms=elapsed, detail=msg)
    if code in (500, 501, 429):
        k = "query" if code == 500 else "grab"
        until = usage.next_slot(db, idx, k, max(usage.effective_limit(idx, k), 1)) or utcnow() + timedelta(hours=1)
        usage.pause(db, idx, f"Indexer meldet Limit erreicht: {msg}", until=until)
    elif code in (100, 101, 102):
        usage.pause(db, idx, f"Zugangsfehler: {msg}", until=utcnow() + timedelta(hours=6))
    else:
        usage.pause(db, idx, msg, backoff=settings_mod.get(db, "indexers")["backoff_minutes"])


def caps(db: Session, idx: Indexer, manual: bool = True) -> dict:
    content, elapsed = _request(db, idx, {"t": "caps"}, "caps", manual)
    root = ET.fromstring(content)
    try:
        _check_error(root, idx)
    except IndexerError as e:
        _handle_api_error(db, idx, str(e), "caps", manual, elapsed)
        raise
    usage.record(db, idx, "caps", manual=manual, elapsed_ms=elapsed)
    out: dict = {"searching": {}, "categories": [], "limits": {}}
    for el in root.iter():
        tag = _local(el.tag)
        if tag in ("search", "tv-search", "movie-search", "audio-search", "book-search"):
            out["searching"][tag] = {"available": el.get("available") == "yes",
                                     "params": [p.strip() for p in (el.get("supportedParams") or "q").split(",")]}
        elif tag == "apilimits":
            usage.apply_remote_limits(idx, dict(el.attrib))
        elif tag == "limits":
            out["limits"] = {"max": _int(el.get("max")), "default": _int(el.get("default"))}
        elif tag == "category":
            cat = {"id": _int(el.get("id")), "name": el.get("name"), "subcats": []}
            for sub in el:
                if _local(sub.tag) == "subcat":
                    cat["subcats"].append({"id": _int(sub.get("id")), "name": sub.get("name")})
            out["categories"].append(cat)
    idx.capabilities = out
    usage.mark_ok(idx)
    return out


def _parse_items(root, idx: Indexer) -> list[Release]:
    out: list[Release] = []
    now = datetime.now(timezone.utc)
    for item in root.iter():
        if _local(item.tag) == "apilimits":
            usage.apply_remote_limits(idx, dict(item.attrib))
            continue
        if _local(item.tag) != "item":
            continue
        d: dict = {"attrs": {}, "cats": []}
        for ch in item:
            tag = _local(ch.tag)
            if tag == "attr":
                name, val = (ch.get("name") or "").lower(), ch.get("value")
                if name == "category":
                    if _int(val) is not None:
                        d["cats"].append(_int(val))
                else:
                    d["attrs"][name] = val
            elif tag == "enclosure":
                d["enclosure"] = ch.get("url")
                d["enclosure_len"] = ch.get("length")
            elif tag == "category" and (ch.text or "").strip().isdigit():
                d["cats"].append(int(ch.text.strip()))
            else:
                d[tag] = (ch.text or "").strip()
        a = d["attrs"]
        title = d.get("title")
        link = d.get("enclosure") or d.get("link")
        magnet = a.get("magneturl")
        if not link and magnet:
            link = magnet
        if not title or not link:
            continue
        size = _int(a.get("size")) or _int(d.get("size")) or _int(d.get("enclosure_len")) or 0
        pub = d.get("pubdate") or a.get("usenetdate")
        age = 0.0
        pub_iso = None
        if pub:
            try:
                pd = parsedate_to_datetime(pub)
                if pd.tzinfo is None:
                    pd = pd.replace(tzinfo=timezone.utc)
                age = max((now - pd).total_seconds() / 3600, 0)
                pub_iso = pd.astimezone(timezone.utc).replace(tzinfo=None).isoformat() + "Z"
            except (TypeError, ValueError):
                pass
        flags = []
        if a.get("downloadvolumefactor") in ("0", "0.0"):
            flags.append("freeleech")
        elif a.get("downloadvolumefactor") in ("0.5", ".5"):
            flags.append("halfleech")
        if a.get("tag"):
            flags.extend(t.strip().lower() for t in a["tag"].split(","))
        imdb = a.get("imdb") or a.get("imdbid")
        if imdb and not str(imdb).startswith("tt"):
            imdb = "tt" + str(imdb).zfill(7)
        info_hash = (a.get("infohash") or "").lower() or None
        if not info_hash and magnet:
            m = re.search(r"btih:([a-f0-9]{40})", magnet, re.I)
            info_hash = m.group(1).lower() if m else None
        out.append(Release(
            guid=d.get("guid") or link, title=title, indexer_id=idx.id, indexer=idx.name, protocol=idx.protocol,
            download_url=link, info_url=d.get("comments") or (d.get("guid") if (d.get("guid") or "").startswith("http") else None),
            size=size, publish_date=pub_iso, age_hours=round(age, 2),
            seeders=_int(a.get("seeders")), leechers=_int(a.get("peers")) if a.get("peers") else _int(a.get("leechers")),
            grabs=_int(a.get("grabs")), info_hash=info_hash, magnet=magnet, categories=sorted(set(d["cats"])),
            imdb_id=imdb, tmdb_id=_int(a.get("tmdbid") or a.get("tmdb")), tvdb_id=_int(a.get("tvdbid")),
            tvmaze_id=_int(a.get("tvmazeid")), flags=flags, indexer_priority=idx.priority,
        ))
    return out


def search(db: Session, idx: Indexer, params: dict, *, kind: str = "query", manual: bool = False) -> list[Release]:
    """Run a single newznab query (``params`` incl. ``t``) and return releases."""
    params = {"extended": 1, "limit": 100, **params}
    content, elapsed = _request(db, idx, params, kind, manual)
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        usage.record(db, idx, kind, success=False, manual=manual, elapsed_ms=elapsed, detail=f"invalid XML: {e}")
        usage.pause(db, idx, f"Ungültige Antwort: {e}", backoff=settings_mod.get(db, "indexers")["backoff_minutes"])
        raise IndexerError(f"invalid XML: {e}") from e
    try:
        _check_error(root, idx)
    except IndexerError as e:
        _handle_api_error(db, idx, str(e), kind, manual, elapsed)
        raise
    releases = _parse_items(root, idx)
    usage.record(db, idx, kind, manual=manual, elapsed_ms=elapsed, results=len(releases),
                 detail=urlencode({k: v for k, v in params.items() if k not in ("apikey",)})[:500])
    usage.mark_ok(idx)
    return releases


def supports(idx: Indexer, mode: str, param: str) -> bool:
    s = (idx.capabilities or {}).get("searching", {}).get(mode)
    if not s:
        return param == "q" and mode == "search"
    return s.get("available", False) and param in s.get("params", [])


def download(db: Session, idx: Indexer, release_url: str, *, manual: bool = False) -> tuple[bytes, str]:
    """Fetch the .nzb / .torrent (counts as a grab). Returns (content, content-type)."""
    usage.check(db, idx, "grab", manual=manual)
    usage.wait_interval(idx)
    url = release_url
    if idx.api_key and "apikey=" not in url and url.startswith(idx.url.rstrip("/")):
        url += ("&" if "?" in url else "?") + "apikey=" + idx.api_key
    t0 = time.monotonic()
    try:
        r = httpx.get(url, headers={"User-Agent": UA}, timeout=60, follow_redirects=False)
        hops = 0
        while r.is_redirect and hops < 5:
            loc = r.headers.get("location", "")
            if loc.startswith("magnet:"):
                usage.record(db, idx, "grab", manual=manual, elapsed_ms=int((time.monotonic() - t0) * 1000))
                return loc.encode(), "application/x-magnet"
            r = httpx.get(httpx.URL(str(r.url)).join(loc), headers={"User-Agent": UA}, timeout=60, follow_redirects=False)
            hops += 1
    except httpx.HTTPError as e:
        usage.record(db, idx, "grab", success=False, manual=manual, detail=str(e))
        raise IndexerError(f"Download fehlgeschlagen: {e}") from e
    elapsed = int((time.monotonic() - t0) * 1000)
    ctype = r.headers.get("content-type", "")
    if r.status_code == 429:
        usage.record(db, idx, "grab", success=False, manual=manual, elapsed_ms=elapsed, detail="HTTP 429")
        usage.pause(db, idx, "HTTP 429 beim Download", until=usage.next_slot(db, idx, "grab", max(usage.effective_limit(idx, "grab"), 1)))
        raise IndexerError("HTTP 429 beim Download")
    if r.status_code >= 400:
        usage.record(db, idx, "grab", success=False, manual=manual, elapsed_ms=elapsed, detail=f"HTTP {r.status_code}")
        raise IndexerError(f"Download HTTP {r.status_code}")
    body = r.content
    if body[:200].lstrip().startswith(b"<?xml") or b"<error" in body[:300]:
        try:
            root = ET.fromstring(body)
            if _local(root.tag) == "error":
                msg = f"[{root.get('code')}] {root.get('description')}"
                _handle_api_error(db, idx, msg, "grab", manual, elapsed)
                raise IndexerError(msg)
        except ET.ParseError:
            pass
    usage.record(db, idx, "grab", manual=manual, elapsed_ms=elapsed, detail=release_url[:300])
    return body, ctype
